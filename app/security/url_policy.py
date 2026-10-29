"""URL Security Policy for SSRF and prohibited destination defense."""

import ipaddress
import socket
import urllib.parse
from typing import List, Optional, Set, Tuple

# Cloud metadata services to block explicitly
PROHIBITED_METADATA_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.internal",
    "100.100.100.200",
}

# Permitted schemes
ALLOWED_SCHEMES = {"http", "https"}


def is_ip_prohibited(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> Tuple[bool, str]:
    """Check if an IP address belongs to private, loopback, link-local, multicast or reserved ranges."""
    if ip.is_loopback:
        return True, f"Loopback IP {ip} is prohibited"
    if ip.is_private:
        return True, f"Private IP {ip} is prohibited"
    if ip.is_link_local:
        return True, f"Link-local IP {ip} is prohibited"
    if ip.is_multicast:
        return True, f"Multicast IP {ip} is prohibited"
    if ip.is_reserved:
        return True, f"Reserved IP {ip} is prohibited"
    if ip.is_unspecified:
        return True, f"Unspecified IP {ip} is prohibited"
    if str(ip) in PROHIBITED_METADATA_HOSTS:
        return True, f"Cloud metadata endpoint IP {ip} is prohibited"
    return False, ""


def resolve_hostname_ips(hostname: str) -> List[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a hostname to all associated IP addresses safely."""
    ips = []
    # Try direct IP parsing first
    try:
        ip = ipaddress.ip_address(hostname.strip("[]"))
        return [ip]
    except ValueError:
        pass

    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for entry in addr_info:
            sockaddr = entry[4]
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                if ip not in ips:
                    ips.append(ip)
            except ValueError:
                continue
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for hostname '{hostname}': {e}") from e

    if not ips:
        raise ValueError(f"Could not resolve any IP address for hostname '{hostname}'")
    return ips


def validate_url_security(
    url: str,
    allow_local_test: bool = False,
    domain_allowlist: Optional[Set[str]] = None,
) -> Tuple[bool, str]:
    """Validate a URL against SSRF, prohibited IP ranges, scheme restrictions, and domain allowlists.

    Returns:
        (is_valid, reason): True and empty string if valid; False and explanation if prohibited.
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string"

    url = url.strip()
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception as e:
        return False, f"Malformed URL: {e}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return False, f"Prohibited URL scheme '{scheme}'. Only HTTP and HTTPS are permitted."

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "URL must have a valid hostname."

    # Check cloud metadata names
    if hostname in PROHIBITED_METADATA_HOSTS:
        return False, f"Prohibited cloud metadata hostname '{hostname}'"

    # Allow local test mode for local testing if explicitly enabled
    if allow_local_test and (hostname in {"127.0.0.1", "localhost", "::1"} or hostname.endswith(".local")):
        # Permitted for local test server
        return True, ""

    # Check domain allowlist if configured
    if domain_allowlist:
        matched = False
        for allowed in domain_allowlist:
            allowed_clean = allowed.lower().strip()
            if hostname == allowed_clean or hostname.endswith("." + allowed_clean):
                matched = True
                break
        if not matched:
            return False, f"Hostname '{hostname}' is not in the configured domain allowlist: {sorted(list(domain_allowlist))}"

    # Resolve and validate DNS against private/prohibited ranges
    try:
        resolved_ips = resolve_hostname_ips(hostname)
    except ValueError as e:
        return False, str(e)

    for ip in resolved_ips:
        prohibited, reason = is_ip_prohibited(ip)
        if prohibited:
            if allow_local_test and ip.is_loopback:
                continue
            return False, f"Resolved destination IP {ip} for {hostname} is prohibited: {reason}"

    return True, ""
