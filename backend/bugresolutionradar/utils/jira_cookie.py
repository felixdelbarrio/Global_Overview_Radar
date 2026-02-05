"""Helpers to load Jira session cookies from local browsers."""

from __future__ import annotations

from typing import Callable, Iterable
from urllib.parse import urlsplit


class JiraCookieError(RuntimeError):
    pass


def extract_domain(base_url: str) -> str:
    value = (base_url or "").strip()
    if not value:
        raise JiraCookieError("JIRA_BASE_URL is required to read browser cookies.")
    if "://" not in value:
        value = f"https://{value}"
    parts = urlsplit(value)
    host = parts.hostname or parts.netloc
    if not host:
        raise JiraCookieError("Invalid JIRA_BASE_URL; could not determine host.")
    return host


def _domain_matches(cookie_domain: str | None, target_domain: str) -> bool:
    if not cookie_domain:
        return True
    cookie_domain = cookie_domain.lstrip(".").lower()
    target = target_domain.lower()
    return target == cookie_domain or target.endswith(f".{cookie_domain}")


def _cookie_header_from_jar(jar: Iterable[object], domain: str) -> str:
    cookies: dict[str, str] = {}
    for entry in jar:
        name = getattr(entry, "name", None)
        value = getattr(entry, "value", None)
        cookie_domain = getattr(entry, "domain", None)
        if not name or value is None:
            continue
        if not _domain_matches(str(cookie_domain) if cookie_domain else None, domain):
            continue
        cookies[name] = str(value)
    if not cookies:
        return ""
    return "; ".join(f"{key}={val}" for key, val in cookies.items())


def read_browser_cookie(domain: str, browser: str | None = None) -> str:
    try:
        import browser_cookie3  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - depends on local env
        raise JiraCookieError(
            "browser-cookie3 no está instalado. Instálalo con `pip install -r requirements.txt`."
        ) from exc

    browser_key = (browser or "").strip().lower()
    CookieLoader = Callable[..., Iterable[object]]
    loaders: list[tuple[str, CookieLoader]] = []

    def add_loader(name: str, fn: CookieLoader) -> None:
        if not browser_key or browser_key == name:
            loaders.append((name, fn))

    if hasattr(browser_cookie3, "chrome"):
        add_loader("chrome", browser_cookie3.chrome)
    if hasattr(browser_cookie3, "edge"):
        add_loader("edge", browser_cookie3.edge)
    if hasattr(browser_cookie3, "firefox"):
        add_loader("firefox", browser_cookie3.firefox)
    if hasattr(browser_cookie3, "safari"):
        add_loader("safari", browser_cookie3.safari)

    if not loaders:
        raise JiraCookieError(
            f"Unsupported browser '{browser}'. "
            "Usa chrome, edge, firefox o safari."
        )

    errors: list[str] = []
    for name, loader in loaders:
        try:
            jar = loader(domain_name=domain)
            cookie = _cookie_header_from_jar(jar, domain)
            if cookie:
                return cookie
            errors.append(f"{name}: no cookies")
        except Exception as exc:  # pragma: no cover - depends on local env
            errors.append(f"{name}: {exc}")

    error_detail = "; ".join(errors) if errors else "sin detalles"
    raise JiraCookieError(f"No se encontraron cookies para {domain}. ({error_detail})")
