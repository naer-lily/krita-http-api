import json
import threading
import traceback
import uuid
from typing import Callable

from PyQt5.QtCore import pyqtSignal, QObject

from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from .Logger import Logger


logger = Logger("QHttpServer")

BIZ_TIMEOUT = 5000

_DOCS_HINT = " See available endpoints: curl -d '{\"code\": \"__docs__\", \"param\": {}}' localhost:1976"


class RequestHandler(BaseHTTPRequestHandler):

    def send_json_error(self, msg: str):
        response_json = json.dumps({
            'ok': False,
            'msg': msg,
        })

        self.send_response_only(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Connection', 'keep-alive')
        response_bytes = response_json.encode('utf-8')
        self.send_header('Content-Length', str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def __go(self):
        if 'Content-Length' not in self.headers:
            logger.warn("No Header 'Content-Length'")
            return self.send_json_error("Header 'Content-Length' is required!" + _DOCS_HINT)

        content_length = int(self.headers['Content-Length'])

        if content_length == 0:
            logger.warn("no request body")
            return self.send_json_error("No Request Body!" + _DOCS_HINT)

        request_body_str = ""
        try:
            request_body_str = self.rfile.read(content_length).decode('utf-8')
            request_body = json.loads(request_body_str)
            if not isinstance(request_body, dict):
                raise ValueError("Body must be a JSON Object")

        except Exception:
            logger.warn(f"body parse error, got '{request_body_str}'")
            return self.send_json_error("Body must be a JSON Object!" + _DOCS_HINT)

        curr_request_id = str(uuid.uuid4())
        response_event = threading.Event()
        response_container = {}

        with self.server.pending_lock:
            self.server.pending_requests[curr_request_id] = (response_event, response_container)

        self.server.signal_handler.new_request.emit(curr_request_id, request_body)

        if not response_event.wait(timeout=BIZ_TIMEOUT / 1000.0):
            with self.server.pending_lock:
                self.server.pending_requests.pop(curr_request_id, None)
            return self.send_json_error(
                f"respond timeout for {BIZ_TIMEOUT} ms, check your biz code!"
                f" request body: {request_body_str}" + _DOCS_HINT
            )

        response = response_container.get('data')

        self.send_response_only(200)

        if not isinstance(response, str):
            try:
                response = json.dumps(response)
            except Exception:
                stack_trace = traceback.format_exc()
                logger.warn(stack_trace)
                response = json.dumps({
                    'ok': False,
                    'msg': f"json dump response failed, check your biz code!"
                           f" request body: {request_body_str}",
                    'data': None,
                    'call_stack': stack_trace,
                })

        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Connection', 'keep-alive')
        response_bytes = response.encode('utf-8')
        self.send_header('Content-Length', str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_POST(self):
        self.__go()

    def do_GET(self):
        self.__go()


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class SignalHandler(QObject):
    new_request = pyqtSignal(str, dict)
    result_ready = pyqtSignal(str)

    def __init__(self):
        super().__init__()


class ServerThread(threading.Thread):
    def __init__(self, signal_handler, port=8080):
        super().__init__(daemon=True)
        self.signal_handler = signal_handler
        self.port = port
        self.responses = {}
        self.responses_lock = threading.Lock()
        self.pending_requests = {}
        self.pending_lock = threading.Lock()

    def run(self):
        server_address = ('', self.port)
        httpd = ThreadingHTTPServer(server_address, RequestHandler)
        httpd.signal_handler = self.signal_handler
        httpd.responses = self.responses
        httpd.responses_lock = self.responses_lock
        httpd.pending_requests = self.pending_requests
        httpd.pending_lock = self.pending_lock
        logger.info(f'Starting httpd server on port {self.port}...')
        httpd.serve_forever()


class QHTTPServer(QObject):
    def __init__(self, port):
        super().__init__()
        self.port = port
        self.signal_handler = SignalHandler()
        self.server_thread = ServerThread(self.signal_handler, port)
        self.signal_handler.new_request.connect(self.__handle_request)
        self.signal_handler.result_ready.connect(self.__on_result_ready)

        def go(req: dict, resolve: Callable[[dict], None]):
            resolve({
                'ok': False,
                'msg': 'No Request Handler given.',
                'data': req,
            })
        self.__on_request = go

    def start(self):
        self.server_thread.start()

    def on_request(self, cb: Callable[[dict, Callable[[dict], None], Callable[[dict], None]], None]):
        def go(req: dict, resolve: Callable[[dict], None]):
            def ok(res):
                resolve({
                    'ok': True,
                    'data': res,
                })

            def fail(msg, res):
                resolve({
                    'ok': False,
                    'msg': msg,
                    'data': res,
                    'call_stack': traceback.format_exc(),
                })

            return cb(req, ok, fail)

        self.__on_request = go

    def __on_result_ready(self, req_id: str):
        with self.server_thread.pending_lock:
            entry = self.server_thread.pending_requests.pop(req_id, None)
        if entry is None:
            return
        event, container = entry
        with self.server_thread.responses_lock:
            container['data'] = self.server_thread.responses.pop(req_id, None)
        event.set()

    def __handle_request(self, req_id, req):
        resolve_called = False

        def resolve(res):
            nonlocal resolve_called
            resolve_called = True
            self.__send_response(req_id, res)

        try:
            self.__on_request(req, resolve)
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.warn(f"something bad happened for request {req}; exception: {e}")
            logger.warn(stack_trace)
            if not resolve_called:
                resolve({
                    'ok': False,
                    'msg': 'something bad happened, check your biz code',
                    'e': repr(e),
                    'call_stack': stack_trace,
                })

    def __send_response(self, req_id, response):
        with self.server_thread.responses_lock:
            self.server_thread.responses[req_id] = response
        self.signal_handler.result_ready.emit(req_id)
