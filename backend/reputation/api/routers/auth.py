from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends

from reputation.auth import AuthUser, require_google_user
from reputation.config import reload_reputation_settings


def _refresh_settings() -> None:
    reload_reputation_settings()


router = APIRouter(dependencies=[Depends(_refresh_settings)])


@router.get("/me")
def auth_me(user: AuthUser = Depends(require_google_user)) -> dict[str, Any]:  # noqa: B008
    return {
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "subject": user.subject,
    }


@router.get("/runtime")
def auth_runtime() -> dict[str, Any]:
    """Expose minimal runtime flags needed by the frontend.

    Intentionally unauthenticated so the UI can decide what to render even when
    auth is bypassed.
    """
    # Cloud Run sets K_SERVICE.
    is_cloud_run = bool(os.environ.get("K_SERVICE"))

    google_cloud_login_requested = (
        os.environ.get("GOOGLE_CLOUD_LOGIN_REQUESTED", "true").strip().lower() == "true"
    )

    return {
        "is_cloud_run": is_cloud_run,
        "google_cloud_login_requested": google_cloud_login_requested,
    }
