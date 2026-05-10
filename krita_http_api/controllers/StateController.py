"""
get and set global state in krita, like brush preset, painting opacity, brush size, blending mode...
"""
from typing import Optional

from pydantic import BaseModel

from krita import Krita

from PyQt5.QtWidgets import QApplication, QToolButton

from ..routing import Request, ResponseFail
from ..utils import (
    active_view, current_tool, set_current_tool, get_active_theme,
    TimeWatch, DocumentInfo, tool_option_widget,
)
from .route import route


class StateSetModel(BaseModel):
    brushSize: Optional[float] = None
    brushRotation: Optional[float] = None
    blendingMode: Optional[str] = None
    brushPreset: Optional[str] = None
    gradient: Optional[str] = None
    pattern: Optional[str] = None
    opacity: Optional[float] = None
    flow: Optional[float] = None
    tool: Optional[str] = None
    eraserMode: Optional[bool] = None
    canvasOnly: Optional[bool] = None
    foreground: Optional[tuple[float, float, float, float]] = None
    background: Optional[tuple[float, float, float, float]] = None


@route("state/get")
def state_get(req: Request) -> dict:
    """Get current Krita painting state: tool, brush, colors, canvas options, etc."""
    watch = TimeWatch()

    with watch.watch("getView"):
        view = active_view()
        if view is None:
            raise ResponseFail("No active view")

    with watch.watch("tool"):
        res = {"tool": current_tool()}

    with watch.watch("viewState"):
        res["brushSize"] = view.brushSize()
        res["brushRotation"] = view.brushRotation()
        res["blendingMode"] = view.currentBlendingMode()
        res["brushPreset"] = view.currentBrushPreset().name()
        res["gradient"] = view.currentGradient().name()
        res["pattern"] = view.currentPattern().name()
        res["opacity"] = view.paintingOpacity()
        res["flow"] = view.paintingFlow()
        res["foreground"] = view.foregroundColor().componentsOrdered()
        res["background"] = view.backgroundColor().componentsOrdered()

    with watch.watch("actionState"):
        res["eraserMode"] = Krita.instance().action("erase_action").isChecked()
        res["canvasOnly"] = Krita.instance().action("view_show_canvas_only").isChecked()

    with watch.watch("globalState"):
        res["zoomFactor"] = QApplication.primaryScreen().devicePixelRatio()
        res["theme"] = get_active_theme()

    with watch.watch("documentState"):
        doc = view.document()
        fname = doc.fileName()
        doc_info = DocumentInfo.from_document(doc)
        res["editTime"] = doc_info.edit_time
        res["fileName"] = fname if fname != "" else None
        res["withSelection"] = Krita.instance().action("deselect").isEnabled()
        res["picResolution"] = [doc.width(), doc.height()]

    with watch.watch("toolOption-" + res["tool"]):
        res["toolOptions"] = get_tool_option_state(res["tool"])

    with watch.watch("layersState"):
        res["activeLayer"] = None
        if node := doc.activeNode():
            res["activeLayer"] = {
                "activeLayerName": node.name(),
                "activeLayerMode": node.blendingMode(),
                "activeLayerOpacity": node.opacity(),
            }

    res["cost"] = watch.result()
    return res


@route("state/set")
def state_set(req: Request[StateSetModel]) -> dict:
    """Set Krita painting state. All fields optional — only provided values are changed."""
    p = req.params
    view = active_view()
    if view is None:
        raise ResponseFail("No active view")

    result = {}

    if p.brushSize is not None:
        view.setBrushSize(p.brushSize)
        result["brushSize"] = p.brushSize

    if p.brushRotation is not None:
        view.setBrushRotation(p.brushRotation)
        result["brushRotation"] = p.brushRotation

    if p.blendingMode is not None:
        view.setCurrentBlendingMode(p.blendingMode)
        result["blendingMode"] = p.blendingMode

    if p.brushPreset is not None:
        resource = Krita.instance().resources("preset").get(p.brushPreset)
        if resource is None:
            raise ResponseFail(f"brushPreset '{p.brushPreset}' not found")
        view.setCurrentBrushPreset(resource)
        result["brushPreset"] = p.brushPreset

    if p.gradient is not None:
        resource = Krita.instance().resources("gradient").get(p.gradient)
        if resource is None:
            raise ResponseFail(f"gradient '{p.gradient}' not found")
        view.setCurrentGradient(resource)
        result["gradient"] = p.gradient

    if p.pattern is not None:
        resource = Krita.instance().resources("pattern").get(p.pattern)
        if resource is None:
            raise ResponseFail(f"pattern '{p.pattern}' not found")
        view.setCurrentPattern(resource)
        result["pattern"] = p.pattern

    if p.opacity is not None:
        view.setPaintingOpacity(p.opacity)
        result["opacity"] = p.opacity

    if p.flow is not None:
        view.setPaintingFlow(p.flow)
        result["flow"] = p.flow

    if p.foreground is not None:
        view.setForeGroundColor(_to_qcolor(p.foreground))
        result["foreground"] = p.foreground

    if p.background is not None:
        view.setBackGroundColor(_to_qcolor(p.background))
        result["background"] = p.background

    if p.tool is not None:
        set_current_tool(p.tool)
        result["tool"] = p.tool

    if p.eraserMode is not None:
        Krita.instance().action("erase_action").setChecked(p.eraserMode)
        result["eraserMode"] = p.eraserMode

    if p.canvasOnly is not None:
        Krita.instance().action("view_show_canvas_only").setChecked(p.canvasOnly)
        result["canvasOnly"] = p.canvasOnly

    return result


def _to_qcolor(rgba: tuple[float, float, float, float]):
    from krita import ManagedColor
    res = ManagedColor("RGBA", "U8", "")
    lst = res.componentsOrdered()
    lst[0] = rgba[0]
    lst[1] = rgba[1]
    lst[2] = rgba[2]
    lst[3] = rgba[3]
    res.setComponents(lst)
    return res


SELECT_ACTIONS_TOOLTIP_REVERSE = {
    Krita.instance().krita_i18nc('@info:tooltip', action): action
    for action in ['Replace', 'Intersect', 'Add', 'Subtract', 'Symmetric Difference']
}

SELECT_MODE_TOOLTIP_REVERSE = {
    Krita.instance().krita_i18nc('@info:tooltip', action): action
    for action in ['Pixel Selection', 'Vector Selection']
}

select_tool_option_select_btns = tool_option_widget.chain(
    lambda parent: [
        i for i in parent.findChildren(QToolButton)
        if i.toolTip() in SELECT_ACTIONS_TOOLTIP_REVERSE
    ]
)

select_tool_option_mode_btns = tool_option_widget.chain(
    lambda parent: [
        i for i in parent.findChildren(QToolButton)
        if i.toolTip() in SELECT_MODE_TOOLTIP_REVERSE
    ]
)


def get_tool_option_state(tool: str) -> dict:
    res = {}
    match tool:
        case "KritaShape/KisToolBrush":
            pass
        case x if x in (
            'KisToolSelectOutline',
            'KisToolSelectElliptical',
            'KisToolSelectRectangular',
            'KisToolSelectPolygonal',
            'KisToolSelectSimilar',
            'KisToolSelectMagnetic',
        ):
            res['type'] = 'SELECT_TOOL'
            for btn in select_tool_option_select_btns.get(Krita.instance().activeWindow()):
                if btn.isChecked():
                    res['selectAction'] = SELECT_ACTIONS_TOOLTIP_REVERSE[btn.toolTip()]
                    break
            for btn in select_tool_option_mode_btns.get(Krita.instance().activeWindow()):
                if btn.isChecked():
                    res['selectMode'] = SELECT_MODE_TOOLTIP_REVERSE[btn.toolTip()]
                    break
    return res
