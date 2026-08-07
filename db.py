from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from config import DB_PATH
from services.normalization import (
    as_bool,
    as_float,
    as_int,
    canonical_url,
    clean_text,
    cross_source_fingerprint,
    iso_datetime,
    listing_uid,
)


LISTING_COLUMNS = [
    "uid",
    "fingerprint",
    "source",
    "external_id",
    "title",
    "description",
    "transaction",
    "property_type",
    "price",
    "expenses",
    "deposit",
    "district",
    "municipality",
    "parish",
    "address",
    "bedrooms",
    "bathrooms",
    "area_m2",
    "furnished",
    "bills_included",
    "students_allowed",
    "student_only",
    "pets_allowed",
    "accessible",
    "latitude",
    "longitude",
    "image_url",
    "url",
    "contact",
    "published_at",
    "first_seen_at",
    "last_seen_at",
    "is_demo",
]


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def connection(path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: Path = DB_PATH) -> None:
    with connection(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS listings (
                uid TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                source TEXT NOT NULL,
                external_id TEXT,
                title TEXT NOT NULL,
                description TEXT,
                "transaction" TEXT NOT NULL CHECK("transaction" IN ('Arrendar', 'Comprar')),
                property_type TEXT NOT NULL,
                price REAL NOT NULL CHECK(price >= 0),
                expenses REAL NOT NULL DEFAULT 0,
                deposit REAL NOT NULL DEFAULT 0,
                district TEXT NOT NULL,
                municipality TEXT,
                parish TEXT,
                address TEXT,
                bedrooms INTEGER NOT NULL DEFAULT 0,
                bathrooms INTEGER NOT NULL DEFAULT 0,
                area_m2 REAL NOT NULL DEFAULT 0,
                furnished INTEGER NOT NULL DEFAULT 0,
                bills_included INTEGER NOT NULL DEFAULT 0,
                students_allowed INTEGER NOT NULL DEFAULT 0,
                student_only INTEGER NOT NULL DEFAULT 0,
                pets_allowed INTEGER NOT NULL DEFAULT 0,
                accessible INTEGER NOT NULL DEFAULT 0,
                latitude REAL,
                longitude REAL,
                image_url TEXT,
                url TEXT,
                contact TEXT,
                published_at TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_listings_filter
            ON listings("transaction", district, price, property_type);
            CREATE INDEX IF NOT EXISTS idx_listings_fingerprint
            ON listings(fingerprint);

            CREATE TABLE IF NOT EXISTS favorites (
                listing_uid TEXT PRIMARY KEY REFERENCES listings(uid) ON DELETE CASCADE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                "transaction" TEXT NOT NULL,
                district TEXT,
                municipality TEXT,
                max_price REAL NOT NULL DEFAULT 0,
                property_type TEXT,
                student_only INTEGER NOT NULL DEFAULT 0,
                ntfy_topic TEXT,
                created_at TEXT NOT NULL,
                last_checked_at TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS alert_notifications (
                alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
                listing_uid TEXT NOT NULL REFERENCES listings(uid) ON DELETE CASCADE,
                notified_at TEXT NOT NULL,
                PRIMARY KEY(alert_id, listing_uid)
            );
            """
        )


def normalize_listing(raw: dict[str, Any], *, is_demo: bool = False) -> dict[str, Any]:
    now = iso_datetime()
    transaction = clean_text(raw.get("transaction")).capitalize()
    if transaction not in {"Arrendar", "Comprar"}:
        raise ValueError("transaction tem de ser Arrendar ou Comprar")
    row = {
        "source": clean_text(raw.get("source")) or "Importação manual",
        "external_id": clean_text(raw.get("external_id")),
        "title": clean_text(raw.get("title")) or "Anúncio sem título",
        "description": clean_text(raw.get("description")),
        "transaction": transaction,
        "property_type": clean_text(raw.get("property_type")) or "Apartamento",
        "price": as_float(raw.get("price")),
        "expenses": as_float(raw.get("expenses")),
        "deposit": as_float(raw.get("deposit")),
        "district": clean_text(raw.get("district")),
        "municipality": clean_text(raw.get("municipality")),
        "parish": clean_text(raw.get("parish")),
        "address": clean_text(raw.get("address")),
        "bedrooms": as_int(raw.get("bedrooms")),
        "bathrooms": as_int(raw.get("bathrooms")),
        "area_m2": as_float(raw.get("area_m2")),
        "furnished": as_bool(raw.get("furnished")),
        "bills_included": as_bool(raw.get("bills_included")),
        "students_allowed": as_bool(raw.get("students_allowed")),
        "student_only": as_bool(raw.get("student_only")),
        "pets_allowed": as_bool(raw.get("pets_allowed")),
        "accessible": as_bool(raw.get("accessible")),
        "latitude": as_float(raw.get("latitude"), default=0) or None,
        "longitude": as_float(raw.get("longitude"), default=0) or None,
        "image_url": clean_text(raw.get("image_url")),
        "url": canonical_url(raw.get("url")),
        "contact": clean_text(raw.get("contact")),
        "published_at": iso_datetime(raw.get("published_at")),
        "first_seen_at": iso_datetime(raw.get("first_seen_at") or now),
        "last_seen_at": now,
        "is_demo": is_demo or as_bool(raw.get("is_demo")),
    }
    if not row["district"]:
        raise ValueError("district é obrigatório")
    if row["price"] <= 0:
        raise ValueError("price tem de ser superior a zero")
    if row["student_only"]:
        row["students_allowed"] = True
    row["uid"] = listing_uid(row)
    row["fingerprint"] = cross_source_fingerprint(row)
    return row


def upsert_listings(rows: Sequence[dict[str, Any]], path: Path = DB_PATH, *, is_demo: bool = False) -> tuple[int, list[str]]:
    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, raw in enumerate(rows, start=1):
        try:
            normalized.append(normalize_listing(dict(raw), is_demo=is_demo))
        except (TypeError, ValueError) as exc:
            errors.append(f"Linha {index}: {exc}")
    if not normalized:
        return 0, errors

    placeholders = ", ".join("?" for _ in LISTING_COLUMNS)
    quoted_columns = ", ".join(f'"{column}"' for column in LISTING_COLUMNS)
    updates = ", ".join(
        f'"{column}"=excluded."{column}"'
        for column in LISTING_COLUMNS
        if column not in {"uid", "first_seen_at"}
    )
    sql = f"""
        INSERT INTO listings ({quoted_columns})
        VALUES ({placeholders})
        ON CONFLICT(uid) DO UPDATE SET {updates}
    """
    with connection(path) as conn:
        conn.executemany(sql, [[row[column] for column in LISTING_COLUMNS] for row in normalized])
    return len(normalized), errors


def count_listings(path: Path = DB_PATH) -> int:
    with connection(path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0])


def count_demo_listings(path: Path = DB_PATH) -> int:
    with connection(path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM listings WHERE is_demo = 1").fetchone()[0])


def get_listings(path: Path = DB_PATH, include_demo: bool = True) -> list[dict[str, Any]]:
    query = """
        SELECT l.*, EXISTS(SELECT 1 FROM favorites f WHERE f.listing_uid = l.uid) AS favorite,
               (SELECT COUNT(DISTINCT d.source) FROM listings d WHERE d.fingerprint = l.fingerprint) AS source_count
        FROM listings l
    """
    params: list[Any] = []
    if not include_demo:
        query += " WHERE l.is_demo = 0"
    query += " ORDER BY l.published_at DESC"
    with connection(path) as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def toggle_favorite(uid: str, path: Path = DB_PATH) -> bool:
    with connection(path) as conn:
        exists = conn.execute("SELECT 1 FROM favorites WHERE listing_uid = ?", (uid,)).fetchone()
        if exists:
            conn.execute("DELETE FROM favorites WHERE listing_uid = ?", (uid,))
            return False
        conn.execute("INSERT INTO favorites(listing_uid, created_at) VALUES (?, ?)", (uid, iso_datetime()))
        return True


def add_alert(alert: dict[str, Any], path: Path = DB_PATH) -> int:
    now = iso_datetime()
    with connection(path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO alerts(name, "transaction", district, municipality, max_price, property_type,
                               student_only, ntfy_topic, created_at, last_checked_at, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                clean_text(alert.get("name")) or "Pesquisa guardada",
                clean_text(alert.get("transaction")) or "Arrendar",
                clean_text(alert.get("district")),
                clean_text(alert.get("municipality")),
                as_float(alert.get("max_price")),
                clean_text(alert.get("property_type")),
                int(as_bool(alert.get("student_only"))),
                clean_text(alert.get("ntfy_topic")),
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)


def get_alerts(path: Path = DB_PATH, enabled_only: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM alerts"
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY created_at DESC"
    with connection(path) as conn:
        return [dict(row) for row in conn.execute(query).fetchall()]


def set_alert_enabled(alert_id: int, enabled: bool, path: Path = DB_PATH) -> None:
    with connection(path) as conn:
        conn.execute("UPDATE alerts SET enabled = ? WHERE id = ?", (int(enabled), alert_id))


def delete_alert(alert_id: int, path: Path = DB_PATH) -> None:
    with connection(path) as conn:
        conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))


def alert_matches(alert: dict[str, Any], listing: dict[str, Any]) -> bool:
    if alert["transaction"] != listing["transaction"]:
        return False
    if alert.get("district") and alert["district"] != listing["district"]:
        return False
    if alert.get("municipality") and alert["municipality"].casefold() != listing.get("municipality", "").casefold():
        return False
    if alert.get("max_price") and float(listing["price"]) > float(alert["max_price"]):
        return False
    if alert.get("property_type") and alert["property_type"] != listing["property_type"]:
        return False
    return not alert.get("student_only") or bool(listing.get("students_allowed"))


def pending_alert_matches(path: Path = DB_PATH) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    alerts = get_alerts(path, enabled_only=True)
    listings = get_listings(path, include_demo=False)
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    with connection(path) as conn:
        for alert in alerts:
            for listing in listings:
                if listing["first_seen_at"] <= alert["created_at"] or not alert_matches(alert, listing):
                    continue
                sent = conn.execute(
                    "SELECT 1 FROM alert_notifications WHERE alert_id = ? AND listing_uid = ?",
                    (alert["id"], listing["uid"]),
                ).fetchone()
                if not sent:
                    matches.append((alert, listing))
    return matches


def mark_notified(alert_id: int, listing_uid_value: str, path: Path = DB_PATH) -> None:
    with connection(path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO alert_notifications(alert_id, listing_uid, notified_at) VALUES (?, ?, ?)",
            (alert_id, listing_uid_value, iso_datetime()),
        )
        conn.execute("UPDATE alerts SET last_checked_at = ? WHERE id = ?", (iso_datetime(), alert_id))
