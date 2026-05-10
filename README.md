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
from .route import route, async_route, Request, AsyncRequest

class FlipModel(BaseModel):
    horizontal: bool = True
    vertical: bool = False

@route('image/flip')
def flip(req: Request[FlipModel]) -> str:
    """Flip the active layer."""
    p = req.params
    if p.horizontal:
        Krita.instance().action('mirrorLayerHorizontal').trigger()
    if p.vertical:
        Krita.instance().action('mirrorLayerVertical').trigger()
    return 'done'

@async_route('image/export')
def export(req: AsyncRequest[ExportModel, str]):
    """Export and respond after processing."""
    # ... async work ...
    req.ok('done')
```

- **`Request[T]`** — `T` is inferred from the type hint; pydantic validates `param` against `T`.
- **`AsyncRequest[T, OkT]`** — same, with `req.ok(payload)` / `req.fail(msg)` to respond.
- Raise `ResponseFail(msg)` in sync handlers to return an error.

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
