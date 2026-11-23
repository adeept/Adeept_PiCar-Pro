#!/usr/bin/env python3
# File name   : Robot.py
# Website     : www.Adeept.com
# Author      : Adeept
import logging
import os
import subprocess
import threading
import time
import numpy as np
import sherpa_onnx
import yaml

from Hardware import LineTracking, Ultrasonic
from Hardware.BatteryMonitor import BatteryMonitor
from Hardware.Buzzer import Buzzer
from Hardware.LED import OnBoardLED
from Hardware.Motor import MotorBank
from Hardware.MPU6050 import MPU6050
from Hardware.OLED import OLED
from Hardware.pca9685 import PCA9685
from Hardware.SystemInfo import SystemInfo
from Hardware.WS2812 import WS2812
from Motion.calibration import ServoCalibration
from Motion.servo_bank import ServoBank

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_SERVER_DIR, "runtime.yml"), encoding="utf-8") as _f:
    _RUNTIME_CFG = yaml.safe_load(_f) or {}
_SPEECH_CFG = _RUNTIME_CFG.get("speech") or {}
_MOTOR_CFG = _RUNTIME_CFG.get("motor") or {}
_JOG_CFG = _RUNTIME_CFG.get("jog") or {}


def _motor_number(value):
    """Accept 1, "1", "M1" and return the integer motor number."""
    text = str(value).strip().upper()
    if text.startswith("M"):
        text = text[1:]
    return int(text)

logger = logging.getLogger(__name__)
__all__ = ["Robot"]


class Robot:
    # PCA9685
    PCA_BUS, PCA_ADDRESS, PWM_FREQ = 1, 0x5F, 50
    # Rear drive motors: enabled list and direction fix come from runtime.yml
    MOTOR_NUMBERS = tuple(_motor_number(n) for n in (_MOTOR_CFG.get("enabled") or (1, 2)))
    MOTOR_DIRECTION = {_motor_number(k): int(v) for k, v in (_MOTOR_CFG.get("direction") or {}).items()}
    # Front Ackermann steering servo
    STEER_CHANNEL = 0
    STEER_DURATION, STEER_SETTLE = 0.12, 0.05
    STEER_LIMIT = 45.0
    STEER_MAX_VEL, STEER_MAX_ACC = 600.0, 15000.0

    # Driving
    DEFAULT_SPEED, TURN_ANGLE = 50, 30.0

    # Arm joints
    ARM_CHANNELS = (1, 2, 3, 4)
    ARM_MAX_VEL, ARM_MAX_ACC = 120.0, 800.0
    # Press-and-hold joint jog: degrees per step and step period
    JOG_STEP = float(_JOG_CFG.get("step", 3.0))
    JOG_PERIOD = float(_JOG_CFG.get("period", 0.05))

    # Servo ticker and indicator LEDs
    TICK = 0.01
    LED_LEFT, LED_RIGHT = 3, 2

    # Buzzer startup chime
    STARTUP_BEEP = [["C5", 0.12]]
    # WS2812 startup breathing
    WS2812_BREATH = (0, 80, 255)
    # Obstacle avoidance
    AVOID_SPEED, AVOID_SLOW_SPEED = 35, 20
    AVOID_CLEAR_CM, AVOID_SLOW_CM = 60.0, 35.0
    AVOID_TURN, AVOID_REVERSE_TICKS, AVOID_TURN_TICKS = 35.0, 4, 8
    # Keep_distance / follow
    FOLLOW_SPEED, FOLLOW_MIN_CM, FOLLOW_MAX_CM, FOLLOW_DEADBAND = 25, 25.0, 40.0, 5.0
    # Line tracking
    LINE_SPEED, LINE_TURN = 20, 28.0
    # Background mode tick
    MODE_TICK = 0.15

    # Speech recognition
    SPEECH_RATE, SPEECH_CHUNK = 16000, 0.2
    SPEECH_DEVICE = _SPEECH_CFG.get("device", "")
    SPEECH_MODEL = os.path.join(_ROOT, _SPEECH_CFG.get("model", ""))
    SPEECH_TOKENS = _SPEECH_CFG.get("tokens", "")
    SPEECH_ENCODER = _SPEECH_CFG.get("encoder", "")
    SPEECH_DECODER = _SPEECH_CFG.get("decoder", "")
    SPEECH_JOINER = _SPEECH_CFG.get("joiner", "")
    SPEECH_MAP = _SPEECH_CFG.get("commands") or {}
    # Voice-driven arm steps (ch1 pan, ch2 arm, ch3 hand, ch4 grip)
    VOICE_PAN_JOINT, VOICE_ARM_JOINT, VOICE_HAND_JOINT, VOICE_GRIP_JOINT = 1, 2, 3, 4
    VOICE_STEP, VOICE_GRIP_STEP = 45.0, 45.0
    
    # Vision tracking
    VISION_TICK, VISION_TIMEOUT = 0.1, 0.2
    VISION_SPEED, VISION_TURN, VISION_DEADBAND = 22, 30.0, 0.06

    # Radar scan (pan servo + ultrasonic)
    SCAN_CHANNEL = 1
    SCAN_LIMIT = 90.0
    SCAN_STEP = 2.0
    SCAN_SETTLE = 0.8
    SCAN_POINT_DELAY = 0.02
    SCAN_MAX_CM = 100.0

    # OLED status
    OLED_TITLE = "Adeept PiCar Pro V2"
    STATUS_TICK, NETWORK_TICK = 1.0, 60.0
    MODE_LABELS = {"drive": "DRIVE", "arm": "ARM", "avoid": "AVOID", "line": "LINE",
                   "follow": "FOLLOW", "speech": "VOICE", "vision_line": "VIS LINE",
                   "vision_color": "VIS COLOR", "vision_motion": "VIS MOTION"}
    
    # Mode names
    VISION_MODES = ("vision_line", "vision_color", "vision_motion")
    AUTO_MODES = ("avoid", "line", "follow") + VISION_MODES

    def __init__(self, cal_path=None, vision=None):
        # Runtime state
        self._lock = threading.RLock()
        self._oled_lock = threading.Lock()
        self._oled_lines = None
        self._network = ("Offline", "-")
        self._network_at = 0.0
        self._status_stop = self._status_thread = None
        self._closed = False
        self._speed = float(self.DEFAULT_SPEED)
        self._direction = 0
        self._steer_offset = 0.0
        self._indicator = "off"
        self._mode = "drive"
        self._mode_stop = self._mode_thread = None
        self._avoid_phase = self._avoid_ticks = 0
        self._avoid_side = 1
        # Press-and-hold joint jog
        self._jog_stop = self._jog_thread = None
        self._jog_channel = None
        # Speech
        self._speech_model = self.SPEECH_MODEL
        self._speech_device = self.SPEECH_DEVICE
        self._recognizer = self._speech_stream = self._speech_proc = None
        # Vision
        self._vision = vision
        self._vision_seq = self._vision_width = 0
        # PCA9685, motors and servo bank
        self._pca = PCA9685(bus_num=self.PCA_BUS, address=self.PCA_ADDRESS, freq=self.PWM_FREQ)
        self._motors = MotorBank(self._pca, motors=self.MOTOR_NUMBERS,
                                 directions=self.MOTOR_DIRECTION)
        count = max(self.ARM_CHANNELS) + 1
        cal = ServoCalibration.load(path=cal_path, count=count)
        config = cal.to_config()
        config[self.STEER_CHANNEL].update(max_vel=self.STEER_MAX_VEL, max_acc=self.STEER_MAX_ACC)
        for channel in self.ARM_CHANNELS:
            config[channel].update(max_vel=self.ARM_MAX_VEL, max_acc=self.ARM_MAX_ACC)
        self._bank = ServoBank(pca=self._pca, count=count, config=config)
        joint = self._bank.joints[self.STEER_CHANNEL]
        self._steer_center, self._steer_dir = joint.neutral, joint.direction
        self._steer_limit = min(self.STEER_LIMIT, joint.neutral - joint.min_angle, joint.max_angle - joint.neutral)
        self._bank.jump_all({ch: j.neutral for ch, j in enumerate(self._bank.joints)})
        # Servo ticker
        self._ticker_stop = threading.Event()
        self._ticker = threading.Thread(target=self._tick_loop, name="robot-servo-tick", daemon=True)
        self._ticker.start()
        # Indicator LEDs, sensors and peripherals
        self._leds = OnBoardLED()
        self._ultra = Ultrasonic()
        self._line = LineTracking()
        self._battery = BatteryMonitor()
        self._buzzer = Buzzer()
        self._mpu6050 = MPU6050()
        self._oled = OLED()
        self._system_info = SystemInfo()
        self._ws2812 = WS2812(bright=128)

        self._ws2812.start()
        self._ws2812.start_breath(*self.WS2812_BREATH)

        self._buzzer.play(self.STARTUP_BEEP)

        self._oled_status()

        self._status_stop = threading.Event()
        self._status_thread = threading.Thread(target=self._status_loop, args=(self._status_stop,), name="robot-status", daemon=True)
        self._status_thread.start()

    def _network_status(self):
        try:
            config = subprocess.run(["ifconfig", "wlan0"], capture_output=True, text=True, timeout=0.5)
            ip = next((line.split()[1] for line in config.stdout.splitlines()
                       if line.strip().startswith("inet ") and len(line.split()) > 1), "")
            link = subprocess.run(["iw", "dev", "wlan0", "link"],
                                  capture_output=True, text=True, timeout=0.5)
            mode = "Station Mode" if "Connected" in link.stdout else "AP Mode"
        except Exception:
            mode = "" 
            ip = ""
        return mode, ip

    def _battery_text(self):
        try:
            return "%.0f%%" % self._battery.read().percent
        except Exception:
            return "--"

    def _oled_status(self):
        if self._oled is None:
            return
        now = time.monotonic()
        if now - self._network_at >= self.NETWORK_TICK:
            self._network = self._network_status()
            self._network_at = now
        net, ip = self._network
        mode = self.MODE_LABELS.get(self._mode, self._mode)
        lines = [self.OLED_TITLE, "NET: " + net, "IP: " + ip, "BAT: " + self._battery_text(), "", "MODE: " + mode]
        if lines != self._oled_lines:
            with self._oled_lock:
                try:
                    self._oled.show_lines(lines, font_size=10, line_height=10)
                    self._oled_lines = lines
                except Exception as exc:
                    logger.warning("OLED status failed: %s", exc)

    def _status_loop(self, stop):
        while not stop.wait(self.STATUS_TICK):
            self._oled_status()

    def _tick_loop(self):
        stop, period, last = self._ticker_stop, self.TICK, time.monotonic()
        while not stop.is_set():
            now = time.monotonic()
            with self._lock:
                try:
                    self._bank.update(now - last)
                except Exception as exc:
                    logger.error("servo tick failed: %s", exc)
                    return
            last = now
            stop.wait(max(0.0, period - (time.monotonic() - now)))

    def _stop_ticker(self):
        stop, self._ticker_stop = self._ticker_stop, None
        if stop is not None:
            stop.set()
        thread, self._ticker = self._ticker, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)

    def _stop_status(self):
        stop, self._status_stop = self._status_stop, None
        if stop is not None:
            stop.set()
        thread, self._status_thread = self._status_thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("Robot is closed")

    def drive(self, speed=None, direction=1, motor_no=None):
        """Drive motors: speed 0..100 (None = set_speed), direction, motor_no (None = all)."""
        self._ensure_open()
        auto = self._mode in self.AUTO_MODES
        self._stop_mode()
        if auto:
            with self._lock:
                self._center_all()
        with self._lock:
            self._direction = -1 if direction < 0 else 1
            self._apply_throttle(speed, motor_no)
            self._set_lamps("off")

    def _apply_throttle(self, speed=None, motor_no=None):
        speed = self._speed if speed is None else speed
        self._motors.drive(speed, self._direction, motor_no)

    def _drive_at(self, speed, direction):
        """Drive at a mode speed without touching the user's set_speed()."""
        with self._lock:
            self._direction = -1 if direction < 0 else 1
            self._apply_throttle(speed)

    def _coast(self):
        with self._lock:
            self._direction = 0
            self._apply_throttle()

    def forward(self):
        self.drive(self._speed, 1)

    def backward(self):
        self.drive(self._speed, -1)

    def stop(self):
        auto = self._mode in self.AUTO_MODES
        self._stop_mode()
        with self._lock:
            self._direction = 0
            self._apply_throttle()
            self._set_lamps("off")
            if auto:
                self._center_all()

    def set_speed(self, speed):
        speed = max(0.0, min(100.0, float(speed)))
        with self._lock:
            self._speed = speed
            self._apply_throttle()

    def halt(self):
        """stop() plus every servo back to its calibrated neutral."""
        auto = self._mode in self.AUTO_MODES
        self.stop()
        if not auto:
            with self._lock:
                self._center_all()

    def _center_all(self):
        for channel, joint in enumerate(self._bank.joints):
            self._bank.move_to(channel, joint.neutral)
        self._steer_offset = 0.0

    def steer(self, offset, settle=True, duration=None):
        self._ensure_open()
        offset = max(-self._steer_limit, min(self._steer_limit, float(offset)))
        if abs(offset - self._steer_offset) < 0.5:
            return offset
        duration = self.STEER_DURATION if duration is None else max(0.0, float(duration))
        with self._lock:
            self._steer_offset = offset
            self._bank.move_to(self.STEER_CHANNEL, self._steer_center + offset * self._steer_dir, duration=duration)
        if settle:
            time.sleep(self.STEER_SETTLE)
        return offset

    def turn_left(self):
        self.stop()
        self.steer(-self.TURN_ANGLE)
        self.forward()
        self.set_indicator("left")

    def turn_right(self):
        self.stop()
        self.steer(self.TURN_ANGLE)
        self.forward()
        self.set_indicator("right")

    def move_joint(self, channel, angle, duration=None):
        if channel not in self.ARM_CHANNELS:
            raise ValueError("arm channel must be one of %s" % (self.ARM_CHANNELS,))
        self._ensure_open()
        if self._mode != "arm":
            self.stop()
            self._mode = "arm"
            self._oled_status()
        with self._lock:
            self._bank.move_to(channel, angle, duration=duration)

    def jog_joint(self, channel, direction):
        if channel not in self.ARM_CHANNELS:
            raise ValueError("arm channel must be one of %s" % (self.ARM_CHANNELS,))
        self._ensure_open()
        self.jog_stop()
        direction = 1.0 if direction >= 0 else -1.0
        if self._mode != "arm":
            self.stop()
            self._mode = "arm"
            self._oled_status()
        self._jog_channel = channel
        self._jog_stop = threading.Event()
        self._jog_thread = threading.Thread(
            target=self._jog_loop, args=(channel, direction),
            name="robot-jog-ch%d" % channel, daemon=True)
        self._jog_thread.start()

    def _jog_loop(self, channel, direction):
        stop, period, step = self._jog_stop, self.JOG_PERIOD, self.JOG_STEP
        while not stop.wait(period):
            with self._lock:
                joint = self._bank.joints[channel]
                target = joint.angle if joint.target is None else joint.target
                self._bank.move_to(channel, target + direction * step)

    def jog_stop(self):
        """Hold every jogging joint at its current angle."""
        stop, self._jog_stop = self._jog_stop, None
        thread, self._jog_thread = self._jog_thread, None
        if stop is not None:
            stop.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.3)
        if self._jog_channel is not None:
            with self._lock:
                self._bank.joints[self._jog_channel].stop()
            self._jog_channel = None

    def set_indicator(self, mode):
        """Steady left/right/off, no blink."""
        if mode not in ("left", "right", "off"):
            raise ValueError("indicator mode must be left/right/off")
        with self._lock:
            self._set_lamps(mode)

    def set_switch(self, port, status):
        """Auxiliary output switch 1/2/3: status 1 = ON, 0 = OFF."""
        with self._lock:
            if self._leds is not None:
                self._leds.set_led(int(port), int(status))

    def _set_lamps(self, mode):
        self._indicator = mode
        if self._leds is None:
            return
        try:
            self._leds.set_led(self.LED_LEFT, mode == "left")
            self._leds.set_led(self.LED_RIGHT, mode == "right")
        except Exception:
            pass

    @property
    def battery(self):
        return self._battery

    @property
    def buzzer(self):
        return self._buzzer

    @property
    def mpu6050(self):
        return self._mpu6050

    @property
    def oled(self):
        return self._oled

    @property
    def system_info(self):
        return self._system_info

    @property
    def ws2812(self):
        return self._ws2812

    @property
    def mode(self):
        """drive / arm / avoid / line / follow / speech / vision_line / vision_color / vision_motion."""
        return self._mode

    def automatic(self):
        self._start_mode("avoid", self._avoid_step)

    def track_line(self):
        self._start_mode("line", self._line_step)

    def keep_distance(self):
        self._start_mode("follow", self._follow_step)

    def vision_line(self):
        self._start_mode("vision_line", self._vision_line_step, self.VISION_TICK, vision_mode="findline")

    def vision_color(self):
        self._start_mode("vision_color", self._vision_color_step, self.VISION_TICK, vision_mode="findColor")

    def vision_motion(self):
        """Chase the largest moving object (Vision "watchDog")."""
        self._start_mode("vision_motion", self._vision_motion_step, self.VISION_TICK, vision_mode="watchDog")

    def radar_scan(self):
        """Pan the scan servo side to side and measure ultrasonic distance.

        Returns a list of [distance_cm, heading_deg] for every in-range hit.
        Heading 90 deg is straight ahead; 0/180 are the left/right extremes.
        """
        self._ensure_open()
        self._stop_mode()
        servo = self._bank.joints[self.SCAN_CHANNEL]
        half = min(self.SCAN_LIMIT, servo.neutral - servo.min_angle, servo.max_angle - servo.neutral)
        result = []

        with self._lock:
            self._center_all()
            self._coast()
        time.sleep(self.SCAN_SETTLE)

        offset = half
        while offset > -half:
            offset -= self.SCAN_STEP
            offset = max(-half, offset)
            with self._lock:
                self._bank.move_to(self.SCAN_CHANNEL, servo.to_absolute(offset))
            time.sleep(self.SCAN_POINT_DELAY)
            try:
                dist = self._ultra.get_distance()
            except Exception as exc:
                dist = 0.0
            if dist <= self.SCAN_MAX_CM:
                heading = 90.0 + servo.direction * offset
                result.append([round(dist, 2), round(heading, 1)])

        with self._lock:
            self._bank.move_to(self.SCAN_CHANNEL, servo.neutral)
        return result

    def _vision_result(self):
        seq, result = self._vision.wait_result(self._vision_seq, self.VISION_TIMEOUT)
        if result is None:
            return None
        self._vision_seq = seq
        return result

    def _vision_drive(self, error):
        offset = 0.0 if abs(error) < self.VISION_DEADBAND else error * self.VISION_TURN
        self.steer(offset, settle=False)
        self._drive_at(self.VISION_SPEED, 1)

    def _vision_line_step(self):
        result = self._vision_result()
        if result is None:
            self._coast()
        elif result.line_found:
            self._vision_drive(result.line_error)
        else:
            self._coast()

    def _vision_color_step(self):
        result = self._vision_result()
        if result is None:
            self._coast()
        elif result.color_detected:
            self._vision_drive(result.color_error_x)
        else:
            self._coast()

    def _vision_motion_step(self):
        result = self._vision_result()
        if result is None or not result.motion_detected or result.motion_rect is None:
            self._coast()
            return
        x, _, w, _ = result.motion_rect
        half = self._vision_width / 2.0
        self._vision_drive((x + w / 2.0 - half) / half)

    def speech(self):
        self._start_mode("speech", self._speech_step, 0.0)

    def _speech_open(self):
        model = self._speech_model
        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=os.path.join(model, self.SPEECH_TOKENS),
            encoder=os.path.join(model, self.SPEECH_ENCODER),
            decoder=os.path.join(model, self.SPEECH_DECODER),
            joiner=os.path.join(model, self.SPEECH_JOINER),
            num_threads=1, sample_rate=self.SPEECH_RATE, feature_dim=80,
            enable_endpoint_detection=True, rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=1.2, rule3_min_utterance_length=300, provider="cpu")
        self._speech_stream = self._recognizer.create_stream()
        self._speech_proc = subprocess.Popen(
            ["arecord", "-D", self._speech_device, "-f", "S16_LE", "-r", str(self.SPEECH_RATE),
             "-c", "1", "-t", "raw", "-q", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=int(self.SPEECH_RATE * self.SPEECH_CHUNK) * 2)

    def _speech_step(self):
        if self._recognizer is None:
            self._speech_open()
        chunk = int(self.SPEECH_RATE * self.SPEECH_CHUNK)
        data = self._speech_proc.stdout.read(chunk * 2)
        if not data:
            raise RuntimeError("microphone stream ended")
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        self._speech_stream.accept_waveform(self.SPEECH_RATE, samples)
        while self._recognizer.is_ready(self._speech_stream):
            self._recognizer.decode_stream(self._speech_stream)
        if not self._recognizer.is_endpoint(self._speech_stream):
            return
        text = self._recognizer.get_result(self._speech_stream)
        self._recognizer.reset(self._speech_stream)
        command = self.SPEECH_MAP.get((text or "").strip().upper())
        if command:
            self._voice_command(command)

    def _voice_command(self, command):
        if command == "stop":
            self._coast()
            with self._lock:
                self._set_lamps("off")
        elif command in ("forward", "backward"):
            self._drive_at(self._speed, 1 if command == "forward" else -1)
            with self._lock:
                self._set_lamps("off")
        elif command in ("left", "right"):
            self._nudge_joint(self.VOICE_PAN_JOINT,
                              -self.VOICE_STEP if command == "left" else self.VOICE_STEP)
        elif command in ("armup", "armdown", "handup", "handdown"):
            joint = self.VOICE_ARM_JOINT if command.startswith("arm") else self.VOICE_HAND_JOINT
            self._nudge_joint(joint, self.VOICE_STEP if command.endswith("up") else -self.VOICE_STEP)
        elif command in ("grab", "loose"):
            self._nudge_joint(self.VOICE_GRIP_JOINT,
                              -self.VOICE_GRIP_STEP if command == "grab" else self.VOICE_GRIP_STEP)
        elif command == "home":
            self._coast()
            with self._lock:
                self._set_lamps("off")
                self._center_all()

    def _nudge_joint(self, channel, delta):
        joint = self._bank.joints[channel]
        target = joint.angle if joint.target is None else joint.target
        with self._lock:
            self._bank.move_to(channel, target + delta)

    def _speech_close(self):
        proc, self._speech_proc = self._speech_proc, None
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except Exception:
                pass
        self._recognizer = self._speech_stream = None

    def _start_mode(self, mode, step, period=None, vision_mode=None):
        self._ensure_open()
        self._stop_mode()
        if vision_mode is not None:
            self._vision.start()
            self._vision.set_mode(vision_mode)
            self._vision_width = self._vision.system().width
            self._vision_seq = self._vision.result_seq()
        with self._lock:
            self._direction = 0
            self._apply_throttle()
            self._set_lamps("off")
            self._center_all()
        self._avoid_phase = self._avoid_ticks = 0
        self._mode = mode
        self._mode_stop = threading.Event()
        self._mode_thread = threading.Thread(target=self._mode_loop, args=(step, self._mode_stop, period),
                                             name="robot-" + mode, daemon=True)
        self._mode_thread.start()
        self._oled_status()

    def _stop_mode(self):
        previous = self._mode
        was_vision = self._mode in self.VISION_MODES
        stop, thread = self._mode_stop, self._mode_thread
        self._mode_stop = self._mode_thread = None
        self._mode = "drive"
        if stop is not None:
            stop.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        if was_vision and self._vision is not None and self._vision.is_running():
            self._vision.set_mode("none")
        self._speech_close()
        if previous != "drive":
            self._oled_status()

    def _mode_loop(self, step, stop, period):
        while not stop.is_set():
            try:
                step()
            except Exception as exc:
                if not stop.is_set():
                    logger.error("%s failed: %s", step.__name__, exc)
                return
            stop.wait(self.MODE_TICK if period is None else period)

    def _avoid_step(self):
        """Cruise, slow down near an obstacle, then back off and turn away."""
        if self._avoid_phase == 1:
            self._avoid_ticks += 1
            if self._avoid_ticks >= self.AVOID_REVERSE_TICKS:
                self._avoid_phase, self._avoid_ticks = 2, 0
                self._drive_at(self.AVOID_SPEED, 1)
            return
        if self._avoid_phase == 2:
            self._avoid_ticks += 1
            if self._avoid_ticks >= self.AVOID_TURN_TICKS:
                self._avoid_phase, self._avoid_ticks = 0, 0
                self.steer(0.0, settle=False)
            return
        dist = self._ultra.get_distance()
        if dist > self.AVOID_CLEAR_CM:
            self.steer(0.0, settle=False)
            self._drive_at(self.AVOID_SPEED, 1)
        elif dist > self.AVOID_SLOW_CM:
            self._drive_at(self.AVOID_SLOW_SPEED, 1)
        else:
            self._avoid_side = -self._avoid_side
            self.steer(self._avoid_side * self.AVOID_TURN, settle=False)
            self._drive_at(self.AVOID_SLOW_SPEED, -1)
            self._avoid_phase, self._avoid_ticks = 1, 0

    def _line_step(self):
        """1 = white, 0 = black: steer toward the sensor that still sees the line."""
        left, middle, right = self._line.read()
        if middle == 0:
            offset = 0.0 if left == right else (-self.LINE_TURN if left == 0 else self.LINE_TURN)
        elif left == 0 and right == 1:
            offset = -self.LINE_TURN
        elif left == 1 and right == 0:
            offset = self.LINE_TURN
        elif left == 0 and right == 0:
            offset = 0.0
        else:
            offset = self._steer_offset      
        self.steer(offset, settle=False)
        self._drive_at(self.LINE_SPEED, 1)

    def _follow_step(self):
        """Keep 25..40 cm behind the object in front, deadband avoids hunting."""
        dist = self._ultra.get_distance()
        if dist > self.FOLLOW_MAX_CM + self.FOLLOW_DEADBAND:
            self._drive_at(self.FOLLOW_SPEED, 1)
        elif dist < self.FOLLOW_MIN_CM - self.FOLLOW_DEADBAND:
            self._drive_at(self.FOLLOW_SPEED, -1)
        else:
            self._coast()

    def close(self):
        if self._closed:
            return
        self._stop_status()
        self._stop_mode()
        self.jog_stop()
        self._closed = True
        self._stop_ticker()
        with self._lock:
            self._set_lamps("off")
            self._motors.close()
            self._bank.close()
            if self._leds is not None:
                self._leds.close()
                self._leds = None
            if self._ultra is not None:
                self._ultra.close()
            if self._line is not None:
                self._line.close()
            self._ultra = self._line = None
            for device in (self._battery, self._buzzer, self._mpu6050, self._oled, self._ws2812):
                if device is not None:
                    device.close()
            self._battery = self._buzzer = self._mpu6050 = self._oled = None
            self._system_info = self._ws2812 = None
            self._pca.deinit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    with Robot() as robot:
        try:
            robot.set_speed(35)
            robot.forward(); time.sleep(1.5)
            robot.backward(); time.sleep(1.5)
            robot.set_speed(50)
            robot.turn_left(); time.sleep(1.2)
            robot.forward(); time.sleep(1.2)
            robot.turn_right(); time.sleep(1.2)
            robot.stop(); time.sleep(0.5)

            robot.set_indicator("left"); time.sleep(0.8)
            robot.set_indicator("right"); time.sleep(0.8)
            robot.set_indicator("off")

            robot.steer(-25); time.sleep(0.3)
            robot.steer(25); time.sleep(0.3)
            robot.steer(0); time.sleep(0.3)
            robot.halt()

            for channel in robot.ARM_CHANNELS:
                robot.move_joint(channel, 45); time.sleep(0.9)
                robot.move_joint(channel, 135, duration=0.4); time.sleep(0.5)
                robot.move_joint(channel, 90); time.sleep(0.9)

            robot.automatic(); time.sleep(4)
            robot.stop(); time.sleep(0.5)
            robot.forward(); time.sleep(1)
            robot.stop(); time.sleep(0.5)

            robot.track_line(); time.sleep(4)
            robot.stop(); time.sleep(0.5)

            robot.keep_distance(); time.sleep(4)
            robot.halt()
        except KeyboardInterrupt:
            pass
        finally:
            robot.halt()
