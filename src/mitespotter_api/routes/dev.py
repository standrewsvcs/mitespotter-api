"""
src/mitespotter_api/routes/dev.py
Developer test page: one HTML page for trying every account flow from a phone

It only calls the public API, so it grants nothing the API doesn't. Registered
only when config.dev_page is on (MITESPOTTER_DEV_PAGE); otherwise /api/dev is 404.

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import html
import secrets


from litestar import Response, get
from litestar.di import NamedDependency
from litestar.enums import MediaType
from litestar.params import FromQuery


from ..config import Config
from ..messages import messages


def notice(message_key: str | None) -> str:
    """A known messages.toml key (from a redirect such as Google's) as an escaped paragraph; anything else, nothing"""
    if not message_key or message_key not in messages.keys():
        return ""
    return f'<p class="notice" role="status">{html.escape(getattr(messages, message_key))}</p>'


def render(config: Config, nonce: str, message_key: str | None = None) -> str:
    """The template with this request's nonce, the CSRF names and any notice filled in"""
    page = config.dev_page_template.read_text(encoding="utf-8")
    for key, value in {
        "notice": notice(message_key),
        "nonce": nonce,
        "csrf_cookie": config.csrf_cookie_name,
        "csrf_header": config.csrf_header_name,
    }.items():
        page = page.replace(f"{{{{{key}}}}}", value)
    return page


def security_headers(nonce: str) -> dict[str, str]:
    """Only this page's own inline script and style run; nothing else loads, frames or leaks"""
    csp = "; ".join((
        "default-src 'none'",
        f"script-src 'nonce-{nonce}'",
        f"style-src 'nonce-{nonce}'",
        "connect-src 'self'",
        "img-src 'self'",
        "form-action 'self'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
    ))
    return {
        "Content-Security-Policy": csp,
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }


@get("/dev", include_in_schema=False)
async def dev_page(config: NamedDependency[Config], message: FromQuery[str | None] = None) -> Response[str]:
    nonce = secrets.token_urlsafe(18)
    return Response(render(config, nonce, message), media_type=MediaType.HTML, headers=security_headers(nonce))
