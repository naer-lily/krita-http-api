from krita import Krita, Extension

from .QHttpServer import QHTTPServer
from .Logger import Logger
from .controllers.route import router

logger = Logger()

class krita_http_api(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        self.http_server = QHTTPServer(1976)
        # self.http_server.setParent(self)
        self.http_server.on_request(router)
        self.server_started = False

        self.socket_server = None
        try:
            from .QWebsocketServer import QWebsocketServer
            self.socket_server = QWebsocketServer(1949)
            self.socket_server.on_request(router)
        except ImportError:
            pass

    def setup(self):
        pass

    def createActions(self, window):
        if not self.server_started:
            if self.socket_server is not None:
                self.socket_server.start()
            self.http_server.start()
            self.server_started = True

# And add the extension to Krita's list of extensions:
Krita.instance().addExtension(krita_http_api(Krita.instance())) 
