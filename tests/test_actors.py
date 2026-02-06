from __future__ import annotations

from reputation.actors import (
    actor_principal_canonicals,
    actor_principal_terms,
    build_actor_alias_map,
    build_actor_aliases_by_canonical,
    canonicalize_actor,
    load_actor_principal,
    load_actor_principal_aliases,
    primary_actor_info,
)


def test_actor_principal_loading_and_aliases() -> None:
    cfg = {
        "actor_principal": {
            "Acme Bank": ["Acme", "Acme Corp"],
            "  ": ["Ignored"],
        },
        "actor_principal_aliases": {
            "Acme Bank": ["Acme Financial"],
            "Beta Bank": ["Beta"],
        },
    }

    principal = load_actor_principal(cfg)
    assert principal == {"Acme Bank": ["Acme", "Acme Corp"]}

    aliases = load_actor_principal_aliases(cfg)
    assert aliases["Acme Bank"] == ["Acme Financial"]
    assert aliases["Beta Bank"] == ["Beta"]

    canonicals = actor_principal_canonicals(cfg)
    assert canonicals == ["Acme Bank"]

    terms = actor_principal_terms(cfg)
    assert "Acme Bank" in terms
    assert "Acme" in terms
    assert "Acme Financial" in terms


def test_alias_map_and_canonicalize() -> None:
    cfg = {
        "actor_principal": {
            "Acme Bank": ["Acme", "Acme Corp"],
        },
        "otros_actores_aliases": {
            "Beta Bank": ["Beta", "Beta Inc"],
        },
    }

    alias_map = build_actor_alias_map(cfg)
    assert canonicalize_actor("Acme", alias_map) == "Acme Bank"
    assert canonicalize_actor("acme corp", alias_map) == "Acme Bank"
    assert canonicalize_actor("Beta", alias_map) == "Beta Bank"
    assert canonicalize_actor("Unknown", alias_map) == "Unknown"

    aliases_by_canonical = build_actor_aliases_by_canonical(cfg)
    assert aliases_by_canonical["Acme Bank"] == ["Acme", "Acme Corp"]
    assert aliases_by_canonical["Beta Bank"] == ["Beta", "Beta Inc"]


def test_primary_actor_info_fallback() -> None:
    cfg = {
        "actor_principal_aliases": {
            "Gamma Bank": ["Gamma"],
        }
    }

    info = primary_actor_info(cfg)
    assert info is not None
    assert info["canonical"] == "Gamma Bank"
    assert info["aliases"] == ["Gamma"]
    assert info["names"] == []
