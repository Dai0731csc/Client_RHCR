# Raw Pose Stream Protocol

The new `TeleProgram(master) -> control_AT(slave)` protocol only sends raw poses. It does not send `delta_frame` or `delta_pose_robot`.

Goals:

- The master only forwards and caches raw vision data
- The control side computes control signals from `initial_calibration + apriltag_detections`
- Message names no longer use `delta_*`

## Transport

The same JSON message types are used on every pose path; only the wire differs:

| Path | Wire | Notes |
|------|------|--------|
| `local_udp` | UDP | Default master bind `0.0.0.0:9001` |
| `local_tcp` | WebSocket `/relay` on TeleProgram | Control connects as `slave` |
| `cloud_tcp` / `cloud_udp` | Cloud relay | Timestamps `cloud_receive_time` / `cloud_send_time` on stream payloads |

- Encoding: `UTF-8 JSON`
- Direction:
  - slave → master: subscribe / unsubscribe
  - master → slave: ready / snapshot / stream payloads

**Gripper** is not part of this stream. Local modes use UDP to the control `tool_listen` port; cloud modes use relay `gripper_command` (see client/server README).

## Version

All messages include:

```json
{
  "protocol": "rhcr-oulu.raw-pose-stream"
}
```

## Slave To Master

### `slave_subscribe`

Subscribe to the raw pose stream.

```json
{
  "type": "slave_subscribe",
  "protocol": "rhcr-oulu.raw-pose-stream",
  "client_time": "2026-04-23T10:00:00.000Z",
  "client_label": "control_AT",
  "tracked_tag_id": 0,
  "wants_snapshot": true
}
```

Fields:

- `client_time`: optional but recommended for log alignment
- `client_label`: optional
- `tracked_tag_id`: optional; not filtered server-side (for logging/future extension)
- `wants_snapshot`: optional, default `true`

### `slave_unsubscribe`

```json
{
  "type": "slave_unsubscribe",
  "protocol": "rhcr-oulu.raw-pose-stream",
  "client_time": "2026-04-23T10:00:05.000Z"
}
```

## Master To Slave

### `master_stream_ready`

Returned after the subscription is established.

```json
{
  "type": "master_stream_ready",
  "protocol": "rhcr-oulu.raw-pose-stream",
  "master_time": "2026-04-23T10:00:00.010Z",
  "transport": "udp",
  "has_detection_state": true,
  "has_initial_calibration": true,
  "has_apriltag_detections": true
}
```

### `detection_state`

Indicates whether vision detection is currently active. **Clock skew fields are logged here once** (on each detection start/stop), not on every `apriltag_detections` frame.

```json
{
  "type": "detection_state",
  "protocol": "rhcr-oulu.raw-pose-stream",
  "transport": "udp",
  "master_seq": 101,
  "active": true,
  "client_send_time": "2026-04-23T10:00:00.100Z",
  "master_receive_time": "2026-04-23T10:00:00.120Z",
  "master_send_time": "2026-04-23T10:00:00.121Z",
  "skew_client_vs_master_ms": -3.2,
  "clock_sync_rtt_client_ms": 9.8,
  "skew_cloud_vs_master_ms": 12.5,
  "clock_sync_rtt_cloud_ms": 4.1,
  "skew_control_vs_cloud_ms": -4.5,
  "clock_sync_rtt_control_ms": 3.6,
  "nominal_frame_rate": 30,
  "frame_size": {
    "width": 1280,
    "height": 720
  }
}
```

### `initial_calibration`

The initial reference pose used by the control side for relative pose computation.

```json
{
  "type": "initial_calibration",
  "protocol": "rhcr-oulu.raw-pose-stream",
  "transport": "udp",
  "master_seq": 102,
  "tag_id": 0,
  "sample_count": 20,
  "captured_at": "2026-04-23T10:00:01.000Z",
  "frame_size": {
    "width": 1280,
    "height": 720
  },
  "source_sample_time_range": {
    "start": "2026-04-23T10:00:00.100Z",
    "end": "2026-04-23T10:00:00.900Z"
  },
  "mean_pose": {
    "t": [0.01, -0.02, 0.45],
    "R": [
      [1.0, 0.0, 0.0],
      [0.0, 1.0, 0.0],
      [0.0, 0.0, 1.0]
    ]
  }
}
```

### `apriltag_detections`

The core raw pose message. The control side should read `pose.t` and `pose.R` directly from here.

```json
{
  "type": "apriltag_detections",
  "protocol": "rhcr-oulu.raw-pose-stream",
  "transport": "udp",
  "master_seq": 103,
  "client_seq": 42,
  "detectTag_start_time": "2026-04-23T10:00:01.100Z",
  "detectTag_end_time": "2026-04-23T10:00:01.115Z",
  "client_send_time": "2026-04-23T10:00:01.116Z",
  "master_receive_time": "2026-04-23T10:00:01.130Z",
  "master_send_time": "2026-04-23T10:00:01.131Z",
  "cloud_receive_time": "2026-04-23T10:00:01.140Z",
  "cloud_send_time": "2026-04-23T10:00:01.141Z",
  "control_socket_receive_time": "2026-04-23T10:00:01.155Z",
  "nominal_frame_rate": 30,
  "frame_size": {
    "width": 1280,
    "height": 720
  },
  "detections": [
    {
      "id": 0,
      "pose_frame": "tag_camera",
      "pose": {
        "t": [0.01, -0.02, 0.45],
        "R": [
          [1.0, 0.0, 0.0],
          [0.0, 1.0, 0.0],
          [0.0, 0.0, 1.0]
        ]
      },
      "corners": [
        {"x": 100.0, "y": 120.0},
        {"x": 180.0, "y": 120.0},
        {"x": 180.0, "y": 200.0},
        {"x": 100.0, "y": 200.0}
      ]
    }
  ]
}
```

Sequence fields (analysis / gap detection):

- `client_seq`: optional; browser increments once per `apriltag_detections` publish (merged through ingest before UDP).
- `master_seq`: assigned by TeleProgram for each UDP broadcast of stream payloads (`detection_state`, `initial_calibration`, `apriltag_detections`).

Timing fields:

- `client_send_time`: stamped by the browser/frontend immediately before publishing a message to TeleProgram.
- `master_receive_time`: stamped by TeleProgram/master backend when it ingests the frontend message.
- `master_send_time`: stamped by TeleProgram/master backend immediately before forwarding to the active outbound link.
- `cloud_receive_time`: optional; present when using cloud relay, stamped when the relay receives the master payload.
- `cloud_send_time`: optional; present when using cloud relay, stamped immediately before the relay forwards to the slave.
- `control_socket_receive_time`: optional; stamped on the control side as soon as the payload reaches the socket / relay ingress path, before queue wait and event processing.
- `control_receive_time`: stamped when the control-stream adapter accepts the payload for filtering / event conversion.

Clock skew (one-shot per capture; **only on `detection_state` in JSONL**, not on each `apriltag_detections` / `teleop_pose`):

| Field | Meaning |
|-------|---------|
| `skew_client_vs_master_ms` | Browser wall clock minus master at sync (positive = client ahead) |
| `skew_cloud_vs_master_ms` | Cloud relay wall clock minus master |
| `skew_control_vs_cloud_ms` | Control wall clock minus cloud (cloud→control hop; measured by control↔cloud `clock_sync` at connect) |
| `clock_sync_rtt_*_ms` | Optional RTT of the sync burst used to estimate skew |

Convention (same as `client/frontend/modules/time_sync.js`):

```text
skew_client_vs_master_ms = T_client - T_master
skew_cloud_vs_master_ms = T_cloud - T_master
skew_control_vs_cloud_ms = T_control - T_cloud

T_on_master_axis = T_iso_ms - skew_*_vs_master_ms
T_control_on_cloud_axis = T_control_iso_ms - skew_control_vs_cloud_ms
```

Segment latency (analysis):

- client→master: `master_receive - (client_send - skew_client_vs_master)`
- master→cloud: `(cloud_receive - master_send) - skew_cloud_vs_master`
- cloud→control: `(control_socket_receive - skew_control_vs_cloud) - cloud_send`

On connect (and when switching UDP/TCP on the relay), peers run `clock_sync_ping` / `clock_sync_ack` / `clock_sync_publish`:

- Master (TeleProgram) ↔ cloud relay → `skew_cloud_vs_master_ms` on forwarded `detection_state`
- Control ↔ cloud relay → `skew_control_vs_cloud_ms` on server `detection_state` log rows
- Browser ↔ master → `skew_client_vs_master_ms` on `detection_state` from the frontend

Local relay (`local_tcp`) also runs clock sync between master and control so control can log client skew from the wire.

**Local-only captures** (`local_tcp` / `local_udp`): `cloud_receive_time`, `cloud_send_time`, `skew_cloud_vs_master_ms`, and `skew_control_vs_cloud_ms` are typically omitted or null; only `skew_client_vs_master_ms` is required for client→master latency.

Analysis (`dataAnalysis/communication_latency.py`) reads skew from `detection_state` only (`require_clock_skew()`), then applies it to all `teleop_pose` rows. Legacy `*_clock_offset_ms` and `skew_control_vs_master_ms` are not supported.

Minimum required fields in `detections[*]`:

- `id` or `tag_id`
- `pose.t`
- `pose.R`

Optional fields:

- `pose_frame`
- `corners`
- `center`
- `decision_margin`
- `hamming`

## Snapshot Rules

After subscription, if `wants_snapshot=true`, the server sends the latest cached payloads in this order:

1. `master_stream_ready`
2. Latest `detection_state`, if available
3. Latest `initial_calibration`, if available
4. Latest `apriltag_detections`, if available

Then it continues streaming realtime incremental messages.

## Semantics

- The master does not compute pose deltas
- The master does not apply filtering, deadbanding, or frame transforms
- `apriltag_detections.detections[*].pose` must match the raw vision pose sent by the frontend
- If the control side needs control signals, it must:
  - choose `tag_id`
  - read `initial_calibration.mean_pose`
  - compute relative pose from current `apriltag_detections[*].pose`

## Control_AT Mapping

Suggested mapping for `control_AT`:

Subscription messages:
  - `slave_subscribe`
  - `slave_unsubscribe`
  - `master_stream_ready`

Data messages:
  - keep receiving `detection_state`
  - newly receive `initial_calibration`
  - keep receiving `apriltag_detections`
  - no longer expect `delta_frame`

## Migration Notes

When sending server-to-client messages, prefer using only the new message names:

- `master_stream_ready`
- `detection_state`
- `initial_calibration`
- `apriltag_detections`
