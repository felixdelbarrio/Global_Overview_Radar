"""Adaptadores de ingest para distintas fuentes (CSV, JSON, XLSX)."""

from bugresolutionradar.adapters.csv_adapter import FilesystemCSVAdapter
from bugresolutionradar.adapters.json_adapter import FilesystemJSONAdapter
from bugresolutionradar.adapters.xlsx_adapter import XlsxAdapter

__all__ = [
    "FilesystemCSVAdapter",
    "FilesystemJSONAdapter",
    "XlsxAdapter",
]
