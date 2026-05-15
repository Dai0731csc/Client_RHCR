from dataclasses import dataclass
from typing import Literal, Union

from .cloud.link import CloudLink
from .frontend.link import FrontendLink
from .local.link import LocalLink

OutboundLinkName = Literal["local", "cloud"]
OutboundLink = Union[LocalLink, CloudLink]


@dataclass
class ClientLinks:
    """Three communication links: frontend (always), local and cloud (one active outbound)."""

    frontend: FrontendLink
    local: LocalLink
    cloud: CloudLink
    active_outbound: OutboundLinkName

    @property
    def outbound(self) -> OutboundLink:
        if self.active_outbound == "cloud":
            return self.cloud
        return self.local
