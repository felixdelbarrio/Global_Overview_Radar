from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from reputation.models import ReputationItem


class ReputationCollector(ABC):
    """Contrato base para cualquier fuente de reputación."""

    source_name: str

    @abstractmethod
    def collect(self) -> Iterable[ReputationItem]:
        """Devuelve items ya normalizados."""
        raise NotImplementedError