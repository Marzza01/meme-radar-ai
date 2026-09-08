"""
Configuration Module
"""

from dataclasses import dataclass, field
from typing import Optional, List
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class PumpMonitorConfig:
    """Configuration for Pump Monitor."""
    
    # Server
    server_url: str = field(default_factory=lambda: os.getenv("SERVER_URL", "https://muhammetakkurtt--pump-fun-real-time-monitor.apify.actor"))
    api_token: str = field(default_factory=lambda: os.getenv("APIFY_TOKEN", ""))
    endpoint: str = field(default_factory=lambda: os.getenv("ENDPOINT", "all"))
    
    # Connection
    connection_timeout: int = field(default_factory=lambda: int(os.getenv("CONNECTION_TIMEOUT", "15")))
    read_timeout: Optional[int] = None    # SSE read timeout (None = unlimited)
    stream_timeout: int = field(default_factory=lambda: int(os.getenv("STREAM_TIMEOUT", "180")))
    reconnect_delay: int = field(default_factory=lambda: int(os.getenv("RECONNECT_DELAY", "3")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "10")))
    keep_alive_interval: int = 30  # Send/Expect pings
    
    # Display
    quiet_mode: bool = False
    debug_mode: bool = False
    show_raw_data: bool = False
    
    # Persistence
    save_to_file: bool = field(default_factory=lambda: os.getenv("SAVE_TO_FILE", "true").lower() == "true")
    output_file: Optional[str] = field(default_factory=lambda: os.getenv("OUTPUT_FILE"))
    
    def __post_init__(self):
        # Override with other env vars if specific flags are set (though usually handled by args in main)
        if os.getenv("DEBUG", "").lower() == "true":
            self.debug_mode = True
        if os.getenv("QUIET", "").lower() == "true":
            self.quiet_mode = True
            
        if self.output_file is None and self.save_to_file:
            endpoint_safe = self.endpoint.replace('/', '_')
            self.output_file = f"pump_data_{endpoint_safe}.jsonl"
            
    def validate(self) -> List[str]:
        issues = []
        if not self.api_token or not self.api_token.strip():
            issues.append("ERROR: API Token is required. Set APIFY_TOKEN in .env or pass --api-token")
            
        if not self.server_url or not self.server_url.strip():
            issues.append("ERROR: Server URL is required. Set SERVER_URL in .env or pass --server-url")
            
        if not self.server_url.startswith(('http://', 'https://')):
            issues.append("WARNING: SERVER_URL should start with http:// or https://")
            
        valid_endpoints = ["all", "tokens/new", "tokens/new/detailed", 
                          "tokens/graduated", "trades/pump", "trades/pumpswap"]
        if self.endpoint not in valid_endpoints:
            issues.append(f"ERROR: Invalid endpoint. Valid values: {valid_endpoints}")
            
        return issues
