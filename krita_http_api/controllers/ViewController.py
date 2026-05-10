"""
manage views in current window.
"""
import math
from typing import Optional, Literal

from pydantic import BaseModel

from krita import Krita

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtWidgets import QMdiArea, QMdiSubWindow, QWidget

from ..Logger import Logger
from ..PerWindowCachedState import PerWindowCachedState
from ..routing import Request, ResponseFail
from .route import route


class ViewSetModel(BaseModel):
    viewId: int
    display: Optional[Literal["MAXIMIZED", "MINIMIZED", "NORMAL"]] = None
    frameless: Optional[bool] = None
    stayOnTop: Optional[bool] = None
    size: Optional[tuple[int, int]] = None
    pos: Optional[tuple[int, int]] = None


logger = Logger()


class _ViewsGetter:
    def __init__(self):
        self.notifier = Krita.instance().notifier()

        def refresh():
            logger.info("view cache refresh")
            if not hasattr(self, "cache"):
                return
            self.cache.clear()

        self.notifier.windowCreated.connect(refresh)
        self.notifier.viewClosed.connect(refresh)
        self.notifier.viewCreated.connect(refresh)
        self.notifier.imageCreated.connect(refresh)

    def __call__(self, window):
        self.notifier.setActive(True)
        views = window.views()
        if views is None:
            return []
        qviews: list[QMdiSubWindow] = (
            window.qwindow().findChild(QMdiArea).findChildren(QMdiSubWindow)
        )

        def get_view_id(subwin: QMdiSubWindow) -> int:
            view_widget = next(
                i for i in subwin.findChildren(QWidget)
                if i.metaObject().className() == "KisView"
            )
            return int(view_widget.objectName().replace("view_", ""))

        qviews.sort(key=get_view_id)
        result = []
        for qview, view in zip(qviews, views):
            result.append((get_view_id(qview), qview, view))
        return result


_view_getter_impl = _ViewsGetter()
_view_getter = PerWindowCachedState(_view_getter_impl)
_view_getter_impl.cache = _view_getter


def _all_views(window) -> list[tuple[int, QMdiSubWindow, "View"]]:
    return _view_getter.get(window)


def _calculate_transform_B_to_C(T_AB, T_AC):
    """(A->B) -> (A->C) -> (B->C)"""
    T_AB_inv = T_AB.inverted()[0]
    return T_AB_inv * T_AC


@route("view/list")
def view_list(req: Request) -> list[dict]:
    """List all views in the active window with geometry, canvas transform, etc."""
    win = Krita.instance().activeWindow()
    views = _all_views(win)
    result = []

    for view_id, qview, view in views:
        if qview.isMaximized():
            display = "MAXIMIZED"
        elif qview.isMinimized():
            display = "MINIMIZED"
        else:
            display = "NORMAL"

        doc = view.document()
        filename = doc.fileName()
        view_frame_geo = qview.geometry()
        area_geo = qview.mdiArea().geometry()
        view_client_geo = qview.contentsRect()

        canvas_to_image = _calculate_transform_B_to_C(
            view.flakeToCanvasTransform(), view.flakeToImageTransform()
        )
        scale = canvas_to_image.m11()
        angle_rad = math.atan2(canvas_to_image.m21(), canvas_to_image.m11())
        rotation = math.degrees(angle_rad)
        pan = canvas_to_image.dx(), canvas_to_image.dy()

        result.append(dict(
            viewId=view_id,
            display=display,
            docId=doc.rootNode().uniqueId().toString() + "-" + filename,
            isFile=bool(filename is not None and filename != ""),
            filename=filename,
            frameless=bool(qview.windowFlags() & Qt.FramelessWindowHint),
            stayOnTop=bool(qview.windowFlags() & Qt.WindowStaysOnTopHint),
            viewFrameSize=(view_frame_geo.width(), view_frame_geo.height()),
            viewFramePos=(view_frame_geo.x(), view_frame_geo.y()),
            viewClientSize=(view_client_geo.width(), view_client_geo.height()),
            viewClientPos=(view_client_geo.x(), view_client_geo.y()),
            canvasRotation=rotation,
            canvasScale=scale,
            canvasPan=pan,
            canvasToImageMatrix=(
                canvas_to_image.m11(), canvas_to_image.m12(), canvas_to_image.m13(),
                canvas_to_image.m21(), canvas_to_image.m22(), canvas_to_image.m23(),
                canvas_to_image.m31(), canvas_to_image.m32(), canvas_to_image.m33(),
            ),
            areaSize=(area_geo.width(), area_geo.height()),
            areaPos=(area_geo.x(), area_geo.y()),
        ))
    return result


@route("view/set")
def set_view(req: Request[ViewSetModel]) -> dict:
    """Set view display properties for a specific viewId."""
    p = req.params
    win = Krita.instance().activeWindow()
    views = _all_views(win)

    qview = None
    for view_id, qv, v in views:
        if p.viewId == view_id:
            qview = qv
            break
    if qview is None:
        raise ResponseFail(f"viewId '{p.viewId}' not found")

    result = {}

    if p.display is not None:
        result["display"] = p.display
        if p.display == "MAXIMIZED":
            qview.showMaximized()
        elif p.display == "MINIMIZED":
            qview.showMinimized()
        else:
            qview.showNormal()

    if p.frameless is not None:
        result["frameless"] = p.frameless
        qview.setWindowFlag(Qt.FramelessWindowHint, p.frameless)

    if p.stayOnTop is not None:
        result["stayOnTop"] = p.stayOnTop
        qview.setWindowFlag(Qt.WindowStaysOnTopHint, p.stayOnTop)

    if p.pos is not None:
        geo = qview.geometry()
        geo.setX(p.pos[0])
        geo.setY(p.pos[1])
        qview.setGeometry(geo)
        result["pos"] = p.pos

    if p.size is not None:
        geo = qview.geometry()
        geo.setWidth(p.size[0])
        geo.setHeight(p.size[1])
        qview.setGeometry(geo)
        result["size"] = p.size

    return result
