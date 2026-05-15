# TeleProgram

`TeleProgram` provides an `aiohttp`-based HTTPS/WSS + UDP service. It supports AprilTag detection on mobile/browser, time sync, initial calibration, and camera calibration, and forwards the raw pose stream to the control side using a `master -> slave` protocol.

Current goals:

- Real-time AprilTag detection in the browser using the camera
- Prefer uploading detections via `WebRTC DataChannel`, and fall back to `WebSocket` on failure
- Backend acts as `master`, caches state, and broadcasts raw poses via `UDP` to the control-side `slave`

## Directory structure

- `main.py`: starts the HTTPS + WSS server
- `backend/app.py`: routes for pages, WebSocket, HTTP APIs, and static assets
- `backend/config.py`: ports, TLS, and ICE config
- `backend/ws_handlers.py`: AprilTag realtime ingestion (WebSocket)
- `backend/master_stream.py`: `master -> slave` UDP raw pose stream
- `backend/webrtc_handlers.py`: WebRTC signaling and DataChannel ingestion
- `backend/calibration_handlers.py`: initial calibration, camera calibration, and validation APIs
- `backend/camera_calibration.py`: OpenCV-based chessboard / single-tag intrinsics calibration
- `frontend/pages/camera.html`: page entry
- `frontend/static/js/`: UI logic, transport, pose math, calibration workflow
- `frontend/static/vendor/`: vendored frontend deps and AprilTag wasm
- `config/cert.pem`, `config/key.pem`: HTTPS/WSS certificates

1. Browser opens `https://<host>:8000/`
2. The page opens the camera; the browser performs local AprilTag detection
3. The client sends detections via `WebRTC DataChannel(label=apriltag)` when available
4. If WebRTC fails, it falls back to `wss://<host>:8000/ws/publish`
5. Initial calibration is sent via `wss://<host>:8000/ws/calibration/publish`
6. Backend `master` caches `detection_state`, `initial_calibration`, and `apriltag_detections`
7. Control-side `slave` subscribes to the UDP raw pose stream

## Endpoints

### Pages and static assets

- `GET /`: camera page
- `GET /static/*`: frontend scripts, styles, and vendor assets

### WebSocket / WebRTC

- `GET /ws/webrtc`: WebRTC signaling
- `GET /ws/publish`: AprilTag WebSocket uplink
- `GET /ws/calibration/publish`: initial calibration WebSocket uplink
- `GET /api/webrtc/config`: returns ICE config for `RTCPeerConnection`

### Camera calibration

- `POST /api/camera-calibration/validate`: validate a single chessboard frame
- `POST /api/camera-calibration`: upload frames and compute intrinsics

## Environment variables

### WebRTC ICE

By default, a public STUN server is returned:

```bash
WEBRTC_STUN_URLS=stun:stun.l.google.com:19302
```

Optional TURN config:

```bash
WEBRTC_TURN_URLS=turn:your-turn-host:3478?transport=udp,turns:your-turn-host:5349?transport=tcp
WEBRTC_TURN_USERNAME=your-username
WEBRTC_TURN_PASSWORD=your-password
```

Whether STUN-only can connect depends on your NAT environment. For reliable cross-network connectivity, configure TURN.

### Master UDP

```bash
MASTER_UDP_HOST=0.0.0.0
MASTER_UDP_PORT=9001
MASTER_UDP_MAX_PACKET_BYTES=65507
```

Control-side `slave` subscribe:

```json
{"type":"slave_subscribe","protocol":"robotic-haircutting.raw-pose-stream.v1","client_label":"control_AT"}
```

Unsubscribe:

```json
{"type":"slave_unsubscribe","protocol":"robotic-haircutting.raw-pose-stream.v1"}
```

Server-side `master` returns:

- `master_stream_ready`
- `detection_state`
- `initial_calibration`
- `apriltag_detections`

See [RAW_POSE_PROTOCOL.md](./RAW_POSE_PROTOCOL.md) for the full protocol.

## Page notes

Default parameters are in `frontend/static/js/camera_state.js`, including:

- `CALIBRATION_TAG_ID = 0`
- `CALIBRATION_SAMPLE_COUNT = 20`
- `CAMERA_CALIBRATION_TARGET_COUNT = 15`
- `CAMERA_CALIBRATION_BOARD_ROWS = 6`
- `CAMERA_CALIBRATION_BOARD_COLS = 9`
- `CAMERA_CALIBRATION_SQUARE_SIZE_MM = 20.0`

## Notes

- WebRTC is only used for realtime uplink from browser to server
- `master` does not compute deltas; it only forwards raw poses
- This README reflects the current `TeleProgram` directory layout
