"""Contrato base de adaptadores de ingest."""

from __future__ import annotations

from abc import ABC, abstractmethod

from bbva_bugresolutionradar.domain.models import ObservedIncident


class Adapter(ABC):
    """Interfaz minima que todo adaptador debe implementar."""

    @abstractmethod
    def source_id(self) -> str:
        """Identificador estable de la fuente (p.ej. filesystem_csv)."""
        raise NotImplementedError

    @abstractmethod
    def read(self) -> list[ObservedIncident]:
        """Lee la fuente y devuelve observaciones canonicas."""
        raise NotImplementedError
