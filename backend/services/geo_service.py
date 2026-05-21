import ipaddress
import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Mapping

logger = logging.getLogger(__name__)

UNKNOWN_REGION = "unknown"
IP_API_FIELDS = "status,message,countryCode,regionName,city"
IP_LOOKUP_CACHE_TTL_S = 6 * 60 * 60
TIMEZONE_REGION_PATTERN = re.compile(r"^[A-Za-z_]+/[A-Za-z0-9_+-]+$")

_ip_lookup_cache: dict[str, tuple[str, float]] = {}
_host_region_cache: str | None = None


def is_private_ip(ip: str) -> bool:
    value = (ip or "").strip()
    if not value:
        return True
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return True
    return bool(
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_multicast
    )


def format_geo_region(*, country_code: str, region_name: str = "", city: str = "") -> str:
    country = (country_code or "").strip().upper()
    city_name = (city or "").strip()
    subdivision = (region_name or "").strip()

    if country and city_name:
        return f"{country}-{city_name}"
    if country and subdivision:
        return f"{country}-{subdivision}"
    if country:
        return country
    return ""


def is_timezone_region_hint(region: str) -> bool:
    value = (region or "").strip()
    return bool(value and TIMEZONE_REGION_PATTERN.match(value))


def is_meaningful_region(region: str) -> bool:
    value = (region or "").strip()
    if not value or value == UNKNOWN_REGION:
        return False
    if is_timezone_region_hint(value):
        return False
    return True


def region_from_infrastructure_headers(headers: Mapping[str, str]) -> str:
    """Geo region from CDN / reverse-proxy headers (not client-supplied X-Region)."""
    country_region = headers.get("X-Vercel-IP-Country-Region", "").strip()
    country = headers.get("X-Vercel-IP-Country", "").strip()
    if country_region and country:
        return format_geo_region(country_code=country, region_name=country_region)
    if country_region:
        return country_region

    cf_country = headers.get("CF-IPCountry", "").strip()
    if cf_country and cf_country.upper() != "XX":
        return cf_country.upper()

    appengine_region = headers.get("X-AppEngine-Region", "").strip()
    appengine_country = headers.get("X-AppEngine-Country", "").strip()
    if appengine_country and appengine_region:
        return format_geo_region(
            country_code=appengine_country,
            region_name=appengine_region,
        )
    if appengine_region:
        return appengine_region
    if appengine_country:
        return appengine_country.upper()

    return ""


def lookup_region_for_host() -> str:
    """Resolve region for the machine running the client backend (outbound public IP)."""
    global _host_region_cache
    if _host_region_cache is not None:
        return _host_region_cache

    url = f"http://ip-api.com/json/?fields={IP_API_FIELDS}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=2.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError, urllib.error.URLError) as error:
        logger.debug("Host geolocation lookup failed: %s", error)
        _host_region_cache = UNKNOWN_REGION
        return UNKNOWN_REGION

    if not isinstance(payload, dict) or payload.get("status") != "success":
        _host_region_cache = UNKNOWN_REGION
        return UNKNOWN_REGION

    region = format_geo_region(
        country_code=str(payload.get("countryCode") or ""),
        region_name=str(payload.get("regionName") or ""),
        city=str(payload.get("city") or ""),
    )
    _host_region_cache = region if region else UNKNOWN_REGION
    return _host_region_cache


def lookup_region_from_ip(ip: str) -> str:
    value = (ip or "").strip()
    if not value or is_private_ip(value):
        return ""

    now = time.monotonic()
    cached = _ip_lookup_cache.get(value)
    if cached is not None:
        region, expires_at = cached
        if expires_at > now:
            return region
        _ip_lookup_cache.pop(value, None)

    url = f"http://ip-api.com/json/{value}?fields={IP_API_FIELDS}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=2.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError, urllib.error.URLError) as error:
        logger.debug("IP geolocation lookup failed for %s: %s", value, error)
        return ""

    if not isinstance(payload, dict) or payload.get("status") != "success":
        return ""

    region = format_geo_region(
        country_code=str(payload.get("countryCode") or ""),
        region_name=str(payload.get("regionName") or ""),
        city=str(payload.get("city") or ""),
    )
    if region:
        _ip_lookup_cache[value] = (region, now + IP_LOOKUP_CACHE_TTL_S)
    return region


def resolve_region(*, headers: Mapping[str, str], ip: str) -> str:
    region = region_from_infrastructure_headers(headers)
    if is_meaningful_region(region):
        return region

    ip_region = lookup_region_from_ip(ip)
    if ip_region:
        return ip_region

    client_region = (headers.get("X-Region") or "").strip()
    if is_meaningful_region(client_region):
        return client_region

    return UNKNOWN_REGION


def resolve_device_region(*, headers: Mapping[str, str], ip: str) -> str:
    """Region for persisting a browser device profile (backend-only, no frontend X-Region)."""
    region = region_from_infrastructure_headers(headers)
    if is_meaningful_region(region):
        return region

    ip_region = lookup_region_from_ip(ip)
    if ip_region:
        return ip_region

    if is_private_ip(ip):
        host_region = lookup_region_for_host()
        if is_meaningful_region(host_region):
            return host_region

    return UNKNOWN_REGION
