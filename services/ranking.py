from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any, Iterable

from .normalization import as_float, clean_text


SUSPICIOUS_PHRASES = {
    "pagar antes da visita": "Pede pagamento antes da visita",
    "sem visitas": "Não permite visita",
    "western union": "Menciona um meio de pagamento de risco",
    "criptomoeda": "Pede pagamento em criptomoeda",
    "urgente hoje": "Pressão para pagamento imediato",
    "proprietário no estrangeiro": "Proprietário ausente — exige confirmação adicional",
}


def fraud_warnings(listing: dict[str, Any], local_median: float | None = None) -> list[str]:
    text = clean_text(f"{listing.get('title', '')} {listing.get('description', '')}").lower()
    warnings = [message for phrase, message in SUSPICIOUS_PHRASES.items() if phrase in text]
    price = as_float(listing.get("price"))
    if local_median and price and price < local_median * 0.55:
        warnings.append("Preço muito abaixo da mediana dos resultados comparáveis")
    if not clean_text(listing.get("url")):
        warnings.append("Sem ligação verificável para o anúncio original")
    if not clean_text(listing.get("address")):
        warnings.append("Localização pouco detalhada")
    return list(dict.fromkeys(warnings))


def completeness_score(listing: dict[str, Any]) -> int:
    useful_fields = (
        "title",
        "price",
        "district",
        "municipality",
        "property_type",
        "area_m2",
        "description",
        "url",
        "published_at",
    )
    present = sum(bool(listing.get(field)) for field in useful_fields)
    return round(100 * present / len(useful_fields))


def days_old(value: Any) -> int:
    raw = clean_text(value)
    if not raw:
        return 999
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except ValueError:
        return 999


def relevance_score(listing: dict[str, Any], student_mode: bool = False, local_median: float | None = None) -> int:
    score = 25
    age = days_old(listing.get("published_at"))
    score += max(0, 25 - min(age, 25))
    score += round(completeness_score(listing) * 0.20)
    if listing.get("furnished"):
        score += 6
    if listing.get("bills_included"):
        score += 6
    if student_mode and listing.get("students_allowed"):
        score += 12
    warnings = fraud_warnings(listing, local_median)
    score -= min(35, len(warnings) * 12)
    return max(0, min(100, score))


def comparable_median(listings: Iterable[dict[str, Any]], target: dict[str, Any]) -> float | None:
    prices = [
        as_float(item.get("price"))
        for item in listings
        if item.get("transaction") == target.get("transaction")
        and item.get("district") == target.get("district")
        and item.get("property_type") == target.get("property_type")
        and as_float(item.get("price")) > 0
    ]
    return median(prices) if prices else None

