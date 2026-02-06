#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import httpx


DEFAULT_PATHS = ["/", "/sentimiento"]
NO_CACHE_HEADERS = {"cache-control": "no-cache", "pragma": "no-cache"}


def _parse_paths(raw: str) -> list[str]:
    paths: list[str] = []
    for chunk in raw.split(","):
        path = chunk.strip()
        if not path:
            continue
        if not path.startswith("/"):
            path = f"/{path}"
        paths.append(path)
    return paths or DEFAULT_PATHS


def _bench(
    name: str,
    url: str,
    client: httpx.Client,
    iterations: int,
    warmup: int,
) -> dict[str, float | str]:
    for _ in range(max(0, warmup)):
        res = client.get(url, headers=NO_CACHE_HEADERS)
        res.raise_for_status()

    times: list[float] = []
    sizes: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter()
        res = client.get(url, headers=NO_CACHE_HEADERS)
        res.raise_for_status()
        times.append(time.perf_counter() - start)
        sizes.append(len(res.content))

    times_ms = sorted(t * 1000 for t in times)
    p50 = statistics.median(times_ms)
    p95_index = max(0, int(len(times_ms) * 0.95) - 1)
    p95 = times_ms[p95_index]
    avg_size = statistics.mean(sizes) if sizes else 0.0
    max_size = max(sizes) if sizes else 0.0

    return {
        "name": name,
        "min_ms": min(times_ms),
        "avg_ms": statistics.mean(times_ms),
        "p50_ms": p50,
        "p95_ms": p95,
        "max_ms": max(times_ms),
        "avg_kb": avg_size / 1024.0,
        "max_kb": max_size / 1024.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Frontend benchmark (HTTP).")
    parser.add_argument("--url", type=str, default="http://localhost:3000")
    parser.add_argument("--paths", type=str, default=",".join(DEFAULT_PATHS))
    parser.add_argument("--iterations", type=int, default=40)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--max-regression", type=float, default=0.15)
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    paths = _parse_paths(args.paths)

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        try:
            probe = client.get(f"{base_url}{paths[0]}", headers=NO_CACHE_HEADERS)
            probe.raise_for_status()
        except httpx.HTTPError as exc:
            print("Frontend benchmark failed: cannot reach the frontend server.")
            print(f"- URL: {base_url}")
            print(f"- Error: {exc}")
            print("Start the frontend first (make dev-front) and retry.")
            raise SystemExit(1)

        results: list[dict[str, float | str]] = []
        for path in paths:
            results.append(
                _bench(
                    f"GET {path}",
                    f"{base_url}{path}",
                    client,
                    args.iterations,
                    args.warmup,
                )
            )

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

    print("Frontend benchmark results")
    print(f"Base URL: {base_url}")
    print(f"Paths: {', '.join(paths)}")
    print("")
    for entry in results:
        avg_ms = float(entry.get("avg_ms", 0.0))
        p50_ms = float(entry.get("p50_ms", 0.0))
        p95_ms = float(entry.get("p95_ms", 0.0))
        max_ms = float(entry.get("max_ms", 0.0))
        avg_kb = float(entry.get("avg_kb", 0.0))
        print(
            f"- {entry['name']}: "
            f"avg {avg_ms:.2f} ms | "
            f"p50 {p50_ms:.2f} ms | "
            f"p95 {p95_ms:.2f} ms | "
            f"max {max_ms:.2f} ms | "
            f"avg {avg_kb:.1f} KB"
        )


if __name__ == "__main__":
    main()
