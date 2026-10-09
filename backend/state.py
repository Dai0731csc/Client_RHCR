MASTER_LATEST_INITIAL_CALIBRATION_KEY = "master_latest_initial_calibration"
MASTER_LATEST_APRILTAG_PAYLOAD_KEY = "master_latest_apriltag_payload"
MASTER_LATEST_DETECTION_STATE_KEY = "master_latest_detection_state"
GRIPPER_COMMAND_TRANSPORT_KEY = "gripper_command_transport"
GRIPPER_COMMAND_PROTOCOL_KEY = "gripper_command_protocol"
MASTER_SLAVE_PEERS_KEY = "master_slave_peers"
MASTER_UDP_TRANSPORT_KEY = "master_udp_transport"
MASTER_UDP_PROTOCOL_KEY = "master_udp_protocol"
MASTER_UDP_SEQUENCE_KEY = "master_udp_sequence"
MASTER_CLOUD_TRANSPORT_KEY = "master_cloud_transport"
MASTER_CLOUD_PUMP_TASK_KEY = "master_cloud_pump_task"
MASTER_LOCAL_RELAY_PEERS_KEY = "master_local_relay_peers"
MASTER_LOCAL_RELAY_CONTROL_KEY = "master_local_relay_control"
MASTER_LOCAL_UDP_CONTROL_KEY = "master_local_udp_control"
WEBRTC_PEER_CONNECTIONS_KEY = "webrtc_peer_connections"
FULL_CHAIN_TIME_SYNC_CAPTURE_SNAPSHOT_KEY = "full_chain_time_sync_capture_snapshot"
FULL_CHAIN_TIME_SYNC_COORDINATOR_KEY = "full_chain_time_sync_coordinator"

APP_STATE_DEFAULTS = {
    MASTER_LATEST_INITIAL_CALIBRATION_KEY: None,
    MASTER_LATEST_APRILTAG_PAYLOAD_KEY: None,
    MASTER_LATEST_DETECTION_STATE_KEY: None,
    GRIPPER_COMMAND_TRANSPORT_KEY: None,
    GRIPPER_COMMAND_PROTOCOL_KEY: None,
    MASTER_SLAVE_PEERS_KEY: dict,
    MASTER_UDP_TRANSPORT_KEY: None,
    MASTER_UDP_PROTOCOL_KEY: None,
    MASTER_UDP_SEQUENCE_KEY: 0,
    MASTER_CLOUD_TRANSPORT_KEY: None,
    MASTER_CLOUD_PUMP_TASK_KEY: None,
    MASTER_LOCAL_RELAY_PEERS_KEY: dict,
    MASTER_LOCAL_RELAY_CONTROL_KEY: None,
    MASTER_LOCAL_UDP_CONTROL_KEY: None,
    WEBRTC_PEER_CONNECTIONS_KEY: set,
    FULL_CHAIN_TIME_SYNC_CAPTURE_SNAPSHOT_KEY: None,
    FULL_CHAIN_TIME_SYNC_COORDINATOR_KEY: None,
}


def init_app_state(app):
    for key, default in APP_STATE_DEFAULTS.items():
        app[key] = default() if callable(default) else default
