#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
import tracemalloc
from pathlib import Path
from typing import Callable

from fastapi.testclient import TestClient

import reputation.config as rep_config
from reputation.api.main import create_app
from reputation.api.routers import reputation as reputation_router


SOURCE_SETTING_KEYS = {
    "news": "source_news",
    "newsapi": "source_newsapi",
    "gdelt": "source_gdelt",
    "guardian": "source_guardian",
    "forums": "source_forums",
    "blogs": "source_blogs",
    "appstore": "source_appstore",
    "trustpilot": "source_trustpilot",
    "google_reviews": "source_google_reviews",
    "google_play": "source_google_play",
    "youtube": "source_youtube",
    "reddit": "source_reddit",
    "twitter": "source_twitter",
    "downdetector": "source_downdetector",
}


def _pick_first(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError("No benchmark files found. Provide --cache/--config.")


def _default_cache_path() -> Path:
    return _pick_first(
        [
            Path("data/cache/reputation_cache__samples__banking_bbva_empresas.json"),
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


def _load_cache_sources(cache_path: Path) -> list[str]:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    sources = payload.get("sources_enabled")
    if isinstance(sources, list) and sources:
        return [str(s).strip().lower() for s in sources if str(s).strip()]
    items = payload.get("items")
    if isinstance(items, list):
        detected = {str(item.get("source", "")).strip().lower() for item in items}
        return sorted({src for src in detected if src})
    return []


def _configure_settings(cache_path: Path, config_path: Path) -> None:
    rep_config.settings.cache_path = cache_path.resolve()
    rep_config.settings.config_path = config_path.resolve()
    rep_config.settings.profiles = ""
    rep_config.settings.sources_allowlist = ""

    for key in SOURCE_SETTING_KEYS.values():
        if hasattr(rep_config.settings, key):
            setattr(rep_config.settings, key, False)

    enabled_sources = _load_cache_sources(cache_path)
    for source in enabled_sources:
        setting_key = SOURCE_SETTING_KEYS.get(source)
        if setting_key and hasattr(rep_config.settings, setting_key):
            setattr(rep_config.settings, setting_key, True)


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
    current, peak = tracemalloc.get_traced_memory()
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
    parser = argparse.ArgumentParser(description="Backend benchmark (reputation API).")
    parser.add_argument("--iterations", type=int, default=40)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--max-regression", type=float, default=0.15)
    args = parser.parse_args()

    cache_path = args.cache or _default_cache_path()
    config_path = args.config or _default_config_path()

    _configure_settings(cache_path, config_path)

    app = create_app()
    app.dependency_overrides[reputation_router._refresh_settings] = lambda: None
    client = TestClient(app)

    def hit_meta() -> None:
        res = client.get("/reputation/meta")
        res.raise_for_status()

    def hit_items() -> None:
        res = client.get(
            "/reputation/items",
            params={
                "entity": "actor_principal",
                "from_date": "2024-01-01",
                "to_date": "2027-01-01",
            },
        )
        res.raise_for_status()

    def hit_compare() -> None:
        payload = [
            {
                "entity": "actor_principal",
                "from_date": "2024-01-01",
                "to_date": "2027-01-01",
            },
            {
                "sentiment": "positive",
                "from_date": "2024-01-01",
                "to_date": "2027-01-01",
            },
        ]
        res = client.post("/reputation/items/compare", json=payload)
        res.raise_for_status()

    results: list[dict[str, float | str]] = [
        _bench("GET /reputation/meta", hit_meta, args.iterations, args.warmup),
        _bench("GET /reputation/items", hit_items, args.iterations, args.warmup),
        _bench(
            "POST /reputation/items/compare", hit_compare, args.iterations, args.warmup
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

    print("Backend benchmark results")
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
