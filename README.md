# Krita HTTP API

Expose Krita API via an HTTP server and an optional websocket server. Uses Python's `http.server` (ThreadingMixIn) bridged to Qt's main thread via `pyqtSignal` for thread-safe Krita API access.

# Usage

1. Download this repo as ZIP and import via Krita menu: **Tools > Scripts > Import Python Plugin from File**. Enable the "HTTP API" plugin.
2. Install pydantic (required for param validation). Uses your system pip — specify Krita's Python version so the correct binary wheel is fetched:
   ```bash
   # Windows — Krita 5.2 uses Python 3.13:
   cd <plugin_dir>\krita_http_api
   pip install --target=./third_deps --python-version 3.13 --platform win_amd64 --only-binary :all: pydantic

   # Linux:
   cd <plugin_dir>/krita_http_api
   pip install --target=./third_deps --python-version 3.13 --platform linux_x86_64 --only-binary :all: pydantic

   # Optional: websocket server
   pip install --target=./third_deps --python-version 3.13 --platform win_amd64 --only-binary :all: websockets
   ```
   Verify Krita's Python version first: **Tools > Scripts > Scripter**, run `import sys; print(sys.version)`.
3. Restart Krita, **open a document**.
4. Send a request:
   ```bash
   curl -d '{"code": "ping", "param": {}}' localhost:1976
   curl -d '{"code": "floating-message", "param": {"message": "Hello, World!"}}' localhost:1976
   curl -d '{"code": "__docs__", "param": {}}' localhost:1976   # API documentation
   ```

Ports: HTTP `1976`, WebSocket `1949` (hardcoded).

# Adding Routes

Use `@route` (sync) or `@async_route` (async) decorators with **pydantic** models for parameter validation:

```python
from pydantic import BaseModel
from .route import route, async_route, Request, ResponseFail
from .route import sleep, create_future          # async primitives

class FlipModel(BaseModel):
    horizontal: bool = True
    vertical: bool = False

# ----- sync ------------------------------------------------------------

@route('image/flip')
def flip(req: Request[FlipModel]) -> str:
    """Flip the active layer."""
    p = req.params
    if p.horizontal:
        Krita.instance().action('mirrorLayerHorizontal').trigger()
    if p.vertical:
        Krita.instance().action('mirrorLayerVertical').trigger()
    return 'done'

# ----- async: procedural (no yield — just return/raise) ----------------

class ExportModel(BaseModel):
    path: str

@async_route('image/export')
def export(req: Request[ExportModel]) -> str:
    p = req.params
    doc = active_document()
    if doc is None:
        raise ResponseFail("No active document")
    doc.saveAs(p.path)
    return 'done'

# ----- async: generator (yield from sleep / future) --------------------

@async_route('image/export-delayed')
def export_delayed(req: Request[ExportModel]) -> str:
    """Export after a short delay — does not block Qt."""
    yield from sleep(100)        # pause 100ms, Qt stays responsive
    doc = active_document()
    doc.saveAs(req.params.path)
    return 'done'

@async_route('dialog/wait-button')
def wait_button(req: Request) -> str:
    """Open a dialog and wait for user to click."""
    fut, resolve = create_future()       # (1) create a future + resolver
    box = QMessageBox()
    box.finished.connect(lambda btn: resolve(btn))  # (2) pass resolver to callback
    box.open()
    result = yield from fut              # (3) pause until resolved
    return f"clicked: {result}"          # (4) result = whatever resolve() was called with
```

- **`Request[T]`** — `T` is inferred from the type hint; pydantic validates `param` against `T`.
- **`return value`** — sends a success response (works in both sync and async routes).
- **`raise ResponseFail(msg)`** — sends an error response (works in both sync and async routes).

### Async primitives (generator-based)

| Primitive | Usage | Effect |
|-----------|-------|--------|
| `sleep(ms)` | `yield from sleep(100)` | Pause `ms` milliseconds via `QTimer.singleShot`. Qt stays responsive. |
| `create_future()` | `fut, resolve = create_future()` | Create a one-shot awaitable. Pass `resolve` to any callback; `yield from fut` pauses until `resolve(value)` is called. |

`yield from sleep(0)` is a useful pattern — it yields to Qt's event loop for one tick without delaying.

View auto-generated docs: `curl -d '{"code": "__docs__", "param": {}}' localhost:1976`

# Request / Response

```typescript
type RequestBody = {
    code: string,       // route code
    param: T,           // validated against pydantic model
}

type Response = {
    ok: true,
    data: any,
} | {
    ok: false,
    msg: string,
    data: any,
    call_stack: string,
}
```

Response is always HTTP 200 — use the `ok` field to check success.

# Limitations

1. Server may reject connections under high concurrency due to `ThreadingMixIn`'s thread-per-request model. Clients should limit max connections.
2. The client must poll state in duration to sync states, which may be expensive. (In practice, calling `state/get` every 33ms had no performance issues.)

# Architecture

![](./sequence_diagram.png)
