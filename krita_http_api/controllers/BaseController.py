"""
basic API: health check, API documentation, floating message, icon, and test routes.
"""
from typing import Optional, Literal

from pydantic import BaseModel

from krita import Krita

from PyQt5.QtCore import QTimer, QSize
from PyQt5.QtGui import QIcon

from ..routing import Request, ResponseFail
from ..utils import qimage_to_png_base64, floating_message
from .route import route, async_route, router, sleep, create_future


class ResourceIconModel(BaseModel):
    resourceType: str
    resourceName: str


class FloatingMessageModel(BaseModel):
    message: str
    timeout: Optional[int] = None
    priority: Optional[int] = None


class IconModel(BaseModel):
    iconName: str
    size: tuple[int, int] = (200, 200)
    mode: Literal["Normal", "Disabled", "Active", "Selected"] = "Normal"
    state: Literal["On", "Off"] = "Off"


# ------------------------------------------------------------------ #
#  documentation
# ------------------------------------------------------------------ #


@route("__docs__")
def api_docs(req: Request) -> str:
    """Return API documentation as Markdown."""
    return router.generate_docs()


# ------------------------------------------------------------------ #
#  core endpoints
# ------------------------------------------------------------------ #


@route("ping")
def ping(req: Request) -> dict:
    """Health check. Returns 'pong'."""
    return {"msg": "pong"}


@route("route-list")
def route_list(req: Request) -> list[str]:
    """List all registered route codes."""
    return router.codes


@route("resource-icon")
def resource_icon(req: Request[ResourceIconModel]) -> str:
    """Get a Krita resource icon as base64 PNG."""
    p = req.params
    resource = Krita.instance().resources(p.resourceType)[p.resourceName]
    return qimage_to_png_base64(resource.image())


@route("floating-message")
def floating_message_route(req: Request[FloatingMessageModel]) -> bool:
    """Display a floating message in the active Krita view."""
    return floating_message(**req.params.model_dump(exclude_none=True))


@route("icon")
def icon_route(req: Request[IconModel]) -> str:
    """Get a Krita icon as base64 PNG."""
    p = req.params
    icon = Krita.instance().icon(p.iconName)
    if icon.isNull():
        raise ResponseFail(f"icon '{p.iconName}' not found")

    mode_map = {
        "Normal": QIcon.Mode.Normal,
        "Disabled": QIcon.Mode.Disabled,
        "Active": QIcon.Mode.Active,
        "Selected": QIcon.Mode.Selected,
    }
    state_map = {"On": QIcon.State.On, "Off": QIcon.State.Off}

    pixmap = icon.pixmap(
        QSize(p.size[0], p.size[1]),
        mode=mode_map.get(p.mode, QIcon.Mode.Normal),
        state=state_map.get(p.state, QIcon.State.Off),
    )
    return qimage_to_png_base64(pixmap.toImage())


# ------------------------------------------------------------------ #
#  test endpoints
# ------------------------------------------------------------------ #


@route("sync-test")
def sync_test(req: Request) -> dict:
    """Simple sync test."""
    return {"req": req.code}


@route("sync-except-test")
def sync_except_test(req: Request) -> dict:
    """Sync handler that raises an exception."""
    return 1 // 0


@async_route("async-ok-test")
def async_ok_test(req: Request) -> dict:
    """Async handler: sleep 100ms then return."""
    yield from sleep(100)
    return {"desc": "this is response body"}


@async_route("async-fail-test")
def async_fail_test(req: Request) -> None:
    """Async handler: sleep 100ms then raise ResponseFail."""
    yield from sleep(100)
    raise ResponseFail("this is fail message", {"desc": "this is response body"})


@async_route("async-future-test")
def async_future_test(req: Request) -> dict:
    """Async handler: create a future, resolve it via QTimer."""
    fut, resolve = create_future()
    QTimer.singleShot(100, lambda: resolve({"desc": "resolved via future"}))
    result = yield from fut
    return result


_counter = 0


@route("thread-safe-test")
def thread_safe_test(req: Request) -> int:
    """Increment a counter — verifies handler runs on main thread."""
    global _counter
    _counter += 1
    return _counter
