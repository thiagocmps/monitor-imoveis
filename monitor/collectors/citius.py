"""Coletor Citius.

Fonte: https://www.citius.mj.pt/portal/consultas/consultasvenda.aspx
Venda de bens penhorados em processos executivos.

A pesquisa é um postback ASP.NET assíncrono (UpdatePanel) protegido por
Dynatrace: só funciona num browser real (header X-dtpc gerado pelo JS).
Por isso este coletor usa Playwright (BrowserManager). A validação do
formulário exige a seleção de um tribunal — não é possível pesquisar
todos os tribunais de uma vez.

O detalhe de cada bem é obtido via endpoint AJAX
`ConsultasVenda.aspx/GetHtmlDetails` (descrição completa, registo,
artigo matricial e moradas dos intervenientes).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from monitor.browser.manager import BrowserManager
from monitor.browser.network import fetch_html
from monitor.collectors.base import BaseCollector, CollectorHealth
from monitor.exceptions import CollectorError
from monitor.models.raw import RawPropertyListing

logger = logging.getLogger(__name__)

FORM_URL = "https://www.citius.mj.pt/portal/consultas/consultasvenda.aspx"

# Tribunais da região (Comarca do Porto, Porto Este e norte da Braga).
# Cobrem a área alvo (Póvoa de Varzim + 30 km) e o Porto.
DEFAULT_TRIBUNALS: list[tuple[str, str]] = [
    ("2871556", "Póvoa de Varzim"),
    ("2871565", "Vila do Conde"),
    ("2871437", "Porto"),
    ("2871534", "Matosinhos"),
    ("2871518", "Maia"),
    ("2871604", "Vila Nova de Gaia"),
    ("2871507", "Gondomar"),
    ("2871595", "Valongo"),
    ("2871577", "Santo Tirso"),
    ("2870610", "Esposende"),
    ("2870556", "Barcelos"),
    ("2870616", "Póvoa de Lanhoso"),
    ("2871690", "Paços de Ferreira"),
    ("2871656", "Lousada"),
    ("2871670", "Paredes"),
    ("2871632", "Penafiel"),
    ("2871663", "Marco de Canaveses"),
    ("2871684", "Felgueiras"),
]

_IDS = {
    "tribunal": "#ctl00_ContentPlaceHolder1_ddlTribunais",
    "tipos_bem": "#ctl00_ContentPlaceHolder1_ddlTiposBem",
    "estados": "#ctl00_ContentPlaceHolder1_ddlEstados",
    "chk_datas": "#ctl00_ContentPlaceHolder1_chkDatas",
    "pesquisar": "#ctl00_ContentPlaceHolder1_btnSearch",
    "registo_count": "#ctl00_ContentPlaceHolder1_lblRecordCount",
    "next_page": "#ctl00_ContentPlaceHolder1_Pager1_btnNextPage",
}

_VALOR_BASE_RE = re.compile(r"[0-9\u00a0 ]+,\d{2}")
_HTML_ID_RE = re.compile(r"Viewer\.Abrir\([^,]+,\s*(\d+)")


class CitiusCollector(BaseCollector):
    source_name = "citius"
    uses_javascript = True

    async def search(self) -> list[RawPropertyListing]:
        settings = self.context.source_settings
        browser_settings = self.context.settings.browser
        results: list[RawPropertyListing] = []
        timeout_ms = browser_settings.navigation_timeout_seconds * 1000

        async with BrowserManager(browser_settings) as browser:
            page = browser.page
            if page is None:
                raise CollectorError("Browser sem página disponível")
            await page.goto(
                FORM_URL,
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            self.context.record_page()

            tribunals = self._resolve_tribunals(settings)
            if settings.all_tribunals:
                tribunals = await self._read_all_tribunals(page)

            for tribunal_id, tribunal_name in tribunals:
                try:
                    found = await self._search_tribunal(
                        page, tribunal_id, tribunal_name, browser_settings, settings
                    )
                except Exception as exc:  # noqa: BLE001
                    self.log(
                        "Tribunal %s falhou: %s", tribunal_name, exc, level=logging.WARNING
                    )
                    continue
                results.extend(found)
                self.log(
                    "Tribunal %s: %d imóveis", tribunal_name, len(found)
                )
                await self._delay()
        return results

    def _resolve_tribunals(self, settings) -> list[tuple[str, str]]:
        if settings.tribunals:
            return [(str(tid), str(tid)) for tid in settings.tribunals]
        return list(DEFAULT_TRIBUNALS)

    async def _read_all_tribunals(self, page) -> list[tuple[str, str]]:
        options = await page.eval_on_selector_all(
            f"{_IDS['tribunal']} option",
            """els => els
                .filter(o => o.value && o.value !== '0')
                .map(o => [o.value, o.text])""",
        )
        return [(str(v), str(t)) for v, t in options]

    async def _search_tribunal(
        self,
        page,
        tribunal_id: str,
        tribunal_name: str,
        browser_settings,
        settings,
    ) -> list[RawPropertyListing]:
        await self._run_search(page, tribunal_id, browser_settings)

        listings: list[RawPropertyListing] = []
        page_idx = 0
        while True:
            page_idx += 1
            items = await self._parse_results_page(page, tribunal_name)
            listings.extend(items)
            self.context.record_page()
            if page_idx >= settings.maximum_pages:
                break
            if not await self._has_next_page(page):
                break
            await self._click_and_wait(
                page, _IDS["next_page"], browser_settings
            )
            await self._delay()
        return listings

    async def _run_search(self, page, tribunal_id: str, browser_settings) -> None:
        # Selecionar o tribunal não dispara postback: o valor é incluído no
        # postback do botão "Pesquisar".
        await page.select_option(_IDS["tribunal"], tribunal_id)
        await page.select_option(_IDS["tipos_bem"], "1")  # Imóvel
        await page.select_option(_IDS["estados"], "927")  # Em venda
        await page.evaluate(
            """() => {
                const cb = document.getElementById('ctl00_ContentPlaceHolder1_chkDatas');
                if (cb) cb.checked = true;
                if (window.chkDatasChecked) chkDatasChecked();
            }"""
        )
        await self._click_and_wait(page, _IDS["pesquisar"], browser_settings)

    async def _parse_results_page(
        self, page, tribunal_name: str
    ) -> list[RawPropertyListing]:
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        listings: list[RawPropertyListing] = []
        for element in soup.select("div.resultadopubvenda"):
            listing = await self._parse_item(page, element, tribunal_name)
            if listing:
                listings.append(listing)
        return listings

    async def _parse_item(
        self, page, element, tribunal_name: str
    ) -> RawPropertyListing | None:
        tipo_bem = _field(element, "Tipo de Bem")
        estado = _field(element, "Estado")
        valor_base = _field(element, "Valor Base")
        modalidade = _field(element, "Modalidade")
        descricao = _field(element, "Descrição do Bem")
        processo = _field(element, "Processo")
        especie = _field(element, "Espécie")

        if not processo and not descricao:
            return None

        legal_process, court = _split_process(processo, tribunal_name)
        url = FORM_URL

        listing = RawPropertyListing(
            source=self.source_name,
            url=url,
            title=descricao[:120] if descricao else None,
            description=descricao,
            property_type=_normalize_tipo(tipo_bem),
            listing_status_text=estado,
            base_value_text=valor_base,
            sale_method_text=modalidade,
            court=court or None,
            legal_process=legal_process,
            source_reference=legal_process,
            raw_data={
                "especie": especie,
                "tribunal_name": tribunal_name,
                "detail_fetched": False,
            },
        )
        listing.base_value = _parse_euro(valor_base)
        listing.price_value = listing.base_value
        listing.price_text = valor_base

        html_id = _html_id(element)
        if html_id is not None:
            listing.source_listing_id = str(html_id)
            detail = await self._fetch_detail(page, html_id)
            if detail:
                self._apply_detail(listing, detail)

        return listing

    async def _fetch_detail(self, page, html_id: int) -> str | None:
        html = await page.evaluate(
            """async (htmlId) => {
                const resp = await fetch('ConsultasVenda.aspx/GetHtmlDetails', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json; charset=utf-8',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: '{htmlId:' + htmlId + '}'
                });
                if (!resp.ok) return null;
                const data = await resp.json();
                return data.d || null;
            }""",
            html_id,
        )
        if not html:
            return None
        self.context.record_page()
        return html

    def _apply_detail(self, listing: RawPropertyListing, detail: str) -> None:
        soup = BeautifulSoup(f"<div>{detail}</div>", "lxml")
        wrapper = soup.find("div")

        description = _field(wrapper, "Descrição do Bem")
        if description:
            listing.description = description
            if not listing.title:
                listing.title = description[:120]

        tribunal = _field(wrapper, "Tribunal")
        if tribunal:
            listing.court = tribunal

        registo = _field(wrapper, "Registo")
        if registo:
            listing.registration_number = _first_token(registo)

        art = _field(wrapper, "Art.Matricial")
        if art:
            listing.tax_article = _first_token(art)

        moradas = _all_fields(wrapper, "Morada")
        if moradas:
            listing.address = moradas[0]

        listing.raw_data["detail_fetched"] = True
        listing.raw_data["moradas_intervenientes"] = moradas
        listing.raw_data["detail_html"] = detail[:50_000]

    async def _has_next_page(self, page) -> bool:
        disabled = await page.get_attribute(_IDS["next_page"], "disabled")
        return disabled is None

    async def _click_and_wait(self, page, selector: str, browser_settings) -> None:
        await self._postback(
            page,
            page.click(selector, force=True),
            browser_settings.navigation_timeout_seconds * 1000,
        )

    async def _postback(self, page, coro: Any, timeout_ms: int) -> None:
        async with page.expect_response(_is_async_response, timeout=timeout_ms):
            await coro
        await page.wait_for_timeout(400)

    async def _delay(self) -> None:
        await asyncio.sleep(self.context.source_settings.delay_seconds)

    async def health_check(self) -> CollectorHealth:
        try:
            html, status = await fetch_html(self.context.client, FORM_URL)
        except Exception as exc:
            return CollectorHealth(self.source_name, False, message=str(exc))
        reachable = status == 200 and "consultasvenda" in html.lower()
        return CollectorHealth(self.source_name, reachable, http_status=status)


def _is_async_response(resp) -> bool:
    return (
        resp.request.method == "POST"
        and "consultasvenda.aspx" in resp.url
    )


def _field(element, label: str) -> str | None:
    """Valor imediatamente a seguir ao <strong> cujo texto começa com label."""
    for strong in element.find_all("strong"):
        if strong.get_text(" ", strip=True).startswith(label):
            parts: list[str] = []
            node = strong.next_sibling
            while node is not None and not _is_stop(node):
                if isinstance(node, str):
                    parts.append(node.strip())
                else:
                    parts.append(node.get_text(" ", strip=True).strip())
                node = node.next_sibling
            value = " ".join(p for p in parts if p).strip()
            return value or None
    return None


def _all_fields(element, label: str) -> list[str]:
    values: list[str] = []
    for strong in element.find_all("strong"):
        if strong.get_text(" ", strip=True).startswith(label):
            parts: list[str] = []
            node = strong.next_sibling
            while node is not None and not _is_stop(node):
                if isinstance(node, str):
                    parts.append(node.strip())
                else:
                    parts.append(node.get_text(" ", strip=True).strip())
                node = node.next_sibling
            value = " ".join(p for p in parts if p).strip()
            if value:
                values.append(value)
    return values


def _is_stop(node) -> bool:
    name = getattr(node, "name", None)
    return name in {"br", "div", "h2", "hr"}


def _first_token(value: str) -> str:
    return value.strip().split(None, 1)[0]


def _html_id(element) -> int | None:
    raw = element.decode()
    match = _HTML_ID_RE.search(raw)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _split_process(processo: str | None, tribunal_name: str) -> tuple[str | None, str | None]:
    if not processo:
        return None, tribunal_name
    if "," in processo:
        number, rest = processo.split(",", 1)
        return number.strip(), rest.strip()
    match = re.search(r"(\d+[/\w.-]+)", processo)
    if match:
        return match.group(1), processo.replace(match.group(1), "").strip(" ,") or None
    return processo.strip(), None


def _parse_euro(value: str | None) -> float | None:
    if not value:
        return None
    match = _VALOR_BASE_RE.search(value)
    if not match:
        return None
    raw = match.group(0).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _normalize_tipo(tipo: str | None) -> str | None:
    if not tipo:
        return None
    value = tipo.strip().lower()
    if "imóvel" in value:
        return "IMOVEL"
    if "veículo" in value or "aeronave" in value or "navio" in value:
        return "OTHER"
    return None
