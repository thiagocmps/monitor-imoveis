"""Painel Streamlit do Monitor Imobiliário.

Lançar com:  streamlit run app.py   (ou  python main.py dashboard)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st
from monitor.database.migrations import initialize_database
from monitor.database.repository import Repository
from monitor.database.session import Database
from monitor.services.export import properties_to_dataframe
from monitor.settings import Settings, apply_overrides, load_settings

st.set_page_config(page_title="Monitor Imobiliário", layout="wide")

_CLASSIFICATION_ORDER = ["PRIORITY_HIGH", "ANALYZE", "WATCH", "LOW_PRIORITY", "EXCLUDE"]

_TYPE_LABELS = {
    "APARTMENT": "Apartamento",
    "HOUSE": "Casa",
    "LAND": "Terreno",
    "COMMERCIAL": "Comercial",
    "OTHER": "Outro",
    "UNKNOWN": "Desconhecido",
}


@st.cache_resource
def _database() -> Database:
    settings = load_settings()
    db = Database(settings)
    initialize_database(db.engine)
    return db


@st.cache_data(ttl=30, show_spinner=False)
def _load_data() -> tuple[pd.DataFrame, dict[str, int]]:
    db = _database()
    session = db.new_session()
    try:
        repo = Repository(session)
        properties = repo.list_properties(status="ACTIVE")
        rows = properties_to_dataframe(_rows(properties))
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
        summary = {
            "active": len(properties),
            "new_24h": repo.count_new_since(since),
        }
    finally:
        session.close()
    return rows, summary


def _rows(properties: list) -> list[dict]:
    return [
        {
            "id": p.id,
            "score": p.score,
            "classification": p.classification,
            "title": p.title,
            "price": p.price,
            "currency": p.currency,
            "property_type": p.property_type,
            "usable_area_m2": p.usable_area_m2,
            "price_per_m2": p.price_per_m2,
            "municipality": p.municipality,
            "parish": p.parish,
            "distance_from_povoa_km": p.distance_from_povoa_km,
            "source": p.source,
            "renovation_level": p.renovation_level,
            "occupancy_status": p.occupancy_status,
            "legal_ownership_type": p.legal_ownership_type,
            "sale_method": p.sale_method,
            "status": p.status,
            "auction_end_at": p.auction_end_at,
            "url": p.url,
            "first_seen_at": p.first_seen_at,
            "last_seen_at": p.last_seen_at,
        }
        for p in properties
    ]


def _effective_settings() -> Settings:
    settings = load_settings()
    db = _database()
    session = db.new_session()
    try:
        overrides = Repository(session).get_override("search")
    finally:
        session.close()
    return apply_overrides(settings, overrides)


def _save_override(overrides: dict) -> None:
    db = _database()
    session = db.new_session()
    try:
        Repository(session).set_override("search", overrides)
        session.commit()
    finally:
        session.close()


def _clear_override() -> None:
    db = _database()
    session = db.new_session()
    try:
        Repository(session).clear_override("search")
        session.commit()
    finally:
        session.close()


def _render_collection_config() -> Settings:
    effective = _effective_settings()
    search = effective.search
    st.sidebar.header("Configuração da recolha")
    st.sidebar.caption("Aplica-se na próxima recolha (coletor automático).")
    with st.sidebar.form("collection_config"):
        maximum_price_eur = st.number_input(
            "Preço máximo (EUR)",
            min_value=1_000,
            max_value=1_000_000,
            step=5_000,
            value=int(search.maximum_price_eur),
        )
        radius_enabled = st.checkbox("Filtrar por raio (km)", value=search.radius.enabled)
        maximum_km = st.slider(
            "Raio máximo (km)",
            min_value=1.0,
            max_value=100.0,
            step=1.0,
            value=float(search.radius.maximum_km),
            disabled=not radius_enabled,
        )
        accepted_types = st.multiselect(
            "Tipos aceites",
            options=list(_TYPE_LABELS),
            default=search.accepted_property_types,
            format_func=_TYPE_LABELS.get,
        )
        accept_unknown = st.checkbox("Aceitar tipo desconhecido", value=search.accept_unknown_type)
        include_occupied = st.checkbox(
            "Incluir imóveis ocupados", value=search.include_occupied_properties
        )
        include_ruins = st.checkbox("Incluir ruínas", value=search.include_ruins)
        unknown_penalty = st.number_input(
            "Penalidade por tipo desconhecido (score)",
            min_value=-50,
            max_value=0,
            step=1,
            value=int(effective.scoring.unknown_type_penalty),
        )
        saved = st.form_submit_button("Guardar", type="primary")
        reset = st.form_submit_button("Repor predefinições")

    if saved:
        _save_override(
            {
                "maximum_price_eur": float(maximum_price_eur),
                "accepted_property_types": list(accepted_types) or ["APARTMENT", "HOUSE"],
                "accept_unknown_type": bool(accept_unknown),
                "include_occupied_properties": bool(include_occupied),
                "include_ruins": bool(include_ruins),
                "radius.enabled": bool(radius_enabled),
                "radius.maximum_km": float(maximum_km),
                "scoring.unknown_type_penalty": float(unknown_penalty),
            }
        )
        st.sidebar.success("Configuração guardada — aplica-se na próxima recolha.")
        st.rerun()
    if reset:
        _clear_override()
        st.sidebar.success("Configuração reposta às predefinições.")
        st.rerun()
    return effective


def _render_collection_preview(rows: pd.DataFrame, settings: Settings) -> None:
    search = settings.search
    matching = rows[rows["price"].fillna(0) <= search.maximum_price_eur]
    if search.radius.enabled:
        matching = matching[
            matching["distance_from_povoa_km"].fillna(0) <= search.radius.maximum_km
        ]
    accepted_types = set(search.accepted_property_types)
    keep = matching["property_type"].apply(
        lambda value: value in accepted_types
        or (search.accept_unknown_type and value == "UNKNOWN")
    )
    st.caption(
        f"Pré-visualização dos critérios de recolha (sobre os imóveis ativos): "
        f"{int(keep.sum())} de {len(rows)} seriam aceites."
    )


def _empty_state_message(config: Settings) -> str:
    db = _database()
    session = db.new_session()
    try:
        repo = Repository(session)
        runs = {name: repo.latest_run(name) for name in _enabled_sources()}
    finally:
        session.close()
    lines = []
    for name, run in runs.items():
        if run is None:
            continue
        found = run.items_found or 0
        if found == 0:
            lines.append(f"- **{name}**: sem imóveis encontrados")
        else:
            lines.append(
                f"- **{name}**: {found} imóveis encontrados, nenhum aceite "
                f"(estado {run.status})"
            )
    text = (
        "Sem imóveis ativos na base de dados. O coletor roda automaticamente "
        f"(todos os dias às {config.schedule.daily_time}) e também no arranque do "
        "contentor; ajuste os critérios em **Configuração da recolha** (painel "
        "lateral) e aguarde a próxima execução."
    )
    if lines:
        text += "\n\nÚltimas execuções:\n\n" + "\n".join(lines)
    return text


def main() -> None:
    rows, summary = _load_data()

    st.title("Monitor Imobiliário")
    st.caption("Oportunidades imobiliárias em fontes públicas portuguesas.")

    config = _render_collection_config()
    _render_kpis(summary, rows)

    if rows.empty:
        st.warning(_empty_state_message(config))
        _render_source_runs()
        _render_recent_events()
        return

    _render_collection_preview(rows, config)

    st.sidebar.header("Filtros")
    available = sorted(rows["source"].dropna().unique())
    sources = st.sidebar.multiselect("Fonte", available, default=available)
    classification_options = [c for c in _CLASSIFICATION_ORDER if c in set(rows["classification"])]
    classifications = st.sidebar.multiselect(
        "Classificação", classification_options, default=classification_options
    )
    max_price = st.sidebar.slider(
        "Preço máximo (EUR)",
        min_value=0,
        max_value=int(rows["price"].max() or 200_000),
        value=int(rows["price"].max() or 200_000),
        step=5_000,
    )

    filtered = rows
    if sources:
        filtered = filtered[filtered["source"].isin(sources)]
    if classifications:
        filtered = filtered[filtered["classification"].isin(classifications)]
    filtered = filtered[filtered["price"].fillna(0) <= max_price]

    st.subheader(f"Imóveis em análise ({len(filtered)})")
    _render_table(filtered)
    _render_details(filtered)

    _render_recent_events()
    _render_source_runs()


def _render_kpis(summary: dict[str, int], rows: pd.DataFrame) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Imóveis ativos", summary["active"])
    col2.metric("Novos (últimas 24 h)", summary["new_24h"])
    col3.metric(
        "Preço médio (EUR)",
        f"{rows['price'].mean():,.0f}" if rows["price"].notna().any() else "-",
    )


def _render_table(rows: pd.DataFrame) -> None:
    if rows.empty:
        st.info("Sem imóveis com os filtros selecionados.")
        return
    display = rows[
        ["id", "score", "classification", "title", "price", "municipality", "source", "url"]
    ].copy()
    display["preco"] = display["price"].apply(
        lambda value: f"{value:,.0f} EUR" if pd.notna(value) else "-"
    )
    st.dataframe(
        display.drop(columns=["price"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d"
            ),
            "classification": "Classificação",
            "title": "Título",
            "preco": "Preço",
            "municipality": "Concelho",
            "source": "Fonte",
            "url": st.column_config.LinkColumn("Anúncio", display_text="abrir"),
        },
    )


def _render_details(rows: pd.DataFrame) -> None:
    if rows.empty:
        return
    options = {
        int(row.id): f"{row.score:.0f} | {row.title or row.id} | {row.source}"
        for row in rows.itertuples()
    }
    selected = st.selectbox(
        "Ver detalhes do imóvel", options, format_func=lambda key: options[key]
    )
    db = _database()
    session = db.new_session()
    try:
        prop = Repository(session).get(selected)
    finally:
        session.close()
    if prop is None:
        return
    st.markdown(f"**{prop.title or 'Sem título'}** — {prop.municipality or '-'}")
    cols = st.columns(4)
    cols[0].write(f"Preço: {prop.price:,.0f} EUR" if prop.price else "Preço: desconhecido")
    cols[1].write(f"Tipologia: {prop.typology or '-'}")
    cols[2].write(f"Área: {prop.usable_area_m2 or '-'} m2")
    cols[3].write(f"Fonte: {prop.source}")
    if prop.score_reasons_json:
        with st.expander("Razões da pontuação", expanded=True):
            for reason in _safe_load(prop.score_reasons_json):
                st.write(f"- {reason}")
    if prop.legal_alerts_json:
        with st.expander("Alertas jurídicos"):
            for alert in _safe_load(prop.legal_alerts_json):
                st.warning(alert)
    if prop.description:
        with st.expander("Descrição"):
            st.write(prop.description)
    if prop.url:
        st.markdown(f"[Abrir anúncio]({prop.url})")


def _render_recent_events() -> None:
    db = _database()
    session = db.new_session()
    try:
        events = Repository(session).recent_events(limit=25)
    finally:
        session.close()
    if not events:
        return
    st.subheader("Eventos recentes")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "data": e.created_at,
                    "tipo": e.event_type,
                    "fonte": e.source,
                    "mensagem": e.message,
                }
                for e in events
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_source_runs() -> None:
    db = _database()
    session = db.new_session()
    try:
        repo = Repository(session)
        runs = {name: repo.latest_run(name) for name in _enabled_sources()}
    finally:
        session.close()
    st.subheader("Últimas execuções por fonte")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "fonte": name,
                    "estado": run.status if run else "-",
                    "inicio": run.started_at if run else None,
                    "imoveis": run.items_found if run else None,
                    "novos": run.items_new if run else None,
                }
                for name, run in runs.items()
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )


def _enabled_sources() -> list[str]:
    return load_settings().enabled_sources


def _safe_load(value: str | None) -> list[str]:
    if not value:
        return []
    import json

    try:
        data = json.loads(value)
        return data if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []


main()
