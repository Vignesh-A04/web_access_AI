"""Navigation utilities with redirect revalidation and SSRF protection."""

from typing import Optional, Set, Tuple
from playwright.async_api import Page, Response

from app.logging.setup import get_logger
from app.security.url_policy import validate_url_security

logger = get_logger("navigation")


class NavigationSecurityError(Exception):
    """Raised when navigation or redirect violates security policy."""
    pass


async def navigate_to_url(
    page: Page,
    url: str,
    allow_local_test: bool = False,
    domain_restrictions: Optional[Set[str]] = None,
    timeout_ms: int = 20000,
) -> Tuple[str, int]:
    """Navigate to an approved URL, inspect response, and verify the post-redirect destination.

    Returns:
        (final_url, status_code)
    """
    # 1. Pre-navigation security check
    valid, reason = validate_url_security(
        url,
        allow_local_test=allow_local_test,
        domain_allowlist=domain_restrictions,
    )
    if not valid:
        raise NavigationSecurityError(f"Target URL rejected by security policy: {reason}")

    logger.info(f"Navigating to {url}", extra={"url": url})
    response: Optional[Response] = await page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=timeout_ms,
    )

    final_url = page.url

    # 2. Post-redirect destination security check
    valid_dest, dest_reason = validate_url_security(
        final_url,
        allow_local_test=allow_local_test,
        domain_allowlist=domain_restrictions,
    )
    if not valid_dest:
        # Destination after redirects violated security! Abort immediately
        logger.error(f"Post-redirect URL {final_url} violated security policy: {dest_reason}")
        await page.goto("about:blank")
        raise NavigationSecurityError(f"Post-redirect destination {final_url} is prohibited: {dest_reason}")

    status = response.status if response else 200
    return final_url, status
