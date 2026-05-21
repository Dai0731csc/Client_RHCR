# Client Installation Guide

This document explains how to install and start the `client` side of the remote hair-cutting robot project on a new machine.

## Scope

- This repository contains the `client` side only
- The `cloud` and `server/control-side` codebases are not public
- Anyone may use this project for academic research
- For discussion about the full system or permission to control the remote robot, contact `shuai.li@oulu.fi` or `zhendai.huang@oulu.fi`

## Prerequisites

- Python `3.11`
- A device with a camera, or a computer connected to an external camera
- A modern browser with `HTTPS` and camera access support
- A valid `config/cloud.json` if cloud connectivity is required

## Working Directory

All commands below are expected to be run from the `client` repository root.

## Install on macOS / Linux

Run:

```bash
./install/unix/bootstrap_client.sh
```

The script asks whether to create a `Python 3.11` virtual environment:

- Answer `yes`: create and use `client/.venv`
- Answer `no`: skip `.venv` and use system `python3.11`

After installation, verify the environment:

```bash
./install/unix/verify_client.sh
```

If you skipped `.venv`, use:

```bash
./install/unix/verify_client.sh --python python3.11
```

## Install on Windows

Run:

```powershell
.\install\windows\bootstrap_client.ps1
```

If PowerShell blocks local scripts, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\install\windows\bootstrap_client.ps1
```

If you want to skip `.venv` and specify a Python interpreter explicitly:

```powershell
.\install\windows\bootstrap_client.ps1 -PythonExe "C:\path\to\python.exe" -Venv no
```

After installation, verify the environment:

```powershell
.\install\windows\verify_client.ps1
```

If you use a specific interpreter, run:

```powershell
.\install\windows\verify_client.ps1 -PythonExe "C:\path\to\python.exe"
```

## Start the Client

If you use `.venv`:

```bash
.venv/bin/python main.py
```

```powershell
.\.venv\Scripts\python.exe main.py
```

If you do not use `.venv`:

```bash
python3.11 main.py
```

```powershell
py -3.11 main.py
```

After startup, the terminal prints a message similar to:

```text
HTTPS + WSS server running at https://0.0.0.0:8000
```

## What the Bootstrap Scripts Do

- Create an optional `client/.venv`
- Install dependencies from `install/requirements.txt`
- Generate local development certificates:
  - `config/certificate/local/ca.crt`
  - `config/certificate/local/cert.pem`
  - `config/certificate/local/key.pem`
- On Windows, install `cryptography` for local certificate generation

## First-Run Notes

- `config/cloud.json` is not generated automatically
- Without a valid configuration, cloud modes cannot establish the full link
- After startup, open `https://<host>:8000/settings` to inspect or change transport settings
- On first access, the browser may show a local certificate warning; if you know this is your local service, continue to the page

## Related Documents

- Install entry: `install/README.md`
- Chinese installation guide: `install/INSTALL_CN.md`
- Chinese usage guide: `doc/USAGE_CN.md`
- English frontend button guide: `doc/FRONTEND_BUTTON_GUIDE_EN.md`
