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

