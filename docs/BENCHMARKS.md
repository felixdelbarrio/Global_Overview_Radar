# Benchmarks and profiling

This project includes a lightweight benchmark harness for ingest and endpoints.

## Run benchmarks

```bash
python scripts/bench_reputation.py --items 500 --iterations 20 --warmup 3
```

## Real datasets

Use an existing cache snapshot to benchmark with real items:

```bash
python scripts/bench_reputation.py --real-cache auto --iterations 10 --warmup 2
```

Optional cap for very large caches:

```bash
python scripts/bench_reputation.py --real-cache /path/to/reputation_cache.json --max-items 5000
```

Makefile helper:

```bash
make bench BENCH_REAL_CACHE=auto
```

## Run profiles

```bash
python scripts/bench_reputation.py --items 500 --iterations 5 --profile
```

Profiles are written to `./benchmarks/*.prof` and can be inspected with tools
like `python -m pstats` or third-party viewers.

## Notes
- Benchmarks run against synthetic data and a temporary config/cache.
- No network calls are executed.
- Use larger `--items` to simulate heavier workloads.
