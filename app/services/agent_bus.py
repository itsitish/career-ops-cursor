"""
Shared task lifecycle types for the local job-ops monitor.

Uses the stdlib only: dataclasses, enums, and UUIDs for task identity.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class TaskStatus(str, Enum):
    """Lifecycle state of a task tracked by the monitor."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskRecord:
    """
    Full task lifecycle record with wall-clock timestamps.

    Attributes:
        task_id: Stable unique id assigned by the monitor at enqueue time.
        task: Original task dict (must include \"type\" for worker routing).
        status: Current lifecycle state.
        created_at: Unix time when the task was enqueued.
        started_at: Unix time when a worker began processing (if started).
        finished_at: Unix time when processing completed or failed (if done).
        worker_id: Worker that ran the task, if any.
        result: Return value from worker ``process`` on success.
        error: Error message string on failure.
    """

    task_id: str
    task: Dict[str, Any]
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    worker_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def new_task_id() -> str:
    """Return a new unique task id (UUID4 string)."""
    return str(uuid.uuid4())
