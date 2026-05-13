import json
import os
import time
import logging
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

TELEMETRY_PATH = "data/telemetry.json"

@dataclass
class SessionMetric:
    timestamp: float
    command: str
    stt_latency: float
    planning_latency: float
    execution_latency: float
    total_latency: float
    success: bool
    error: Optional[str] = None
    vibe_urgency: float = 0.0

class TelemetrySystem:
    """
    Observability layer for JARVIS performance tracking.
    """
    def __init__(self):
        self.logs = []
        self._load()

    def _load(self):
        if os.path.exists(TELEMETRY_PATH):
            try:
                with open(TELEMETRY_PATH, 'r') as f:
                    self.logs = json.load(f)
            except:
                self.logs = []

    def _save(self):
        try:
            # Keep only last 1000 logs to save space
            self.logs = self.logs[-1000:]
            with open(TELEMETRY_PATH, 'w') as f:
                json.dump(self.logs, f, indent=2)
        except:
            pass

    def log_session(self, metric: SessionMetric):
        self.logs.append(asdict(metric))
        self._save()
        logger.info(f"Telemetry: Latency={metric.total_latency:.2f}s Success={metric.success}")

    def get_stats(self):
        if not self.logs:
            return "No data yet."
        
        avg_latency = sum(l['total_latency'] for l in self.logs) / len(self.logs)
        success_rate = sum(1 for l in self.logs if l['success']) / len(self.logs) * 100
        return f"Avg Latency: {avg_latency:.2f}s | Success Rate: {success_rate:.1f}%"

_TELEMETRY = None

def get_telemetry() -> TelemetrySystem:
    global _TELEMETRY
    if _TELEMETRY is None:
        _TELEMETRY = TelemetrySystem()
    return _TELEMETRY
