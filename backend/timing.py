TIMING_FIELD_NAMES = (
    "detectTag_start_time",
    "detectTag_end_time",
    "client_send_time",
    "client_clock_offset_ms",
    "client_clock_rtt_ms",
    "server_receive_time",
    "server_send_time",
)


def copy_timing_fields(payload):
    return {
        field_name: payload.get(field_name)
        for field_name in TIMING_FIELD_NAMES
        if field_name in payload
    }

