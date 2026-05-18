from datetime import datetime, timezone

TIMING_FIELD_NAMES = (
    "detectTag_start_time",
    "detectTag_end_time",
    "client_send_time",
    "client_clock_offset_ms",
    "client_clock_rtt_ms",
    "server_receive_time",
    "server_send_time",
    "cloud_receive_time",
    "cloud_send_time",
    "control_socket_receive_time",
)


def current_utc_iso_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def with_server_receive_time(payload):
    enriched_payload = dict(payload)
    enriched_payload["server_receive_time"] = current_utc_iso_timestamp()
    return enriched_payload


def with_server_send_time(payload):
    enriched_payload = dict(payload)
    enriched_payload["server_send_time"] = current_utc_iso_timestamp()
    return enriched_payload


def create_ack_payload(received):
    server_receive_time = current_utc_iso_timestamp()
    server_send_time = current_utc_iso_timestamp()
    return {
        "type": "ack",
        "server_receive_time": server_receive_time,
        "server_send_time": server_send_time,
        "received": received,
    }


def copy_timing_fields(payload):
    return {
        field_name: payload.get(field_name)
        for field_name in TIMING_FIELD_NAMES
        if field_name in payload
    }
