"""Adaptadores de ingest para distintas fuentes (CSV, JSON, XLSX)."""

from bbva_bugresolutionradar.adapters.csv_adapter import FilesystemCSVAdapter
from bbva_bugresolutionradar.adapters.json_adapter import FilesystemJSONAdapter
from bbva_bugresolutionradar.adapters.xlsx_adapter import XlsxAdapter

__all__ = [
    "FilesystemCSVAdapter",
    "FilesystemJSONAdapter",
    "XlsxAdapter",
]
