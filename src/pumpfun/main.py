#!/usr/bin/env python3
"""
Pump Monitor - Entry Point
"""

import sys
import asyncio
import argparse
import logging
from src.config import PumpMonitorConfig
from src.client import AsyncPumpClient
from src.utils import setup_logging, GracefulShutdown

def parse_args():
    parser = argparse.ArgumentParser(description="Pump.fun Monitor")
    parser.add_argument('--endpoint', '-e', default='all', help='Endpoint (all, trades/pump, etc)')
    parser.add_argument('--server-url', '-s', help='Server URL')
    parser.add_argument('--api-token', '-t', help='API Token')
    parser.add_argument('--output', '-o', help='Output file')
    parser.add_argument('--quiet', '-q', action='store_true', help='Quiet mode')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    parser.add_argument('--show-raw', action='store_true', help='Show raw event data')
    parser.add_argument('--no-save', action='store_true', help='Disable file saving')
    return parser.parse_args()

async def async_main():
    args = parse_args()
    
    # 1. Setup Config
    config = PumpMonitorConfig()
    
    # Apply overrides
    if args.endpoint: config.endpoint = args.endpoint
    if args.server_url: config.server_url = args.server_url
    if args.api_token: config.api_token = args.api_token
    if args.output: config.output_file = args.output
    if args.quiet: config.quiet_mode = True
    if args.debug: config.debug_mode = True
    if args.show_raw: config.show_raw_data = True
    if args.no_save: config.save_to_file = False
    
    # 2. Setup Logging
    setup_logging(config.debug_mode)
    
    # 3. Validate
    issues = config.validate()
    if issues:
        for issue in issues:
            logging.error(issue)
        return 1
        
    # 4. Graceful Shutdown
    shutdown = GracefulShutdown()
    loop = asyncio.get_running_loop()
    shutdown.attach_signal_handlers(loop)
    
    # 5. Run Client
    client = AsyncPumpClient(config)
    client_task = asyncio.create_task(client.start())
    
    # Wait for either shutdown signal or client failure
    shutdown_task = asyncio.create_task(shutdown.wait())
    
    try:
        done, pending = await asyncio.wait(
            [client_task, shutdown_task], 
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel whatever is still running
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
        if client_task in done:
            # Check if client failed with exception
            try:
                client_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logging.error(f"Client failed: {e}")
                
    except KeyboardInterrupt:
        pass
    finally:
        await client.stop()

def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()