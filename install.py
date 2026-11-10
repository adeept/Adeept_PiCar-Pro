#!/usr/bin/python3
# coding=utf-8
# File name: install.py
# Author: Adeept

import os
import re
import sys
import pwd
import shlex
import shutil
import tempfile
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = ROOT_DIR / "product.yml"

WIFI_SERVICE = "wifi-hotspot-manager.service"
ROBOT_SERVICE = "Adeept_Robot.service"

PROTECTED_ROOT_ITEMS = {".git", "install.py", "product.yml", "README.md"}

def run_command(cmd, cwd=None):
    print("\n>>>", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)

def privileged_command(cmd):
    if os.geteuid() != 0:
        cmd = ["sudo"] + cmd
    run_command(cmd)

def check_dependencies():
    packages = []
    if not __import__("importlib.util", fromlist=["find_spec"]).find_spec("yaml"):
        packages.append("python3-yaml")
    if packages:
        privileged_command(["apt-get", "update"])
        privileged_command(["apt-get", "install", "-y"] + packages)

def load_config():
    import yaml
    if not CONFIG_FILE.is_file():
        raise FileNotFoundError(f"Config file not found: {CONFIG_FILE}")

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    product = config.get("product", {})
    if not product.get("name") or not product.get("code"):
        raise ValueError("Product name or code is missing")
    return config

def get_user_info():
    try:
        username = os.environ.get("SUDO_USER") or pwd.getpwuid(os.getuid()).pw_name
        user = pwd.getpwnam(username)
        return username, user.pw_dir
    except KeyError:
        raise RuntimeError(f"Cannot find user information: {username}")

def check_rpi_model():
    model = Path("/sys/firmware/devicetree/base/model").read_bytes()
    match = re.search(rb"Raspberry Pi ([345])", model)
    return int(match.group(1)) if match else None

def check_raspbian_version():
    return int(Path("/etc/debian_version").read_text().strip().split(".")[0])

def check_os_bit():
    result = subprocess.run(["getconf", "LONG_BIT"], capture_output=True, text=True)
    return int(result.stdout.strip()) if result.returncode == 0 else None

def resolve_path(path):
    result = (ROOT_DIR / path).resolve()
    if result != ROOT_DIR and ROOT_DIR not in result.parents:
        raise ValueError(f"Invalid path: {path}")
    return result

def copy_repository(source, destination, is_root=False):
    destination.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        if item.name == ".git" or (is_root and item.name in PROTECTED_ROOT_ITEMS):
            continue

        target = destination / item.name

        if item.is_dir() and not item.is_symlink():
            shutil.copytree(
                item, target, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
        elif item.is_symlink():
            if target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            target.symlink_to(os.readlink(item))
        else:
            shutil.copy2(item, target)


def download_repository(repo):
    name, url = repo["name"], repo["url"]
    branch, destination = repo["branch"], resolve_path(repo["destination"])

    print(f"\n========== Downloading {name} ==========")
    print(f"Branch: {branch}")
    print(f"Destination: {destination}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_repo = Path(temp_dir) / "repository"
        run_command([
            "git", "clone", "--depth", "1",
            "--single-branch", "--branch", branch,
            url, str(temp_repo)
        ])
        copy_repository(temp_repo, destination, destination == ROOT_DIR)


def install_requirements(config):
    import yaml

    requirements_file = config.get("install", {}).get("dependencies", "requirements.yaml")
    requirements_path = resolve_path(requirements_file)

    if not requirements_path.is_file():
        raise FileNotFoundError(f"Requirements file not found: {requirements_path}")

    with open(requirements_path, "r", encoding="utf-8") as f:
        requirements = yaml.safe_load(f) or {}

    apt_packages = requirements.get("apt", [])
    pip_packages = requirements.get("pip", [])

    if not isinstance(apt_packages, list) or not isinstance(pip_packages, list):
        raise ValueError("apt and pip dependencies must be lists")

    if apt_packages:
        privileged_command(["apt-get", "update"])
        privileged_command(["apt-get", "install", "-y"] + apt_packages)

    # if check_rpi_model() == 5:
    #     pip_packages += requirements.get("pip_rpi5", [])

    if pip_packages:
        privileged_command([sys.executable, "-m", "pip", "install", "--break-system-packages"] + pip_packages)


def install_service_file(service_name, content):
    service_path = f"/etc/systemd/system/{service_name}"

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        privileged_command(["install", "-m", "644", temp_path, service_path])
    finally:
        os.unlink(temp_path)

    privileged_command(["systemctl", "daemon-reload"])
    privileged_command(["systemctl", "enable", service_name])


def install_wifi_service(user_home):
    source = ROOT_DIR / "wifi_hotspot_manager.sh"
    if not source.is_file():
        raise FileNotFoundError(f"WiFi script not found: {source}")

    script_path = Path(user_home) / "wifi_hotspot_manager.sh"
    privileged_command(["install", "-m", "755", str(source), str(script_path)])

    service_content = f"""[Unit]
Description=WiFi and Hotspot Manager Service
After=network.target NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
ExecStart={shlex.quote(str(script_path))}
User=root
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""
    install_service_file(WIFI_SERVICE, service_content)
    print(f"WiFi service {WIFI_SERVICE} enabled")


def install_robot_service(user_home):
    startup_script = Path(user_home) / "startup.sh"
    robot_server = ROOT_DIR / "Server" / "WebServer.py"

    if not startup_script.exists():
        startup_content = f"#!/bin/bash\nsleep 3\nsudo python3 {shlex.quote(str(robot_server))}\n"
        startup_script.write_text(startup_content, encoding="utf-8")
        startup_script.chmod(0o755)
        print(f"Startup script created: {startup_script}")

    service_content = f"""[Unit]
Description=Auto-start Robot Control Service
After={WIFI_SERVICE}
Wants={WIFI_SERVICE}

[Service]
Type=simple
User=root
WorkingDirectory={shlex.quote(str(user_home))}
ExecStart={shlex.quote(str(startup_script))}
Restart=no

[Install]
WantedBy=multi-user.target
"""
    install_service_file(ROBOT_SERVICE, service_content)
    print(f"Robot service {ROBOT_SERVICE} enabled")


def enable_SPI_I2C():
    print("\nEnabling SPI and I2C...")
    raspi_config = shutil.which("raspi-config")
    if not raspi_config:
        raise RuntimeError("raspi-config not found. Cannot enable SPI/I2C.")
    privileged_command([raspi_config, "nonint", "do_spi", "0"])
    privileged_command([raspi_config, "nonint", "do_i2c", "0"])
    print("SPI enabled.")
    print("I2C enabled.")

def main():
    enable_SPI_I2C()
    check_dependencies()
    config = load_config()
    product = config["product"]
    install_config = config.get("install", {})

    print("\n================================")
    print(f"Product: {product['name']}")
    print(f"Product Code: {product['code']}")
    print(f"Raspberry Pi: {check_rpi_model()}")
    print(f"Debian Version: {check_raspbian_version()}")
    print(f"OS Bit: {check_os_bit()}")
    print("================================")

    for repo in config.get("repositories", []):
        download_repository(repo)

    install_requirements(config)

    username, user_home = get_user_info()
    print(f"Username: {username}")
    print(f"User Home: {user_home}")

    if install_config.get("wifi_service", True):
        install_wifi_service(user_home)

    if install_config.get("robot_service", True):
        install_robot_service(user_home)

    print("\nInstallation completed.")
    print("You can now power off the Raspberry Pi to install the camera and Robot HAT.")
    print("After powering on, the robot program will run automatically. WebServer.py is the default auto‑start program. If you want to control the robot via your phone, please modify startup.sh.")

    if install_config.get("reboot", True):
        print("\nRestarting Raspberry Pi...")
        privileged_command(["reboot"])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(f"\nCommand failed: {error}")
        sys.exit(error.returncode)
    except Exception as error:
        print(f"\nInstallation failed: {error}")
        sys.exit(1)
