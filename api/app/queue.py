"""
Job-dispatch abstraction. The API only ever *produces* jobs by name — it
never imports worker code directly (see SYSTEM_DESIGN.md's Container
Diagram: API and workers are separate services, only connected through the
queue). `CeleryQueueClient` is the real implementation; `InMemoryQueueClient`
is what tests use, since this sandbox has no live Redis to send to.

Task names match exactly what workers/*/worker.py registers, e.g.
"ocr_worker.extract_document" — see each worker's @app.task(name=...).
"""

from abc import ABC, abstractmethod

from celery import Celery

from app.config import settings


class QueueClient(ABC):
    @abstractmethod
    def enqueue(self, task_name: str, **kwargs) -> None: ...


class CeleryQueueClient(QueueClient):
    """A producer-only Celery app — it sends tasks by name, it never
    registers or runs any task itself. Matches the real deployment: the API
    process is not one of the worker containers."""

    # Task-name prefix -> the queue its worker actually consumes. Each worker
    # container runs with an explicit -Q flag, so a task published without a
    # queue lands on the default "celery" queue that nothing is listening on:
    # the API keeps returning 202, the broker keeps accepting jobs, and every
    # document sits at status="processing" forever with no error anywhere.
    # Observed as 21 tasks banked up on "celery" while ocr, ai_parser and
    # chain were all empty.
    _QUEUE_BY_PREFIX = {
        "ocr_worker": "ocr",
        "ai_parser_worker": "ai_parser",
        "chain_worker": "chain",
    }

    def __init__(self):
        self._app = Celery("api_producer", broker=settings.CELERY_BROKER_URL)
        # Declared as well as passed per-send: task_routes covers anything that
        # sends through this app without going via enqueue().
        self._app.conf.task_routes = {
            f"{prefix}.*": {"queue": queue} for prefix, queue in self._QUEUE_BY_PREFIX.items()
        }

    def enqueue(self, task_name: str, **kwargs) -> None:
        target_queue = self._QUEUE_BY_PREFIX.get(task_name.split(".")[0])
        if target_queue is None:
            # An unrecognised prefix is a programming error, not something to
            # silently drop onto a queue no worker reads.
            raise ValueError(
                f"No queue mapped for task '{task_name}'. Add its prefix to "
                f"CeleryQueueClient._QUEUE_BY_PREFIX and give the worker a matching -Q."
            )
        self._app.send_task(task_name, kwargs=kwargs, queue=target_queue)


class InMemoryQueueClient(QueueClient):
    """Records what was enqueued instead of sending it anywhere. Lets tests
    assert "the upload endpoint tried to enqueue an OCR job for this
    document" without needing a live broker or a running worker."""

    def __init__(self):
        self.enqueued: list[dict] = []

    def enqueue(self, task_name: str, **kwargs) -> None:
        self.enqueued.append({"task_name": task_name, "kwargs": kwargs})


_default_queue = None


def get_queue() -> QueueClient:
    """FastAPI dependency. Real deployment gets a real Celery producer;
    tests override this via dependency_overrides with InMemoryQueueClient."""
    global _default_queue
    if _default_queue is None:
        _default_queue = CeleryQueueClient()
    return _default_queue
