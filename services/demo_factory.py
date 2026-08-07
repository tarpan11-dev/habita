from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from config import DISTRICTS


DISTRICT_DATA = {
    "Aveiro": (["Aveiro", "Ílhavo", "Santa Maria da Feira"], 0.92, (40.64, -8.65)),
    "Beja": (["Beja", "Moura", "Odemira"], 0.68, (38.02, -7.86)),
    "Braga": (["Braga", "Guimarães", "Vila Nova de Famalicão"], 0.90, (41.55, -8.42)),
    "Bragança": (["Bragança", "Mirandela", "Macedo de Cavaleiros"], 0.62, (41.81, -6.76)),
    "Castelo Branco": (["Castelo Branco", "Covilhã", "Fundão"], 0.70, (39.82, -7.49)),
    "Coimbra": (["Coimbra", "Figueira da Foz", "Lousã"], 0.95, (40.21, -8.43)),
    "Évora": (["Évora", "Estremoz", "Montemor-o-Novo"], 0.78, (38.57, -7.91)),
    "Faro": (["Faro", "Portimão", "Loulé"], 1.18, (37.02, -7.93)),
    "Guarda": (["Guarda", "Seia", "Gouveia"], 0.63, (40.54, -7.27)),
    "Leiria": (["Leiria", "Caldas da Rainha", "Marinha Grande"], 0.88, (39.74, -8.81)),
    "Lisboa": (["Lisboa", "Oeiras", "Amadora"], 1.48, (38.72, -9.14)),
    "Portalegre": (["Portalegre", "Elvas", "Ponte de Sor"], 0.60, (39.29, -7.43)),
    "Porto": (["Porto", "Matosinhos", "Vila Nova de Gaia"], 1.20, (41.15, -8.61)),
    "Santarém": (["Santarém", "Tomar", "Torres Novas"], 0.78, (39.24, -8.69)),
    "Setúbal": (["Setúbal", "Almada", "Barreiro"], 1.02, (38.52, -8.89)),
    "Viana do Castelo": (["Viana do Castelo", "Ponte de Lima", "Valença"], 0.76, (41.69, -8.83)),
    "Vila Real": (["Vila Real", "Chaves", "Peso da Régua"], 0.68, (41.30, -7.74)),
    "Viseu": (["Viseu", "Tondela", "Lamego"], 0.75, (40.66, -7.91)),
    "Açores": (["Ponta Delgada", "Angra do Heroísmo", "Horta"], 0.86, (37.74, -25.67)),
    "Madeira": (["Funchal", "Câmara de Lobos", "Machico"], 1.00, (32.65, -16.91)),
}

RENT_TITLES = {
    "Quarto": ["Quarto mobilado", "Quarto luminoso", "Quarto perto de transportes", "Quarto em casa partilhada"],
    "Estúdio": ["Estúdio equipado", "T0 renovado", "Estúdio no centro", "T0 com varanda"],
    "Apartamento": ["Apartamento pronto a habitar", "Apartamento perto de serviços", "Apartamento mobilado", "Apartamento com boa exposição solar"],
    "Moradia": ["Moradia com espaço exterior", "Casa tranquila", "Moradia renovada", "Casa perto do centro"],
    "Residência universitária": ["Quarto individual em residência", "Estúdio em residência", "Alojamento universitário", "Quarto em residência estudantil"],
}

BUY_TITLES = {
    "Apartamento": ["Apartamento renovado", "Apartamento para habitação própria", "Apartamento com varanda", "Apartamento perto do centro"],
    "Moradia": ["Moradia com jardim", "Moradia familiar", "Casa renovada", "Moradia com garagem"],
    "Estúdio": ["T0 para investimento", "Estúdio renovado", "T0 no centro", "Estúdio compacto"],
}


def generate_demo_listings(per_district: int = 24, seed: int = 20260807) -> list[dict]:
    """Gera uma montra grande e determinística, sempre marcada como demonstração."""
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    for district in DISTRICTS:
        municipalities, factor, center = DISTRICT_DATA[district]
        for index in range(per_district):
            is_buy = index % 4 == 0
            transaction = "Comprar" if is_buy else "Arrendar"
            municipality = municipalities[index % len(municipalities)]
            if is_buy:
                property_type = rng.choice(list(BUY_TITLES))
                bedrooms = 0 if property_type == "Estúdio" else rng.randint(1, 4)
                area = rng.randint(32, 58) if property_type == "Estúdio" else rng.randint(52, 185)
                price = round((65_000 + area * rng.randint(1_350, 3_150)) * factor / 5_000) * 5_000
                deposit = 0
                expenses = rng.choice([0, 25, 40, 55, 70]) if property_type == "Apartamento" else 0
                titles = BUY_TITLES[property_type]
                students_allowed = False
                student_only = False
            else:
                property_type = rng.choices(
                    ["Quarto", "Estúdio", "Apartamento", "Moradia", "Residência universitária"],
                    weights=[34, 17, 31, 8, 10],
                    k=1,
                )[0]
                bedrooms = 1 if property_type in {"Quarto", "Residência universitária"} else (0 if property_type == "Estúdio" else rng.randint(1, 4))
                area_ranges = {
                    "Quarto": (10, 24),
                    "Residência universitária": (11, 22),
                    "Estúdio": (24, 48),
                    "Apartamento": (45, 130),
                    "Moradia": (75, 180),
                }
                area = rng.randint(*area_ranges[property_type])
                base = {"Quarto": 310, "Residência universitária": 355, "Estúdio": 540, "Apartamento": 720, "Moradia": 980}[property_type]
                price = round((base + max(0, bedrooms - 1) * 205 + rng.randint(-75, 210)) * factor / 5) * 5
                price = max(180, price)
                deposit = price * rng.choice([1, 1, 2])
                expenses = rng.choice([0, 0, 35, 50, 70, 90])
                titles = RENT_TITLES[property_type]
                student_only = property_type == "Residência universitária"
                students_allowed = student_only or rng.random() < 0.68

            suspicious = (not is_buy) and rng.random() < 0.025
            description = (
                "Exemplo fictício suspeito: proprietário no estrangeiro e pagar antes da visita."
                if suspicious
                else "Anúncio fictício para experimentar a pesquisa, os filtros, a comparação e os favoritos."
            )
            external_id = f"generated-{district.lower().replace(' ', '-')}-{index:03d}"
            rows.append(
                {
                    "source": "Montra de demonstração",
                    "external_id": external_id,
                    "title": f"{rng.choice(titles)} — {municipality}",
                    "description": description,
                    "transaction": transaction,
                    "property_type": property_type,
                    "price": price,
                    "expenses": expenses,
                    "deposit": deposit,
                    "district": district,
                    "municipality": municipality,
                    "parish": "",
                    "address": f"Zona de {municipality} {index + 1}",
                    "bedrooms": bedrooms,
                    "bathrooms": 1 if bedrooms < 3 else rng.choice([1, 2, 2, 3]),
                    "area_m2": area,
                    "furnished": (not is_buy) and rng.random() < 0.64,
                    "bills_included": (not is_buy) and expenses == 0 and rng.random() < 0.38,
                    "students_allowed": students_allowed,
                    "student_only": student_only,
                    "pets_allowed": rng.random() < 0.28,
                    "accessible": rng.random() < 0.22,
                    "latitude": center[0] + rng.uniform(-0.16, 0.16),
                    "longitude": center[1] + rng.uniform(-0.16, 0.16),
                    "url": f"https://example.com/habitua/{external_id}",
                    "published_at": (now - timedelta(days=rng.randint(0, 45), hours=rng.randint(0, 23))).isoformat(timespec="seconds"),
                    "is_demo": True,
                }
            )
    return rows

