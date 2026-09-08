"""
Async Pump Monitor Client
"""

import asyncio
import json
import logging
import aiohttp
import re
from typing import Optional, Dict
from datetime import datetime

from .config import PumpMonitorConfig
from .event_handler import EventHandler
from .file_manager import AsyncFileManager
from .stats_manager import StatsManager

logger = logging.getLogger(__name__)

class SubscriptionRequiredError(Exception):
    """Raised when Apify actor cannot start due to subscription issues."""
    pass

class AsyncPumpClient:
    """Async client for Pump.fun SSE stream."""
    
    def __init__(self, config: PumpMonitorConfig):
        self.config = config
        self.file_manager = AsyncFileManager(config.output_file) if config.save_to_file else None
        self.stats_manager = StatsManager()
        self.session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds
        
    async def start(self):
        """Start the client."""
        logger.info("🚀 Starting Async Pump Monitor")
        self._running = True
        
        # Start file manager
        if self.file_manager:
            await self.file_manager.start()
            
        # Initial health check
        await self._check_health()
            
        # Main loop
        while self._running:
            try:
                await self._connect_and_stream()
            except SubscriptionRequiredError as e:
                logger.error(str(e))
                print("\n" + "!" * 60)
                print(f"🛑 ACTION REQUIRED: {e}")
                print("!" * 60 + "\n")
                self._running = False
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Connection error: {e}")
                
            if self._running:
                logger.info(f"🔄 Reconnecting in {self.config.reconnect_delay}s...")
                await asyncio.sleep(self.config.reconnect_delay)
                
    async def stop(self):
        """Stop the client."""
        self.print_stats(final=True)
        self._running = False
        if self.session:
            await self.session.close()
        if self.file_manager:
            await self.file_manager.stop()
        logger.info("🛑 Client stopped")
        
    async def _check_health(self):
        """Check server health."""

        health_url = f"{self.config.server_url.rstrip('/')}/health"
        headers = {'Authorization': f'Bearer {self.config.api_token}'}
        
        try:
            async with aiohttp.ClientSession(headers=headers) as health_session:
                async with health_session.get(health_url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        conns = data.get('connections', {}).get('total', 0)
                        self.stats_manager.set_connection_count(conns)
                        if not self.config.quiet_mode:
                            logger.info(f"🟢 Health OK | Active Connections: {conns}")
                    else:
                        logger.warning(f"🟡 Health Check returned {response.status}")
        except Exception as e:
            logger.warning(f"Health check failed: {e}")

    async def _connect_and_stream(self):
        """Connect to SSE endpoint and process stream."""
        events_url = f"{self.config.server_url.rstrip('/')}/events/{self.config.endpoint}"
        
        headers = {
            'Authorization': f'Bearer {self.config.api_token}',
            'Accept': 'text/event-stream',
            'Connection': 'keep-alive'
        }
        
        timeout = aiohttp.ClientTimeout(
            total=None,  # Infinite total timeout for streaming
            connect=self.config.connection_timeout,
            sock_read=self.config.stream_timeout
        )
        
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            self.session = session
            logger.info(f"🌊 Connecting to {events_url}...")
            
            async with session.get(events_url) as response:
                if response.status != 200:
                    text = await response.text()
                    
                    # Handle Apify Subscription Errors
                    try:
                        error_data = json.loads(text)
                        error_type = error_data.get('error', {}).get('type')
                        error_msg = error_data.get('error', {}).get('message', '')
                        
                        if error_type == 'cannot-start-actor-runs':
                            url = "https://console.apify.com/actors/dYp0TfkeICrbiaqc4/standby?fpr=muh"
                            raise SubscriptionRequiredError(f"Trial Required! Please start your free trial here: {url}")
                            
                    except json.JSONDecodeError:
                        pass
                        
                    raise Exception(f"Server returned {response.status}: {text}")
                    
                logger.info("✅ Connected! Streaming data...")
                
                # Buffer for SSE processing
                buffer = ""
                async for line_bytes in response.content:
                    if not self._running:
                        break
                        
                    # Periodic Tasks inside the stream loop
                    current_time = datetime.now().timestamp()
                    if current_time - self._last_health_check > self._health_check_interval:
                        asyncio.create_task(self._check_health())
                        self._last_health_check = current_time
                        
                    if self.stats_manager.should_print_stats(interval=60) and not self.config.quiet_mode:
                        self.print_stats()
                        
                    line = line_bytes.decode('utf-8').strip()
                    if not line:
                        continue
                        
                    # Basic SSE parsing
                    if line.startswith('event: '):
                        current_event_type = line[7:]
                    elif line.startswith('data: '):
                        data_str = line[6:]
                        try:

                            event_data = json.loads(data_str)
                            
                            # Using the captured event type if available, or extract from data
                            event_type = locals().get('current_event_type', 'message')
                            
                            # Process the event
                            await self._process_event(event_type, event_data)
                            
                            # Reset for next event
                            current_event_type = None
                            
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to decode JSON: {data_str}")
                    
    async def _process_event(self, event_type: str, data: Dict):
        """Handle a single event."""
        
        # 0. Skip pings for stats/files but log debug
        if event_type == "ping":
            if self.config.debug_mode: logger.debug("ping received")
            return

        # 1. Update Stats
        self.stats_manager.add_event(event_type)
        if event_type == "connected":
            conn_id = data.get("connection_id")
            if not self.config.quiet_mode:
                print(f"✅ Connection Established ID: {conn_id}")

        # 2. Save to file
        if self.file_manager:
            await self.file_manager.save_event(event_type, data)
            
        # 3. Display
        if not self.config.quiet_mode:
            if self.config.show_raw_data:
                print(EventHandler.format_raw_data(event_type, data))
            
            formatted = EventHandler.format_event(event_type, data)
            print(formatted)

    def print_stats(self, final: bool = False):
        """Print statistics."""
        stats = self.stats_manager.get_stats()
        header = "📊 Final Statistics" if final else "📊 Live Statistics"
        print(f"\n{header}:")
        print(f"   🕐 Uptime: {stats['uptime']}")
        print(f"   📨 Total Events: {stats['total_events']}")
        print(f"   ⚡ Avg Events/Min: {stats['events_per_min']}")
        print(f"   🔗 Active Connections: {stats['connections']}")
        if stats['event_breakdown']:
            print("   📋 Event Types:")
            for k, v in stats['event_breakdown'].items():
                print(f"      {k}: {v}")
        
        if self.file_manager:
            file_size = self.file_manager.get_file_size()
            if file_size > 0:
                print(f"   📁 File size: {file_size:,} bytes")
                
        print("-" * 60)

