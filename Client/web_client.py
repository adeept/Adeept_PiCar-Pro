#!/usr/bin/env python3
# Website     : www.Adeept.com
import argparse
import signal
import sys

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QToolBar, QWidget,
)

STYLE = """
QWidget { background:#141a1d; color:#e3f2f6; font-family:"Segoe UI","PingFang SC","Noto Sans CJK SC","DejaVu Sans","Helvetica Neue",sans-serif; font-size:12px; }
QToolBar { border:none; padding:6px 8px; spacing:8px; }
QLineEdit { background:#0d1214; border:1px solid #2b3a41; border-radius:4px; padding:5px 8px; min-width:180px; }
QLineEdit:focus { border-color:#0288d1; }
QPushButton { background:#0277bd; border:none; border-radius:4px; padding:5px 10px; }
QPushButton:hover { background:#0288d1; }
QPushButton:pressed { background:#01579b; }
QLabel#status { color:#7f9aa5; padding-left:6px; }
"""

START_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{margin:0;height:100vh;display:grid;place-items:center;background:#141a1d;
color:#e3f2f6;font:14px/1.6 "Segoe UI",system-ui,sans-serif}
main{max-width:520px;padding:0 24px}
h1{font-size:22px;margin:0 0 12px;color:#4fc3f7}
p{color:#9fb6be;margin:6px 0}
code{color:#81d4fa}
</style></head><body><main>
<h1>Adeept PiCar-Pro</h1>
<p>Type the robot IP in the toolbar and press <b>Connect</b>.</p>
<p>The robot serves its console on <code>http://&lt;ip&gt;:5000</code>; this window just wraps it.</p>
<p>Web profile only. Switch the server with <code>Server.py --mode web</code>.</p>
</main></body></html>"""

ERROR_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{margin:0;height:100vh;display:grid;place-items:center;background:#141a1d;
color:#e3f2f6;font:14px/1.6 "Segoe UI",system-ui,sans-serif}
main{max-width:560px;padding:0 24px}
h1{font-size:20px;margin:0 0 12px;color:#f06a63}
p{color:#9fb6be;margin:6px 0}
a{color:#4fc3f7}
code{color:#81d4fa}
</style></head><body><main>
<h1>Robot not reachable</h1>
<p><code>%s</code> did not answer.</p>
<p>Check that the robot is powered, joined to the same Wi-Fi, and running the web profile
(<code>sudo python3 Server.py --mode web</code>, port 5000).</p>
<p><a href="%s">Retry</a></p>
</main></body></html>"""


class Page(QWebEnginePage):
    def __init__(self, parent=None, echo=False):
        super().__init__(parent)
        self._echo = echo

    def javaScriptConsoleMessage(self, level, message, line, source):
        if self._echo:
            super().javaScriptConsoleMessage(level, message, line, source)


class WebShell(QMainWindow):
    def __init__(self, host="", echo_js=False):
        super().__init__()
        self.setWindowTitle("Adeept PiCar-Pro — Web Console")
        self.resize(1200, 820)
        self.setStyleSheet(STYLE)
        self._store = QSettings("Adeept", "Adeept PiCar-Pro Web")
        self._url = ""
        self._fallback = False

        self._view = QWebEngineView(self)
        self._view.setPage(Page(self._view, echo_js))
        self.setCentralWidget(self._view)
        self._build_toolbar()
        self._wire()

        host = host or str(self._store.value("host", ""))
        self._host.setText(host)
        if host:
            self.open_host(host)
        else:
            self._show_start()

    def _build_toolbar(self):
        self._bar = QToolBar()
        self._bar.setMovable(False)
        self.addToolBar(self._bar)

        self._host = QLineEdit()
        self._host.setPlaceholderText("Robot IP, e.g. 192.168.4.1")
        self._go = QPushButton("Connect")
        self._reload = QPushButton("Reload")
        self._status = QLabel("offline")
        self._status.setObjectName("status")

        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(QLabel("Robot Server IP:"))
        row.addWidget(self._host)
        row.addWidget(self._go)
        row.addWidget(self._reload)
        row.addWidget(self._status)
        self._bar.addWidget(holder)

    def _wire(self):
        self._go.clicked.connect(lambda: self.open_host(self._host.text()))
        self._host.returnPressed.connect(lambda: self.open_host(self._host.text()))
        self._reload.clicked.connect(self.reload)

        page = self._view.page()
        page.fullScreenRequested.connect(self._fullscreen)
        page.loadStarted.connect(lambda: self._status.setText("loading…"))
        page.loadProgress.connect(lambda value: self._status.setText("loading… %d%%" % value))
        page.loadFinished.connect(self._loaded)
        page.titleChanged.connect(self._titled)

        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)

        for keys, slot in (("F11", self._toggle_fullscreen), ("F5", self.reload), ("Ctrl+R", self.reload), ("Ctrl+Q", self.close)):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(slot)

    @staticmethod
    def target(text):
        text = text.strip()
        for scheme in ("http://", "https://"):
            if text.startswith(scheme):
                text = text[len(scheme):]
        text = text.strip("/")
        if not text:
            return ""
        if ":" not in text:
            text += ":5000"
        return "http://" + text + "/"

    def open_host(self, text):
        url = self.target(text)
        if not url:
            self._status.setText("enter the robot IP")
            return
        self._url = url
        self._store.setValue("host", self._host.text().strip())
        self._status.setText("connecting…")
        self._view.setUrl(QUrl(url))

    def reload(self):
        if self._url:
            self._view.setUrl(QUrl(self._url))

    def _loaded(self, ok):
        if self._fallback:
            self._fallback = False
            return
        if not ok:
            self._status.setText("unreachable")
            self._fallback = True
            self._view.setHtml(ERROR_PAGE % (self._url, self._url), QUrl(self._url))
            return
        if self._url:
            self._status.setText("online")

    def _titled(self, title):
        self.setWindowTitle("Adeept PiCar-Pro — Web Console")

    def _show_start(self):
        self._status.setText("offline")
        self._view.setHtml(START_PAGE, QUrl("http://robot.local/"))

    def _fullscreen(self, request):
        request.accept()
        on = request.toggleOn()
        self._bar.setVisible(not on)
        self.showFullScreen() if on else self.showNormal()

    def _toggle_fullscreen(self):
        on = not self.isFullScreen()
        self._bar.setVisible(not on)
        self.showFullScreen() if on else self.showNormal()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Adeept PiCar-Pro web-mode desktop client")
    parser.add_argument("--host", default="192.168.4.1", help="Robot IP, connect on start")
    parser.add_argument("--log-js", action="store_true", help="echo the robot page's JS console messages")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    window = WebShell(args.host, args.log_js)
    signal.signal(signal.SIGINT, lambda *_: window.close())
    pulse = QTimer()
    pulse.timeout.connect(lambda: None)
    pulse.start(200)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
