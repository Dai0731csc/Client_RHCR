import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, cast

from ..models import CameraCalibrationResult, DeviceProfile
from .geo_service import UNKNOWN_REGION, lookup_region_for_host, resolve_device_region


DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "devices"
SAFE_FILENAME_PATTERN = re.compile(r"[^0-9A-Za-z_.-]+")

_host_region = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_client_ip(headers: Mapping[str, str], remote: Optional[str]) -> str:
    forwarded_for = headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()

    real_ip = headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()

    return remote or ""


def ensure_host_region() -> str:
    """Resolve and cache region for the computer running TeleProgram (not the phone browser)."""
    global _host_region
    if _host_region and _host_region != UNKNOWN_REGION:
        return _host_region
    _host_region = lookup_region_for_host()
    return _host_region


def get_host_region() -> str:
    return _host_region or UNKNOWN_REGION


def build_cloud_connect_headers() -> dict[str, str]:
    region = ensure_host_region()
    if region and region != UNKNOWN_REGION:
        return {"X-Region": region}
    return {}


def resolve_region(*, incoming: str, existing: str | None = None) -> str:
    incoming = (incoming or "").strip()
    existing = (existing or "").strip()
    if incoming and incoming != UNKNOWN_REGION:
        return incoming
    if existing and existing != UNKNOWN_REGION:
        return existing
    return UNKNOWN_REGION


def safe_device_filename(ip: str) -> str:
    name = SAFE_FILENAME_PATTERN.sub("_", ip.strip())
    name = name.strip("._")
    return f"{name or 'unknown'}.json"


class DeviceRegistry:
    def __init__(self, root: Path = DATA_ROOT):
        self.root = Path(root)

    def upsert_device(
        self,
        *,
        ip: str,
        region: str,
        calibration_result: Optional[CameraCalibrationResult] = None,
    ) -> DeviceProfile:
        path = self.root / safe_device_filename(ip)
        data = self._load(path)
        now = utc_now()

        data["ip"] = ip or data.get("ip") or "unknown"
        data["region"] = resolve_region(incoming=region, existing=data.get("region"))
        data["last_seen_at"] = now
        data.setdefault("first_seen_at", now)

        if calibration_result is not None:
            data["camera_calibration"] = calibration_result
            data["camera_calibration_updated_at"] = now
        else:
            data.setdefault("camera_calibration", None)
            data.setdefault("camera_calibration_updated_at", None)

        self._save(path, data)
        return data

    def update_from_request(
        self,
        request,
        *,
        calibration_result: Optional[CameraCalibrationResult] = None,
    ) -> DeviceProfile:
        ip = get_client_ip(request.headers, request.remote)
        region = resolve_device_region(headers=request.headers, ip=ip)
        return self.upsert_device(
            ip=ip,
            region=region,
            calibration_result=calibration_result,
        )

    def get_device(self, *, ip: str) -> DeviceProfile:
        path = self.root / safe_device_filename(ip)
        data = self._load(path)
        if not data.get("ip"):
            data["ip"] = ip or "unknown"
        if not data.get("region"):
            data["region"] = "unknown"
        return data

    def get_from_request(self, request) -> DeviceProfile:
        ip = get_client_ip(request.headers, request.remote)
        return self.get_device(ip=ip)

    def _load(self, path: Path) -> DeviceProfile:
        if not path.exists():
            return cast(DeviceProfile, {
                "version": 1,
                "ip": "unknown",
                "region": "unknown",
                "first_seen_at": None,
                "last_seen_at": None,
                "camera_calibration": None,
                "camera_calibration_updated_at": None,
            })

        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            data = {}

        if not isinstance(data, dict):
            data = {}

        data["version"] = 1
        data["ip"] = data.get("ip") or "unknown"
        data["region"] = data.get("region") or "unknown"
        data.setdefault("first_seen_at", None)
        data.setdefault("last_seen_at", None)
        data.setdefault("camera_calibration", None)
        data.setdefault("camera_calibration_updated_at", None)
        return cast(DeviceProfile, data)

    def _save(self, path: Path, data: DeviceProfile):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        tmp_path.replace(path)


device_store = DeviceRegistry()
