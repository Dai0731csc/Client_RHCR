# Client Usage Guide

This document explains the basic usage of the `client` side of the remote hair-cutting robot project. It focuses on starting the service, opening the frontend pages, and following the normal operation flow.

## Scope

- This repository contains the `client` side only
- The `cloud` and `server/control-side` codebases are not public
- This document does not describe the permission workflow for controlling the remote robot
- For discussion about the full system or permission to control the remote robot, contact `shuai.li@oulu.fi` or `zhendai.huang@oulu.fi`

## 1. Start the Service

From the `client` repository root, run:

```bash
.venv/bin/python main.py
```

or:

```bash
python3.11 main.py
```

On Windows:

```powershell
.\.venv\Scripts\python.exe main.py
```

After startup, the frontend is normally available at:

- `https://<host>:8000/`
- `https://<host>:8000/settings`

## 2. Find the Machine IP Address

If you access the frontend from a phone, tablet, or another computer, first find the IP address of the machine running the `client`.

- Windows: run `ipconfig`
- macOS: run `ifconfig`
- Linux: run `ip addr` or `hostname -I`

In most cases, use the IPv4 address of the active network interface, for example `192.168.1.23`.

## 3. Open the Frontend Pages

Open these URLs in a browser:

- Camera page: `https://<computer-ip>:8000/`
- Settings page: `https://<computer-ip>:8000/settings`

On first access, the browser may show a local HTTPS certificate warning. If you know the page is served by your own `client`, continue to the page.

## 4. Recommended Workflow

Recommended sequence:

1. Start the `client`
2. Open the settings page and verify the transport mode, `session_id`, `cloud_host`, and local topology
3. Open the camera page
4. Click `Open rear camera`
5. Click `Time sync`
6. If the device has not been calibrated yet, run `Camera calibration`
7. Run `Initial calibration`
8. Click `Start continuous detection`
9. If needed, use `Open gripper / Close gripper`

## 5. Settings Page

The settings page is used to adjust the runtime transport configuration. Changes are applied automatically; there is no separate Save button.

Main fields:

- `Transport Mode`: choose one of `local_udp`, `local_tcp`, `cloud_tcp`, `cloud_udp`
- `Session ID`: cloud session identifier
- `Cloud Host`: cloud relay host address
- `Local Topology`: `same_machine` or `same_lan`

Notes:

- The `client` and the control `server` must use the same transport mode
- In cloud modes, both sides normally also need the same `session_id`
- Without a valid cloud configuration, cloud links will not function correctly

## 6. Camera Page

The camera page is used for frontend capture, calibration, and continuous detection. Common actions:

- `Open rear camera`: open the rear camera
- `Camera calibration`: capture chessboard images and compute camera intrinsics
- `Time sync`: perform browser-to-backend time synchronization
- `Initial calibration`: collect the initial AprilTag reference pose
- `Start continuous detection`: continuously detect and upload AprilTag data
- `Open gripper / Close gripper`: send gripper open/close commands

## 7. Typical Scenarios

### First Use on a New Device

Recommended sequence:

1. Open the camera
2. Run time sync
3. Complete camera calibration
4. Complete initial calibration
5. Start continuous detection

### Reuse After Calibration Already Exists

Recommended sequence:

1. Start the `client`
2. Check settings page parameters
3. Open the camera
4. Run time sync once
5. Re-run initial calibration if the environment or camera position changed noticeably
6. Start continuous detection

## 8. Common Issues

### The page does not open

Check:

- whether the `client` is already running
- whether the IP address is correct
- whether port `8000` is reachable
- whether the access device and the `client` machine are on the same network, or otherwise routable

### The browser cannot open the camera

Check:

- whether the page is opened over `HTTPS`
- whether the browser has camera permission
- whether the device actually has an available camera

### Continuous detection cannot be started

This usually means valid camera intrinsics are not available yet. Complete camera calibration first.

### Cloud link is unavailable

Check:

- whether `config/cloud.json` exists and is correct
- whether `Transport Mode` matches the control side
- whether `session_id` and `cloud_host` are correct

## 9. Related Documents

- Chinese usage guide: `doc/USAGE_CN.md`
- Chinese frontend button guide: `doc/FRONTEND_BUTTON_GUIDE_CN.md`
- English frontend button guide: `doc/FRONTEND_BUTTON_GUIDE_EN.md`
- Chinese installation guide: `install/INSTALL_CN.md`
- English installation guide: `install/INSTALL_EN.md`
