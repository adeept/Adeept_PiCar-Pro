#!/usr/bin/env python3
# Website     : www.Adeept.com
import argparse
import json
import math
import re
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QColorDialog, QComboBox, QDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QSizePolicy, QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

LOGO = Path(__file__).resolve().with_name("logo.png")
RADAR_MAX_CM = 50.0

STYLE = """
QWidget { background:#161a1d; color:#e1f5fe; font-family:"Segoe UI","PingFang SC","Noto Sans CJK SC","DejaVu Sans","Helvetica Neue",sans-serif; font-size:12px; }
QGroupBox { border:1px solid #263238; border-radius:6px; margin-top:9px; padding-top:6px; }
QGroupBox::title { subcontrol-origin:margin; left:8px; padding:0 4px; color:#81d4fa; }
QToolButton, QPushButton { background:#0277bd; border:none; border-radius:4px; padding:4px 6px; }
QToolButton:hover, QPushButton:hover { background:#0288d1; }
QToolButton:pressed, QPushButton:pressed { background:#01579b; }
QToolButton:disabled, QPushButton:disabled { background:#37474f; color:#78909c; }
QLineEdit, QSpinBox, QComboBox { background:#0f1214; border:1px solid #37474f; border-radius:3px; padding:3px 6px; }
QSlider::groove:horizontal { height:4px; background:#37474f; border-radius:2px; }
QSlider::handle:horizontal { width:14px; margin:-5px 0; border-radius:7px; background:#4fc3f7; }
QPlainTextEdit { border:1px solid #263238; border-radius:4px; background:#0f1214; font-family:Consolas; font-size:11px; }
QLabel#brand { background:transparent; }
"""

BOX_STYLE = """
QGroupBox {{ border:1px solid {border}; }}
QGroupBox::title {{ color:{title}; }}
QToolButton, QPushButton {{ background:{base}; }}
QToolButton:hover, QPushButton:hover {{ background:{hover}; }}
QToolButton:pressed, QPushButton:pressed {{ background:{press}; }}
QToolButton:checked {{ background:{checked}; }}
"""

ACCENTS = {
    "drive": "#1565c0",
    "arm": "#00796b",
    "modes": "#5e35b1",
    "aux": "#546e7a",
    "lights": "#ef6c00",
    "find": "#00838f",
    "vision": "#00838f",
}


def nice(name):
    tokens = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|[0-9]+", name)
    return " ".join(token[0].upper() + token[1:] for token in tokens)


class CommandLink(QObject):
    PORT = 8888
    online_changed = Signal(bool)
    reply = Signal(str, object)
    notice = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._online = False
        self._socket = QWebSocket(parent=self)
        self._socket.connected.connect(self._opened)
        self._socket.disconnected.connect(self._closed)
        self._socket.textMessageReceived.connect(self._received)
        self._socket.errorOccurred.connect(self._failed)

    @property
    def online(self):
        return self._online

    def open(self, host):
        self.close()
        self._socket.open(QUrl("ws://%s:%d" % (host, self.PORT)))

    def close(self):
        self._socket.close()

    def send(self, command):
        if not self._online:
            return False
        self._socket.sendTextMessage(command)
        return True

    def send_object(self, payload):
        return self.send(json.dumps(payload, ensure_ascii=False))

    def _opened(self):
        self._online = True
        self.online_changed.emit(True)

    def _closed(self):
        if self._online:
            self._online = False
            self.online_changed.emit(False)

    def _failed(self, _error):
        self._closed()
        self.notice.emit("control link error: %s" % self._socket.errorString())

    def _received(self, text):
        try:
            message = json.loads(text)
        except ValueError:
            self.notice.emit(text.strip())
            return
        if message.get("status") != "ok":
            self.notice.emit(str(message.get("data")))
            return
        self.reply.emit(message.get("title") or "", message.get("data"))


class VideoFeed(QObject):
    PORT = 5000
    frame = Signal(QImage)
    online_changed = Signal(bool)
    notice = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._net = QNetworkAccessManager(self)
        self._reply = None
        self._buffer = b""
        self._host = None
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.setInterval(2000)
        self._retry.timeout.connect(self._request)

    @property
    def online(self):
        return self._reply is not None

    def open(self, host):
        self.close()
        self._host = host
        self._request()

    def close(self):
        self._retry.stop()
        self._host = None
        self._drop()

    def _drop(self):
        reply, self._reply = self._reply, None
        self._buffer = b""
        if reply is None:
            return
        reply.abort()
        reply.deleteLater()
        self.online_changed.emit(False)

    def _request(self):
        if not self._host or self._reply is not None:
            return
        request = QNetworkRequest(QUrl("http://%s:%d/video_feed" % (self._host, self.PORT)))
        request.setRawHeader(b"Cache-Control", b"no-cache")
        reply = self._net.get(request)
        reply.setReadBufferSize(0)
        reply.readyRead.connect(self._read)
        reply.finished.connect(self._finished)
        self._reply = reply
        self.online_changed.emit(True)

    def _read(self):
        if self._reply is None:
            return
        data = self._reply.readAll().data()
        if not data:
            return
        self._buffer += data
        while True:
            head = self._buffer.find(b"\r\n\r\n")
            if head < 0:
                break
            tail = self._buffer.find(b"\xff\xd9", head + 4)
            if tail < 0:
                break
            jpeg = self._buffer[head + 4:tail + 2]
            self._buffer = self._buffer[tail + 2:]
            image = QImage.fromData(jpeg, "JPG")
            if not image.isNull():
                self.frame.emit(image)
        if len(self._buffer) > 1 << 20:
            self._buffer = self._buffer[-4096:]

    def _finished(self):
        reply, self._reply = self._reply, None
        if reply is None:
            return
        code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        if code is not None and int(code) != 200:
            self.notice.emit("video: HTTP %s, vision not running" % code)
        elif reply.error() != QNetworkReply.NoError:
            self.notice.emit("video: %s" % reply.errorString())
        else:
            self.notice.emit("video stream ended")
        reply.deleteLater()
        self.online_changed.emit(False)
        if self._host:
            self._retry.start()


class VideoView(QWidget):
    picked = Signal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = None
        self.setMinimumSize(620, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.CrossCursor)

    def show_frame(self, image):
        self._image = image
        self.update()

    def clear(self):
        self._image = None
        self.update()

    def _frame_rect(self):
        if self._image is None or self._image.isNull():
            return QRect()
        scale = min(self.width() / self._image.width(), self.height() / self._image.height())
        width = max(1, int(self._image.width() * scale))
        height = max(1, int(self._image.height() * scale))
        return QRect((self.width() - width) // 2, (self.height() - height) // 2, width, height)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if self._image is None:
            painter.setPen(QColor("#78909c"))
            painter.drawText(self.rect(), Qt.AlignCenter, "camera offline — connect to see the stream")
            return
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(self._frame_rect(), self._image)

    def mousePressEvent(self, event):
        rect = self._frame_rect()
        point = event.position().toPoint()
        if self._image is None or not rect.contains(point):
            return
        x = (point.x() - rect.x()) * self._image.width() // rect.width()
        y = (point.y() - rect.y()) * self._image.height() // rect.height()
        color = self._image.pixelColor(x, y)
        self.picked.emit(color.red(), color.green(), color.blue())


class RadarView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []
        self._sweep = 0.0
        self._scanning = False
        self._max = RADAR_MAX_CM
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._step)
        self.setMinimumSize(540, 310)

    @property
    def range_cm(self):
        return self._max

    def start(self):
        self._points = []
        self._sweep = 0.0
        self._max = RADAR_MAX_CM
        self._scanning = True
        self._timer.start()
        self.update()

    def finish(self, points):
        self._points = [(float(d), float(a)) for d, a in points]
        self._max = max([RADAR_MAX_CM] + [d for d, _ in self._points])
        self._scanning = False
        self._timer.stop()
        self.update()

    def _step(self):
        self._sweep = (self._sweep + 4.0) % 181.0
        self.update()

    def _center(self):
        return QPointF(self.width() / 2.0, self.height() - 34.0)

    def _radius(self):
        return max(60.0, min(self.width() / 2.0 - 58.0, self.height() - 74.0))

    def _at(self, distance, angle):
        center = self._center()
        radius = self._radius() * min(1.0, distance / self._max)
        rad = math.radians(angle)
        return QPointF(center.x() - radius * math.cos(rad), center.y() - radius * math.sin(rad))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0f1719"))
        center, radius = self._center(), self._radius()
        arc = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
        painter.setPen(QPen(QColor("#33565c"), 1.2))
        for fraction in (0.2, 0.4, 0.6, 0.8, 1.0):
            ring = QRectF(center.x() - radius * fraction, center.y() - radius * fraction,
                          radius * fraction * 2, radius * fraction * 2)
            painter.drawArc(ring, 0, 180 * 16)
        painter.setPen(QPen(QColor("#5d7d84"), 1.6))
        painter.drawArc(arc, 0, 180 * 16)
        painter.setPen(QPen(QColor("#2a4247"), 1))
        for degree in range(0, 181, 15):
            painter.drawLine(center, self._at(self._max, degree))
        painter.setPen(QColor("#8fb3ba"))
        for degree in (0, 15, 30, 60, 90, 120, 150, 180):
            point = self._at(self._max, degree)
            vector = point - center
            scale = (radius + 24) / max(1.0, radius)
            label = QPointF(center.x() + vector.x() * scale, center.y() + vector.y() * scale)
            painter.drawText(QRectF(label.x() - 18, label.y() - 9, 36, 18), Qt.AlignCenter, str(degree))
        painter.setPen(QColor("#6d949c"))
        for fraction in (0.2, 0.4, 0.6, 0.8, 1.0):
            painter.drawText(QRectF(center.x() + 9, center.y() - radius * fraction - 14, 46, 16),
                             Qt.AlignLeft, "%dcm" % round(self._max * fraction))
        painter.setPen(QPen(QColor("#1de9b6"), 1))
        painter.setBrush(QColor("#1de9b6"))
        painter.drawEllipse(center, 2.5, 2.5)
        if self._scanning:
            painter.setPen(QPen(QColor("#ffee58"), 1.4))
            painter.drawLine(center, self._at(self._max, self._sweep))
            font = painter.font()
            font.setPointSize(26)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#e0f7fa"))
            painter.drawText(self.rect().adjusted(0, 28, 0, 0), Qt.AlignHCenter | Qt.AlignTop, "SCAN")
        nearest = min(self._points, key=lambda item: item[0]) if self._points else None
        for distance, angle in self._points:
            ratio = distance / self._max
            color = QColor("#ff5252") if ratio < 0.33 else QColor("#ffb300") if ratio < 0.66 else QColor("#4dd0e1")
            painter.setPen(QPen(color.darker(130), 1))
            painter.setBrush(color)
            painter.drawEllipse(self._at(distance, angle), 3.4, 3.4)
        if nearest is not None:
            painter.setPen(QPen(QColor("#ffffff"), 1.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(self._at(nearest[0], nearest[1]), 7, 7)


class RadarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Radar scan — PiCar-Pro")
        self.resize(620, 430)
        self.setStyleSheet(STYLE)
        self._view = RadarView(self)
        self._status = QLabel("idle")
        self._status.setStyleSheet("color:#8fb3ba")
        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        row = QHBoxLayout()
        row.addWidget(self._status, 1)
        row.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self._view, 1)
        layout.addLayout(row)

    def start(self):
        self._status.setText("scanning… the robot pauses while the servo sweeps 180°")
        self._view.start()
        self.show()
        self.raise_()
        self.activateWindow()

    def finish(self, points):
        self._view.finish(points)
        if not points:
            self._status.setText("no echo within range")
            return
        nearest = min(points, key=lambda item: item[0])
        self._status.setText("%d points · nearest %.1f cm @ %.0f° · range %.0f cm"
                             % (len(points), nearest[0], nearest[1], self._view.range_cm))


class Client(QWidget):
    KEYS = {
        Qt.Key_Up: "forward 1",
        Qt.Key_Down: "backward 1",
        Qt.Key_Left: "left 1",
        Qt.Key_Right: "right 1",
    }

    def __init__(self, host=""):
        super().__init__()
        self.setWindowTitle("Adeept PiCar-Pro — App Client")
        self.resize(1340, 906)
        self.setMinimumSize(1200, 880)
        self.setStyleSheet(STYLE)
        mark = QPixmap(str(LOGO))
        if not mark.isNull():
            self.setWindowIcon(QIcon(mark))
        self._store = QSettings("Adeept", "PiCar-Pro Client")
        self._link = CommandLink(self)
        self._video = VideoFeed(self)
        self._modes = QButtonGroup(self)
        self._modes.setExclusive(False)
        self._light_modes = QButtonGroup(self)
        self._light_modes.setExclusive(True)
        self._active_mode = None
        self._suppress_modes = False
        self._held = set()
        self._radar = None
        self._rgb = QColor(str(self._store.value("lightColor", "#0288d1")))
        self._effect = "breath"
        self._build()
        self._wire()
        QApplication.instance().installEventFilter(self)
        if host:
            self._host.setText(host)
            self._toggle()

    def _box(self, title, layout, accent):
        box = QGroupBox(title)
        base = QColor(accent)
        box.setStyleSheet(BOX_STYLE.format(
            border=base.name(), title=base.lighter(150).name(), base=base.name(),
            hover=base.lighter(118).name(), press=base.darker(118).name(),
            checked=base.lighter(155).name()))
        box.setLayout(layout)
        return box

    def _hold(self, text, command, release, size=(64, 42)):
        button = QToolButton()
        button.setText(text)
        button.setToolTip(command)
        button.setMinimumSize(*size)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.pressed.connect(lambda: self._command(command))
        button.released.connect(lambda: self._command(release))
        return button

    def _brand(self):
        label = QLabel()
        label.setObjectName("brand")
        pixmap = QPixmap(str(LOGO))
        if not pixmap.isNull():
            label.setPixmap(pixmap.scaledToHeight(30, Qt.SmoothTransformation))
            label.setToolTip("Adeept PiCar-Pro")
        else:
            label.setText("Adeept")
        return label

    def _build(self):
        self._host = QLineEdit(str(self._store.value("host", "192.168.4.1")))
        self._host.setPlaceholderText("Robot Server IP")
        self._host.setFixedWidth(150)
        self._toggle_button = QPushButton("Connect")
        self._toggle_button.setFixedWidth(96)
        self._state = QLabel("offline")
        self._temp = QLabel("TEMP --")
        self._load = QLabel("LOAD --")
        self._ram = QLabel("RAM --")
        self._battery = QLabel("BATT --")
        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(self._brand())
        bar.addWidget(QLabel("Robot Server IP:"))
        bar.addWidget(self._host)
        bar.addWidget(self._toggle_button)
        bar.addWidget(self._state)
        bar.addStretch(1)
        for label in (self._temp, self._load, self._ram, self._battery):
            label.setStyleSheet("color:#4fc3f7;padding-left:10px")
            bar.addWidget(label)
        self._video_view = VideoView()
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(300)
        self._log.setFixedHeight(182)
        left = QVBoxLayout()
        left.setContentsMargins(9, 9, 9, 0)
        left.setSpacing(8)
        left.addWidget(self._drive_box())
        left.addWidget(self._arm_box())
        left.addWidget(self._mode_box())
        left.addWidget(self._aux_box())
        left.addWidget(self._light_box())
        left.addStretch(1)
        panel = QWidget()
        panel.setLayout(left)
        panel.setFixedWidth(372)
        vision = QHBoxLayout()
        vision.setSpacing(8)
        vision.addWidget(self._find_box(), 1)
        vision.addWidget(self._vision_box(), 1)
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(self._video_view, 1)
        right.addLayout(vision)
        right.addWidget(self._log)
        body = QHBoxLayout()
        body.addWidget(panel)
        body.addLayout(right, 1)
        root = QVBoxLayout(self)
        root.addLayout(bar)
        root.addLayout(body, 1)
        self._paint_state(False)

    def _drive_box(self):
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.addWidget(self._hold("Forward", "forward 1", "stop"), 0, 0, 1, 2)
        grid.addWidget(self._hold("Left", "left 1", "stop"), 1, 0)
        grid.addWidget(self._hold("Right", "right 1", "stop"), 1, 1)
        grid.addWidget(self._hold("Backward", "backward 1", "stop"), 2, 0, 1, 2)
        self._speed_label = QLabel("5")
        self._speed_label.setFixedWidth(22)
        self._speed = QSlider(Qt.Horizontal)
        self._speed.setRange(1, 10)
        self._speed.setValue(int(self._store.value("speed", 5)))
        self._speed_label.setText(str(self._speed.value()))
        self._speed.valueChanged.connect(self._speed_changed)
        row = QHBoxLayout()
        row.setContentsMargins(0, 10, 0, 0)
        row.addWidget(QLabel("Speed"))
        row.addWidget(self._speed, 1)
        row.addWidget(self._speed_label)
        grid.addLayout(row, 3, 0, 1, 2)
        return self._box("Drive", grid, ACCENTS["drive"])

    def _arm_box(self):
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        joints = (
            ("lookLeft", "lookRight", "lrStop"),
            ("armUp", "armDown", "armStop"),
            ("handUp", "handDown", "handStop"),
            ("grab", "loose", "glStop"),
        )
        for row, (left_cmd, right_cmd, stop) in enumerate(joints):
            grid.addWidget(self._hold(nice(left_cmd), left_cmd, stop, (150, 36)), row, 0)
            grid.addWidget(self._hold(nice(right_cmd), right_cmd, stop, (150, 36)), row, 1)
        return self._box("Arm / camera", grid, ACCENTS["arm"])

    def _mode_box(self):
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for index, command in enumerate(("automatic", "trackLine", "keepDistance",
                                         "speech", "motionGet")):
            button = QToolButton()
            button.setText(nice(command))
            button.setToolTip(command)
            button.setProperty("command", command)
            button.setCheckable(True)
            button.setMinimumHeight(34)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.toggled.connect(lambda on, cmd=command: self._mode_toggled(cmd, on))
            self._modes.addButton(button)
            if index == 4:
                grid.addWidget(button, 2, 0, 1, 2)
            else:
                grid.addWidget(button, index // 2, index % 2)
        return self._box("Modes", grid, ACCENTS["modes"])

    def _find_box(self):
        row = QHBoxLayout()
        row.setSpacing(5)
        self._find_toggle = QToolButton()
        self._find_toggle.setText("Find Color")
        self._find_toggle.setToolTip("findColor / stopCV")
        self._find_toggle.setCheckable(True)
        self._find_toggle.setMinimumHeight(34)
        self._find_toggle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._find_toggle.toggled.connect(self._find_toggled)
        self._find_rgb = QColor(str(self._store.value("findColor", "#e53935")))
        self._find_swatch = QToolButton()
        self._find_swatch.setFixedSize(38, 34)
        self._find_swatch.setToolTip("color to track")
        self._find_swatch.clicked.connect(self._pick_find_rgb)
        self._find_label = QLabel(self._find_rgb.name().upper())
        self._find_label.setStyleSheet("color:#8fb3ba")
        pick = QPushButton("RGB")
        pick.setFixedWidth(44)
        pick.clicked.connect(self._pick_find_rgb)
        row.addWidget(self._find_toggle, 1)
        row.addWidget(self._find_swatch)
        row.addWidget(self._find_label)
        row.addWidget(pick)
        self._refresh_find_swatch()
        return self._box("Find Color", row, ACCENTS["find"])

    def _aux_box(self):
        grid = QGridLayout()
        grid.setSpacing(4)
        for index in (1, 2, 3):
            toggle = QToolButton()
            toggle.setText("P%d" % index)
            toggle.setToolTip("Switch_%d_on / Switch_%d_off" % (index, index))
            toggle.setCheckable(True)
            toggle.setMinimumHeight(32)
            toggle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            toggle.toggled.connect(
                lambda on, n=index: self._command("Switch_%d_%s" % (n, "on" if on else "off")))
            grid.addWidget(toggle, 0, index - 1)
        home = QPushButton("Home")
        home.setToolTip("home")
        home.clicked.connect(lambda: self._command("home"))
        scan = QPushButton("Radar Scan")
        scan.setToolTip("scan")
        scan.clicked.connect(self._scan)
        self._buzzer = QToolButton()
        self._buzzer.setText("Buzzer Music")
        self._buzzer.setToolTip("Buzzer_Music / Buzzer_Music_Off")
        self._buzzer.setCheckable(True)
        self._buzzer.setMinimumHeight(32)
        self._buzzer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._buzzer.toggled.connect(self._buzzer_changed)
        grid.addWidget(home, 1, 0)
        grid.addWidget(scan, 1, 1)
        grid.addWidget(self._buzzer, 1, 2)
        return self._box("Auxiliary", grid, ACCENTS["aux"])

    def _light_box(self):
        grid = QGridLayout()
        grid.setSpacing(4)
        for index, effect in enumerate(("police", "rainbow", "flowing", "breath")):
            button = QToolButton()
            button.setText(nice(effect))
            button.setToolTip(effect)
            button.setCheckable(True)
            button.setMinimumHeight(30)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.toggled.connect(lambda on, name=effect: on and self._light_effect(name))
            self._light_modes.addButton(button)
            grid.addWidget(button, index // 2, index % 2)
        self._light_swatch = QToolButton()
        self._light_swatch.setFixedSize(38, 30)
        self._light_swatch.setToolTip("send RGB to flowing / breath")
        self._light_swatch.clicked.connect(self._pick_rgb)
        self._rgb_label = QLabel(self._rgb.name().upper())
        self._rgb_label.setStyleSheet("color:#8fb3ba")
        pick = QPushButton("RGB")
        pick.clicked.connect(self._pick_rgb)
        off = QPushButton("Police Off")
        off.setToolTip("policeOff")
        off.clicked.connect(self._light_off)
        grid.addWidget(self._light_swatch, 2, 0)
        grid.addWidget(self._rgb_label, 2, 1)
        grid.addWidget(pick, 2, 2)
        grid.addWidget(off, 3, 0, 1, 3)
        self._refresh_swatch()
        return self._box("WS2812 Lights", grid, ACCENTS["lights"])

    def _vision_box(self):
        row = QHBoxLayout()
        row.setSpacing(6)
        self._cvfl = QToolButton()
        self._cvfl.setText("CVFL")
        self._cvfl.setToolTip("CVFL / stop")
        self._cvfl.setCheckable(True)
        self._cvfl.setFixedWidth(72)
        self._cvfl.setMinimumHeight(30)
        self._cvfl.toggled.connect(self._cvfl_toggled)
        self._threshold = QSpinBox()
        self._threshold.setRange(0, 255)
        self._threshold.setFixedWidth(80)
        self._threshold.setValue(int(self._store.value("threshold", 80)))
        self._threshold.editingFinished.connect(
            lambda: self._command("CVFLSP %d" % self._threshold.value()))
        self._line_color = QComboBox()
        self._line_color.setFixedWidth(106)
        self._line_color.addItems(("White line", "Black line"))
        self._line_color.currentIndexChanged.connect(
            lambda index: self._command("CVFLColorSet %d" % (1 - index)))
        row.addWidget(self._cvfl)
        row.addWidget(QLabel("CVFLSP"))
        row.addWidget(self._threshold)
        row.addSpacing(10)
        row.addWidget(QLabel("CVFLColorSet"))
        row.addWidget(self._line_color)
        row.addStretch(1)
        return self._box("Line Follower", row, ACCENTS["vision"])

    def _wire(self):
        self._toggle_button.clicked.connect(self._toggle)
        self._link.online_changed.connect(self._paint_state)
        self._link.reply.connect(self._on_reply)
        self._link.notice.connect(self._log_line)
        self._video.frame.connect(self._video_view.show_frame)
        self._video.notice.connect(self._log_line)
        self._video_view.picked.connect(self._sample_color)
        self._poll = QTimer(self)
        self._poll.setInterval(3000)
        self._poll.timeout.connect(self._poll_info)

    def _toggle(self):
        if self._link.online:
            self._link.send("stop")
            self._poll.stop()
            self._link.close()
            self._video.close()
            self._video_view.clear()
            self._log_line("disconnected")
            return
        host = self._host.text().strip()
        if not host:
            self._log_line("enter the robot IP first")
            return
        self._store.setValue("host", host)
        self._log_line("connecting to %s" % host)
        self._link.open(host)
        self._video.open(host)
        self._poll.start()

    def _paint_state(self, online):
        self._state.setText("online" if online else "offline")
        self._state.setStyleSheet("color:%s;font-weight:600" % ("#66bb6a" if online else "#ef5350"))
        self._toggle_button.setText("Disconnect" if online else "Connect")
        if online:
            self._command("get_info", quiet=True)
            self._command("wsB %d" % self._speed.value(), quiet=True)

    def _command(self, text, quiet=False):
        if not self._link.send(text):
            return
        if not quiet:
            self._log_line("> " + text)

    def _speed_changed(self, value):
        self._speed_label.setText(str(value))
        self._store.setValue("speed", value)
        self._command("wsB %d" % value, quiet=True)

    def _clear_modes(self):
        self._suppress_modes = True
        for button in self._modes.buttons():
            button.setChecked(False)
        self._find_toggle.setChecked(False)
        self._cvfl.setChecked(False)
        self._suppress_modes = False
        self._active_mode = None

    def _start_mode(self, command):
        self._active_mode = command
        self._suppress_modes = True
        for button in self._modes.buttons():
            button.setChecked(button.property("command") == command)
        if command != "findColor":
            self._find_toggle.setChecked(False)
        if command != "CVFL":
            self._cvfl.setChecked(False)
        self._suppress_modes = False
        self._command(command)

    def _off_mode(self, command, stop):
        if self._active_mode == command:
            self._active_mode = None
            self._command(stop)

    def _mode_toggled(self, command, on):
        if self._suppress_modes:
            return
        if on:
            self._start_mode(command)
        else:
            self._off_mode(command, "stop")

    def _cvfl_toggled(self, on):
        if self._suppress_modes:
            return
        if on:
            self._start_mode("CVFL")
        else:
            self._off_mode("CVFL", "stop")

    def _find_toggled(self, on):
        if self._suppress_modes:
            return
        if on:
            self._send_find_color()
            self._start_mode("findColor")
        else:
            self._off_mode("findColor", "stopCV")

    def _stop_all(self):
        self._clear_modes()
        self._command("stop")

    def _light_effect(self, effect):
        self._effect = effect
        payload = {"lightMode": effect}
        if effect in ("flowing", "breath"):
            payload["data"] = [self._rgb.red(), self._rgb.green(), self._rgb.blue()]
        if self._link.send_object(payload):
            self._log_line("> %s %s" % (effect, self._rgb.name().upper()))

    def _light_off(self):
        self._light_modes.setExclusive(False)
        for button in self._light_modes.buttons():
            button.setChecked(False)
        self._light_modes.setExclusive(True)
        self._effect = "breath"
        self._command("policeOff")

    def _pick_rgb(self):
        color = QColorDialog.getColor(self._rgb, self, "Light RGB")
        if not color.isValid():
            return
        self._rgb = color
        self._store.setValue("lightColor", color.name())
        self._refresh_swatch()
        if self._effect in ("flowing", "breath"):
            self._light_effect(self._effect)

    def _refresh_swatch(self):
        self._light_swatch.setStyleSheet("background:%s;border:1px solid %s;border-radius:4px"
                                         % (self._rgb.name(), self._rgb.darker(140).name()))
        self._rgb_label.setText(self._rgb.name().upper())

    def _refresh_find_swatch(self):
        self._find_swatch.setStyleSheet("background:%s;border:1px solid %s;border-radius:4px"
                                        % (self._find_rgb.name(),
                                           self._find_rgb.darker(140).name()))
        self._find_label.setText(self._find_rgb.name().upper())

    def _send_find_color(self):
        red, green, blue = self._find_rgb.red(), self._find_rgb.green(), self._find_rgb.blue()
        if self._link.send_object({"title": "findColorSet", "data": [red, green, blue]}):
            self._log_line("> findColorSet %s" % self._find_rgb.name().upper())
        return [red, green, blue]

    def _toggle_find(self, on):
        if on:
            self._send_find_color()
            self._command("findColor")
        else:
            self._command("stopCV")

    def _pick_find_rgb(self):
        color = QColorDialog.getColor(self._find_rgb, self, "Find Color RGB")
        if not color.isValid():
            return
        self._find_rgb = color
        self._store.setValue("findColor", color.name())
        self._refresh_find_swatch()
        if self._find_toggle.isChecked():
            self._send_find_color()

    def _buzzer_changed(self, on):
        self._command("Buzzer_Music" if on else "Buzzer_Music_Off")

    def _scan(self):
        if not self._link.online:
            self._log_line("connect before scanning")
            return
        if self._radar is None:
            self._radar = RadarDialog(self)
        self._radar.start()
        self._log_line("scanning, the robot pauses while the radar sweeps...")
        self._command("scan")

    def _sample_color(self, red, green, blue):
        self._find_rgb = QColor(red, green, blue)
        self._store.setValue("findColor", self._find_rgb.name())
        self._refresh_find_swatch()
        self._link.send_object({"title": "findColorSet", "data": [red, green, blue]})
        self._log_line("color sampled %s" % self._find_rgb.name().upper())

    def _poll_info(self):
        if self._link.online:
            self._link.send("get_info")

    def _on_reply(self, title, data):
        if title == "get_info" and isinstance(data, list):
            self._show_info(data)
        elif title == "scanResult":
            self._show_scan(data or [])

    def _show_info(self, data):
        values = ["--"] * 4
        for index, value in enumerate(data[:4]):
            values[index] = "--" if value is None else value
        self._temp.setText("TEMP %s°C" % values[0])
        self._load.setText("LOAD %s%%" % values[1])
        self._ram.setText("RAM %s%%" % values[2])
        self._battery.setText("BATT %s%%" % values[3])

    def _show_scan(self, points):
        if self._radar is not None:
            self._radar.finish(points)
        if not points:
            self._log_line("scan: no echo in range")
            return
        nearest = min(points, key=lambda item: item[0])
        self._log_line("scan: %d points, nearest %.1f cm at %.0f°"
                       % (len(points), nearest[0], nearest[1]))

    def _log_line(self, text):
        self._log.appendPlainText(text)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.KeyPress, QEvent.KeyRelease):
            focus = QApplication.focusWidget()
            if not isinstance(focus, (QLineEdit, QSpinBox, QComboBox, QPlainTextEdit)):
                if event.key() == Qt.Key_Escape and event.type() == QEvent.KeyPress:
                    self._stop_all()
                    return True
                if event.key() in self.KEYS:
                    self._drive_key(event.key(), event)
                    return True
        return super().eventFilter(watched, event)

    def _drive_key(self, key, event):
        if event.isAutoRepeat():
            return
        if event.type() == QEvent.KeyPress:
            self._held.add(key)
            self._command(self.KEYS[key], quiet=True)
            return
        self._held.discard(key)
        if not self._held:
            self._command("stop", quiet=True)

    def shutdown(self):
        if self._link.online:
            self._link.send("stop")
        self._poll.stop()
        self._link.close()
        self._video.close()

    def closeEvent(self, event):
        self.shutdown()
        if self._radar is not None:
            self._radar.close()
        super().closeEvent(event)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Adeept PiCar-Pro app-mode desktop client")
    parser.add_argument("--host", default="192.168.4.1", help="Robot Server IP, connect immediately")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    window = Client(args.host)

    def _quit(*_):
        window.shutdown()
        app.quit()

    signal.signal(signal.SIGINT, _quit)
    pulse = QTimer()
    pulse.timeout.connect(lambda: None)
    pulse.start(200)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
