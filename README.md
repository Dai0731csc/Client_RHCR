# TeleProgram

`TeleProgram` provides an `aiohttp`-based HTTPS/WSS + UDP service. It supports AprilTag detection on mobile/browser, time sync, initial calibration, and camera calibration, and forwards the raw pose stream either to cloud or directly to the control side.

Current goals:

- Real-time AprilTag detection in the browser using the camera
- Prefer uploading detections via `WebRTC DataChannel`, and fall back to `WebSocket` on failure
- Backend acts as `master`, caches state, and broadcasts raw poses via `UDP` to the control-side `slave`

## Directory structure

- `main.py`: starts the HTTPS + WSS server
- `backend/main.py`: app factory, frontend route registration, and startup/shutdown
- `backend/config.py`: ports, TLS, cloud transport, and ICE config
- `backend/links/frontend/`: browser ↔ backend (HTTP/WebSocket/WebRTC registrations)
- `backend/links/local/`: LAN UDP pose stream + gripper to the control server
- `backend/links/cloud/`: cloud relay (TCP WebSocket or UDP to `/relay`)
- `backend/links/pose_protocol.py`: shared raw-pose JSON protocol constants and helpers
- `backend/wiring/links.py`: installs the active outbound link on startup
- `backend/routers/`: WebSocket/WebRTC handlers and HTTP route handlers (used by the frontend link)
- `backend/services/`: payload ingest, calibration, gripper dispatch, and device persistence
- `backend/models/`: payload and profile shapes
- `backend/utils.py`: timing, timestamps, and ack helpers
- `backend/data/devices/`: device records keyed by IP (including camera calibration)
- `frontend/camera.html`: page entry
- `frontend/state/`, `frontend/modules/`, `frontend/ui/`: frontend state, workflow modules, and controls
- `frontend/vendor/`: vendored frontend deps and AprilTag wasm
- `config/cert.pem`, `config/key.pem`: HTTPS/WSS certificates

1. Browser opens `https://<host>:8000/`
2. The page opens the camera; the browser performs local AprilTag detection
3. The client sends detections via `WebRTC DataChannel(label=apriltag)` when available
4. If WebRTC fails, it falls back to `wss://<host>:8000/ws/publish`
5. Initial calibration is sent via `wss://<host>:8000/ws/calibration/publish`
6. Backend `master` caches `detection_state`, `initial_calibration`, and `apriltag_detections`
7. Backend `master` forwards the stream via `cloud_tcp`, `cloud_udp`, or local UDP

## Endpoints

### Pages and static assets

- `GET /`: camera page
- `GET /static/*`: frontend scripts, styles, and vendor assets

### WebSocket / WebRTC

- `GET /ws/webrtc`: WebRTC signaling
- `GET /ws/publish`: AprilTag WebSocket uplink
- `GET /ws/calibration/publish`: initial calibration WebSocket uplink
- `GET /api/webrtc/config`: returns ICE config for `RTCPeerConnection`
- `GET /api/device-profile`: returns the current device profile inferred from request IP
- `GET /api/device-profile/{ip}`: returns a saved device profile by IP

### Camera calibration

- `POST /api/camera-calibration/validate`: validate a single chessboard frame
- `POST /api/camera-calibration`: upload frames and compute intrinsics

## 配置（不使用环境变量）

### WebRTC ICE

在 **`client/config/cloud.json`** 的 **`webrtc`** 段配置（逗号分隔多条 URL，也可用 JSON 数组）：

```json
"webrtc": {
  "stun_urls": "stun:stun.l.google.com:19302",
  "turn_urls": "turn:your-turn-host:3478?transport=udp",
  "turn_username": "your-username",
  "turn_password": "your-password"
}
```

仅 STUN 能否穿 NAT 取决于网络；跨公网建议配 TURN。

### 本机 Master UDP / 夹爪

同一文件可写（不配则用代码默认）：

```json
"master_udp_host": "0.0.0.0",
"master_udp_port": 9001,
"master_udp_max_packet_bytes": 65507,
"gripper_service_host": "127.0.0.1",
"gripper_service_port": 9002
```

云上路径仍由 `base_url`、`transport_mode` 等字段控制：

```json
{
  "base_url": "",
  "transport_mode": "local_udp",
  "udp_host": "127.0.0.1",
  "udp_port": 8440,
  "session_id": "default",
  "token": ""
}
```

Supported `transport_mode` values:

- `cloud_tcp`: use `ws(s)://.../relay` on the cloud server
- `cloud_udp`: send raw JSON datagrams to the cloud UDP relay
- `local_udp`: expose the local master UDP port directly to the control-side slave

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

Default parameters are in `frontend/state/state.js`, including:

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
