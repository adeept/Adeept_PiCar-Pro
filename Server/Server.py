#!/usr/bin/env python3
# File name   : Server.py
# Website     : www.Adeept.com
# Author      : Adeept
"""Single WebSocket control server for the app and web profiles.
"""
import argparse
import asyncio
import json
import logging
import os
import threading
import yaml
from websockets.asyncio.server import serve
from Robot import Robot

_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger(__name__)
__all__ = ["ControlRouter", "main"]

def load_config(path=None):
    path = path or os.path.join(_SERVER_DIR, "runtime.yml")
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}

def _number(value, default=None):
    if value is None:
        return default
    return float(value)


class ControlRouter:
    """Translate the configured command table into Robot calls."""

    def __init__(self, robot, vision, mode, profile, defaults=None):
        self.robot = robot
        self.vision = vision
        self.profile = profile
        self.defaults = defaults or {}
        self.commands = {k.lower(): v for k, v in (self.defaults.get("commands") or {}).items()}
        self.commands.update({k.lower(): v for k, v in (profile.get("commands") or {}).items()})
        self.dict_commands = dict((self.defaults.get("dict") or {}))
        self.dict_commands.update(profile.get("dict") or {})
        self.speed_scale = float(profile.get("speed_scale", 1))
        self.steer_trim = float(profile.get("steer_trim", 0))
        self.line_pos_scale = float(profile.get("line_pos_scale", 1))
        self._line_positions = [0.0, 0.0]
        self._music_thread = None
        self.mode = mode

    def handle(self, raw):
        logger.info("incoming command: %s", raw)
        message = raw
        if isinstance(raw, str):
            try:
                message = json.loads(raw)
            except ValueError:
                message = raw
        if isinstance(message, dict):
            response = self._handle_dict(message)
        elif not isinstance(message, str):
            response = self._error("message must be text or object")
        else:
            response = self._handle_text(message)
        logger.info("response: %s", response)
        return response

    def _handle_text(self, text):
        parts = text.strip().split()
        if not parts:
            return self._error("empty command")
        name, args = parts[0].lower(), parts[1:]
        spec = self.commands.get(name)
        if spec is None:
            return self._error("unknown command: %s" % name)
        expected = spec.get("args")
        if expected is not None and len(args) != int(expected):
            return self._error("%s expects %s argument(s)" % (name, expected))
        return self._dispatch(spec, args, {"command": name})

    def _handle_dict(self, message):
        title = message.get("title")
        spec = self.dict_commands.get(title) if title else None
        if spec is None and message.get("lightMode"):
            spec = self.dict_commands.get("lightMode")
        if spec is None:
            return self._error("unknown object message")
        return self._dispatch(spec, [], message)

    def _dispatch(self, spec, args, message):
        action = spec.get("action")
        logger.info("dispatch action=%s args=%s message=%s", action, args, message)
        method = getattr(self, "_action_" + str(action), None)
        if method is None:
            return self._error("unsupported action: %s" % action)
        try:
            data, title = method(spec, args, message)
            return {"status": "ok", "title": title or "", "data": data}
        except Exception as exc:
            logger.exception("command failed: %s", spec)
            return self._error(str(exc))

    def _action_drive(self, spec, args, message):
        self.robot.stop()
        if spec.get("trim"):
            self.robot.steer(self.steer_trim)
        self.robot.drive(self._speed(spec), int(spec.get("direction", 1)))
        return None, ""

    def _action_turn(self, spec, args, message):
        angle = _number(spec.get("angle", 30)) * int(spec.get("direction", 1))
        self.robot.stop()
        self.robot.steer(angle)
        self.robot.drive(self._speed(spec), 1)
        indicator = spec.get("indicator")
        if indicator:
            self.robot.set_indicator(indicator)
        return None, ""

    def _action_stop(self, spec, args, message):
        self.robot.stop()
        self.robot.jog_stop()
        return None, ""

    def _action_halt(self, spec, args, message):
        self.robot.halt()
        self.robot.set_indicator("off")
        return None, ""

    def _action_steer(self, spec, args, message):
        self.robot.steer(_number(args[0], 0))
        return None, ""

    def _action_joint(self, spec, args, message):
        self.robot.move_joint(int(spec["channel"]), _number(spec["angle"], 90))
        return None, ""

    def _action_jog(self, spec, args, message):
        self.robot.jog_joint(int(spec["channel"]), int(spec.get("direction", 1)))
        return None, ""

    def _action_jog_stop(self, spec, args, message):
        self.robot.jog_stop()
        return None, ""

    def _action_switch(self, spec, args, message):
        self.robot.set_switch(int(spec["channel"]), int(spec.get("status", 1)))
        return None, ""

    def _action_mode(self, spec, args, message):
        getattr(self.robot, spec["method"])()
        return None, ""

    def _action_speed(self, spec, args, message):
        self.robot.set_speed(_number(args[0], 50) * self.speed_scale)
        return None, ""

    def _action_info(self, spec, args, message):
        state = self.robot.system_info.as_dict()
        data = [str(state.get("cpu_temp")), str(state.get("cpu_usage")), str(state.get("ram_usage"))]
        if spec.get("battery"):
            try:
                data.append(str(int(round(self.robot.battery.read().percent))))
            except Exception:
                data.append(None)
        return data, "get_info"

    def _action_vision_stop(self, spec, args, message):
        self.robot.stop()
        if self.vision is not None:
            self.vision.set_mode("none")
        return None, ""

    def _action_scan(self, spec, args, message):
        return self.robot.radar_scan(), "scanResult"

    def _action_light(self, spec, args, message):
        effect = spec.get("effect") or message.get("lightMode") or "breath"
        color = message.get("data") or spec.get("color") or [0, 80, 255]
        if effect == "police":
            self.robot.ws2812.start_police()
        elif effect == "rainbow":
            self.robot.ws2812.start_rainbow()
        elif effect == "flowing":
            self.robot.ws2812.start_flowing(*color[:3])
        else:
            self.robot.ws2812.start_breath(*color[:3])
        return None, ""

    def _action_color(self, spec, args, message):
        if self.vision is None:
            raise RuntimeError("vision is not enabled")
        color = message.get("data") or args
        if self.mode == "app":
            self.vision.set_color_rgb(*[int(v) for v in color[:3]])
        else:
            self.vision.set_color_hsv(*[int(v) for v in color[:3]])
        return None, ""

    def _action_color_index(self, spec, args, message):
        if self.vision is None:
            raise RuntimeError("vision is not enabled")
        # 255 = track a white line, 0 = track a black line
        self.vision.set_line_color(255 if int(_number(args[0], 0)) else 0)
        return None, ""

    def _action_line_pos(self, spec, args, message):
        if self.vision is None:
            raise RuntimeError("vision is not enabled")
        index = int(spec.get("index", 1)) - 1
        self._line_positions[index] = _number(args[0], 0) * self.line_pos_scale
        self.vision.set_line_positions(*self._line_positions)
        return None, ""

    def _action_line_threshold(self, spec, args, message):
        if self.vision is None:
            raise RuntimeError("vision is not enabled")
        self.vision.set_line_threshold(int(_number(args[0], 0)))
        return None, ""

    def _action_buzzer(self, spec, args, message):
        command = spec.get("command", "play")
        if command == "stop":
            self.robot.buzzer.stop()
        elif self._music_thread is None or not self._music_thread.is_alive():
            self._music_thread = threading.Thread(
                target=self.robot.buzzer.play_happy_birthday,
                name="robot-buzzer", daemon=True)
            self._music_thread.start()
        return None, ""

    def _action_indicator(self, spec, args, message):
        self.robot.set_indicator(spec["mode"])
        return None, ""

    def _speed(self, spec):
        value = spec.get("speed")
        if value == "current":
            return None
        return None if value is None else _number(value)

    @staticmethod
    def _error(message):
        return {"status": "error", "title": "", "data": message}


async def _authenticate(websocket, auth):
    if not auth.get("enabled", False):
        return await websocket.recv()
    while True:
        raw = await websocket.recv()
        text = raw if isinstance(raw, str) else json.dumps(raw)
        parts = text.split(":", 1)
        if len(parts) == 2 and parts[0] == auth.get("username") and parts[1] == auth.get("password"):
            await websocket.send("congratulation, you have connect with server\r\n"
                                 "now, you can do something else")
            return await websocket.recv()
        await websocket.send("sorry, the username or password is wrong, please submit again")


async def _client(websocket, router, auth):
    try:
        first = await _authenticate(websocket, auth)
        while True:
            response = router.handle(first)
            first = None
            await websocket.send(json.dumps(response, ensure_ascii=False))
            first = await websocket.recv()
    except Exception as exc:
        logger.info("client disconnected: %s", exc)


async def _serve(host, port, router, auth):
    async def handler(websocket):
        await _client(websocket, router, auth)

    async with serve(handler, host, port):
        await asyncio.Future()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Adeept Picar Pro Robot Control Server")
    parser.add_argument("--mode", choices=("app", "web"), help="control profile")
    parser.add_argument("--config", help="path to runtime.yml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    server = config.get("server") or {}
    mode = args.mode or server.get("mode", "web")
    profile = (server.get("modes") or {}).get(mode)
    if not profile:
        raise SystemExit("server.modes.%s is missing in runtime.yml" % mode)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    vision = None
    vision_config = server.get("vision") or {}
    if vision_config.get("enabled", True):
        try:
            from Vision import Vision
            vision = Vision.get()
            vision.start(camera_type=vision_config.get("camera", "auto"),
                         width=int(vision_config.get("width", 640)),
                         height=int(vision_config.get("height", 480)),
                         fps=int(vision_config.get("fps", 30)),
                         web=bool(vision_config.get("web", True)),
                         host=server.get("host", "0.0.0.0"),
                         port=int(vision_config.get("web_port", 5000)))
        except Exception:
            logger.exception("vision start failed; vision commands will return errors")
            vision = None

    robot = Robot(vision=vision, profile=mode)
    router = ControlRouter(robot, vision, mode, profile, server.get("defaults"))
    try:
        asyncio.run(_serve(server.get("host", "0.0.0.0"), int(server.get("port", 8888)), router, profile.get("auth") or {}))
    except KeyboardInterrupt:
        pass
    finally:
        robot.close()
        if vision is not None:
            vision.stop()


if __name__ == "__main__":
    main()
