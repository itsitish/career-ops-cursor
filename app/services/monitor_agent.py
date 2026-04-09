"""
Monitor agent: dispatches tasks from a queue to registered workers.

Runs a background dispatcher thread; task execution runs in short-lived
threads so multiple workers can be busy concurrently.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, List, Optional, Protocol

from app.services.agent_bus import TaskRecord, TaskStatus, new_task_id

# Sentinel placed on the queue to unblock ``get`` during shutdown.
_SHUTDOWN = object()


class WorkerProtocol(Protocol):
    """Expected interface for worker objects registered with the monitor."""

    worker_id: str

    def can_handle(self, task_type: str) -> bool:
        """Return True if this worker can run the given task type."""
        ...

    def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the task and return a result dict."""
        ...


class MonitorAgent:
    """
    Orchestrates a ``queue.Queue`` of tasks and dispatches them to workers.

    Public methods are thread-safe where noted. Snapshot and register are
    safe to call while the dispatcher is running.
    """

    def __init__(self) -> None:
        self._workers: List[Any] = []
        self._task_queue: "queue.Queue[Any]" = queue.Queue()
        self._tasks: Dict[str, TaskRecord] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # worker_id -> current task_id or None when idle
        self._worker_current: Dict[str, Optional[str]] = {}

    def register_worker(self, worker: Any) -> None:
        """
        Register a worker implementing ``worker_id``, ``can_handle``, ``process``.

        Must be called before ``start()`` or from the same thread that owns
        startup; not safe to add workers concurrently with dispatch without
        extra synchronization beyond this lock.
        """
        wid = getattr(worker, "worker_id", None)
        if not isinstance(wid, str) or not wid:
            raise ValueError("worker must have a non-empty str worker_id")
        with self._lock:
            if any(getattr(w, "worker_id", None) == wid for w in self._workers):
                raise ValueError(f"worker_id already registered: {wid!r}")
            self._workers.append(worker)
            self._worker_current[wid] = None

    def enqueue(self, task_dict: Dict[str, Any]) -> str:
        """
        Enqueue a task dict (must include key ``type`` for routing).

        Returns the assigned ``task_id``.
        """
        task_id = new_task_id()
        now = time.time()
        record = TaskRecord(
            task_id=task_id,
            task=dict(task_dict),
            status=TaskStatus.QUEUED,
            created_at=now,
        )
        with self._lock:
            self._tasks[task_id] = record
        self._task_queue.put(task_id)
        return task_id

    def start(self) -> None:
        """Start the background dispatcher thread (idempotent if already running)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._dispatcher_loop, name="monitor-dispatch", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """
        Signal shutdown, unblock the queue, and join the dispatcher thread.

        In-flight worker threads may still finish after this returns.
        """
        self._stop.set()
        self._task_queue.put(_SHUTDOWN)
        t = self._thread
        if t is not None:
            t.join(timeout=timeout)
        self._thread = None

    def snapshot(self) -> Dict[str, Any]:
        """
        Return counts by status and per-worker idle/busy information.

        Keys: ``queued``, ``running``, ``completed``, ``failed``, ``workers``.
        """
        with self._lock:
            counts = {s.value: 0 for s in TaskStatus}
            for rec in self._tasks.values():
                counts[rec.status.value] += 1
            workers_snap: List[Dict[str, Any]] = []
            for w in self._workers:
                wid = w.worker_id
                cur = self._worker_current.get(wid)
                busy = cur is not None
                workers_snap.append(
                    {
                        "worker_id": wid,
                        "status": "busy" if busy else "idle",
                        "current_task_id": cur,
                    }
                )
        return {
            "queued": counts[TaskStatus.QUEUED.value],
            "running": counts[TaskStatus.RUNNING.value],
            "completed": counts[TaskStatus.COMPLETED.value],
            "failed": counts[TaskStatus.FAILED.value],
            "workers": workers_snap,
        }

    # --- internal ---

    def _pick_worker(self, task_type: str) -> Optional[Any]:
        for w in self._workers:
            try:
                if w.can_handle(task_type):
                    return w
            except Exception:
                continue
        return None

    def _dispatcher_loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._task_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is _SHUTDOWN:
                break

            task_id: str = item
            with self._lock:
                record = self._tasks.get(task_id)
                if record is None:
                    continue
                task_type = record.task.get("type", "")
                worker = self._pick_worker(task_type)
                if worker is None:
                    record.status = TaskStatus.FAILED
                    record.finished_at = time.time()
                    record.error = f"no worker for task type {task_type!r}"
                    continue
                # mark running and reserve worker
                record.status = TaskStatus.RUNNING
                record.started_at = time.time()
                record.worker_id = worker.worker_id
                self._worker_current[worker.worker_id] = task_id
                wid = worker.worker_id
                task_copy = dict(record.task)

            threading.Thread(
                target=self._run_task,
                args=(task_id, worker, task_copy, wid),
                name=f"task-{task_id[:8]}",
                daemon=True,
            ).start()

    def _run_task(
        self,
        task_id: str,
        worker: Any,
        task: Dict[str, Any],
        worker_id: str,
    ) -> None:
        try:
            payload = dict(task)
            payload.setdefault("task_id", task_id)
            result = worker.process(payload)
            if not isinstance(result, dict):
                result = {"value": result}
            with self._lock:
                rec = self._tasks.get(task_id)
                if rec:
                    rec.status = TaskStatus.COMPLETED
                    rec.finished_at = time.time()
                    rec.result = result
                self._worker_current[worker_id] = None
        except Exception as exc:  # noqa: BLE001 — boundary for worker errors
            with self._lock:
                rec = self._tasks.get(task_id)
                if rec:
                    rec.status = TaskStatus.FAILED
                    rec.finished_at = time.time()
                    rec.error = str(exc)
                self._worker_current[worker_id] = None
