#!/usr/bin/env python3
"""
Demo: two mock workers, six tasks, periodic monitor snapshots for 8 seconds.

Run from anywhere: ``python scripts/agent_monitor_demo.py``
(project root is added to ``sys.path``).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict

# Resolve package imports without requiring editable install
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.monitor_agent import MonitorAgent  # noqa: E402


class MockWorker:
    """Minimal worker: handles one task type and simulates work."""

    def __init__(self, worker_id: str, task_type: str, delay_s: float = 0.15) -> None:
        self.worker_id = worker_id
        self._task_type = task_type
        self._delay_s = delay_s

    def can_handle(self, task_type: str) -> bool:
        """Return True when the demo worker owns this synthetic task type."""
        return task_type == self._task_type

    def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Sleep briefly and echo the payload to simulate a completed worker task."""
        time.sleep(self._delay_s)
        return {"worker_id": self.worker_id, "echo": task.get("payload"), "task_id": task.get("task_id")}


def main() -> None:
    """Register demo workers, enqueue tasks, print snapshots, then shut down."""
    monitor = MonitorAgent()
    monitor.register_worker(MockWorker("w-alpha", "alpha", delay_s=0.2))
    monitor.register_worker(MockWorker("w-beta", "beta", delay_s=0.25))

    monitor.start()
    for i in range(6):
        kind = "alpha" if i % 2 == 0 else "beta"
        monitor.enqueue({"type": kind, "payload": f"job-{i}"})

    for _ in range(8):
        print(monitor.snapshot())
        time.sleep(1.0)

    monitor.stop()


if __name__ == "__main__":
    main()
