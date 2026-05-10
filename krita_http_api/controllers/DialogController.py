"""
display dialog for user interaction.
"""
import uuid
from typing import Optional

from pydantic import BaseModel

from krita import Krita

from PyQt5.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QDialogButtonBox

from ..routing import Request, AsyncRequest, ResponseFail
from ..QtEnum import MessageBoxStandardButton, MessageBoxIcon
from .route import route, async_route


dialog_status: dict[str, dict] = {}


class MsgBoxModel(BaseModel):
    msg: str
    title: Optional[str] = None
    icon: Optional[str] = "Information"
    buttons: Optional[list[str]] = None
    defaultButton: Optional[str] = None
    blocking: Optional[bool] = False


@route("dialog/msg-box")
def msg_box(req: Request[MsgBoxModel]) -> str:
    """Open a non-blocking message box. Returns a dialogId for polling the result."""
    p = req.params
    box = QMessageBox(Krita.instance().activeWindow().qwindow())
    box.setWindowTitle(p.title or "")
    box.setText(p.msg)
    box.setMinimumSize(200, 100)
    box.resize(200, 100)

    box.setIcon(MessageBoxIcon.from_str(p.icon or "Information"))

    button_strs = p.buttons or [
        MessageBoxStandardButton.to_str(MessageBoxStandardButton.raw.Ok)
    ]
    buttons = None
    for bs in button_strs:
        btn = MessageBoxStandardButton.from_str(bs)
        buttons = btn if buttons is None else buttons | btn
    box.setStandardButtons(buttons)

    default_btn = p.defaultButton or MessageBoxStandardButton.to_str(
        MessageBoxStandardButton.raw.Ok
    )
    box.setDefaultButton(MessageBoxStandardButton.from_str(default_btn))

    box.setModal(p.blocking or False)

    dialog_id = str(uuid.uuid4())
    dialog_status[dialog_id] = {"type": "PENDING"}

    def on_finished(result):
        res_type = MessageBoxStandardButton.to_str(result)
        if res_type is None:
            dialog_status[dialog_id] = {"type": "EXIT"}
        else:
            dialog_status[dialog_id] = {"type": "OK", "button": res_type}

    box.finished.connect(on_finished)
    box.open()
    return dialog_id


@async_route("dialog/result")
def dialog_result(req: AsyncRequest[str, dict]):
    """Poll the result of a dialog by dialogId.
    Send param as a bare string: {"code": "dialog/result", "param": "<dialogId>"}
    """
    dialog_id = req.params
    if dialog_id not in dialog_status:
        return req.fail(f"No dialog with id {dialog_id}")

    res = dialog_status[dialog_id]
    if res["type"] != "PENDING":
        del dialog_status[dialog_id]

    req.ok(res)
