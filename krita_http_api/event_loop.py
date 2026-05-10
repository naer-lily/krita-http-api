"""
Generator-based async primitives for @async_route handlers.

Driven by QTimer.singleShot on the Qt main thread — zero polling, zero blocking.
Results are delivered via ``return`` (success) or ``raise ResponseFail`` (error).
"""
import threading
import traceback
from dataclasses import dataclass

from PyQt5.QtCore import QTimer

from .Logger import Logger

logger = Logger("EventLoop")


# ------------------------------------------------------------------ #
#  yield primitives
# ------------------------------------------------------------------ #

@dataclass
class _Sleep:
    ms: int


@dataclass
class _AwaitFuture:
    future: 'Future'


def sleep(ms: int):
    yield _Sleep(ms)


# ------------------------------------------------------------------ #
#  Future
# ------------------------------------------------------------------ #

class Future:
    """One-shot awaitable. Call ``set_result()`` or ``set_exception()`` to resume."""

    def __init__(self, loop=None):
        if loop is None:
            loop = EventLoop.get_event_loop()
        self._loop = loop
        self._result = None
        self._exception = None
        self._resolved = False

    def set_result(self, result=None):
        if self._resolved:
            return
        self._result = result
        self._resolved = True
        self._loop._on_future_resolved(self)

    def set_exception(self, exc):
        if self._resolved:
            return
        self._exception = exc
        self._resolved = True
        self._loop._on_future_resolved(self)

    def resolve(self):
        return self.set_result

    def __iter__(self):
        yield _AwaitFuture(self)
        if self._exception is not None:
            raise self._exception
        return self._result


def create_future():
    """Returns ``(future, resolve_callback)``.

    Usage::

        fut, resolve = create_future()
        QTimer.singleShot(100, lambda: resolve("done"))
        result = yield from fut
    """
    loop = EventLoop.get_event_loop()
    fut = Future(loop)
    return fut, fut.set_result


# ------------------------------------------------------------------ #
#  event loop
# ------------------------------------------------------------------ #

class EventLoop:
    _local = threading.local()

    @classmethod
    def get_event_loop(cls):
        if not hasattr(cls._local, 'instance'):
            cls._local.instance = cls()
        return cls._local.instance

    def __init__(self):
        self._futures: dict[int, tuple[Future, object]] = {}

    def run_coroutine(self, coroutine):
        self._step(coroutine)

    def _step(self, coroutine):
        try:
            v = next(coroutine)
        except StopIteration:
            return
        except Exception:
            logger.warn(f"event loop exception:\n{traceback.format_exc()}")
            return

        match v:
            case _Sleep(ms):
                QTimer.singleShot(ms, lambda: self._step(coroutine))
            case _AwaitFuture(fut):
                if fut._resolved:
                    self._step(coroutine)
                else:
                    self._futures[id(fut)] = (fut, coroutine)
            case _:
                logger.warn(
                    f"async_route handler yielded unknown value: {type(v).__name__}({v!r}). "
                    "Use 'yield from sleep(ms)' or 'yield from future'."
                )

    def _on_future_resolved(self, future):
        entry = self._futures.pop(id(future), None)
        if entry is None:
            return
        _, coroutine = entry
        self._step(coroutine)
