"""
Pump.fun Monitor Package

Async Python SSE Client for Pump.fun Real-time Trading Data Monitoring
"""

__version__ = "2.0.0"
__author__ = "Muhammet Akkurt"
__description__ = "Real-time Pump.fun trading data monitor via SSE"

# Export new async classes
from src.config import PumpMonitorConfig
from src.client import AsyncPumpClient
from src.event_handler import EventHandler
from src.stats_manager import StatsManager

__all__ = [
    'PumpMonitorConfig',
    'AsyncPumpClient',
    'EventHandler',
    'StatsManager'
]
