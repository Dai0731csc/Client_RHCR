# Client Frontend Button Guide

This document explains the purpose, prerequisites, and recommended usage of the buttons and toggles in the `client` frontend. The frontend mainly has two pages:

- `https://<host>:8000/`: camera page (`Viewfinder`)
- `https://<host>:8000/settings`: settings page (`Settings`)

## 0. How to Access the Frontend

Before opening the frontend on a phone or another device, first find the IP address of the computer that is running the `client`.

### 1. Find the computer IP address

- Windows: run `ipconfig` in Command Prompt
- macOS: run `ifconfig` in Terminal, or check it in `System Settings -> Network`
- Linux: run `ip addr` or `hostname -I` in Terminal

In most cases, you should use the IPv4 address of the active LAN interface, for example `192.168.1.23`.

### 2. Enter the URL in the browser

- Camera page: `https://<computer-ip>:8000/`
- Settings page: `https://<computer-ip>:8000/settings`

For example, if the computer IP is `192.168.1.23`, open:

- `https://192.168.1.23:8000/`
- `https://192.168.1.23:8000/settings`

### 3. Access notes

- The phone or access device must be on the same network as the computer running the `client`, or otherwise be able to route to it.
- On first access, the browser may show an HTTPS certificate warning because the system typically uses a local development certificate.
- If you are sure you are connecting to the intended device, continue in the browser and open the page.
- If the page does not open, first check that the IP address is correct, port `8000` is reachable, and the `client` service is already running.

## 1. Camera Page Buttons

There are 6 main buttons at the top of the camera page. When camera calibration mode is enabled, 2 floating buttons also appear inside the preview area.

### 1. Open rear camera / Close camera

- Location: first button on the top bar
- Purpose: open or close the rear camera
- Prerequisites:
  - the page must run in a secure `HTTPS` context
  - the browser must be granted camera permission
  - the frontend first tries to request the rear camera; if not available, it falls back to a generic `environment` camera
- Result after clicking:
  - when opened successfully, the live preview starts
  - the frontend loads the current device camera calibration profile
  - if camera intrinsics already exist, continuous detection becomes available
  - when closed, continuous detection stops, the current calibration session is cleared, and realtime connections are closed
- Recommended usage: open the camera first after entering the page

### 2. Camera calibration

- Location: second button on the top bar
- Purpose: enter or exit camera calibration mode
- Prerequisites:
  - the camera must already be open
  - it cannot be used while initial calibration, time sync, or camera calibration upload/capture is in progress
- Result after clicking:
  - after entering calibration mode, the preview shows progress as `0 / 15`
  - two floating buttons appear: capture chessboard frame, and upload/compute intrinsics
  - when leaving calibration mode, all chessboard frames from the current session are cleared
- Typical usage: first-time setup on a new device, or recalibration after camera/lens conditions change

### 3. Time sync

- Location: third button on the top bar
- Purpose: perform one browser-to-backend time synchronization
- Prerequisites:
  - the camera must already be open
  - it cannot run at the same time as initial calibration
- Result after clicking:
  - the frontend performs a time sync sampling procedure
  - after success, the latest sync result is stored; the next click acts as a re-sync
  - after failure, other buttons remain usable, but no sync result is kept
- Recommended usage: run it before formal operation, and run it again if network conditions change

### 4. Initial calibration

- Location: fourth button on the top bar
- Purpose: collect AprilTag calibration samples, compute the initial reference pose, and send it to the backend
- Prerequisites:
  - the camera must already be open
  - the calibration AprilTag must be stably visible in the camera view
  - the current default calibration tag ID is `0`
- Result after clicking:
  - the frontend tries to collect up to `20` valid samples
  - if sampling times out, too few valid samples are collected, or the tag cannot be detected, the calibration fails
  - after success, the averaged pose is sent to the backend as `initial_calibration`
- Recommended usage: run it only after the camera position and reference tag are stable

### 5. Start continuous detection / Stop continuous detection

- Location: fifth button on the top bar
- Purpose: start or stop continuous AprilTag detection
- Prerequisites:
  - the camera must already be open
  - a valid camera calibration result must already exist
  - if this button is disabled, it usually means camera calibration has not been completed yet
- Result after clicking:
  - when started, the frontend continuously detects AprilTags and draws green overlays and distance labels
  - detection results are sent through `WebRTC DataChannel` when available, with fallback to `WebSocket`
  - when stopped, the detection loop ends, the overlay is cleared, and `detection_state=false` is reported to the backend
- Recommended usage: only start continuous detection after camera calibration has been completed

### 6. Open gripper / Close gripper

- Location: sixth button on the top bar
- Purpose: toggle the gripper state
- Prerequisites:
  - this button can be clicked even if the camera is not open
  - the backend must already have a valid gripper forwarding path
- Result after clicking:
  - if the current state is `closed`, clicking sends `open`
  - if the current state is `open`, clicking sends `close`
  - the button is temporarily disabled while the command is in flight, to prevent repeated commands
- Note: the frontend only sends the command; whether the gripper actually moves depends on the backend and downstream device chain

## 2. Floating Buttons in the Preview Area

These two buttons only appear in camera calibration mode.

### 1. Capture calibration frame

- Location: floating button at the bottom of the video preview
- Purpose: capture one chessboard calibration frame
- Prerequisites:
  - camera calibration mode must already be enabled
  - the chessboard must be clearly visible in the camera view
  - the current target is `15` valid images
- Result after clicking:
  - the frontend captures the current video frame
  - it then asks the backend to validate whether the chessboard is visible in that frame
  - the progress only increases if validation passes
  - if the chessboard is not detected, no error is shown, but the frame is not counted
- Current chessboard configuration:
  - `board_type = chessboard`
  - `rows = 6`
  - `cols = 9`
  - `square_size_mm = 20.0`

### 2. Upload and compute intrinsics

- Location: floating button at the bottom of the video preview
- Purpose: upload the captured chessboard frames and compute camera intrinsics
- Prerequisites:
  - camera calibration mode must already be enabled
  - all `15 / 15` valid frames must already be collected
- Result after clicking:
  - the frontend uploads the images and chessboard metadata to the backend
  - after the backend returns the calibration result, the frontend stores the new camera intrinsics
  - after a successful upload, camera calibration mode exits automatically
  - once completed, continuous detection becomes available
- Note: if upload fails, the current calibration mode and collected frames are kept so the user can retry

## 3. Settings Page Controls

There is no separate Save button on the settings page. All changes are applied automatically and immediately trigger outbound reconnection when needed.

### 1. Back to Camera

- Location: top-left return link on the settings page
- Purpose: go back to the camera page
- Note: this only changes the page; it does not undo settings that were already auto-applied

### 2. Transport Mode

- Location: the first toggle group on the settings page
- Available options:
  - `local_udp`
  - `local_tcp`
  - `cloud_tcp`
  - `cloud_udp`
- Behavior:
  - exactly one option is always selected
  - clicking a new option immediately submits the change to `/api/settings`
  - after success, the backend rebuilds the outbound link for the new mode
- Usage guidance:
  - `local_tcp` and `local_udp` are mainly for local debugging
  - in normal use, `Transport Mode` usually does not need to be changed
  - keep the default `cloud_tcp` in general use
  - only switch to `local_tcp` or `local_udp` when explicitly doing local integration or link troubleshooting
  - the transport mode on the client and the control server must match

### 3. Session ID

- Location: input field below `Transport Mode`
- Purpose: set the current session ID
- Behavior:
  - changes are auto-applied after about `400 ms`
  - no manual save is needed
- Usage guidance: in cloud mode, the client and the remote side must use the same `session_id`

### 4. Cloud Host

- Location: input field below `Session ID`
- Purpose: set the cloud relay host address
- Behavior:
  - changes are auto-applied after about `400 ms`
  - relevant for `cloud_tcp` and `cloud_udp`

### 5. Local Topology

- Location: below `Cloud Host`
- Available options:
  - `same_machine`
  - `same_lan`
- Behavior:
  - exactly one option is always selected
  - changing it immediately auto-applies the new setting
- Usage guidance:
  - choose `same_machine` when the client and control server are on the same machine
  - choose `same_lan` when they are on different machines in the same LAN

### 6. Local LAN Host

- Location: input field below `Local Topology`
- Purpose: specify the LAN IP address of the client machine
- Behavior:
  - changes are auto-applied after about `400 ms`
  - mainly used in the `same_lan` scenario
- Usage guidance: enter the actual LAN IP that the control server can reach

## 4. Recommended Operation Order

### First-time setup

1. Open `Settings` and confirm `Transport Mode`, `Session ID`, `Cloud Host`, or local topology.
2. Return to the camera page and click `Open rear camera`.
3. Click `Camera calibration` to enter camera calibration mode.
4. Click `Capture calibration frame` until `15` valid chessboard frames are collected.
5. Click `Upload and compute intrinsics`.
6. Run `Time sync` if needed.
7. Run `Initial calibration`.
8. Click `Start continuous detection`.

### Daily use

1. Open the camera.
2. Re-run `Time sync` if network or device conditions changed.
3. Re-run `Initial calibration` if the camera reference frame needs to be refreshed.
4. Start continuous detection.
5. Use `Open gripper / Close gripper` as needed.

## 5. Common Observations

- If `Start continuous detection` is disabled, the usual reason is that valid camera intrinsics do not exist yet, so camera calibration must be completed first.
- If a chessboard capture does not increase the counter, the current frame did not pass chessboard validation. Adjust angle, distance, or lighting and try again.
- Settings taking effect immediately is expected behavior. There is no Save button on the settings page.
- Returning to the camera page does not discard settings. They are written back into runtime configuration.
- If the gripper button is clicked but nothing happens physically, the frontend may have sent the command, but the backend path or downstream device may not have responded correctly.

## 6. Operational Notes

- After `Initial calibration`, the phone must not be moved immediately. Keep the phone and camera pose fixed for at least `3` seconds, then click `Start continuous detection`. Only after continuous detection has started may the phone begin to move.
- Once the client and the robot-side link are connected, do not start or stop `Start continuous detection` arbitrarily from random poses. Stopping continuous detection should be treated as the end of the current control cycle.
- If continuous detection is stopped midway, the next control cycle must re-run both `Time sync` and `Initial calibration`.
- If continuous detection is stopped midway, the robot side must also reset the robot before the next control cycle, to avoid reusing the previous reference state.
- During `Initial calibration` and continuous detection, the AprilTag should remain clear, complete, and as front-facing to the camera as possible. Do not let hands, tools, or fixtures block the tag.
- During camera calibration, do not capture many nearly identical chessboard views. Use different distances, positions, and slight tilt angles; otherwise the intrinsic calibration quality may degrade and reduce detection stability.
- Settings changes apply immediately and can trigger outbound reconnection. Do not modify `Transport Mode`, `Session ID`, `Cloud Host`, or local topology while the robot is already prepared for active control.
- `local_tcp` and `local_udp` are intended for local debugging. In a normal remote-control workflow, `Transport Mode` should usually remain at the default `cloud_tcp`.
- If the camera is closed and reopened, re-check the current link state, and before formal control, re-run `Time sync` and `Initial calibration` instead of assuming the previous cycle is still valid.
- `Open gripper / Close gripper` only means the frontend sent the command. It does not guarantee that the end effector has already completed the action. For grasping or releasing, rely on robot-side or gripper-side feedback.
