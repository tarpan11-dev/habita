from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # permite testar o núcleo antes de instalar dependências da interface
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False


APP_NAME = "Habitua"
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.getenv("HABITUA_DB_PATH", DATA_DIR / "habitua.db"))
DEMO_DATA_PATH = DATA_DIR / "demo_listings.csv"

DISTRICTS = [
    "Aveiro",
    "Beja",
    "Braga",
    "Bragança",
    "Castelo Branco",
    "Coimbra",
    "Évora",
    "Faro",
    "Guarda",
    "Leiria",
    "Lisboa",
    "Portalegre",
    "Porto",
    "Santarém",
    "Setúbal",
    "Viana do Castelo",
    "Vila Real",
    "Viseu",
    "Açores",
    "Madeira",
]

PROPERTY_TYPES = [
    "Quarto",
    "Apartamento",
    "Moradia",
    "Estúdio",
    "Residência universitária",
]

TRANSACTIONS = ["Arrendar", "Comprar"]
