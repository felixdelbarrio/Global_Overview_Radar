from __future__ import annotations

from abc import ABC, abstractmethod

from bbva_bugresolutionradar.domain.models import ObservedIncident


class Adapter(ABC):
    @abstractmethod
    def source_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def read(self) -> list[ObservedIncident]:
        raise NotImplementedError
