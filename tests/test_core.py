from __future__ import annotations

from pathlib import Path

from db import count_listings, get_listings, init_db, normalize_listing, toggle_favorite, upsert_listings
from services.ranking import fraud_warnings, relevance_score
from services.demo_factory import generate_demo_listings


def sample(**overrides):
    row = {
        "source": "Teste",
        "external_id": "abc-1",
        "title": "Quarto mobilado",
        "description": "Visitas disponíveis.",
        "transaction": "Arrendar",
        "property_type": "Quarto",
        "price": 420,
        "district": "Porto",
        "municipality": "Porto",
        "address": "Zona universitária",
        "students_allowed": "Sim",
        "published_at": "2026-08-06T12:00:00+00:00",
        "url": "https://example.com/listing/1?tracking=abc",
    }
    row.update(overrides)
    return row


def test_normalization_is_stable():
    first = normalize_listing(sample())
    second = normalize_listing(sample(url="https://example.com/listing/1?other=1"))
    assert first["uid"] == second["uid"]
    assert first["students_allowed"] is True
    assert first["url"] == "https://example.com/listing/1"


def test_database_upsert_and_favorite(tmp_path: Path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    inserted, errors = upsert_listings([sample()], path=db_path)
    assert inserted == 1
    assert not errors
    assert count_listings(db_path) == 1
    listing = get_listings(db_path)[0]
    assert toggle_favorite(listing["uid"], db_path) is True
    assert get_listings(db_path)[0]["favorite"] == 1


def test_suspicious_listing_loses_score():
    safe = normalize_listing(sample())
    suspicious = normalize_listing(
        sample(
            external_id="abc-2",
            title="Preço urgente hoje",
            description="Proprietário no estrangeiro; pagar antes da visita por criptomoeda.",
            price=150,
        )
    )
    assert len(fraud_warnings(suspicious, local_median=420)) >= 3
    assert relevance_score(safe, True, 420) > relevance_score(suspicious, True, 420)


def test_large_demo_catalog_covers_every_district():
    rows = generate_demo_listings(per_district=24)
    assert len(rows) == 480
    assert len({row["district"] for row in rows}) == 20
    assert all(row["is_demo"] for row in rows)
    assert {row["transaction"] for row in rows} == {"Arrendar", "Comprar"}
