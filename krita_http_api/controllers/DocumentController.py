"""
read and write document and image data.
"""
import os
from datetime import datetime
from typing import Callable, Any

from pydantic import BaseModel

from krita import Krita

from PyQt5.QtWidgets import QLineEdit

from ..routing import Request, ResponseFail
from ..utils import active_document, active_window, DocumentInfo
from ..PerWindowCachedState import PerWindowCachedState
from .route import route, async_route, sleep


class OpenDocumentModel(BaseModel):
    path: str


class ConvertOpenModel(BaseModel):
    original_path: str
    target_path: str


class ImageModel(BaseModel):
    withImage: bool


class ImageTiledModel(BaseModel):
    tileSize: int = 256


@route("document/layers")
def get_layers(req: Request) -> list[dict]:
    """List all layers in the active document."""
    doc = active_document()
    if doc is None:
        raise ResponseFail("No active document")
    return _walk_nodes(doc.rootNode())


def _walk_nodes(node, depth=0) -> list[dict]:
    result = []
    for child in node.childNodes():
        info = dict(
            name=child.name(),
            type=child.type(),
            visible=child.visible(),
            opacity=child.opacity(),
            blendingMode=child.blendingMode(),
            depth=depth,
        )
        result.append(info)
        result.extend(_walk_nodes(child, depth + 1))
    return result


@route("document/open")
def open_image(req: Request[OpenDocumentModel]) -> str:
    """Open an image file as a new document."""
    doc = Krita.instance().openDocument(req.params.path)
    if doc is None:
        raise ResponseFail(f"failed to open '{req.params.path}'")
    active_window().addView(doc)
    return "done"


@route("document/convert_to_open")
def convert_open(req: Request[ConvertOpenModel]) -> str:
    """Open an image and save as a different format."""
    p = req.params
    doc = Krita.instance().openDocument(p.original_path)
    if doc is None:
        raise ResponseFail(f"failed to open '{p.original_path}'")
    doc.saveAs(p.target_path)
    active_window().addView(doc)
    return "done"


@async_route("document/image")
def get_image(req: Request[ImageModel]) -> dict:
    """Get document pixel data (width, height, depth, model, optional base64)."""
    doc = active_document()
    if doc is None:
        raise ResponseFail("No active document")

    w, h = doc.width(), doc.height()
    depth = doc.colorDepth()
    model = doc.colorModel()

    a = datetime.now().timestamp()
    pixel_data = doc.pixelData(0, 0, w, h)
    b = datetime.now().timestamp()

    result = dict(
        w=w, h=h, depth=depth, model=model,
        getPixelBytesCost=round((b - a) * 1000),
    )

    if req.params.withImage:
        base64 = str(pixel_data.toBase64(), "utf-8")
        c = datetime.now().timestamp()
        result["base64"] = base64
        result["getBase64Cost"] = round((c - b) * 1000)

    return result


@async_route("document/image-tiled")
def get_image_tiled(req: Request[ImageTiledModel]) -> dict:
    """Get document pixel data in tiles. Yields sleep(0) between tiles so Qt stays responsive."""
    doc = active_document()
    if doc is None:
        raise ResponseFail("No active document")

    w, h = doc.width(), doc.height()
    tile_size = req.params.tileSize

    tiles = []
    for y in range(0, h, tile_size):
        for x in range(0, w, tile_size):
            tw = min(tile_size, w - x)
            th = min(tile_size, h - y)
            pixel_data = doc.pixelData(x, y, tw, th)
            tiles.append({
                "x": x, "y": y, "w": tw, "h": th,
                "base64": str(pixel_data.toBase64(), "utf-8"),
            })
            yield from sleep(0)

    return {"w": w, "h": h, "tileSize": tile_size, "tiles": tiles}


def _get_record_dir(window):
    recorder_docker = next(
        i for i in window.dockers() if i.objectName() == "RecorderDocker"
    )
    return recorder_docker.findChild(QLineEdit, "editDirectory")


_recorder_dir_widget = PerWindowCachedState(_get_record_dir)


@async_route("document/records")
def get_records(req: Request) -> dict:
    """Get recording directory and frame files."""
    doc = active_document()
    if doc is None:
        raise ResponseFail("No active document")

    if not Krita.instance().action("recorder_record_toggle").isChecked:
        raise ResponseFail("not recording")

    dir_obj = _recorder_dir_widget.get(active_window())
    record_directory = dir_obj.text()

    w, h = doc.width(), doc.height()
    depth = doc.colorDepth()
    model = doc.colorModel()
    formatted_date = DocumentInfo.from_document(doc).create_date.strftime("%Y%m%d%H%M%S")
    doc_record_path = os.path.join(record_directory, formatted_date).replace("\\", "/")

    if not os.path.exists(doc_record_path):
        raise ResponseFail("No record yet")

    return dict(
        w=w, h=h, depth=depth, model=model,
        path=doc_record_path,
        records=os.listdir(doc_record_path),
    )
