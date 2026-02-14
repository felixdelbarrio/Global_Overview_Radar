#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import tracemalloc
from pathlib import Path
from typing import Callable

import reputation.config as rep_config
from reputation.config import load_business_config
from reputation.models import ReputationCacheDocument, ReputationItem
from reputation.services.ingest_service import ReputationIngestService


def _pick_first(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError("No benchmark files found. Provide --cache/--config.")


def _default_cache_path() -> Path:
    return _pick_first(
        [
            Path(
                "data/cache/reputation_cache__banking_bbva_empresas__banking_bbva_retail.json"
            ),
            Path("data/cache/reputation_cache.json"),
        ]
    )


def _default_config_path() -> Path:
    return _pick_first(
        [
            Path("data/reputation_samples/banking_bbva_empresas.json"),
            Path("data/reputation/banking_bbva_retail.json"),
        ]
    )


def _configure_settings(cache_path: Path, config_path: Path) -> None:
    rep_config.settings.cache_path = cache_path.resolve()
    rep_config.settings.config_path = config_path.resolve()
    rep_config.settings.profiles = ""
    rep_config.settings.sources_allowlist = ""


def _clone_items(items: list[ReputationItem]) -> list[ReputationItem]:
    return [item.model_copy(deep=True) for item in items]


def _bench(
    name: str,
    fn: Callable[[], None],
    iterations: int,
    warmup: int,
) -> dict[str, float | str]:
    for _ in range(max(0, warmup)):
        fn()

    times: list[float] = []
    tracemalloc.start()
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    times_ms = [t * 1000 for t in times]
    times_ms.sort()
    p50 = statistics.median(times_ms)
    p95_index = max(0, int(len(times_ms) * 0.95) - 1)
    p95 = times_ms[p95_index]
    return {
        "name": name,
        "min_ms": min(times_ms),
        "avg_ms": statistics.mean(times_ms),
        "p50_ms": p50,
        "p95_ms": p95,
        "max_ms": max(times_ms),
        "peak_kb": peak / 1024.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest benchmark (hotspots/stages).")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--max-regression", type=float, default=0.15)
    args = parser.parse_args()

    os.environ.setdefault("LLM_ENABLED", "false")
    os.environ.setdefault("REPUTATION_TRANSLATE_TARGET", "")

    cache_path = args.cache or _default_cache_path()
    config_path = args.config or _default_config_path()
    _configure_settings(cache_path, config_path)

    cfg = load_business_config()
    doc = ReputationCacheDocument.model_validate_json(
        cache_path.read_text(encoding="utf-8")
    )
    base_items = doc.items
    existing_items = _clone_items(base_items)
    service = ReputationIngestService()

    def stage_geo_hints() -> None:
        service._apply_geo_hints(cfg, _clone_items(base_items))

    def stage_noise_filter() -> None:
        service._filter_noise_items(cfg, _clone_items(base_items), notes=[])

    def stage_sentiment_existing() -> None:
        service._apply_sentiment(
            cfg,
            _clone_items(base_items),
            existing=existing_items,
            notes=[],
        )

    def stage_sentiment_no_existing() -> None:
        service._apply_sentiment(cfg, _clone_items(base_items), existing=None, notes=[])

    def stage_merge_dedupe() -> None:
        service._merge_items(_clone_items(existing_items), _clone_items(base_items))

    def stage_postprocess_pipeline() -> None:
        items = _clone_items(base_items)
        items = service._apply_geo_hints(cfg, items)
        items = service._filter_noise_items(cfg, items, notes=[])
        service._apply_sentiment(cfg, items, existing=existing_items, notes=[])

    results: list[dict[str, float | str]] = [
        _bench("ingest:geo_hints", stage_geo_hints, args.iterations, args.warmup),
        _bench("ingest:noise_filter", stage_noise_filter, args.iterations, args.warmup),
        _bench(
            "ingest:sentiment_existing",
            stage_sentiment_existing,
            args.iterations,
            args.warmup,
        ),
        _bench(
            "ingest:sentiment_no_existing",
            stage_sentiment_no_existing,
            args.iterations,
            args.warmup,
        ),
        _bench(
            "ingest:merge_dedupe",
            stage_merge_dedupe,
            args.iterations,
            args.warmup,
        ),
        _bench(
            "ingest:postprocess_pipeline",
            stage_postprocess_pipeline,
            args.iterations,
            args.warmup,
        ),
    ]

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")

    if args.baseline:
        if not args.baseline.exists():
            print(f"Baseline not found: {args.baseline} (skipping comparison)")
        else:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
            baseline_by_name = {
                entry.get("name"): entry
                for entry in baseline
                if isinstance(entry, dict) and entry.get("name")
            }
            regressions: list[str] = []
            for entry in results:
                name = str(entry.get("name", ""))
                base = baseline_by_name.get(name)
                if not base:
                    continue
                base_avg = float(base.get("avg_ms", 0.0))
                entry_avg = float(entry.get("avg_ms", 0.0))
                threshold = base_avg * (1 + args.max_regression)
                if entry_avg > threshold:
                    regressions.append(
                        f"{name}: {entry_avg:.2f} ms > {threshold:.2f} ms"
                    )
            if regressions:
                print("Regressions detected:")
                for item in regressions:
                    print(f"- {item}")
                raise SystemExit(1)

    print("Ingest benchmark results")
    print(f"Cache: {cache_path}")
    print(f"Config: {config_path}")
    print("")
    for entry in results:
        avg_ms = float(entry.get("avg_ms", 0.0))
        p50_ms = float(entry.get("p50_ms", 0.0))
        p95_ms = float(entry.get("p95_ms", 0.0))
        max_ms = float(entry.get("max_ms", 0.0))
        peak_kb = float(entry.get("peak_kb", 0.0))
        print(
            f"- {entry['name']}: "
            f"avg {avg_ms:.2f} ms | "
            f"p50 {p50_ms:.2f} ms | "
            f"p95 {p95_ms:.2f} ms | "
            f"max {max_ms:.2f} ms | "
            f"peak {peak_kb:.1f} KB"
        )


if __name__ == "__main__":
    main()
