# Raw Pose Stream Protocol

The new `TeleProgram(master) -> control_AT(slave)` protocol only sends raw poses. It does not send `delta_frame` or `delta_pose_robot`.

Goals:

- The master only forwards and caches raw vision data
- The control side computes control signals from `initial_calibration + apriltag_detections`
- Message names no longer use `delta_*`

## Transport

- Transport: `UDP`
- Default bind: `0.0.0.0:9001`
- Encoding: `UTF-8 JSON`
- Direction:
  - slave -> master: subscribe / unsubscribe
  - master -> slave: ready / snapshot / stream payloads

## Version

All messages include:

```json
{
  "protocol": "rhcr-oulu.raw-pose-stream"
}
```

## Client To Server

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

## Server To Client

### `master_stream_ready`

Returned after the subscription is established.

```json
{
  "type": "master_stream_ready",
  "protocol": "rhcr-oulu.raw-pose-stream",
  "server_time": "2026-04-23T10:00:00.010Z",
  "transport": "udp",
  "has_detection_state": true,
  "has_initial_calibration": true,
  "has_apriltag_detections": true
}
```

### `detection_state`

Indicates whether vision detection is currently active.

```json
{
  "type": "detection_state",
  "protocol": "rhcr-oulu.raw-pose-stream",
  "transport": "udp",
  "master_seq": 101,
  "active": true,
  "client_send_time": "2026-04-23T10:00:00.100Z",
  "server_receive_time": "2026-04-23T10:00:00.120Z",
  "server_send_time": "2026-04-23T10:00:00.121Z",
  "client_clock_offset_ms": -3.2,
  "client_clock_rtt_ms": 9.8,
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
  "client_clock_offset_ms": -3.2,
  "client_clock_rtt_ms": 9.8,
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
  "server_receive_time": "2026-04-23T10:00:01.130Z",
  "server_send_time": "2026-04-23T10:00:01.131Z",
  "client_clock_offset_ms": -3.2,
  "client_clock_rtt_ms": 9.8,
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
