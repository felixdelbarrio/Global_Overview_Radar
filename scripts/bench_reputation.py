#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Iterator, Mapping

from fastapi.testclient import TestClient

from reputation.api.main import create_app
from reputation.config import reload_reputation_settings, settings as rep_settings
from reputation.models import ReputationCacheDocument, ReputationItem
from reputation.repositories.cache_repo import ReputationCacheRepo
from reputation.services.ingest_service import ReputationIngestService


@dataclass
class BenchResult:
    name: str
    samples_ms: list[float]

    def summary(self) -> dict[str, float]:
        values = sorted(self.samples_ms)
        count = len(values)
        mean = statistics.mean(values) if values else 0.0
        stdev = statistics.pstdev(values) if count > 1 else 0.0
        return {
            "count": float(count),
            "mean_ms": mean,
            "stdev_ms": stdev,
            "min_ms": values[0] if values else 0.0,
            "p50_ms": _percentile(values, 50),
            "p95_ms": _percentile(values, 95),
            "max_ms": values[-1] if values else 0.0,
        }


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    if pct <= 0:
        return values[0]
    if pct >= 100:
        return values[-1]
    k = (len(values) - 1) * (pct / 100)
    idx = int(k)
    frac = k - idx
    if idx + 1 < len(values):
        return values[idx] * (1 - frac) + values[idx + 1] * frac
    return values[idx]


@contextmanager
def temp_env(overrides: Mapping[str, str | None]) -> Iterator[None]:
    old = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _make_items(count: int) -> list[ReputationItem]:
    now = datetime.now(timezone.utc)
    items: list[ReputationItem] = []
    for idx in range(count):
        items.append(
            ReputationItem(
                id=f"item-{idx}",
                source="news",
                geo="ES" if idx % 2 == 0 else "US",
                actor="Acme Bank" if idx % 2 == 0 else "Beta Bank",
                title=f"Title {idx}",
                text="Synthetic benchmark mention.",
                published_at=now - timedelta(days=idx % 30),
                collected_at=now,
                sentiment="positive" if idx % 3 == 0 else "neutral",
            )
        )
    return items


def _write_config(path: Path) -> None:
    payload = {
        "actor_principal": {"Acme Bank": ["Acme"]},
        "actor_principal_aliases": {"Acme Bank": ["Acme Corp"]},
        "otros_actores_aliases": {"Beta Bank": ["Beta"]},
        "geografias": ["ES", "US"],
    }
    path.write_text(json_dumps(payload), encoding="utf-8")


def json_dumps(payload: object) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _write_cache(path: Path, items: list[ReputationItem]) -> None:
    doc = ReputationCacheDocument(
        generated_at=datetime.now(timezone.utc),
        config_hash="bench",
        sources_enabled=["news"],
        items=items,
        market_ratings=[],
        market_ratings_history=[],
    )
    ReputationCacheRepo(path).save(doc)


def _load_items_from_cache(path: Path) -> list[ReputationItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    doc = ReputationCacheDocument.model_validate(data)
    return list(doc.items)


def _resolve_real_cache(value: str) -> Path | None:
    raw = value.strip()
    if not raw:
        return None
    if raw.lower() == "auto":
        repo_root = Path(__file__).resolve().parents[1]
        cache_dir = repo_root / "data" / "cache"
        candidates = list(cache_dir.glob("reputation_cache*.json"))
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
        return candidates[0]
    return Path(raw).expanduser().resolve()


class BenchIngestService(ReputationIngestService):
    def __init__(self, items: list[ReputationItem]) -> None:
        super().__init__()
        self._bench_items = items

    def _build_collectors(self, cfg: dict, sources_enabled: list[str]):
        return ([], ["bench: collectors bypassed"])

    def _collect_items(
        self,
        collectors,
        notes,
        progress=None,
        min_dt=None,
        collected_at=None,
    ):
        return list(self._bench_items)


def _measure(fn: Callable[[], object], iterations: int, warmup: int) -> list[float]:
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return samples


def _profile(label: str, fn: Callable[[], object], output_dir: Path) -> Path:
    import cProfile

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{label}.prof"
    profiler = cProfile.Profile()
    profiler.enable()
    fn()
    profiler.disable()
    profiler.dump_stats(str(path))
    return path


def bench_endpoints(
    client: TestClient, iterations: int, warmup: int
) -> list[BenchResult]:
    results: list[BenchResult] = []

    def _wrap(name: str, call: Callable[[], None]) -> None:
        samples = _measure(call, iterations, warmup)
        results.append(BenchResult(name=name, samples_ms=samples))

    _wrap("GET /reputation/meta", lambda: _assert_ok(client.get("/reputation/meta")))
    _wrap(
        "GET /reputation/items",
        lambda: _assert_ok(
            client.get(
                "/reputation/items",
                params={"from_date": "2024-01-01", "to_date": "2026-01-01"},
            )
        ),
    )
    _wrap(
        "POST /reputation/items/compare",
        lambda: _assert_ok(
            client.post(
                "/reputation/items/compare",
                json=[{"entity": "actor_principal"}, {"sentiment": "positive"}],
            )
        ),
    )
    return results


def _assert_ok(response) -> None:
    if response.status_code >= 400:
        raise RuntimeError(f"Request failed: {response.status_code} {response.text}")


def bench_ingest(
    items: list[ReputationItem], iterations: int, warmup: int
) -> BenchResult:
    service = BenchIngestService(items)
    samples = _measure(lambda: service.run(force=True), iterations, warmup)
    return BenchResult(name="Ingest pipeline (synthetic)", samples_ms=samples)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Global Overview Radar")
    parser.add_argument(
        "--items", type=int, default=500, help="Number of synthetic items"
    )
    parser.add_argument(
        "--iterations", type=int, default=20, help="Benchmark iterations"
    )
    parser.add_argument("--warmup", type=int, default=3, help="Warmup iterations")
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Write cProfile output to ./benchmarks",
    )
    parser.add_argument(
        "--real-cache",
        type=str,
        default="",
        help="Path to a real reputation_cache.json or 'auto' to use the largest cache.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=0,
        help="Cap items when using --real-cache (0 = no cap).",
    )
    args = parser.parse_args()

    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config_path = tmp_path / "config.json"
        cache_path = tmp_path / "reputation_cache.json"
        _write_config(config_path)

        real_cache_path = _resolve_real_cache(args.real_cache)
        if real_cache_path and real_cache_path.exists():
            items = _load_items_from_cache(real_cache_path)
            if args.max_items > 0:
                items = items[: args.max_items]
            shutil.copyfile(real_cache_path, cache_path)
        else:
            items = _make_items(args.items)
            _write_cache(cache_path, items)

        env_overrides: dict[str, str | None] = {
            "REPUTATION_CONFIG_PATH": str(config_path),
            "REPUTATION_CACHE_PATH": str(cache_path),
            "REPUTATION_SOURCE_NEWS": "true",
            "REPUTATION_SOURCES_ALLOWLIST": "news",
            "REPUTATION_PROFILE": "",
            "REPUTATION_PROFILE_STATE_DISABLED": "true",
        }

        with temp_env(env_overrides):
            reload_reputation_settings()
            rep_settings.cache_path = cache_path
            client = TestClient(create_app())

            endpoint_results = bench_endpoints(client, args.iterations, args.warmup)
            ingest_result = bench_ingest(items, args.iterations, args.warmup)

            print("\n== Benchmark results (ms) ==")
            for result in [ingest_result, *endpoint_results]:
                summary = result.summary()
                print(
                    f"{result.name}: mean={summary['mean_ms']:.2f} "
                    f"p50={summary['p50_ms']:.2f} p95={summary['p95_ms']:.2f} "
                    f"min={summary['min_ms']:.2f} max={summary['max_ms']:.2f}"
                )

            if args.profile:
                output_dir = Path("benchmarks")
                ingest_profile = _profile(
                    "reputation_ingest",
                    lambda: BenchIngestService(items).run(force=True),
                    output_dir,
                )
                endpoint_profile = _profile(
                    "reputation_endpoints",
                    lambda: bench_endpoints(client, 1, 0),
                    output_dir,
                )
                print("\nProfile output:")
                print(f"- {ingest_profile}")
                print(f"- {endpoint_profile}")


if __name__ == "__main__":
    main()
