from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from .normalization import slug


@dataclass(frozen=True)
class Source:
    name: str
    category: str
    homepage: str
    description: str
    modes: tuple[str, ...] = ("Arrendar", "Comprar")


SOURCES = [
    Source("Idealista", "Portais imobiliários", "https://www.idealista.pt/", "Casas, apartamentos e quartos em Portugal."),
    Source("Imovirtual", "Portais imobiliários", "https://www.imovirtual.com/pt/", "Compra e arrendamento de imóveis."),
    Source("SUPERCASA", "Portais imobiliários", "https://supercasa.pt/", "Anúncios de profissionais e particulares."),
    Source("CASA SAPO", "Portais imobiliários", "https://casa.sapo.pt/", "Portal imobiliário nacional."),
    Source("OLX Imóveis", "Classificados", "https://www.olx.pt/imoveis/", "Classificados de particulares e profissionais."),
    Source("BQuarto", "Alojamento estudantil", "https://www.bquarto.pt/", "Quartos e partilhas de casa.", ("Arrendar",)),
    Source("Uniplaces", "Alojamento estudantil", "https://www.uniplaces.com/pt/", "Alojamento de média duração para estudantes.", ("Arrendar",)),
    Source("HousingAnywhere", "Alojamento estudantil", "https://housinganywhere.com/pt/", "Alojamento para estudantes e jovens profissionais.", ("Arrendar",)),
    Source("Spotahome", "Alojamento estudantil", "https://www.spotahome.com/pt", "Arrendamento de quartos e casas verificados.", ("Arrendar",)),
    Source("Observatório do Alojamento Estudantil", "Fontes institucionais", "https://www.observatorioalojamento.pt/", "Informação e oferta orientada a estudantes.", ("Arrendar",)),
    Source("DGES — Alojamento", "Fontes institucionais", "https://www.dges.gov.pt/pt/pagina/alojamento-estudantil-ensino-superior", "Residências, apoios e protocolos oficiais.", ("Arrendar",)),
]


def search_url(source: Source, transaction: str, district: str, municipality: str = "") -> str:
    location = municipality or district
    location_slug = slug(location)
    if source.name == "Idealista" and location_slug:
        action = "arrendar-casas" if transaction == "Arrendar" else "comprar-casas"
        return f"https://www.idealista.pt/{action}/{location_slug}/"
    if source.name == "Imovirtual" and location_slug:
        action = "arrendar" if transaction == "Arrendar" else "comprar"
        return f"https://www.imovirtual.com/pt/resultados/{action}/imoveis/{location_slug}"
    if source.name == "SUPERCASA" and location_slug:
        action = "arrendar-casas" if transaction == "Arrendar" else "comprar-casas"
        return f"https://supercasa.pt/{action}/{location_slug}"
    if source.name == "CASA SAPO" and location_slug:
        action = "alugar" if transaction == "Arrendar" else "comprar"
        return f"https://casa.sapo.pt/{action}/{location_slug}/"
    if source.name == "BQuarto":
        return f"https://www.bquarto.pt/{quote_plus(location)}" if location else source.homepage
    return source.homepage

