from __future__ import annotations

import hashlib
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import openpyxl

from bbva_bugresolutionradar.adapters.filesystem import FilesystemAdapter
from bbva_bugresolutionradar.adapters.utils import to_date, to_str
from bbva_bugresolutionradar.domain.enums import Severity, Status
from bbva_bugresolutionradar.domain.models import ObservedIncident

if TYPE_CHECKING:
    # Import only for type checking to avoid runtime overhead
    from openpyxl.worksheet.worksheet import Worksheet


def _s(v: object) -> str:
    """String safe: convierte a str y nunca devuelve None."""
    return (to_str(v) or "").strip()


def _as_date(v: object) -> Optional[date]:
    """Normaliza a date usando to_date (devuelve date|None)."""
    return to_date(v)


def _clean_status_text(v: object) -> str:
    """
    Normaliza el texto de estatus:
    - convierte a str
    - quita emojis y caracteres raros
    - colapsa espacios
    """
    s = _s(v)
    # elimina símbolos tipo ✅ etc. (dejamos letras/números/espacios)
    s = re.sub(r"[^\w\sáéíóúüñÁÉÍÓÚÜÑ-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class XlsxAdapter(FilesystemAdapter):
    """
    XLSX adapter de filesystem.

    Versión robusta y genérica:
      - Recorre TODOS los .xlsx de ASSETS_DIR (sin depender del nombre del fichero).
      - Recorre TODAS las hojas de cada libro.
      - Detecta columnas por cabeceras (contains) en cada hoja.
      - Si falta id, genera source_key determinista.
      - Si falta fecha de incidente, usa columnas de fecha alternativas
        y, en último término, cualquier cabecera que contenga 'fecha'.
      - Usa columna 'estatus' cuando esté informada (con limpieza de texto).
      - Si el estado queda UNKNOWN, por defecto se considera OPEN.
      - No aborta si una hoja o un fichero no cumplen los mínimos → se ignoran.
    """

    def __init__(self, source_id: str, assets_root: str) -> None:
        super().__init__(source_id, assets_root)

    def read(self) -> List[ObservedIncident]:
        out: List[ObservedIncident] = []

        for path in sorted(self.assets_dir().glob("*.xlsx")):
            try:
                wb = openpyxl.load_workbook(path, data_only=True)
            except zipfile.BadZipFile:
                # fichero corrupto o no-xlsx renombrado
                print(
                    f"[XlsxAdapter] WARN: '{path.name}' no es un XLSX válido (BadZipFile). Se ignora."
                )
                continue

            for ws in wb.worksheets:
                out.extend(self._read_sheet(path, ws))

        return out

    def _read_sheet(self, path: Path, ws: "Worksheet") -> List[ObservedIncident]:
        """
        Lee una hoja cualquiera de un libro Excel, intentando mapearla al modelo ObservedIncident
        usando nombres de columna aproximados.
        """
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []

        headers: List[str] = [_s(h) for h in rows[0]]

        def idx_contains(*needles: str) -> Optional[int]:
            needles_l = [n.lower() for n in needles if n]
            for i, h in enumerate(headers):
                if not h:
                    continue
                hl = h.lower()
                if any(n in hl for n in needles_l):
                    return i
            return None

        # Campos clave
        col_id = idx_contains("id de reporte", "id reporte", "reporte id", "id", "ticket")

        col_opened = idx_contains(
            "fecha de incidente",
            "fecha incidente",
            "incidente",
            "fecha apertura",
        )
        col_opened_fallback = idx_contains(
            "fecha de reporte",
            "fecha reporte",
            "reporte a",
            "fecha alta",
            "fecha creación",
            "fecha creacion",
            "fecha de actualización",
            "fecha actualizacion",
            "updated",
            "update",
        )

        # Fallback muy genérico: cualquier cabecera que contenga 'fecha'
        if col_opened is None and col_opened_fallback is None:
            col_any_fecha = idx_contains("fecha")
            if col_any_fecha is not None:
                col_opened = col_any_fecha

        # Si AÚN así no hemos encontrado ninguna columna de fecha, esta hoja no sirve
        if col_opened is None and col_opened_fallback is None:
            return []

        col_status = idx_contains("estatus", "estado", "status")
        col_sev = idx_contains("criticidad", "severidad", "severity", "prioridad", "priority")
        col_title = idx_contains(
            "descripción",
            "descripcion",
            "detalle",
            "summary",
            "titulo",
            "título",
            "asunto",
            "mejora",  # para hojas de NPS / mejoras
        )
        col_feature = idx_contains("funcionalidad", "feature", "módulo", "modulo", "funcion")
        col_product = idx_contains(
            "tema", "canal", "producto", "product", "aplicacion", "aplicación"
        )

        observed_at = datetime.now().astimezone()
        out: List[ObservedIncident] = []

        def stable_auto_key(row_idx_1based: int, opened_at: Optional[date], title: str) -> str:
            basis = (
                f"{path.name}|{ws.title}|{row_idx_1based}|"
                f"{opened_at.isoformat() if opened_at else ''}|{title}"
            ).strip()
            h = hashlib.md5(basis.encode("utf-8")).hexdigest()[:12]
            return f"AUTO-{h}"

        for row_idx, r in enumerate(rows[1:], start=2):  # fila real Excel
            # Título
            title = _s(r[col_title]) if (col_title is not None and r[col_title] is not None) else ""

            # Fecha de apertura / incidente
            opened_at = (
                _as_date(r[col_opened])
                if (col_opened is not None and r[col_opened] is not None)
                else None
            )
            if (
                opened_at is None
                and col_opened_fallback is not None
                and r[col_opened_fallback] is not None
            ):
                opened_at = _as_date(r[col_opened_fallback])

            if opened_at is None:
                # sin fecha no tenemos forma de situar la incidencia en el tiempo
                continue

            # ID / clave de origen
            source_key = _s(r[col_id]) if (col_id is not None and r[col_id] is not None) else ""
            if not source_key:
                source_key = stable_auto_key(row_idx, opened_at, title)

            # Estatus: si está informado, manda; si no, OPEN por defecto
            status_raw: Optional[str] = None
            if col_status is not None and r[col_status] is not None:
                status_raw = _clean_status_text(r[col_status])

            status = _map_status(status_raw)

            # cualquier UNKNOWN pasa a OPEN (default de negocio)
            if status == Status.UNKNOWN:
                status = Status.OPEN

            # Severidad
            sev_raw = _s(r[col_sev]) if (col_sev is not None and r[col_sev] is not None) else None
            severity = _map_severity(sev_raw)

            # Producto / funcionalidad
            feature = (
                _s(r[col_feature])
                if (col_feature is not None and r[col_feature] is not None)
                else None
            )
            product = (
                _s(r[col_product])
                if (col_product is not None and r[col_product] is not None)
                else None
            )

            out.append(
                ObservedIncident(
                    source_id=self.source_id(),
                    source_key=source_key,
                    observed_at=observed_at,
                    title=title or "",
                    status=status,
                    severity=severity,
                    opened_at=opened_at,
                    closed_at=None,
                    updated_at=None,
                    clients_affected=None,
                    product=product or None,
                    feature=feature or None,
                    resolution_type=None,
                )
            )

        return out


def _map_status(raw: Optional[str]) -> Status:
    if not raw:
        return Status.UNKNOWN
    s = raw.strip().lower()

    # "resuelto", "resuelta", "solucionado", etc. -> CLOSED
    if "resuelto" in s or "resuelta" in s or "solucion" in s or "solucionad" in s:
        return Status.CLOSED

    if "abiert" in s or "open" in s:
        return Status.OPEN
    if "cerr" in s or "close" in s:
        return Status.CLOSED
    if "progreso" in s or "progress" in s:
        return Status.IN_PROGRESS
    if "bloque" in s or "block" in s:
        return Status.BLOCKED
    return Status.UNKNOWN


def _map_severity(raw: Optional[str]) -> Severity:
    if not raw:
        return Severity.UNKNOWN
    s = raw.strip().lower()
    if "crit" in s:
        return Severity.CRITICAL
    if "alta" in s or "high" in s:
        return Severity.HIGH
    if "media" in s or "med" in s:
        return Severity.MEDIUM
    if "baja" in s or "low" in s:
        return Severity.LOW
    return Severity.UNKNOWN
