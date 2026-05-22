from datetime import datetime
from typing import Any, Mapping, cast

from scipy.spatial.transform import Rotation as R

from ..models import AprilTagDetectionsPayload, DetectionStatePayload, InitialCalibrationPayload
from ..state import (
    MASTER_LATEST_APRILTAG_PAYLOAD_KEY,
    MASTER_LATEST_DETECTION_STATE_KEY,
    MASTER_LATEST_INITIAL_CALIBRATION_KEY,
)
from ..links import get_links
from ..utils import with_server_receive_time
#New!
import numpy as np
from scipy.spatial.transform import Rotation as R
#
def _log(message):
    print(f"[TeleProgram] {message}")


def _broadcast(app, payload, *, add_server_send_time=False):
    get_links(app).outbound.broadcast_pose(
        app,
        payload,
        add_server_send_time=add_server_send_time,
    )


def get_detection_tag_id(detection: Mapping[str, Any] | None):
    if not isinstance(detection, dict):
        return None

    detection_tag_id = detection.get("tag_id")
    if detection_tag_id is not None:
        return detection_tag_id
    return detection.get("id")


def format_numeric_vector(values):
    if values is None:
        return "n/a"
    values = list(values)
    if len(values) == 0:
        return "n/a"
    return "[" + ", ".join(f"{float(value):.2f}" for value in values) + "]"


def ingest_initial_calibration_payload(
    app,
    payload: InitialCalibrationPayload,
    *,
    source="websocket",
) -> InitialCalibrationPayload:
    app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] = payload
    _broadcast(app, payload, add_server_send_time=True)
    mean_pose = payload.get("mean_pose", {})
    mean_t = mean_pose.get("t")
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] calibration payload "
        f"({source}): tag_id={payload.get('tag_id')} "
        f"sample_count={payload.get('sample_count')} mean_t={mean_t}"
    )
    return payload

#New
# 工具函数：将任意矩阵投影为合法旋转矩阵（右手系、det=1、正交）    
def make_valid_rot_mat(R_mat):
    R_mat = np.array(R_mat)
    U, _, Vt = np.linalg.svd(R_mat)
    R_proj = U @ Vt
    return R_proj

async def ingest_apriltag_payload(app, payload: dict[str, Any], *, source="websocket"):
    payload = with_server_receive_time(payload)
    message_type = payload.get("type")

    if message_type == "detection_state":
        detection_state_payload = cast(DetectionStatePayload, payload)
        app[MASTER_LATEST_DETECTION_STATE_KEY] = detection_state_payload
        _broadcast(app, detection_state_payload, add_server_send_time=True)
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] detection state "
            f"({source}): active={bool(detection_state_payload.get('active', False))} "
            f"fps={detection_state_payload.get('nominal_frame_rate')} "
            f"frame_size={detection_state_payload.get('frame_size')}"
        )
        return detection_state_payload

    if message_type != "apriltag_detections":
        return payload

    latest_detection_state = app[MASTER_LATEST_DETECTION_STATE_KEY] or {}
    master_payload = cast(AprilTagDetectionsPayload, {
        **payload,
        "nominal_frame_rate": payload.get(
            "nominal_frame_rate",
            latest_detection_state.get("nominal_frame_rate"),
        ),
        "frame_size": payload.get("frame_size", latest_detection_state.get("frame_size")),
    })
    app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] = master_payload
    _broadcast(app, master_payload, add_server_send_time=True)

    detections = master_payload.get("detections") or []
    detection_summaries = []

    # ========== 新增：长方体尺寸 & ID偏移映射 ==========
    W = 0.15   # 左右宽(m)，改成你实际值
    H = 0.265   # 上下高(m)
    L = 0.155   # 前后长(m)
    half_W = W / 2
    half_H = H / 2
    half_L = L / 2
    import numpy as np
    # 每个tag：(Ti在刚体B下旋转矩阵R_Ti_B, Ti在刚体B下平移t_Ti_B)
    tag_ti2body = {
    # 0 正面朝前
    0: (
        np.array([[0,0,1],[1,0,0],[0,1,0]]),
        [half_L, 0, 0]
    ),
    # 1 左侧面朝左
    1: (
        np.array([[0,1,0],[0,0,-1],[1,0,0]]),
        [0, -half_W, 0]
    ),
    # 2 顶面朝上
    2: (
        np.array([[0,1,0],[1,0,0],[0,0,1]]),
        [0, 0, half_H]
    ),
    # 3 右侧面朝右
    3: (
        np.array([[0,1,0],[0,0,1],[1,0,0]]),
        [0, half_W, 0]
    ),
    # 4 背面朝后
    4: (
        np.array([[0,0,-1],[1,0,0],[0,1,0]]),
        [-half_L, 0, 0]
    )
    }
    # 新建空列表，存每个标签算出的【刚体B在相机C下的平移】
    cam_t_in_body_list = []
    cam_R_in_body_list = []

    for detection in detections:
        detection_tag_id = get_detection_tag_id(detection)
        pose = detection.get("pose") or {}
        #New!
        t_camera_in_tag = pose.get('t')
        R_camera_in_tag = pose.get('R')
        # 1. 转numpy数组
        R_C_Ti = np.array(R_camera_in_tag)
        t_C_Ti = np.array(t_camera_in_tag)

        # 2. 取出提前定义好的 Ti 相对刚体 B 的旋转、平移
        R_Ti_B, t_Ti_B = tag_ti2body[detection_tag_id]

        # 3. 套公式：求 刚体B 在 相机C 下的位姿
        R_C_B = R_C_Ti@ R_Ti_B
        t_C_B=R_C_Ti@t_Ti_B+t_C_Ti
        # 4. 存入列表，后续融合
        cam_t_in_body_list.append(t_C_B)
        cam_R_in_body_list.append(R_C_B)
        #    
        detection_summaries.append(
            f"tag_id={detection_tag_id} "
            #f"t={format_numeric_vector(pose.get('t'))} "
            f"t_C_B={format_numeric_vector(t_C_B)} "
            f"R_C_B={(R_C_B)} "
            #f"euler_xyz_deg={format_numeric_vector(R.from_matrix(pose.get('R')).as_euler('xyz', degrees=True)) if pose.get('R') else 'n/a'}"
        )
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] apriltag packet received "
        f"({source}, count={len(detections)}, detections={detection_summaries})"
    )
    #New!
    #width w height h length l
    # ===================== 你原来的代码不动，只在这里加旋转融合 =====================
    final_cam_in_body_t = None
    final_cam_in_body_R = None  # 新增：融合后的旋转
    num = len(cam_t_in_body_list)

    
    
    # 平移融合（你原来的写法 100% 保留）
    if num == 1:
        final_cam_in_body_t = cam_t_in_body_list[0]
        final_cam_in_body_R = cam_R_in_body_list[0]
    


# ---------------------- 你的主逻辑（变量名完全不变） ----------------------
    elif num == 2:
        final_cam_in_body_t = (cam_t_in_body_list[0] + cam_t_in_body_list[1]) / 2

        # 直接用你的 cam_R_in_body_list
        R1 = make_valid_rot_mat(cam_R_in_body_list[0])
        R2 = make_valid_rot_mat(cam_R_in_body_list[1])

        q1 = R.from_matrix(R1).as_quat()
        q2 = R.from_matrix(R2).as_quat()

        q_sum = q1 + q2
        q_mean = q_sum / np.linalg.norm(q_sum)

        final_cam_in_body_R = R.from_quat(q_mean).as_matrix()

    elif num == 3:
        final_cam_in_body_t = sum(cam_t_in_body_list) / 3

        # 直接用你的 cam_R_in_body_list
        R1 = make_valid_rot_mat(cam_R_in_body_list[0])
        R2 = make_valid_rot_mat(cam_R_in_body_list[1])
        R3 = make_valid_rot_mat(cam_R_in_body_list[2])

        q1 = R.from_matrix(R1).as_quat()
        q2 = R.from_matrix(R2).as_quat()
        q3 = R.from_matrix(R3).as_quat()

        q_avg = q1 + q2 + q3
        q_avg /= np.linalg.norm(q_avg)

        final_cam_in_body_R = R.from_quat(q_avg).as_matrix()

    # 存入全局（平移 + 旋转 都存）
    if final_cam_in_body_t is not None:
        app["camera_in_body_trans"] = final_cam_in_body_t.tolist()
    if final_cam_in_body_R is not None:
        app["camera_in_body_rot"] = final_cam_in_body_R.tolist()

    return master_payload
