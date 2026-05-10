import inspect
from datetime import datetime

from PyQt5.QtCore import qInfo, qWarning


class Logger:
    def __init__(self, name: str = ""):
        self.name = name if name else self._detect_caller()

    @staticmethod
    def _detect_caller() -> str:
        frame = inspect.currentframe()
        try:
            caller = frame.f_back.f_back
            filepath = caller.f_code.co_filename.replace("\\", "/")
        finally:
            del frame

        try:
            idx = filepath.rindex("pykrita/")
            return filepath[idx + len("pykrita/"):]
        except ValueError:
            return filepath

    def _format(self, level: str, msg: str) -> bytes:
        frame = inspect.currentframe()
        try:
            caller = frame.f_back.f_back
            lineno = caller.f_lineno
        finally:
            del frame

        datestr = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        return f"[{level}][{self.name}:{lineno}] {datestr}: {msg}".encode("utf-8")

    def info(self, msg: str):
        qInfo(self._format('INFO', msg))

    def warn(self, msg: str):
        qWarning(self._format("WARN", msg))
