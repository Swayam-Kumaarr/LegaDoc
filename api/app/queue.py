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

    def __init__(self):
        self._app = Celery("api_producer", broker=settings.CELERY_BROKER_URL)
        self._app.conf.task_routes = {
            "ocr_worker.*": {"queue": "ocr"},
            "ai_parser_worker.*": {"queue": "ai_parser"},
            "chain_worker.*": {"queue": "chain"},
        }

    def enqueue(self, task_name: str, **kwargs) -> None:
        prefix = task_name.split(".")[0]
        q_map = {
            "ocr_worker": "ocr",
            "ai_parser_worker": "ai_parser",
            "chain_worker": "chain",
        }
        target_q = q_map.get(prefix)
        if target_q:
            self._app.send_task(task_name, kwargs=kwargs, queue=target_q)
        else:
            self._app.send_task(task_name, kwargs=kwargs)


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
