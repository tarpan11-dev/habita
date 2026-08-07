from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit


TRUE_VALUES = {"1", "true", "sim", "yes", "y", "s"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def slug(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", clean_text(value))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() in TRUE_VALUES


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return default if isinstance(value, float) and math.isnan(value) else float(value)
    raw = clean_text(value).replace("€", "").replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return default


def as_int(value: Any, default: int = 0) -> int:
    return int(round(as_float(value, default)))


def iso_datetime(value: Any | None = None) -> str:
    if value in (None, ""):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time())
    else:
        raw = clean_text(value)
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return datetime.now(timezone.utc).isoformat(timespec="seconds")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def canonical_url(value: Any) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        return raw
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def listing_uid(row: dict[str, Any]) -> str:
    source = slug(row.get("source"))
    external = clean_text(row.get("external_id"))
    url = canonical_url(row.get("url"))
    identity = f"{source}|{external or url}"
    if not external and not url:
        identity += "|" + cross_source_fingerprint(row)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def cross_source_fingerprint(row: dict[str, Any]) -> str:
    components = [
        slug(row.get("transaction")),
        slug(row.get("district")),
        slug(row.get("municipality")),
        slug(row.get("address") or row.get("title")),
        slug(row.get("property_type")),
        str(as_int(row.get("bedrooms"))),
        str(int(round(as_float(row.get("area_m2")) / 5) * 5)),
        str(int(round(as_float(row.get("price")) / 10) * 10)),
    ]
    return hashlib.sha256("|".join(components).encode("utf-8")).hexdigest()[:20]

