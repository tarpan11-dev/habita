# Habitua

Aplicação Streamlit em português para organizar a procura de quartos, residências, apartamentos e moradias para arrendar ou comprar em Portugal.

O Habitua tem duas formas complementares de trabalhar:

1. **Pesquisa multiportal:** cria atalhos para Idealista, Imovirtual, SUPERCASA, CASA SAPO, OLX, BQuarto, Uniplaces, HousingAnywhere, Spotahome e fontes institucionais.
2. **Pesquisa agregada:** mostra numa única interface anúncios recebidos por CSV, JSON, RSS ou feeds/parcerias autorizados.

Não existe recolha automática escondida de portais. Muitos sites não disponibilizam uma API pública ou limitam a reutilização dos anúncios. Esta arquitetura evita bloqueios e permite ligar cada fonte através do canal oficialmente autorizado.

## Funcionalidades

- Arrendamento e compra, com modo orientado a estudantes.
- Filtros por distrito, concelho, preço, tipo, quartos, perfil estudante/público geral, mobília, despesas, animais e acessibilidade.
- Cartões comparáveis, mapa, favoritos e comparação lado a lado.
- Deteção de possíveis duplicados entre fontes.
- Pontuação de compatibilidade e avisos de prudência para linguagem potencialmente suspeita.
- Calculadora de custo de arrendamento e prestação de crédito.
- Importação CSV/JSON e atualização de feeds JSON/RSS.
- Pesquisas guardadas e alertas por ntfy.
- Base de dados SQLite local.
- Mais de 490 resultados fictícios, distribuídos por todos os distritos e claramente identificados para experimentar a interface.
- Intervalo de preço e distrito em destaque, com paginação de 12, 24 ou 48 resultados.

## Instalação no Windows

1. Extrai o ZIP e abre a pasta `habitua` no VS Code.
2. Faz duplo clique em `run.bat`.
3. Aguarda a instalação inicial e abre `http://localhost:8501` se o browser não abrir automaticamente.

Em PowerShell, o equivalente é:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Ligar anúncios reais

### CSV ou JSON

Na página **Importar**, descarrega o modelo CSV. As colunas obrigatórias são:

```text
source, external_id, title, transaction, property_type, price, district
```

O campo `transaction` deve ser `Arrendar` ou `Comprar`. Um JSON pode ser uma lista de objetos ou ter o formato `{"listings": [...]}`.

### Feed JSON autorizado

1. Copia `.env.example` para `.env`.
2. Preenche:

```dotenv
HABITUA_JSON_FEEDS=https://parceiro.example/feed.json,https://outro.example/listings.json
```

### RSS/Atom

```dotenv
HABITUA_RSS_FEEDS=Residência Exemplo|https://residencia.example/feed.xml
HABITUA_RSS_DEFAULTS={"https://residencia.example/feed.xml":{"district":"Porto","price":500,"transaction":"Arrendar","property_type":"Quarto"}}
```

RSS genérico raramente inclui preço e localização em campos estruturados; os valores predefinidos servem apenas para feeds uniformes. Para produção, é preferível um feed JSON com todos os campos.

## Alertas ntfy

1. Instala a aplicação ntfy no telemóvel e subscreve um tópico longo e difícil de adivinhar.
2. Cria um alerta na interface e indica esse tópico.
3. Mantém o monitor em execução:

```powershell
python alert_monitor.py --interval 300
```

Para testar uma vez:

```powershell
python alert_monitor.py --once
```

O monitor só alerta para anúncios reais adicionados depois da criação do alerta; ignora os dados de demonstração.

## Estrutura

```text
habitua/
├── app.py
├── alert_monitor.py
├── config.py
├── db.py
├── services/
│   ├── ingestion.py
│   ├── normalization.py
│   ├── ranking.py
│   └── sources.py
├── data/demo_listings.csv
├── tests/test_core.py
├── .env.example
├── requirements.txt
├── run.bat
└── run.sh
```

## Segurança e limites

- A pontuação não garante qualidade nem ausência de fraude.
- Visita o imóvel, confirma identidade e legitimidade do anunciante, lê o contrato e não pagues apenas para “reservar” uma casa não verificada.
- Confirma preços e disponibilidade no anúncio original.
- Usa apenas feeds que tenhas autorização para consultar, guardar e apresentar.
- SQLite é adequado para uso local ou uma pequena demonstração. Para uma aplicação pública com vários utilizadores, troca a persistência por PostgreSQL e adiciona autenticação.

## Testes

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```
