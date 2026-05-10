"""
get and trigger actions in krita.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from krita import Krita

from PyQt5.QtGui import QKeySequence

from ..routing import Request, ResponseFail
from .route import route


ACTION_TIMEOUT = 3


class ActionCheckedModel(BaseModel):
    action: str


class ActionActModel(BaseModel):
    action: str
    act: Literal["checked", "unchecked", "trigger"]


@route("action/list")
def action_list(req: Request) -> dict:
    """List all Krita actions with their shortcuts, tooltips, and states."""
    result = {}
    for action in Krita.instance().actions():
        result[action.objectName()] = dict(
            shortcuts=QKeySequence.listToString(action.shortcuts()),
            toolTip=action.toolTip(),
            checkable=action.isCheckable(),
            checked=action.isChecked(),
            enabled=action.isEnabled(),
        )
    return result


@route("action/checked")
def action_checked(req: Request[ActionCheckedModel]) -> bool:
    """Check if a checkable action is checked."""
    action = Krita.instance().action(req.params.action)
    if action is None:
        raise ResponseFail(f"action '{req.params.action}' not found")
    if not action.isCheckable():
        raise ResponseFail(f"action '{req.params.action}' is not checkable")
    return action.isChecked()


@route("action/act")
def action_act(req: Request[ActionActModel]):
    """Trigger or toggle a Krita action."""
    p = req.params
    action = Krita.instance().action(p.action)
    if action is None:
        raise ResponseFail(f"action '{p.action}' not found")

    if p.act in ("checked", "unchecked"):
        if not action.isCheckable():
            raise ResponseFail(f"action '{p.action}' is not checkable")
        action.setChecked(p.act == "checked")
    else:
        action.trigger()


_latest_actions: list[tuple[str, datetime]] = []


@route("action/listen")
def action_listen(req: Request) -> list[str]:
    """Get list of actions triggered within the last 3 seconds."""
    _init_action_listeners()
    global _latest_actions
    if not _latest_actions:
        return []

    now = datetime.now()
    valid = [
        name for name, ts in _latest_actions
        if (now - ts).seconds < ACTION_TIMEOUT
    ]
    _latest_actions.clear()
    return valid


_first_run = True


def _init_action_listeners():
    global _first_run
    if not _first_run:
        return
    _first_run = False

    for action in Krita.instance().actions():
        def make_callback(a):
            def cb():
                global _latest_actions
                now = datetime.now()
                _latest_actions.append((a.objectName(), now))
                _latest_actions[:] = [
                    (n, t) for n, t in _latest_actions
                    if (now - t).seconds < ACTION_TIMEOUT
                ]
            return cb
        action.triggered.connect(make_callback(action))
