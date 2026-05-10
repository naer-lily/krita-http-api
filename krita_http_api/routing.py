"""
Route system with pydantic validation and auto-generated documentation.

Install pydantic for parameter validation:
    pip install --target=./third_deps pydantic
"""
import inspect
import types
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar, Union, get_type_hints, get_args, get_origin

from .Logger import Logger
from .event_loop import EventLoop

logger = Logger("routing")


class ResponseFail(Exception):
    """Raise in route handlers to respond with an error."""

    def __init__(self, msg: str, res=None):
        super().__init__(msg)
        self.msg = msg
        self.res = res


T = TypeVar("T")


class Request(Generic[T]):
    """Route request wrapper. Access validated params via ``.params``."""

    __slots__ = ("code", "params")

    def __init__(self, code: str, params: T):
        self.code = code
        self.params = params


@dataclass
class RouteDef:
    code: str
    handler: Callable
    sync: bool
    param_type: Any
    ok_type: Any
    doc: str
    module: str


class HttpRouter:
    def __init__(self):
        self._routes: dict[str, RouteDef] = {}

    # ------------------------------------------------------------------ #
    #  registration
    # ------------------------------------------------------------------ #

    def add_route(self, code: str, handler, *, sync: bool):
        if code in self._routes:
            raise KeyError(f"route code '{code}' duplicated")

        hints = get_type_hints(handler)
        return_hint = hints.pop("return", None)

        req_hint: Any = None
        for _name, hint in hints.items():
            req_hint = hint
            break

        param_type = None

        if req_hint is not None:
            origin = get_origin(req_hint)
            args = get_args(req_hint)
            if origin is Request and len(args) >= 1:
                param_type = args[0]

        ok_type = return_hint

        self._routes[code] = RouteDef(
            code=code,
            handler=handler,
            sync=sync,
            param_type=param_type,
            ok_type=ok_type,
            doc=inspect.getdoc(handler) or "",
            module=inspect.getfile(handler),
        )

    # ------------------------------------------------------------------ #
    #  dispatch
    # ------------------------------------------------------------------ #

    @staticmethod
    def _hint():
        return (
            " See available endpoints: "
            "curl -d '{\"code\": \"__docs__\", \"param\": {}}' localhost:1976"
        )

    def __call__(self, req, ok_cb, fail_cb):
        if "code" not in req:
            return fail_cb("field 'code' missing. " + self._hint(), None)
        if not isinstance(req["code"], str):
            return fail_cb("field 'code' must be string. " + self._hint(), None)
        if "param" not in req:
            return fail_cb("field 'param' missing. " + self._hint(), None)

        code = req["code"]
        route = self._routes.get(code)
        if route is None:
            return fail_cb(
                f"route '{code}' not found. valid routes: {list(self._routes.keys())}"
                f"  --  {self._hint()}",
                None,
            )

        logger.info(f"request '{code}', param: {req['param']}")

        try:
            validated = self._validate(route.param_type, req["param"])
        except ResponseFail as e:
            return fail_cb(f"{e.msg}  --  {self._hint()}", e.res)

        if route.sync:
            request = Request(code=code, params=validated)
            try:
                result = route.handler(request)
            except ResponseFail as e:
                return fail_cb(e.msg, e.res)
            except Exception as e:
                return fail_cb(str(e), None)
            ok_cb(result)
        else:
            request = Request(code=code, params=validated)
            try:
                result = route.handler(request)
            except ResponseFail as e:
                return fail_cb(e.msg, e.res)
            except Exception as e:
                return fail_cb(str(e), None)

            if isinstance(result, types.GeneratorType):
                def _drive():
                    try:
                        value = yield from result
                        ok_cb(value)
                    except ResponseFail as e:
                        fail_cb(e.msg, e.res)
                    except Exception as e:
                        fail_cb(str(e), None)

                EventLoop.get_event_loop().run_coroutine(_drive())
            else:
                ok_cb(result)

    # ------------------------------------------------------------------ #
    #  validation
    # ------------------------------------------------------------------ #

    @staticmethod
    def _validate(param_type, param):
        if param_type is None:
            return param
        try:
            from pydantic import TypeAdapter
        except ImportError:
            logger.warn("pydantic not installed — skipping param validation")
            return param
        try:
            return TypeAdapter(param_type).validate_python(param)
        except Exception as e:
            raise ResponseFail(str(e)) from e

    # ------------------------------------------------------------------ #
    #  documentation
    # ------------------------------------------------------------------ #

    def generate_docs(self) -> str:
        lines = [
            "# Krita HTTP API",
            "",
            "Send POST requests to `localhost:1976` with JSON body:",
            "",
            "```json",
            '{"code": "<endpoint>", "param": {...}}',
            "```",
            "",
            "Response is always HTTP 200 — use the `ok` field to check success.",
            "",
            "---",
            "",
            "## Endpoints",
            "",
        ]

        for code in sorted(self._routes.keys()):
            if code == "__docs__":
                continue
            route = self._routes[code]
            lines.append(f"### `{code}`")
            lines.append("")
            mode = "sync" if route.sync else "async"
            lines.append(f"*{mode}*  |  `{route.module}`")
            lines.append("")
            if route.doc:
                lines.append(route.doc.strip())
                lines.append("")

            self._write_param_section(lines, route)
            self._write_return_section(lines, route)
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def _write_param_section(self, lines: list[str], route: RouteDef):
        if route.param_type is None:
            lines.append("- **Parameters:** `any`")
            return
        lines.append(f"- **Parameters:** `{_type_repr(route.param_type)}`")
        if isinstance(route.param_type, type) and hasattr(route.param_type, "model_fields"):
            lines.append("")
            lines.append("| Field | Type | Default |")
            lines.append("|-------|------|---------|")
            for field_name, field_info in route.param_type.model_fields.items():
                ftype = _type_repr(field_info.annotation)
                default = _default_repr(field_info)
                lines.append(f"| `{field_name}` | {ftype} | {default} |")

    def _write_return_section(self, lines: list[str], route: RouteDef):
        if route.ok_type is None:
            return
        lines.append(f"- **Returns:** `{_type_repr(route.ok_type)}`")
        if isinstance(route.ok_type, type) and hasattr(route.ok_type, "model_fields"):
            lines.append("")
            lines.append("| Field | Type |")
            lines.append("|-------|------|")
            for field_name, field_info in route.ok_type.model_fields.items():
                ftype = _type_repr(field_info.annotation)
                lines.append(f"| `{field_name}` | {ftype} |")

    @property
    def codes(self) -> list[str]:
        return list(self._routes.keys())


# ---------------------------------------------------------------------- #
#  type name rendering helpers for documentation
# ---------------------------------------------------------------------- #

def _type_repr(tp: Any) -> str:
    if tp is None:
        return "any"
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is not None:
        if origin is Union or origin is type(Union[int, str]):
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return f"{_type_repr(non_none[0])}?"
            return " | ".join(_type_repr(a) for a in args)
        origin_name = getattr(origin, "__name__", str(origin))
        args_repr = ", ".join(_type_repr(a) for a in args)
        return f"{origin_name}[{args_repr}]"
    if isinstance(tp, type):
        return tp.__name__
    return str(tp)


def _default_repr(field_info) -> str:
    if field_info.is_required():
        return "*required*"
    default = field_info.default
    if default is None:
        return "`None`"
    return f"`{default}`"


# ---------------------------------------------------------------------- #
#  decorators
# ---------------------------------------------------------------------- #

_router = HttpRouter()


def route(code: str):
    """Register a **synchronous** route.

    Usage::

        @route('ping')
        def ping(req: Request) -> dict:
            return {'msg': 'pong'}

        @route('state/set')
        def state_set(req: Request[StateSetModel]) -> dict:
            req.params.brushSize  # validated by pydantic
    """

    def decorator(func):
        _router.add_route(code, func, sync=True)
        return func

    return decorator


def async_route(code: str):
    """Register an **asynchronous** route.

    Generator style (yield from sleep / future)::

        @async_route('wait-animation')
        def wait_animation(req: Request) -> dict:
            yield from sleep(100)
            return {"done": True}

        @async_route('dialog/wait')
        def dialog_wait(req: Request[str]) -> dict:
            fut, resolve = create_future()
            QTimer.singleShot(100, lambda: resolve("done"))
            result = yield from fut
            return {"result": result}

    Procedural style (no yield — just return/raise)::

        @async_route('doc/image')
        def get_image(req: Request[ImageModel]) -> dict:
            if not doc:
                raise ResponseFail("no document")
            return {"width": doc.width()}
    """

    def decorator(func):
        _router.add_route(code, func, sync=False)
        return func

    return decorator


# re-export for convenience
router = _router
