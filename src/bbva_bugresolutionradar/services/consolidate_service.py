from __future__ import annotations

from datetime import datetime

from bbva_bugresolutionradar.domain.merge import compute_global_id, merge_observation
from bbva_bugresolutionradar.domain.models import (
    CacheDocument,
    ObservedIncident,
    RunInfo,
    RunSource,
)


class ConsolidateService:
    def consolidate(
        self,
        existing: CacheDocument,
        observations: list[ObservedIncident],
        sources: list[RunSource],
    ) -> CacheDocument:
        now = datetime.now().astimezone()
        run_id = f"{now.isoformat()}#001"

        doc = existing
        doc.generated_at = now
        doc.runs.append(RunInfo(run_id=run_id, started_at=now, sources=sources))

        for obs in observations:
            gid = compute_global_id(obs.source_id, obs.source_key)
            prev = doc.incidents.get(gid)
            doc.incidents[gid] = merge_observation(prev, obs, gid, run_id)

        return doc
