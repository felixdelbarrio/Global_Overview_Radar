from __future__ import annotations

from process_registry import (
    kill_registered_processes,
    process_registry_dir,
    record_description,
)


def main() -> int:
    results = kill_registered_processes()
    if not results:
        print(
            f"==> No hay instancias activas registradas en {process_registry_dir()}",
            flush=True,
        )
        return 0

    killed = 0
    stale = 0
    for status, record in results:
        description = record_description(record)
        if status == "killed":
            print(f"==> Cerrado: {description}", flush=True)
            killed += 1
            continue
        print(f"==> Limpiado registro huérfano: {description}", flush=True)
        stale += 1

    if killed:
        print(f"==> OK: {killed} instancia(s) detenida(s).", flush=True)
    elif stale:
        print(
            "==> No quedaban procesos vivos; solo se limpiaron registros antiguos.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
