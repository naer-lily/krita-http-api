"""
get and set docker display status.
"""
from typing import Optional

from pydantic import BaseModel

from krita import Krita

from PyQt5.QtWidgets import QDockWidget, QWidget

from ..routing import Request, ResponseFail
from .route import route


class DockerSetStateModel(BaseModel):
    objectName: str
    visible: Optional[bool] = None
    floating: Optional[bool] = None
    pos: Optional[tuple[int, int]] = None
    size: Optional[tuple[int, int]] = None
    withHeader: Optional[bool] = None


_docker_original_titlebar: dict[str, QWidget] = {}


def _docker_headless(docker: QDockWidget) -> bool:
    result = docker.titleBarWidget().objectName().startswith("EMPTY_")
    docker_id = docker.window().objectName() + docker.objectName()
    if docker_id not in _docker_original_titlebar:
        if not result:
            _docker_original_titlebar[docker_id] = docker.titleBarWidget()
    return result


def _set_docker_headless(docker: QDockWidget, headless: bool):
    if _docker_headless(docker) == headless:
        return
    if headless:
        w = QWidget()
        w.setObjectName(f"EMPTY_{docker.objectName()}")
        docker.setTitleBarWidget(w)
    else:
        docker_id = docker.window().objectName() + docker.objectName()
        old = _docker_original_titlebar.get(docker_id)
        if old:
            x = docker.titleBarWidget()
            docker.setTitleBarWidget(old)
            x.deleteLater()


@route("docker/list")
def docker_list(req: Request) -> dict:
    """List all dockers with visibility, floating state, and header status."""
    result = {}
    for docker in Krita.instance().dockers():
        geo = docker.geometry()
        result[docker.objectName()] = dict(
            visible=docker.isVisible(),
            floating=docker.isFloating(),
            withHeader=not _docker_headless(docker),
        )
        if docker.isFloating():
            result[docker.objectName()]["geometry"] = [
                geo.x(), geo.y(), geo.width(), geo.height()
            ]
    return result


@route("docker/get-state")
def docker_get_state(req: Request[str]) -> dict:
    """Get full state for a specific docker by objectName."""
    object_name = req.params
    docker = next(
        (d for d in Krita.instance().dockers() if d.objectName() == object_name),
        None,
    )
    if docker is None:
        raise ResponseFail(f"No docker named '{object_name}'")
    geo = docker.geometry()
    return dict(
        objectName=object_name,
        visible=docker.isVisible(),
        floating=docker.isFloating(),
        pos=[geo.x(), geo.y()],
        size=[geo.width(), geo.height()],
        withHeader=not _docker_headless(docker),
    )


@route("docker/set-state")
def docker_set_state(req: Request[DockerSetStateModel]) -> dict:
    """Set visibility, floating, position, size, or header for a docker."""
    p = req.params
    docker = next(
        (d for d in Krita.instance().dockers() if d.objectName() == p.objectName),
        None,
    )
    if docker is None:
        raise ResponseFail(f"No docker named '{p.objectName}'")

    result = {"objectName": p.objectName}

    if p.visible is not None:
        geo = docker.geometry()
        docker.setVisible(p.visible)
        docker.setGeometry(geo)
        result["visible"] = p.visible

    if p.floating is not None:
        docker.setFloating(p.floating)
        result["floating"] = p.floating

    if p.pos is not None or p.size is not None:
        geo = docker.geometry()
        result["oldgeo"] = [geo.x(), geo.y(), geo.width(), geo.height()]
        if p.pos is not None:
            geo.setX(p.pos[0])
            geo.setY(p.pos[1])
            result["pos"] = p.pos
        if p.size is not None:
            geo.setWidth(p.size[0])
            geo.setHeight(p.size[1])
            result["size"] = p.size
        docker.setGeometry(geo)
        docker.repaint()
        geo = docker.geometry()
        result["newgeo"] = [geo.x(), geo.y(), geo.width(), geo.height()]

    if p.withHeader is not None:
        _set_docker_headless(docker, not p.withHeader)

    return result


@route("docker/hide-all")
def docker_hide_all(req: Request) -> bool:
    """Hide all dockers."""
    for docker in Krita.instance().dockers():
        docker.setVisible(False)
    return True
