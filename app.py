from __future__ import annotations

import html
import math
import pandas as pd
import streamlit as st

from config import APP_NAME, BASE_DIR, DEMO_DATA_PATH, DISTRICTS, PROPERTY_TYPES, TRANSACTIONS
from db import (
    add_alert,
    count_listings,
    count_demo_listings,
    delete_alert,
    get_alerts,
    get_listings,
    init_db,
    set_alert_enabled,
    toggle_favorite,
    upsert_listings,
)
from services.ingestion import REQUIRED_COLUMNS, configured_feeds, ingest_configured_feeds, rows_from_upload
from services.demo_factory import generate_demo_listings
from services.ranking import comparable_median, days_old, fraud_warnings, relevance_score
from services.sources import SOURCES, search_url


st.set_page_config(page_title=f"{APP_NAME} — Habitação em Portugal", page_icon="🏡", layout="wide")


CSS = """
<style>
  .block-container {max-width: 1280px; padding-top: 1.6rem; padding-bottom: 4rem;}
  [data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,.18);}
  .hero {padding: 1.35rem 1.5rem; border-radius: 22px; color: white;
    background: linear-gradient(125deg, #173d35 0%, #1e6654 58%, #d28b4b 140%);
    box-shadow: 0 14px 36px rgba(18,62,52,.18); margin-bottom: 1.1rem;}
  .hero h1 {font-size: clamp(2rem, 5vw, 3.5rem); line-height: 1; margin: 0 0 .55rem;}
  .hero p {max-width: 760px; font-size: 1.05rem; margin: 0; opacity: .9;}
  .eyebrow {text-transform: uppercase; letter-spacing: .12em; font-size: .73rem; font-weight: 700; opacity:.78;}
  .muted {color: #6f7b77; font-size: .9rem;}
  .badge {display:inline-block; padding:.22rem .58rem; margin:0 .28rem .28rem 0; border-radius:999px;
    background:rgba(33,116,94,.11); color:#17634f; font-size:.78rem; font-weight:650;}
  .badge.warn {background:rgba(217,130,43,.14); color:#9a540e;}
  .badge.demo {background:rgba(90,98,111,.12); color:#59616e;}
  .source-card {padding: 1rem 1.1rem; border:1px solid rgba(128,128,128,.2); border-radius:16px; min-height:130px;}
  .price {font-size:1.65rem; font-weight:780; color:#17634f; line-height:1.1;}
  .listing-title {font-size:1.12rem; font-weight:750; line-height:1.25; margin-bottom:.35rem;}
  .footer-note {padding:1rem; border-radius:14px; background:rgba(33,116,94,.07); margin-top:2rem;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def seed_database() -> None:
    init_db()
    if count_demo_listings() < 400:
        rows = generate_demo_listings(per_district=24)
        if DEMO_DATA_PATH.exists():
            frame = pd.read_csv(DEMO_DATA_PATH)
            rows.extend(frame.where(pd.notna(frame), None).to_dict(orient="records"))
        upsert_listings(rows, is_demo=True)


@st.cache_data(ttl=15, show_spinner=False)
def load_listings(include_demo: bool = True) -> list[dict]:
    return get_listings(include_demo=include_demo)


def clear_listing_cache() -> None:
    load_listings.clear()


def money(value: float, transaction: str = "Arrendar") -> str:
    amount = f"{value:,.0f} €".replace(",", " ")
    return amount + (" / mês" if transaction == "Arrendar" else "")


def hero(kicker: str, title: str, body: str) -> None:
    st.markdown(
        f'<div class="hero"><div class="eyebrow">{html.escape(kicker)}</div>'
        f'<h1>{html.escape(title)}</h1><p>{html.escape(body)}</p></div>',
        unsafe_allow_html=True,
    )


def district_options(listings: list[dict]) -> list[str]:
    available = {str(item["district"]) for item in listings if item.get("district")}
    return [district for district in DISTRICTS if district in available] + sorted(available.difference(DISTRICTS))


def filter_listings(listings: list[dict], filters: dict) -> list[dict]:
    text_query = filters.get("text", "").casefold()
    result = []
    for item in listings:
        haystack = " ".join(
            str(item.get(field, ""))
            for field in ("title", "description", "municipality", "parish", "address", "source")
        ).casefold()
        if item["transaction"] != filters["transaction"]:
            continue
        if filters["district"] and item["district"] != filters["district"]:
            continue
        if filters["municipality"] and item.get("municipality") != filters["municipality"]:
            continue
        if filters["property_types"] and item["property_type"] not in filters["property_types"]:
            continue
        if not filters["min_price"] <= float(item["price"]) <= filters["max_price"]:
            continue
        if int(item.get("bedrooms") or 0) < filters["min_bedrooms"]:
            continue
        if filters["students_only"] and not item.get("students_allowed"):
            continue
        if filters["general_public"] and item.get("student_only"):
            continue
        if filters["furnished"] and not item.get("furnished"):
            continue
        if filters["bills_included"] and not item.get("bills_included"):
            continue
        if filters["pets"] and not item.get("pets_allowed"):
            continue
        if filters["accessible"] and not item.get("accessible"):
            continue
        if text_query and text_query not in haystack:
            continue
        result.append(item)
    return result


def deduplicate(listings: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for item in listings:
        current = grouped.get(item["fingerprint"])
        if current is None or item.get("published_at", "") > current.get("published_at", ""):
            grouped[item["fingerprint"]] = item
    return list(grouped.values())


def render_listing(item: dict, universe: list[dict], student_mode: bool) -> None:
    local_median = comparable_median(universe, item)
    warnings = fraud_warnings(item, local_median)
    score = relevance_score(item, student_mode, local_median)
    with st.container(border=True):
        left, middle, right = st.columns([1.2, 4.3, 1.7], vertical_alignment="top")
        with left:
            st.markdown(
                f'<div class="price">{money(float(item["price"]), item["transaction"])}</div>',
                unsafe_allow_html=True,
            )
            if item.get("expenses"):
                st.caption(f'+ {money(float(item["expenses"]))} de despesas')
            if item.get("area_m2") and item["transaction"] == "Comprar":
                st.caption(f'{money(float(item["price"]) / float(item["area_m2"]), "Comprar")} / m²')
            st.metric("Compatibilidade", f"{score}/100")
        with middle:
            st.markdown(f'<div class="listing-title">{html.escape(str(item["title"]))}</div>', unsafe_allow_html=True)
            location = ", ".join(filter(None, [item.get("parish"), item.get("municipality"), item.get("district")]))
            st.caption(f"📍 {location} · {item.get('source', 'Fonte não indicada')}")
            badges = [item.get("property_type", "Imóvel")]
            if item.get("bedrooms"):
                badges.append(f"T{item['bedrooms']}")
            if item.get("area_m2"):
                badges.append(f"{float(item['area_m2']):g} m²")
            if item.get("furnished"):
                badges.append("Mobilado")
            if item.get("bills_included"):
                badges.append("Despesas incluídas")
            if item.get("student_only"):
                badges.append("Exclusivo para estudantes")
            elif item.get("students_allowed"):
                badges.append("Aceita estudantes")
            else:
                badges.append("Público geral")
            badge_html = "".join(f'<span class="badge">{html.escape(str(label))}</span>' for label in badges)
            if item.get("is_demo"):
                badge_html += '<span class="badge demo">Demonstração — não é um anúncio real</span>'
            if warnings:
                badge_html += f'<span class="badge warn">⚠ {len(warnings)} sinal(is) a verificar</span>'
            st.markdown(badge_html, unsafe_allow_html=True)
            if item.get("description"):
                st.write(item["description"])
            if int(item.get("source_count") or 1) > 1:
                st.caption(f"Possível duplicado encontrado em {item['source_count']} fontes; foi mostrada uma só ficha.")
            if warnings:
                with st.expander("Ver verificações de segurança"):
                    for warning in warnings:
                        st.write(f"• {warning}")
                    st.caption("Estes sinais não provam fraude. Confirma sempre identidade, propriedade e contrato.")
        with right:
            age = days_old(item.get("published_at"))
            st.caption("Hoje" if age == 0 else f"Há {age} dia(s)" if age < 999 else "Data desconhecida")
            label = "♥ Guardado" if item.get("favorite") else "♡ Guardar"
            if st.button(label, key=f"fav-{item['uid']}", use_container_width=True):
                toggle_favorite(item["uid"])
                clear_listing_cache()
                st.rerun()
            if item.get("url"):
                st.link_button("Abrir anúncio original ↗", item["url"], use_container_width=True)
            compare_key = f"compare-{item['uid']}"
            st.checkbox("Comparar", key=compare_key)


def page_discover() -> None:
    hero("Pesquisa habitacional em Portugal", "Encontra casa sem perder o fio", "Arrendamento, compra e alojamento estudantil numa pesquisa organizada, comparável e mais segura.")
    all_rows = load_listings(include_demo=True)
    real_count = sum(not item.get("is_demo") for item in all_rows)
    if real_count == 0:
        st.info("Estás a ver dados fictícios para explorar a aplicação. Importa um feed autorizado, CSV ou JSON para mostrar anúncios reais.")

    st.markdown("### Pesquisa rápida")
    q1, q2, q3, q4 = st.columns([1.25, 1.4, 1, 1])
    with q1:
        transaction = st.segmented_control("Objetivo", TRANSACTIONS, default="Arrendar") or "Arrendar"
    available = [item for item in all_rows if item["transaction"] == transaction]
    districts = district_options(available)
    with q2:
        district = st.selectbox("Distrito", [""] + districts, format_func=lambda x: x or "Portugal inteiro")
    prices = [float(item["price"]) for item in available if not district or item["district"] == district]
    default_max = int(max(prices, default=2_000 if transaction == "Arrendar" else 750_000))
    step = 25 if transaction == "Arrendar" else 5_000
    with q3:
        min_price = st.number_input(
            "Preço mínimo (€ / mês)" if transaction == "Arrendar" else "Preço mínimo (€)",
            min_value=0,
            value=0,
            step=step,
            key=f"quick-min-{transaction}",
        )
    with q4:
        max_price = st.number_input(
            "Preço máximo (€ / mês)" if transaction == "Arrendar" else "Preço máximo (€)",
            min_value=0,
            value=default_max,
            step=step,
            key=f"quick-max-{transaction}-{district or 'all'}",
        )
    if min_price > max_price:
        st.warning("O preço mínimo é superior ao máximo. Troca os dois valores para veres resultados.")

    with st.sidebar:
        st.markdown("### Filtros avançados")
        municipalities = sorted({item.get("municipality") for item in available if item.get("municipality") and (not district or item["district"] == district)})
        municipality = st.selectbox("Concelho", [""] + municipalities, format_func=lambda x: x or "Todos")
        property_types = st.multiselect("Tipo de imóvel", PROPERTY_TYPES)
        min_bedrooms = st.number_input("Quartos mínimos", min_value=0, max_value=15, value=0)
        audience = st.selectbox("Perfil", ["Todos", "Estudantes", "Público geral / não estudantes"])
        students_only = audience == "Estudantes"
        general_public = audience == "Público geral / não estudantes"
        furnished = st.checkbox("Mobilado")
        bills_included = st.checkbox("Despesas incluídas")
        pets = st.checkbox("Aceita animais")
        accessible = st.checkbox("Acessível / mobilidade reduzida")
        text_query = st.text_input("Palavra-chave", placeholder="metro, varanda, universidade…")
        include_demo = st.toggle("Mostrar demonstração", value=True)

    filters = {
        "transaction": transaction,
        "district": district,
        "municipality": municipality,
        "property_types": property_types,
        "min_price": float(min_price),
        "max_price": float(max_price),
        "min_bedrooms": int(min_bedrooms),
        "students_only": students_only,
        "general_public": general_public,
        "furnished": furnished,
        "bills_included": bills_included,
        "pets": pets,
        "accessible": accessible,
        "text": text_query,
    }
    rows = [item for item in all_rows if include_demo or not item.get("is_demo")]
    filtered = deduplicate(filter_listings(rows, filters))

    controls, page_size_col, map_col = st.columns([3, 1, 1])
    with controls:
        sort = st.selectbox("Ordenar", ["Mais relevantes", "Mais recentes", "Preço mais baixo", "Maior área"], label_visibility="collapsed")
    with page_size_col:
        page_size = st.selectbox("Por página", [12, 24, 48], index=1)
    with map_col:
        show_map = st.toggle("Mapa")

    if sort == "Mais relevantes":
        filtered.sort(key=lambda item: relevance_score(item, students_only, comparable_median(rows, item)), reverse=True)
    elif sort == "Mais recentes":
        filtered.sort(key=lambda item: item.get("published_at", ""), reverse=True)
    elif sort == "Preço mais baixo":
        filtered.sort(key=lambda item: float(item["price"]))
    else:
        filtered.sort(key=lambda item: float(item.get("area_m2") or 0), reverse=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Resultados", len(filtered))
    m2.metric("Mediana", money(float(pd.Series([item["price"] for item in filtered]).median()), transaction) if filtered else "—")
    m3.metric("Aceitam estudantes", sum(bool(item.get("students_allowed")) for item in filtered))
    m4.metric("Com despesas incluídas", sum(bool(item.get("bills_included")) for item in filtered))

    page_count = max(1, math.ceil(len(filtered) / page_size))
    page_key = f"results-page-{transaction}-{page_size}"
    if st.session_state.get(page_key, 1) > page_count:
        st.session_state[page_key] = 1
    page_col, summary_col = st.columns([1, 4], vertical_alignment="bottom")
    with page_col:
        page_number = int(st.number_input("Página", min_value=1, max_value=page_count, value=1, key=page_key))
    start = (page_number - 1) * page_size
    visible = filtered[start : start + page_size]
    with summary_col:
        if filtered:
            st.caption(f"A mostrar {start + 1}–{min(start + page_size, len(filtered))} de {len(filtered)} resultados · página {page_number} de {page_count}")

    if show_map:
        points = pd.DataFrame(
            [{"lat": item["latitude"], "lon": item["longitude"], "title": item["title"]} for item in filtered if item.get("latitude") and item.get("longitude")]
        )
        if points.empty:
            st.warning("Os resultados atuais não têm coordenadas.")
        else:
            st.map(points, latitude="lat", longitude="lon", size=32, color="#21745e")

    if not filtered:
        st.warning("Não encontrei resultados com estes filtros. Aumenta o preço máximo ou retira um dos critérios.")
    for item in visible:
        render_listing(item, rows, students_only)

    compared = [item for item in filtered if st.session_state.get(f"compare-{item['uid']}")]
    if compared:
        st.markdown("### Comparação rápida")
        comparison = pd.DataFrame(
            {
                item["title"]: {
                    "Preço": money(float(item["price"]), item["transaction"]),
                    "Despesas": money(float(item.get("expenses") or 0)),
                    "Área": f"{float(item.get('area_m2') or 0):g} m²",
                    "Quartos": item.get("bedrooms", 0),
                    "Mobilado": "Sim" if item.get("furnished") else "Não",
                    "Estudantes": "Sim" if item.get("students_allowed") else "Não",
                    "Concelho": item.get("municipality", ""),
                }
                for item in compared[:4]
            }
        )
        st.dataframe(comparison, use_container_width=True)
        if len(compared) > 4:
            st.caption("A comparação mostra no máximo quatro imóveis.")


def page_portals() -> None:
    hero("Pesquisa multiportal", "Procura em várias fontes", "Abre pesquisas nas principais plataformas e consulta também opções institucionais para estudantes.")
    c1, c2, c3 = st.columns(3)
    transaction = c1.selectbox("Objetivo", TRANSACTIONS)
    district = c2.selectbox("Distrito", DISTRICTS, index=DISTRICTS.index("Porto"))
    municipality = c3.text_input("Concelho (opcional)", placeholder="Ex.: Matosinhos")
    st.caption("As ligações levam ao portal original. Confirma os filtros na página de destino, pois os endereços de pesquisa podem mudar.")
    categories = list(dict.fromkeys(source.category for source in SOURCES))
    for category in categories:
        st.markdown(f"### {category}")
        eligible = [source for source in SOURCES if source.category == category and transaction in source.modes]
        columns = st.columns(3)
        for index, source in enumerate(eligible):
            with columns[index % 3]:
                with st.container(border=True):
                    st.markdown(f"#### {source.name}")
                    st.write(source.description)
                    st.link_button("Pesquisar nesta fonte ↗", search_url(source, transaction, district, municipality), use_container_width=True)


def page_favorites() -> None:
    hero("Lista pessoal", "Favoritos", "Guarda candidatos, compara custos e mantém apenas os imóveis que merecem uma visita.")
    rows = [item for item in load_listings() if item.get("favorite")]
    rows = deduplicate(rows)
    if not rows:
        st.info("Ainda não guardaste nenhum imóvel. Usa ♡ Guardar na página Descobrir.")
        return
    for item in rows:
        render_listing(item, rows, bool(item.get("students_allowed")))


def page_alerts() -> None:
    hero("Novos anúncios", "Alertas ntfy", "Guarda critérios e recebe uma notificação quando um feed autorizado trouxer um novo resultado compatível.")
    with st.form("new-alert", border=True):
        st.markdown("### Criar alerta")
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Nome", placeholder="Quarto no Porto até 450 €")
        transaction = c2.selectbox("Objetivo", TRANSACTIONS)
        district = c3.selectbox("Distrito", [""] + DISTRICTS, format_func=lambda value: value or "Qualquer")
        c4, c5, c6 = st.columns(3)
        municipality = c4.text_input("Concelho (opcional)")
        max_price = c5.number_input("Preço máximo", min_value=0, value=500 if transaction == "Arrendar" else 250_000, step=25 if transaction == "Arrendar" else 5_000)
        property_type = c6.selectbox("Tipo", [""] + PROPERTY_TYPES, format_func=lambda value: value or "Qualquer")
        student_only = st.checkbox("Apenas opções que aceitam estudantes")
        ntfy_topic = st.text_input("Tópico ntfy", placeholder="habitua-henrique-codigo-privado")
        st.caption("Usa um tópico difícil de adivinhar ou um servidor ntfy autenticado. O tópico não é uma palavra-passe.")
        submitted = st.form_submit_button("Guardar alerta", type="primary")
        if submitted:
            add_alert(
                {
                    "name": name,
                    "transaction": transaction,
                    "district": district,
                    "municipality": municipality,
                    "max_price": max_price,
                    "property_type": property_type,
                    "student_only": student_only,
                    "ntfy_topic": ntfy_topic,
                }
            )
            st.success("Alerta guardado. Executa o monitor para receber notificações automáticas.")
            st.rerun()

    alerts = get_alerts()
    if not alerts:
        return
    st.markdown("### Alertas guardados")
    for alert in alerts:
        with st.container(border=True):
            left, middle, right = st.columns([4, 2, 1])
            left.markdown(f"**{alert['name']}**")
            criteria = [alert["transaction"], alert.get("district") or "Portugal", alert.get("property_type") or "Todos os tipos"]
            if alert.get("max_price"):
                criteria.append(f"até {money(alert['max_price'], alert['transaction'])}")
            left.caption(" · ".join(criteria))
            enabled = middle.toggle("Ativo", value=bool(alert["enabled"]), key=f"alert-enabled-{alert['id']}")
            if enabled != bool(alert["enabled"]):
                set_alert_enabled(alert["id"], enabled)
                st.rerun()
            if right.button("Eliminar", key=f"delete-alert-{alert['id']}"):
                delete_alert(alert["id"])
                st.rerun()
    st.code("python alert_monitor.py --interval 300", language="powershell")


def page_calculator() -> None:
    hero("Planeamento", "Calculadora de custos", "Transforma o preço do anúncio numa estimativa mais próxima do esforço financeiro real.")
    rent_tab, buy_tab = st.tabs(["Arrendamento", "Compra"])
    with rent_tab:
        c1, c2, c3 = st.columns(3)
        rent = c1.number_input("Renda mensal (€)", min_value=0.0, value=650.0, step=25.0)
        expenses = c2.number_input("Despesas mensais (€)", min_value=0.0, value=80.0, step=10.0)
        deposit_months = c3.number_input("Meses de caução", min_value=0, max_value=12, value=2)
        income = st.number_input("Rendimento líquido mensal do agregado (€)", min_value=0.0, value=1500.0, step=50.0)
        monthly = rent + expenses
        upfront = rent + rent * deposit_months
        effort = monthly / income * 100 if income else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Custo mensal", money(monthly))
        m2.metric("Entrada estimada", money(upfront, "Comprar"))
        m3.metric("Taxa de esforço", f"{effort:.1f}%" if income else "—")
        st.caption("Não inclui mudança, mobiliário, comissões ou outros custos contratuais.")
    with buy_tab:
        c1, c2, c3 = st.columns(3)
        price = c1.number_input("Preço do imóvel (€)", min_value=0.0, value=220_000.0, step=5_000.0)
        down_payment = c2.number_input("Entrada (€)", min_value=0.0, value=44_000.0, step=5_000.0)
        years = c3.number_input("Prazo (anos)", min_value=1, max_value=50, value=35)
        c4, c5, c6 = st.columns(3)
        annual_rate = c4.number_input("Taxa anual estimada (%)", min_value=0.0, value=3.5, step=0.1)
        condo = c5.number_input("Condomínio mensal (€)", min_value=0.0, value=45.0, step=5.0)
        insurance = c6.number_input("Seguros mensais (€)", min_value=0.0, value=35.0, step=5.0)
        principal = max(0.0, price - down_payment)
        months = years * 12
        monthly_rate = annual_rate / 100 / 12
        payment = principal / months if monthly_rate == 0 else principal * monthly_rate * (1 + monthly_rate) ** months / ((1 + monthly_rate) ** months - 1)
        total_monthly = payment + condo + insurance
        m1, m2, m3 = st.columns(3)
        m1.metric("Crédito estimado", money(payment))
        m2.metric("Total mensal base", money(total_monthly))
        m3.metric("Capital financiado", money(principal, "Comprar"))
        st.warning("Estimativa indicativa: não inclui IMT, Imposto do Selo, escritura, avaliação, comissões nem variações de taxa. Confirma sempre numa simulação bancária.")


def template_csv() -> bytes:
    columns = sorted(REQUIRED_COLUMNS) + [
        "external_id", "description", "expenses", "deposit", "municipality", "parish", "address",
        "bedrooms", "bathrooms", "area_m2", "furnished", "bills_included", "students_allowed",
        "student_only", "pets_allowed", "accessible", "latitude", "longitude", "image_url", "url", "contact", "published_at",
    ]
    return pd.DataFrame(columns=columns).to_csv(index=False).encode("utf-8")


def page_import() -> None:
    hero("Dados e integrações", "Importar anúncios", "Adiciona ficheiros próprios ou atualiza feeds autorizados sem misturar exemplos com dados reais.")
    upload_tab, feeds_tab = st.tabs(["CSV / JSON", "Feeds configurados"])
    with upload_tab:
        st.download_button("Descarregar modelo CSV", template_csv(), "habitua_modelo.csv", "text/csv")
        uploaded = st.file_uploader("Seleciona um ficheiro", type=["csv", "json"])
        if uploaded and st.button("Validar e importar", type="primary"):
            try:
                rows = rows_from_upload(uploaded.name, uploaded.getvalue())
                count, errors = upsert_listings(rows)
                clear_listing_cache()
                if count:
                    st.success(f"{count} anúncios processados.")
                if errors:
                    st.warning("Algumas linhas não foram importadas:\n\n" + "\n\n".join(errors[:10]))
            except Exception as exc:
                st.error(f"Não foi possível importar: {exc}")
        with st.expander("Formato esperado"):
            st.write("Colunas obrigatórias: " + ", ".join(sorted(REQUIRED_COLUMNS)))
            st.write("Valores booleanos aceites: Sim/Não, true/false ou 1/0. Os preços devem ser numéricos.")
    with feeds_tab:
        feeds = list(configured_feeds())
        if feeds:
            st.dataframe(pd.DataFrame(feeds, columns=["Tipo", "Endereço", "Nome"]), hide_index=True, use_container_width=True)
            if st.button("Atualizar agora", type="primary"):
                with st.spinner("A atualizar feeds…"):
                    count, messages = ingest_configured_feeds()
                clear_listing_cache()
                st.success(f"{count} anúncios processados.")
                for message in messages:
                    st.write(f"• {message}")
        else:
            st.info("Ainda não existem feeds configurados. Adiciona HABITUA_JSON_FEEDS ou HABITUA_RSS_FEEDS ao ficheiro .env.")
        st.caption("Liga apenas feeds que tens autorização para consultar e republicar.")


def page_guide() -> None:
    hero("Transparência e segurança", "Como usar o Habitua", "A aplicação organiza a pesquisa; a decisão final continua a exigir visita, documentos e contrato.")
    st.markdown("### Antes de pagar")
    checks = [
        "Visita o imóvel ou pede uma visita por vídeo em direto com confirmação da localização.",
        "Confirma a identidade do senhorio ou mediador e a legitimidade para arrendar ou vender.",
        "Lê o contrato completo, inventário, despesas, duração, caução e condições de saída.",
        "Não envies dinheiro apenas para reservar um imóvel que não verificaste.",
        "Guarda anúncios, mensagens, recibos e comprovativos num local seguro.",
    ]
    for check in checks:
        st.checkbox(check, key=f"safety-{check}")
    st.markdown("### O que significam as pontuações")
    st.write("A compatibilidade privilegia anúncios recentes, completos e adequados aos filtros. Os avisos são regras de prudência, não uma acusação de fraude nem uma garantia de segurança.")
    st.markdown("### Fontes e privacidade")
    st.write("Cada anúncio mantém a ligação para a origem. O Habitua não copia anúncios de portais sem autorização: recebe feeds próprios/parceiros, importações do utilizador e disponibiliza atalhos de pesquisa para as restantes plataformas.")


seed_database()

with st.sidebar:
    st.markdown("# 🏡 Habitua")
    st.caption("Habitação clara, num só lugar")
    page = st.radio(
        "Navegação",
        ["Descobrir", "Pesquisar nos portais", "Favoritos", "Alertas", "Calculadora", "Importar", "Guia e segurança"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(f"Base local: {count_listings()} registos")

PAGES = {
    "Descobrir": page_discover,
    "Pesquisar nos portais": page_portals,
    "Favoritos": page_favorites,
    "Alertas": page_alerts,
    "Calculadora": page_calculator,
    "Importar": page_import,
    "Guia e segurança": page_guide,
}
PAGES[page]()

st.markdown(
    '<div class="footer-note"><strong>Habitua</strong> organiza resultados e ajuda a comparar. '
    'Preços, disponibilidade e condições devem ser confirmados no anúncio original.</div>',
    unsafe_allow_html=True,
)
