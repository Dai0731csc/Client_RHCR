"""Client links facade (lazy: importing pose_protocol alone does not load cloud TCP/WSS stack)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

LINKS_KEY = "client_links"

__all__ = [
    "LINKS_KEY",
    "ClientLinks",
    "CloudLink",
    "FrontendLink",
    "LocalLink",
    "MASTER_STREAM_PROTOCOL",
    "OutboundLink",
    "OutboundLinkName",
    "get_links",
]

if TYPE_CHECKING:
    from .registry import ClientLinks


def get_links(app) -> ClientLinks:
    from .registry import ClientLinks

    links = app.get(LINKS_KEY)
    if links is None:
        raise RuntimeError("client links are not installed")
    return links


def __getattr__(name: str) -> Any:
    if name == "ClientLinks":
        from .registry import ClientLinks

        return ClientLinks
    if name == "OutboundLink":
        from .registry import OutboundLink

        return OutboundLink
    if name == "OutboundLinkName":
        from .registry import OutboundLinkName

        return OutboundLinkName
    if name == "CloudLink":
        from .cloud.link import CloudLink

        return CloudLink
    if name == "FrontendLink":
        from .frontend.link import FrontendLink

        return FrontendLink
    if name == "LocalLink":
        from .local.link import LocalLink

        return LocalLink
    if name == "MASTER_STREAM_PROTOCOL":
        from .pose_protocol import MASTER_STREAM_PROTOCOL

        return MASTER_STREAM_PROTOCOL
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
