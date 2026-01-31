"""Enums de dominio para severidad y estado de incidencias."""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    """Niveles de severidad estandarizados."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class Status(str, Enum):
    """Estados de vida de una incidencia."""

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"
