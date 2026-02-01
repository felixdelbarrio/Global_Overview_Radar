from __future__ import annotations

from typing import Any, Mapping

from reputation.collectors.utils import normalize_text


def _clean_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def load_actor_principal(cfg: Mapping[str, Any]) -> dict[str, list[str]]:
    raw = cfg.get("actor_principal") or {}
    result: dict[str, list[str]] = {}
    if isinstance(raw, dict):
        for canonical, names in raw.items():
            if not isinstance(canonical, str):
                continue
            cleaned = canonical.strip()
            if not cleaned:
                continue
            result[cleaned] = _clean_list(names)
    elif isinstance(raw, list):
        for value in raw:
            if isinstance(value, str) and value.strip():
                result[value.strip()] = []
    return result


def load_actor_principal_aliases(cfg: Mapping[str, Any]) -> dict[str, list[str]]:
    raw = cfg.get("actor_principal_aliases") or {}
    result: dict[str, list[str]] = {}
    if isinstance(raw, dict):
        for canonical, aliases in raw.items():
            if not isinstance(canonical, str):
                continue
            cleaned = canonical.strip()
            if not cleaned:
                continue
            alias_list = _clean_list(aliases)
            if alias_list:
                result[cleaned] = alias_list
    elif isinstance(raw, list):
        for value in raw:
            if isinstance(value, str) and value.strip():
                result[value.strip()] = []
    return result


def actor_principal_canonicals(cfg: Mapping[str, Any]) -> list[str]:
    principal = load_actor_principal(cfg)
    canonicals = list(principal.keys())
    if canonicals:
        return canonicals
    aliases = load_actor_principal_aliases(cfg)
    return list(aliases.keys())


def actor_principal_terms(cfg: Mapping[str, Any]) -> list[str]:
    terms: list[str] = []
    principal = load_actor_principal(cfg)
    for canonical, names in principal.items():
        terms.append(canonical)
        terms.extend(names)
    aliases = load_actor_principal_aliases(cfg)
    for canonical, alias_list in aliases.items():
        terms.append(canonical)
        terms.extend(alias_list)
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        if term and term not in seen:
            ordered.append(term)
            seen.add(term)
    return ordered


def build_actor_aliases_by_canonical(
    cfg: Mapping[str, Any],
    include_principal: bool = True,
    include_others: bool = True,
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}

    def add(canonical: str, values: object) -> None:
        alias_list = _clean_list(values)
        if not alias_list:
            return
        bucket = result.setdefault(canonical, [])
        for alias in alias_list:
            if alias not in bucket:
                bucket.append(alias)

    if include_principal:
        for canonical, names in load_actor_principal(cfg).items():
            add(canonical, names)
        for canonical, aliases in load_actor_principal_aliases(cfg).items():
            add(canonical, aliases)

    if include_others:
        raw = cfg.get("otros_actores_aliases") or {}
        if isinstance(raw, dict):
            for canonical, aliases in raw.items():
                if not isinstance(canonical, str):
                    continue
                cleaned = canonical.strip()
                if not cleaned:
                    continue
                add(cleaned, aliases)

    return result


def build_actor_alias_map(
    cfg: Mapping[str, Any],
    include_principal: bool = True,
    include_others: bool = True,
) -> dict[str, str]:
    alias_map: dict[str, str] = {}

    def add(canonical: str, alias: str) -> None:
        key = normalize_text(alias)
        if not key:
            return
        alias_map[key] = canonical

    if include_principal:
        for canonical, names in load_actor_principal(cfg).items():
            add(canonical, canonical)
            for name in names:
                add(canonical, name)
        for canonical, aliases in load_actor_principal_aliases(cfg).items():
            add(canonical, canonical)
            for alias in aliases:
                add(canonical, alias)

    if include_others:
        raw = cfg.get("otros_actores_aliases") or {}
        if isinstance(raw, dict):
            for canonical, aliases in raw.items():
                if not isinstance(canonical, str):
                    continue
                cleaned = canonical.strip()
                if not cleaned:
                    continue
                add(cleaned, cleaned)
                for alias in _clean_list(aliases):
                    add(cleaned, alias)

    return alias_map


def canonicalize_actor(name: str, alias_map: Mapping[str, str]) -> str:
    cleaned = name.strip()
    if not cleaned:
        return ""
    key = normalize_text(cleaned)
    return alias_map.get(key, cleaned)


def primary_actor_info(cfg: Mapping[str, Any]) -> dict[str, object] | None:
    principal = load_actor_principal(cfg)
    if not principal:
        aliases = load_actor_principal_aliases(cfg)
        if not aliases:
            return None
        canonical = next(iter(aliases.keys()))
        return {
            "canonical": canonical,
            "names": [],
            "aliases": aliases.get(canonical, []),
        }

    canonical = next(iter(principal.keys()))
    aliases = load_actor_principal_aliases(cfg)
    return {
        "canonical": canonical,
        "names": principal.get(canonical, []),
        "aliases": aliases.get(canonical, []),
    }
