import json
from datetime import datetime

from aiohttp import web

from ..services.calibration_service import (
    camera_calibration_available,
    run_camera_calibration,
    run_camera_calibration_validation,
)
from ..services.device_service import device_store
from ..services.stream_service import ingest_initial_calibration_payload


def _log(message):
    print(f"[TeleProgram] {message}")


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
            "master_time": datetime.now().isoformat(timespec="seconds"),
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
    if not camera_calibration_available():
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
        result = run_camera_calibration(board_type, metadata, image_bytes_list)
    except ValueError as error:
        error_code = (
            "insufficient_valid_images" if board_type == "chessboard" else "unsupported_board_type"
        )
        return web.json_response(
            {
                "success": False,
                "error": error_code,
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
        _log(f"camera calibration failed: {error}")
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
    device_store.update_from_request(request, calibration_result=result)
    return web.json_response(result)


async def camera_calibration_validate_handler(request):
    if not camera_calibration_available():
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
        result = run_camera_calibration_validation(image_bytes, metadata)
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
        _log(f"camera calibration validation failed: {error}")
        return web.json_response(
            {
                "success": False,
                "error": "validation_failed",
                "message": str(error),
            },
            status=500,
        )

    return web.json_response(result)
