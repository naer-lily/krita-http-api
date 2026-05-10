"""
register remote shortcuts and poll triggered shortcuts.
"""
from krita import Krita

from pydantic import BaseModel

from ..routing import Request
from .route import route


class ShortcutRegisterModel(BaseModel):
    actionId: str
    shortcut: str


_registered_shortcuts: dict[str, str] = {}


@route("remote-shortcut/current")
def current_shortcut(req: Request) -> str | None:
    """Get the most recently triggered remote shortcut."""
    return None


@route("remote-shortcut/list")
def shortcut_list(req: Request) -> list[str]:
    """List all registered remote shortcuts."""
    return list(_registered_shortcuts.keys())


@route("remote-shortcut/register")
def shortcut_register(req: Request[ShortcutRegisterModel]) -> dict:
    """Register a remote shortcut for polling."""
    _registered_shortcuts[req.params.actionId] = req.params.shortcut
    return dict(actionId=req.params.actionId, shortcut=req.params.shortcut)


@route("remote-shortcut/remove")
def shortcut_remove(req: Request[str]) -> bool:
    """Remove a registered remote shortcut by actionId."""
    _registered_shortcuts.pop(req.params, None)
    return True
