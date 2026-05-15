import json
from datetime import datetime

from aiohttp import web

from .camera_calibration import (
    calibrate_apriltag_camera,
    calibrate_chessboard_camera,
    try_import_cv2,
    validate_chessboard_image,
)
from .master_stream import broadcast_master_payload
from .state import MASTER_LATEST_INITIAL_CALIBRATION_KEY


def _log(message):
    print(f"[TeleProgram] {message}")


def ingest_initial_calibration_payload(app, payload, *, source="websocket"):
    app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] = payload
    broadcast_master_payload(
        app,
        payload,
        add_server_send_time=True,
    )
    mean_pose = payload.get("mean_pose", {})
    mean_t = mean_pose.get("t")
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] calibration payload "
        f"({source}): tag_id={payload.get('tag_id')} "
        f"sample_count={payload.get('sample_count')} mean_t={mean_t}"
    )
    return payload

def _format_float(value, digits=3):
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return "n/a"


def _extract_nominal_frame_rate(metadata):
    camera_settings = metadata.get("camera_settings", {}) if isinstance(metadata, dict) else {}
    frame_rate = camera_settings.get("frameRate")
    if isinstance(frame_rate, (int, float)):
        return float(frame_rate)
    return None


async def calibration_publish_websocket_handler(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    client = request.remote
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] transport connected: "
        f"transport=websocket channel=calibration client={client}"
    )

    await ws.send_json(
        {
            "type": "calibration_publish_ready",
            "server_time": datetime.now().isoformat(timespec="seconds"),
        }
    )

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            try:
                payload = json.loads(msg.data)
            except json.JSONDecodeError:
                continue

            ingest_initial_calibration_payload(request.app, payload, source="websocket")
        elif msg.type == web.WSMsgType.ERROR:
            _log(f"calibration publish ws error: {ws.exception()}")

    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] transport disconnected: "
        f"transport=websocket channel=calibration client={client}"
    )
    return ws


async def camera_calibration_handler(request):
    if try_import_cv2() is None:
        return web.json_response(
            {
                "success": False,
                "error": "opencv_unavailable",
                "message": "OpenCV (cv2) is required for camera calibration on the server",
            },
            status=503,
        )

    if not request.content_type.startswith("multipart/"):
        return web.json_response(
            {
                "success": False,
                "error": "invalid_content_type",
                "message": "Expected multipart/form-data",
            },
            status=400,
        )

    reader = await request.multipart()
    metadata = None
    image_bytes_list = []

    async for field in reader:
        if field.name == "metadata":
            try:
                metadata = json.loads(await field.text())
            except json.JSONDecodeError:
                return web.json_response(
                    {
                        "success": False,
                        "error": "invalid_metadata",
                        "message": "metadata must be valid JSON",
                    },
                    status=400,
                )
            continue

        if field.name == "images":
            image_bytes = await field.read(decode=False)
            if image_bytes:
                image_bytes_list.append(image_bytes)

    if metadata is None:
        return web.json_response(
            {
                "success": False,
                "error": "missing_metadata",
                "message": "metadata field is required",
            },
            status=400,
        )

    board_type = metadata.get("board_type", "chessboard")

    if board_type == "chessboard" and not image_bytes_list:
        return web.json_response(
            {
                "success": False,
                "error": "missing_images",
                "message": "At least one image must be uploaded",
            },
            status=400,
        )

    try:
        if board_type == "chessboard":
            result = calibrate_chessboard_camera(image_bytes_list, metadata)
        elif board_type == "apriltag_single":
            result = calibrate_apriltag_camera(metadata)
        else:
            return web.json_response(
                {
                    "success": False,
                    "error": "unsupported_board_type",
                    "message": f"Unsupported calibration board type: {board_type}",
                },
                status=400,
            )
    except ValueError as error:
        return web.json_response(
            {
                "success": False,
                "error": "insufficient_valid_images",
                "message": str(error),
            },
            status=400,
        )
    except RuntimeError as error:
        return web.json_response(
            {
                "success": False,
                "error": "opencv_unavailable",
                "message": str(error),
            },
            status=503,
        )
    except Exception as error:
        return web.json_response(
            {
                "success": False,
                "error": "calibration_failed",
                "message": str(error),
            },
            status=500,
        )

    intrinsics = result.get("intrinsics", {})
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] camera calibration result: "
        f"board_type={result.get('board_type')} "
        f"valid={result.get('valid_image_count')}/{result.get('total_image_count')} "
        f"size={result.get('image_width')}x{result.get('image_height')} "
        f"nominal_fps={_format_float(_extract_nominal_frame_rate(result))} "
        f"rms={_format_float(result.get('rms'))} "
        f"reprojection_error={_format_float(result.get('reprojection_error'))} "
        f"fx={_format_float(intrinsics.get('fx'))} "
        f"fy={_format_float(intrinsics.get('fy'))} "
        f"cx={_format_float(intrinsics.get('cx'))} "
        f"cy={_format_float(intrinsics.get('cy'))}"
    )
    return web.json_response(result)


async def camera_calibration_validate_handler(request):
    if try_import_cv2() is None:
        return web.json_response(
            {
                "success": False,
                "error": "opencv_unavailable",
                "message": "OpenCV (cv2) is required for camera calibration on the server",
            },
            status=503,
        )

    if not request.content_type.startswith("multipart/"):
        return web.json_response(
            {
                "success": False,
                "error": "invalid_content_type",
                "message": "Expected multipart/form-data",
            },
            status=400,
        )

    reader = await request.multipart()
    metadata = None
    image_bytes = None

    async for field in reader:
        if field.name == "metadata":
            try:
                metadata = json.loads(await field.text())
            except json.JSONDecodeError:
                return web.json_response(
                    {
                        "success": False,
                        "error": "invalid_metadata",
                        "message": "metadata must be valid JSON",
                    },
                    status=400,
                )
            continue

        if field.name == "image" and image_bytes is None:
            image_bytes = await field.read(decode=False)

    if metadata is None:
        return web.json_response(
            {
                "success": False,
                "error": "missing_metadata",
                "message": "metadata field is required",
            },
            status=400,
        )

    if metadata.get("board_type", "chessboard") != "chessboard":
        return web.json_response(
            {
                "success": False,
                "error": "unsupported_board_type",
                "message": "Only chessboard validation is supported",
            },
            status=400,
        )

    if not image_bytes:
        return web.json_response(
            {
                "success": False,
                "error": "missing_image",
                "message": "image field is required",
            },
            status=400,
        )

    try:
        result = validate_chessboard_image(image_bytes, metadata)
    except RuntimeError as error:
        return web.json_response(
            {
                "success": False,
                "error": "opencv_unavailable",
                "message": str(error),
            },
            status=503,
        )
    except Exception as error:
        return web.json_response(
            {
                "success": False,
                "error": "validation_failed",
                "message": str(error),
            },
            status=500,
        )

    return web.json_response(result)
