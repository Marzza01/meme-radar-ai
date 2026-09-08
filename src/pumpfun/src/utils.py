import logging
import sys
import asyncio

def setup_logging(debug: bool = False):
    """Configure application logging."""
    logger = logging.getLogger()
    
    # Reset existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    # Set levels for some noisy libraries to WARNING/ERROR unless in debug
    if not debug:
        logging.getLogger("aiohttp").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)

class GracefulShutdown:
    """Handle graceful shutdown signals (SIGINT, SIGTERM)."""
    
    def __init__(self):
        self.shutdown_event = None
        
    def attach_signal_handlers(self, loop):
        """Attach signal handlers to the asyncio loop."""
        import signal
        self.shutdown_event = asyncio.Event()
        
        def signal_handler(sig):
            logging.info(f"🛑 Received signal {sig.name}...")
            self.shutdown_event.set()
            
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: signal_handler(sig))
            except NotImplementedError:
                # Windows doesn't fully support add_signal_handler
                logging.debug(f"Signal {sig} handler not supported on this platform")

    async def wait(self):
        """Wait for shutdown signal."""
        if self.shutdown_event:
            await self.shutdown_event.wait()
