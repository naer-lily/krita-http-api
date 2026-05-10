import asyncio
import json
import threading
import traceback
import uuid
from typing import Callable

import websockets
from websockets import WebSocketServerProtocol

from PyQt5.QtCore import pyqtSignal, QObject

from .Logger import Logger


logger = Logger("QWebsocketServer")

BIZ_TIMEOUT = 5.0
MAX_CONCURRENT_TASKS = 10


class SignalHandler(QObject):
    new_request = pyqtSignal(str, str)
    result_ready = pyqtSignal(str, str)


class QWebsocketServer(threading.Thread):
    def __init__(self, port=8765):
        super().__init__(daemon=True)
        self._signal_handler = SignalHandler()
        self._port = port
        self.clients: dict[str, WebSocketServerProtocol] = {}
        self._futures: dict[str, asyncio.Future] = {}
        self._futures_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

        self._signal_handler.result_ready.connect(self._on_result_ready)

    def _on_result_ready(self, request_id: str, response_json: str):
        with self._futures_lock:
            future = self._futures.pop(request_id, None)
        if future is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(future.set_result, response_json)

    async def _per_message(self, websocket: WebSocketServerProtocol, message: str):
        try:
            request_json = json.loads(message)
            request_id = request_json.get('request_id', str(uuid.uuid4()))
        except json.JSONDecodeError:
            request_id = str(uuid.uuid4())

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        with self._futures_lock:
            self._futures[request_id] = future

        try:
            self._signal_handler.new_request.emit(request_id, message)
            result = await asyncio.wait_for(future, timeout=BIZ_TIMEOUT)
        except asyncio.TimeoutError:
            result = json.dumps({'ok': False, 'msg': 'TIMEOUT'})
        finally:
            with self._futures_lock:
                self._futures.pop(request_id, None)

        await websocket.send(result)

    async def _echo(self, websocket: WebSocketServerProtocol, path: str) -> None:
        connection_id = str(uuid.uuid4())
        self.clients[connection_id] = websocket
        logger.info(f"Client connected: {connection_id}")

        try:
            async for message in websocket:
                async with self._semaphore:
                    asyncio.create_task(self._per_message(websocket, message))
        except websockets.ConnectionClosed:
            logger.info(f"Client disconnected: {connection_id}")
        finally:
            if connection_id in self.clients:
                del self.clients[connection_id]

    async def _main(self):
        self._loop = asyncio.get_running_loop()
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        async with websockets.serve(self._echo, "localhost", self._port):
            logger.info(f"WebSocket server started on port {self._port}")
            await asyncio.Future()

    def on_request(self, cb: Callable):
        def _on_request(request_id: str, request_body: str):
            try:
                request_json = json.loads(request_body)
            except Exception:
                self._signal_handler.result_ready.emit(request_id, json.dumps({
                    'ok': False,
                    'msg': "expect a json object, got ...(check 'data' field)",
                    'data': request_body,
                    'request_id': request_id,
                }))
                return

            def ok(res):
                self._signal_handler.result_ready.emit(request_id, json.dumps({
                    'ok': True,
                    'data': res,
                    'request_id': request_id,
                }))

            def fail(msg, res=None):
                self._signal_handler.result_ready.emit(request_id, json.dumps({
                    'ok': False,
                    'msg': msg,
                    'data': res,
                    'call_stack': traceback.format_exc(),
                    'request_id': request_id,
                }))

            try:
                cb(request_json, ok, fail)
            except Exception as e:
                stack_trace = traceback.format_exc()
                logger.warn(f"ws request error: {e}")
                logger.warn(stack_trace)
                fail(str(e))

        self._signal_handler.new_request.connect(_on_request)

    def run(self):
        asyncio.run(self._main())
