from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Event, RLock
from typing import Any
from uuid import uuid4


@dataclass
class Job:
    id: str
    kind: str
    payload: dict[str, Any]
    state: str = "queued"
    progress: float = 0.0
    message: str = "Queued"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_event: Event = field(default_factory=Event, repr=False)
    future: Future[dict[str, Any]] | None = field(default=None, repr=False)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "payload": self.payload,
            "state": self.state,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }


ProgressCallback = Callable[[float, str], None]
JobOperation = Callable[[Event, ProgressCallback], dict[str, Any]]


class JobManager:
    def __init__(self, max_workers: int = 1) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hfss-job")
        self._jobs: dict[str, Job] = {}
        self._lock = RLock()

    def submit(
        self,
        kind: str,
        payload: dict[str, Any],
        operation: JobOperation,
    ) -> dict[str, Any]:
        job = Job(id=uuid4().hex, kind=kind, payload=dict(payload))
        with self._lock:
            self._jobs[job.id] = job
            job.future = self._executor.submit(self._execute, job, operation)
        return job.to_json()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
            return [job.to_json() for job in jobs]

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._require(job_id).to_json()

    def cancel(self, job_id: str, stop: Callable[[], bool] | None = None) -> dict[str, Any]:
        should_stop = False
        with self._lock:
            job = self._require(job_id)
            if job.state in {"completed", "failed", "cancelled"}:
                return job.to_json()
            should_stop = job.state == "running"
            job.cancel_event.set()
            if job.future and job.future.cancel():
                job.state = "cancelled"
                job.completed_at = datetime.now(UTC).isoformat()
                job.message = "Cancelled before execution"
        stop_error = None
        if stop and should_stop:
            try:
                stop()
            except Exception as exc:  # noqa: BLE001 - cancellation state must remain queryable
                stop_error = str(exc)
        with self._lock:
            if job.state not in {"completed", "failed", "cancelled"}:
                job.state = "cancelling"
                job.message = (
                    f"Cancellation requested; backend stop failed: {stop_error}"
                    if stop_error
                    else "Cancellation requested"
                )
            return job.to_json()

    def _execute(self, job: Job, operation: JobOperation) -> dict[str, Any]:
        with self._lock:
            if job.cancel_event.is_set():
                job.state = "cancelled"
                job.completed_at = datetime.now(UTC).isoformat()
                return {}
            job.state = "running"
            job.started_at = datetime.now(UTC).isoformat()
            job.message = "Running"
            job.progress = 0.01

        def progress(value: float, message: str) -> None:
            with self._lock:
                job.progress = min(max(float(value), 0.0), 1.0)
                job.message = str(message)

        try:
            result = operation(job.cancel_event, progress)
            with self._lock:
                if job.cancel_event.is_set():
                    job.state = "cancelled"
                    job.message = "Cancelled"
                else:
                    job.state = "completed"
                    job.progress = 1.0
                    job.message = "Completed"
                    job.result = result
                job.completed_at = datetime.now(UTC).isoformat()
            return result
        except Exception as exc:  # noqa: BLE001 - jobs must retain arbitrary backend failures
            with self._lock:
                job.state = "failed"
                job.error = str(exc)
                job.message = str(exc)
                job.completed_at = datetime.now(UTC).isoformat()
            return {}

    def _require(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"Job not found: {job_id}") from exc
