# Adeept PiCar-Pro Desktop Client

Desktop client for the Adeept PiCar-Pro robot. It ships in two flavours that match the two server profiles: a browser shell (`web_client.py`) and a full control panel (`app_client.py`). The only third-party dependency is **PySide6** (Qt 6, with QtWebEngine).

| Mode | Client file | What it does |
| ---- | ----------- | ------------ |
| **web** | `web_client.py` | Desktop browser shell. Enter the robot IP, it loads the console the robot publishes on `http://<ip>:5000`. Controls, video and login all come from that web page. |
| **app** | `app_client.py` | Single-file client. WebSocket `8888` for commands plus MJPEG `5000` for video; transport and UI live in one file. |

## Quick Start

Four steps: Python → PySide6 → server → client. The server runs on the Raspberry Pi, the client runs on your PC.

### 1. Install Python

Install **Python 3.10 or newer** (3.13 recommended) on the machine that will run the client.

**Windows**

Download the installer from [python.org](https://www.python.org/downloads/) and tick *Add python.exe to PATH*. Verify:

```powershell
python --version
```

**Linux (Debian / Ubuntu / Raspberry Pi OS)**

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip
python3 --version
```

**macOS**

Install with Homebrew, or use the python.org package:

```bash
brew install python@3.13
python3 --version
```

### 2. Install PySide6

Use a virtual environment so the system Python stays clean.

**Windows (PowerShell)**

```powershell
python -m pip install --upgrade pip
pip install PySide6
```

**Linux / macOS**

```bash
cd ~/Adeept_PiCar-Pro
python3 -m pip install --upgrade pip
pip install PySide6
```

### 3. Start the server in a mode (on the robot)

`Server/Server.py` takes `--mode app` or `--mode web`. The CLI flag overrides `server.mode` in `Server/runtime.yml`, which defaults to `web`.

On the Raspberry Pi, in the repository root:

```bash
sudo killall python3
cd ~/Adeept_PiCar-Pro

# app 
sudo python3 Server/Server.py --mode app

# web 
sudo python3 Server/Server.py --mode web
```

Match the client to the mode: `app_client.py` against the `app` profile, `web_client.py` against the `web` profile.

> Fresh Pi OS image? Run `sudo python3 install.py` once first. It enables SPI/I2C, installs the server requirements and registers the autostart service. After that the robot starts `Server.py` on boot using `server.mode` from `runtime.yml`.

### 4. Run the client

Run the client that matches the server mode. 
Please confirm your Raspberry Pi IP address and ensure this PC and the robot are on the same local area network.

**Windows**

```powershell
python Client\web_client.py --host 192.168.4.1     # web profile server
python Client\app_client.py --host 192.168.4.1     # app profile server
```

**Linux / macOS**

```bash
cd ~/Adeept_PiCar-Pro

python3 Client/web_client.py --host 192.168.4.1     # web profile server
python3 Client/app_client.py --host 192.168.4.1     # app profile server
```

Leave `--host` off and type the IP in the window instead; press Enter or click **Connect**. 


## Files

| File | Purpose |
| ---- | ------- |
| `web_client.py` | web-mode desktop shell (QtWebEngine + address bar + fullscreen + JS log switch) |
| `app_client.py` | app-mode client, transport and UI merged into one file |
| `logo.png` | brand mark, shown in the top bar and used as the window icon |
| `app.ico` | multi-size icon generated from `logo.png`, only needed when building the exe |

## Notes and limits

- The web shell only covers the web profile (`admin/123456` handshake). If the server runs in app mode, web login will fail — use `app_client.py` instead.
- Web-mode command semantics are bound to the `web` block of `Server/runtime.yml`.
