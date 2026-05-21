from datetime import datetime, timezone

TIMING_FIELD_NAMES = (
    "detectTag_start_time",
    "detectTag_end_time",
    "client_send_time",
    "master_receive_time",
    "master_send_time",
    "cloud_receive_time",
    "cloud_send_time",
    "control_socket_receive_time",
    "control_receive_time",
)


def current_utc_iso_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def with_master_receive_time(payload):
    enriched_payload = dict(payload)
    timestamp = current_utc_iso_timestamp()
    enriched_payload["master_receive_time"] = timestamp
    return enriched_payload


def with_master_send_time(payload):
    enriched_payload = dict(payload)
    timestamp = current_utc_iso_timestamp()
    enriched_payload["master_send_time"] = timestamp
    return enriched_payload


def create_ack_payload(received):
    master_receive_time = current_utc_iso_timestamp()
    master_send_time = current_utc_iso_timestamp()
    return {
        "type": "ack",
        "master_receive_time": master_receive_time,
        "master_send_time": master_send_time,
        "received": received,
    }


def copy_timing_fields(payload):
    return {
        field_name: payload.get(field_name)
        for field_name in TIMING_FIELD_NAMES
        if field_name in payload
    }
