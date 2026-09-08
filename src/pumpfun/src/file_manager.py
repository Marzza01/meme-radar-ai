"""
Async File Manager
"""

import json
import logging
import asyncio
import aiofiles
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

class AsyncFileManager:
    """Handles asynchronous file writing using aiofiles."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._queue = asyncio.Queue()
        self._running = False
        self._worker_task = None
        
    async def start(self):
        """Start the background writer worker."""
        self._running = True
        self._worker_task = asyncio.create_task(self._writer_worker())
        logger.debug(f"File writer started: {self.filepath}")
        
    async def stop(self):
        """Stop the writer worker and flush pending items."""
        self._running = False
        if self._worker_task:
            await self._queue.join()  # Wait for queue to process
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.debug("File writer stopped")

    async def save_event(self, event_type: str, event_data: Dict[str, Any]):
        """Queue an event to be saved."""
        if not self._running:
            return
            
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "data": event_data
        }
        await self._queue.put(json.dumps(record, ensure_ascii=False) + '\n')

    async def _writer_worker(self):
        """Background worker that writes to file."""
        while self._running or not self._queue.empty():
            try:
                line = await self._queue.get()
                
                async with aiofiles.open(self.filepath, mode='a', encoding='utf-8') as f:
                    await f.write(line)
                    
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"File write error: {e}")
                self._queue.task_done()

    def get_file_size(self) -> int:
        """Get output file size in bytes."""
        try:
            import os
            return os.path.getsize(self.filepath) if os.path.exists(self.filepath) else 0
        except:
            return 0
