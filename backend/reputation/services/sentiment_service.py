from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, cast

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
    competitors: list[str]


def _coerce_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        items = cast(list[object], value)
        return [v.strip() for v in items if isinstance(v, str) and v.strip()]
    return []


def _coerce_str_list_map(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    mapping = cast(dict[str, object], value)
    result: dict[str, list[str]] = {}
    for key, items in mapping.items():
        values = _coerce_str_list(items)
        if values:
            result[key] = values
    return result


class ReputationSentimentService:
    def __init__(self, cfg: dict[str, object]) -> None:
        self._cfg = cfg
        self._keywords = _coerce_str_list(cfg.get("keywords"))
        self._global_competitors = _coerce_str_list(cfg.get("global_competitors"))
        self._competitors_by_geo = _coerce_str_list_map(cfg.get("competidores_por_geografia"))
        self._geos = _coerce_str_list(cfg.get("geografias"))
        self._geo_aliases = _coerce_str_list_map(cfg.get("geografias_aliases"))

    def analyze_items(self, items: Iterable[ReputationItem]) -> list[ReputationItem]:
        result: list[ReputationItem] = []
        for item in items:
            result.append(self.analyze_item(item))
        return result

    def analyze_item(self, item: ReputationItem) -> ReputationItem:
        text = self._build_text(item)
        language = item.language or self._detect_language(text)
        geo = item.geo or self._detect_geo(text, item)
        competitors = self._detect_competitors(text, geo)

        score = self._sentiment_score(text, language)
        label = self._score_to_label(score)

        item.language = language or item.language
        item.geo = geo or item.geo
        if competitors:
            item.competitor = competitors[0]

        item.sentiment = label
        item.signals["sentiment_score"] = score
        if competitors:
            item.signals["competitors"] = competitors
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
        for geo in self._geos:
            geo_lc = geo.lower()
            if geo_lc in text:
                return geo
            aliases = self._geo_aliases.get(geo, [])
            for alias in aliases:
                if alias.lower() in text:
                    return geo
        return None

    def _detect_competitors(self, text: str, geo: str | None) -> list[str]:
        competitors: list[str] = []
        if "bbva" in text:
            competitors.append("BBVA")
        else:
            for keyword in self._keywords:
                if keyword.lower() in text:
                    competitors.append("BBVA")
                    break

        scoped: list[str] = []
        if geo and geo in self._competitors_by_geo:
            scoped.extend(self._competitors_by_geo.get(geo, []))
        scoped.extend(self._global_competitors)

        for name in scoped:
            if name.lower() in text:
                competitors.append(name)

        seen: set[str] = set()
        ordered: list[str] = []
        for name in competitors:
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
