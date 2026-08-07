from __future__ import annotations

import json
import os
from io import BytesIO
from typing import Any, Iterable

import feedparser
import pandas as pd
import requests

from db import upsert_listings
from services.normalization import clean_text


REQUIRED_COLUMNS = {"title", "transaction", "property_type", "price", "district", "source"}


def dataframe_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError("Faltam colunas obrigatórias: " + ", ".join(sorted(missing)))
    return frame.where(pd.notna(frame), None).to_dict(orient="records")


def rows_from_upload(name: str, payload: bytes) -> list[dict[str, Any]]:
    lower_name = name.lower()
    if lower_name.endswith(".csv"):
        return dataframe_rows(pd.read_csv(BytesIO(payload)))
    if lower_name.endswith(".json"):
        parsed = json.loads(payload.decode("utf-8"))
        if isinstance(parsed, dict):
            parsed = parsed.get("listings", [])
        if not isinstance(parsed, list):
            raise ValueError("O JSON deve ser uma lista ou conter a chave 'listings'.")
        return [dict(item) for item in parsed]
    raise ValueError("Formato não suportado. Usa CSV ou JSON.")


def fetch_json_feed(url: str, timeout: int = 15) -> list[dict[str, Any]]:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "Habitua/1.0 (authorized-feed-client)"})
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        payload = payload.get("listings", payload.get("items", []))
    if not isinstance(payload, list):
        raise ValueError("O feed JSON não devolveu uma lista de anúncios.")
    return [dict(item) for item in payload]


def fetch_rss_feed(url: str, source_name: str = "RSS") -> list[dict[str, Any]]:
    response = requests.get(url, timeout=15, headers={"User-Agent": "Habitua/1.0 (authorized-feed-client)"})
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    defaults = _rss_defaults_for(url)
    if not defaults.get("district") or not defaults.get("price"):
        raise ValueError("Este RSS precisa de district e price em HABITUA_RSS_DEFAULTS.")
    rows: list[dict[str, Any]] = []
    for entry in feed.entries:
        tags = {tag.term.lower() for tag in entry.get("tags", []) if getattr(tag, "term", None)}
        rows.append(
            {
                "source": source_name or clean_text(feed.feed.get("title")) or "RSS",
                "external_id": clean_text(entry.get("id") or entry.get("link")),
                "title": clean_text(entry.get("title")),
                "description": clean_text(entry.get("summary")),
                "url": clean_text(entry.get("link")),
                "published_at": clean_text(entry.get("published") or entry.get("updated")),
                "transaction": defaults.get("transaction", "Arrendar"),
                "property_type": defaults.get("property_type", "Apartamento"),
                "district": defaults["district"],
                "price": defaults["price"],
                "students_allowed": "estudantes" in tags,
            }
        )
    return rows


def _rss_defaults_for(url: str) -> dict[str, Any]:
    # Ex.: HABITUA_RSS_DEFAULTS='{"feed-url":{"district":"Porto","price":500}}'
    try:
        return json.loads(os.getenv("HABITUA_RSS_DEFAULTS", "{}"))[url]
    except (KeyError, TypeError, json.JSONDecodeError):
        return {}


def configured_feeds() -> Iterable[tuple[str, str, str]]:
    for url in filter(None, (item.strip() for item in os.getenv("HABITUA_JSON_FEEDS", "").split(","))):
        yield "json", url, "Feed JSON"
    for item in filter(None, (item.strip() for item in os.getenv("HABITUA_RSS_FEEDS", "").split(","))):
        name, separator, url = item.partition("|")
        yield "rss", url if separator else name, name if separator else "RSS"


def ingest_configured_feeds() -> tuple[int, list[str]]:
    total = 0
    messages: list[str] = []
    for kind, url, source_name in configured_feeds():
        try:
            rows = fetch_json_feed(url) if kind == "json" else fetch_rss_feed(url, source_name)
            count, errors = upsert_listings(rows)
            total += count
            messages.append(f"{source_name}: {count} anúncios processados")
            messages.extend(errors[:5])
        except Exception as exc:  # mostra uma falha por feed sem parar os restantes
            messages.append(f"{source_name}: falhou ({exc})")
    return total, messages
