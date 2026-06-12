from datetime import datetime, timezone

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
