"""Unit tests for URL and network SSRF security policy."""

import pytest
from app.security.url_policy import validate_url_security, is_ip_prohibited
import ipaddress


def test_valid_https_url():
    valid, reason = validate_url_security("https://example.com/test", allow_local_test=False)
    assert valid is True
    assert reason == ""


def test_reject_prohibited_schemes():
    for scheme in ["ftp://example.com", "file:///etc/passwd", "javascript:alert(1)", "data:text/html,test"]:
        valid, reason = validate_url_security(scheme, allow_local_test=False)
        assert valid is False
        assert "scheme" in reason.lower()


def test_reject_private_ip_destinations():
    for private_url in [
        "http://10.0.0.1/admin",
        "http://192.168.1.100/router",
        "http://172.16.0.5/api",
    ]:
        valid, reason = validate_url_security(private_url, allow_local_test=False)
        assert valid is False
        assert "prohibited" in reason.lower()


def test_loopback_rejection_default():
    valid, reason = validate_url_security("http://127.0.0.1:8000/api", allow_local_test=False)
    assert valid is False
    assert "prohibited" in reason.lower()


def test_loopback_allowed_in_local_test_mode():
    valid, reason = validate_url_security("http://127.0.0.1:8000/test-site", allow_local_test=True)
    assert valid is True
    assert reason == ""

    valid_localhost, _ = validate_url_security("http://localhost:8000/test-site", allow_local_test=True)
    assert valid_localhost is True


def test_reject_cloud_metadata_endpoints():
    for meta_url in [
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
    ]:
        valid, reason = validate_url_security(meta_url, allow_local_test=False)
        assert valid is False
        assert "metadata" in reason.lower() or "prohibited" in reason.lower()


def test_domain_allowlist_enforcement(monkeypatch):
    allowlist = {"example.com", "trusted-service.org"}
    # Allowed
    valid, _ = validate_url_security("https://example.com/page", domain_allowlist=allowlist)
    assert valid is True

    valid_sub, _ = validate_url_security("https://www.example.com/page", domain_allowlist=allowlist)
    assert valid_sub is True

    # Denied by domain allowlist
    valid_denied, reason = validate_url_security("https://untrusted-site.com/page", domain_allowlist=allowlist)
    assert valid_denied is False
    assert "allowlist" in reason.lower()

