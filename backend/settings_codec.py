from __future__ import annotations

from typing import Any, Mapping


def as_bool(value, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def resolve_status_selection(selections, *, selection_name: str, fallback: str) -> str:
    if isinstance(selections, Mapping):
        enabled_items: list[str] = []
        for item_id, item_data in selections.items():
            status = item_data.get("status") if isinstance(item_data, Mapping) else item_data
            if as_bool(status, default=False):
                enabled_items.append(str(item_id).strip())

        enabled_items = [item_id for item_id in enabled_items if item_id]
        if len(enabled_items) > 1:
            raise ValueError(
                f"{selection_name} has multiple entries with status=true: "
                + ", ".join(enabled_items)
            )
        if len(enabled_items) == 1:
            return enabled_items[0]

    return fallback


def normalize_transport_modes(
    raw_modes: Any,
    *,
    supported_transport_modes,
    default_transport_modes,
) -> dict[str, bool]:
    if isinstance(raw_modes, Mapping):
        base = {key: False for key in supported_transport_modes}
        for key in supported_transport_modes:
            if key in raw_modes:
                value = raw_modes.get(key)
                status = value.get("status") if isinstance(value, Mapping) else value
                base[key] = as_bool(status, default=False)
        return base
    return {
        key: bool(default_transport_modes.get(key))
        for key in supported_transport_modes
    }


def transport_modes_for_mode(
    mode: str,
    *,
    supported_transport_modes,
) -> dict[str, bool]:
    if mode not in supported_transport_modes:
        raise ValueError(f"Unsupported transport_mode={mode!r}")
    return {key: key == mode for key in supported_transport_modes}
