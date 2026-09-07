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

    def enqueue(self, task_name: str, **kwargs) -> None:
        # Route by the task-name prefix (e.g. "chain_worker" out of
        # "chain_worker.write_hash") into a queue of the same name — each
        # worker's Dockerfile CMD listens on exactly that queue (-Q flag).
        #
        # Without this, every task from every producer landed on Celery's
        # shared default queue ("celery"), which every worker container
        # also consumed from with no routing at all. Whichever worker
        # happened to dequeue a message first would try to run it — a task
        # it didn't have registered (e.g. ai_parser_worker grabbing
        # "chain_worker.write_hash") was silently discarded, not requeued
        # or retried. With 3 worker types sharing one queue, roughly 2/3 of
        # every job type was being dropped on the floor at random, which is
        # exactly the kind of bug that looks like "sometimes documents
        # never finish processing" with no obvious pattern.
        #
        # A name with no dot has no worker prefix to route by, so the queue
        # would come out as the whole task name — a queue no container is
        # listening on. That is the same silent-drop failure described above,
        # reached a different way: the call succeeds, the broker accepts the
        # message, and the job is simply never run. Refuse it instead, so a
        # malformed task name fails at the call site where it can be fixed
        # rather than becoming another "sometimes documents never finish".
        if "." not in task_name:
            raise ValueError(
                f"Unroutable task name {task_name!r}: expected '<worker>.<task>' "
                f"(e.g. 'ocr_worker.extract_document'), so the queue can be derived "
                f"from the worker prefix that each container's -Q flag listens on."
            )

        queue = task_name.split(".", 1)[0]
        self._app.send_task(task_name, kwargs=kwargs, queue=queue)


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
