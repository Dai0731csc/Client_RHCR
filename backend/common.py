from datetime import datetime, timezone


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
