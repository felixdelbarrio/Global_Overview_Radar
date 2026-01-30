from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from reputation.collectors.utils import match_keywords, normalize_text
from reputation.models import ReputationItem


_ES_POSITIVE = {
    "bueno",
    "buena",
    "excelente",
    "genial",
    "rapido",
    "rapida",
    "facil",
    "util",
    "satisfecho",
    "satisfecha",
    "recomendable",
    "mejor",
    "fiable",
    "estable",
    "seguro",
    "segura",
    "perfecto",
    "perfecta",
}
_ES_NEGATIVE = {
    "malo",
    "mala",
    "horrible",
    "lento",
    "lenta",
    "error",
    "errores",
    "fallo",
    "fallos",
    "bug",
    "bugs",
    "problema",
    "problemas",
    "caida",
    "caidas",
    "cae",
    "bloqueado",
    "bloqueada",
    "imposible",
    "nunca",
    "pesimo",
    "pesima",
    "fatal",
    "mala atencion",
    "comision",
    "comisiones",
}
_ES_NEGATIVE_PHRASES = {
    "no funciona",
    "no sirve",
    "no abre",
    "no carga",
    "no deja",
    "no puedo",
}
_EN_POSITIVE = {
    "good",
    "great",
    "excellent",
    "fast",
    "easy",
    "useful",
    "satisfied",
    "reliable",
    "stable",
    "secure",
    "perfect",
    "best",
}
_EN_NEGATIVE = {
    "bad",
    "terrible",
    "slow",
    "error",
    "errors",
    "bug",
    "bugs",
    "issue",
    "issues",
    "problem",
    "problems",
    "down",
    "crash",
    "crashes",
    "broken",
    "impossible",
    "never",
    "worst",
    "fees",
    "commission",
}
_EN_NEGATIVE_PHRASES = {
    "does not work",
    "doesn't work",
    "not working",
    "won't open",
    "cannot access",
}

_LANG_HINTS_ES = {"el", "la", "de", "que", "y", "para", "con", "sin", "no", "una", "un"}
_LANG_HINTS_EN = {"the", "and", "for", "with", "without", "not", "this", "that", "from"}

_COUNTRY_CODE_MAP = {
    "es": "España",
    "mx": "México",
    "pe": "Perú",
    "co": "Colombia",
    "ar": "Argentina",
    "tr": "Turquía",
}


@dataclass
class SentimentResult:
    label: str
    score: float
    language: str | None
    geo: str | None
    actors: list[str]


class ReputationSentimentService:
    def __init__(self, cfg: dict) -> None:
        self._cfg = cfg
        self._keywords = [k.strip() for k in cfg.get("keywords", []) if isinstance(k, str) and k.strip()]
        self._global_actors = [
            c.strip() for c in cfg.get("otros_actores_globales", []) if c.strip()
        ]
        self._actors_by_geo = cfg.get("otros_actores_por_geografia", {}) or {}
        self._actor_aliases = cfg.get("otros_actores_aliases", {}) or {}
        self._geos = [g.strip() for g in cfg.get("geografias", []) if g.strip()]
        self._geo_aliases = cfg.get("geografias_aliases", {}) or {}

    def analyze_items(self, items: Iterable[ReputationItem]) -> list[ReputationItem]:
        result: list[ReputationItem] = []
        for item in items:
            result.append(self.analyze_item(item))
        return result

    def analyze_item(self, item: ReputationItem) -> ReputationItem:
        text = self._build_text(item)
        language = item.language or self._detect_language(text)
        geo = item.geo or self._detect_geo(text, item)
        actors = self._detect_actors(text, geo, item.signals)

        score = self._sentiment_score(text, language)
        label = self._score_to_label(score)

        item.language = language or item.language
        item.geo = geo or item.geo
        if actors:
            item.actor = actors[0]

        item.sentiment = label
        item.signals["sentiment_score"] = score
        if actors:
            item.signals["actors"] = actors
        return item

    @staticmethod
    def _build_text(item: ReputationItem) -> str:
        parts = [item.title or "", item.text or ""]
        return " ".join(p for p in parts if p).strip().lower()

    def _detect_language(self, text: str) -> str | None:
        if not text:
            return None
        es_hits = sum(1 for w in _LANG_HINTS_ES if f" {w} " in f" {text} ")
        en_hits = sum(1 for w in _LANG_HINTS_EN if f" {w} " in f" {text} ")
        if es_hits == en_hits:
            return None
        return "es" if es_hits > en_hits else "en"

    def _detect_geo(self, text: str, item: ReputationItem) -> str | None:
        country = item.signals.get("country")
        if isinstance(country, str):
            mapped = _COUNTRY_CODE_MAP.get(country.lower())
            if mapped:
                return mapped
        normalized = normalize_text(text)
        for geo in self._geos:
            geo_norm = normalize_text(geo)
            if geo_norm and geo_norm in normalized:
                return geo
            aliases = self._geo_aliases.get(geo, [])
            for alias in aliases:
                if isinstance(alias, str):
                    alias_norm = normalize_text(alias)
                    if alias_norm and alias_norm in normalized:
                        return geo
        return None

    def _detect_actors(
        self,
        text: str,
        geo: str | None,
        signals: dict | None = None,
    ) -> list[str]:
        actors: list[str] = []
        normalized = normalize_text(text)
        hints: list[str] = []
        if signals:
            for key in ("entity", "entity_hint", "query"):
                value = signals.get(key)
                if isinstance(value, str) and value.strip():
                    hints.append(value.strip())

        scoped = []
        if geo and geo in self._actors_by_geo:
            scoped.extend(self._actors_by_geo.get(geo, []))
        elif not geo and isinstance(self._actors_by_geo, dict):
            for names in self._actors_by_geo.values():
                if isinstance(names, list):
                    scoped.extend(names)
        scoped.extend(self._global_actors)

        hint_actors: list[str] = []
        if hints:
            for name in scoped:
                if not isinstance(name, str):
                    continue
                matched = any(match_keywords(hint, [name]) for hint in hints)
                if not matched:
                    aliases = self._actor_aliases.get(name) or []
                    for alias in aliases:
                        if isinstance(alias, str) and any(match_keywords(hint, [alias]) for hint in hints):
                            matched = True
                            break
                if matched:
                    hint_actors.append(name)

        bbva_in_hints = any("bbva" in normalize_text(h) for h in hints)
        bbva_in_text = "bbva" in normalized or any(match_keywords(text, [kw]) for kw in self._keywords)

        if hint_actors:
            actors.extend(hint_actors)
        elif bbva_in_text or bbva_in_hints:
            actors.append("BBVA")

        for name in scoped:
            if not isinstance(name, str):
                continue
            if name in actors:
                continue
            matched = match_keywords(text, [name])
            if not matched:
                aliases = self._actor_aliases.get(name) or []
                for alias in aliases:
                    if isinstance(alias, str) and match_keywords(text, [alias]):
                        matched = True
                        break
            if not matched and hints:
                for hint in hints:
                    if match_keywords(hint, [name]):
                        matched = True
                        break
                    aliases = self._actor_aliases.get(name) or []
                    for alias in aliases:
                        if isinstance(alias, str) and match_keywords(hint, [alias]):
                            matched = True
                            break
                    if matched:
                        break
            if matched:
                actors.append(name)

        if (bbva_in_text or bbva_in_hints) and "BBVA" not in actors:
            if hint_actors:
                actors.append("BBVA")
            else:
                actors.insert(0, "BBVA")

        seen: set[str] = set()
        ordered: list[str] = []
        for name in actors:
            if name not in seen:
                ordered.append(name)
                seen.add(name)
        return ordered

    def _sentiment_score(self, text: str, language: str | None) -> float:
        if not text:
            return 0.0
        tokens = text.split()
        if language == "en":
            pos = sum(1 for t in tokens if t in _EN_POSITIVE)
            neg = sum(1 for t in tokens if t in _EN_NEGATIVE)
            neg += sum(1 for p in _EN_NEGATIVE_PHRASES if p in text)
        else:
            pos = sum(1 for t in tokens if t in _ES_POSITIVE)
            neg = sum(1 for t in tokens if t in _ES_NEGATIVE)
            neg += sum(1 for p in _ES_NEGATIVE_PHRASES if p in text)
        total = pos + neg
        if total == 0:
            return 0.0
        return (pos - neg) / total

    @staticmethod
    def _score_to_label(score: float) -> str:
        if score >= 0.2:
            return "positive"
        if score <= -0.2:
            return "negative"
        return "neutral"
