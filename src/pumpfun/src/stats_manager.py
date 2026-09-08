"""
Statistics and Metrics Manager
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Any

class StatsManager:
    """Tracks event statistics and client performance."""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.total_events = 0
        self.event_counts = {}
        self.connections = 0  # From server health check
        self._last_print_time = time.time()
        
    def add_event(self, event_type: str):
        """Record an event occurrence."""
        self.total_events += 1
        self.event_counts[event_type] = self.event_counts.get(event_type, 0) + 1
        
    def set_connection_count(self, count: int):
        """Update active connection count from server."""
        self.connections = count
        
    def get_uptime(self) -> timedelta:
        return datetime.now() - self.start_time
        
    def get_events_per_minute(self) -> float:
        minutes = max(self.get_uptime().total_seconds() / 60, 0.001)
        return self.total_events / minutes
        
    def get_stats(self) -> Dict[str, Any]:
        """Return comprehensive statistics."""
        return {
            "uptime": str(self.get_uptime()).split('.')[0],
            "total_events": self.total_events,
            "events_per_min": round(self.get_events_per_minute(), 1),
            "connections": self.connections,
            "event_breakdown": self.event_counts
        }
        
    def should_print_stats(self, interval: int = 60) -> bool:
        """Check if stats should be printed based on interval."""
        if time.time() - self._last_print_time > interval:
            self._last_print_time = time.time()
            return True
        return False
