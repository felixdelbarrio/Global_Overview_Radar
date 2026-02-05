#!/usr/bin/env python3
"""Sync Jira session cookie from local browser into .env."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from bugresolutionradar.config import settings  # noqa: E402
from bugresolutionradar.user_settings import update_user_settings  # noqa: E402
from bugresolutionradar.utils.jira_cookie import (  # noqa: E402
    JiraCookieError,
    extract_domain,
    read_browser_cookie,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Jira cookie from browser.")
    parser.add_argument(
        "--browser",
        choices=["chrome", "edge", "firefox", "safari"],
        default="",
        help="Browser to read cookies from (default: auto).",
    )
    parser.add_argument(
        "--no-auth-mode",
        action="store_true",
        help="Do not force JIRA_AUTH_MODE=cookie.",
    )
    args = parser.parse_args()

    try:
        domain = extract_domain(settings.jira_base_url)
        cookie = read_browser_cookie(domain, args.browser or None)
        updates = {"jira.session_cookie": cookie}
        if not args.no_auth_mode:
            updates["jira.auth_mode"] = "cookie"
        update_user_settings(updates)
    except JiraCookieError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("JIRA_SESSION_COOKIE actualizado correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
