"""Helpers de rede e extração de dados estruturados (JSON-LD, microdados)."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

logger = logging.getLogger(__name__)

MAX_HTML_BYTES = 3_000_000
MAX_JSON_BYTES = 2_000_000

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}


def build_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(_HEADERS)
    if extra:
        headers.update(extra)
    return headers


async def fetch_html(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = MAX_HTML_BYTES,
    follow_redirects: bool = True,
) -> tuple[str, int]:
    """Descarrega HTML com limite de tamanho. Devolve (html, status)."""
    async with client.stream("GET", url, headers=build_headers(), follow_redirects=follow_redirects) as resp:
        resp.raise_for_status()
        chunks = []
        size = 0
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > max_bytes:
                logger.warning("Conteúdo demasiado grande em %s (%.1f MB)", url, size / 1e6)
                break
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace"), resp.status_code


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = MAX_JSON_BYTES,
) -> tuple[dict[str, Any] | list[Any] | None, int]:
    """Descarrega JSON com limite de tamanho. Devolve (dados, status)."""
    async with client.stream("GET", url, headers=build_headers({"Accept": "application/json"})) as resp:
        resp.raise_for_status()
        chunks = []
        size = 0
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise ValueError(f"JSON demasiado grande: {size} bytes")
            chunks.append(chunk)
    data = json.loads(b"".join(chunks).decode("utf-8", errors="replace"))
    return data, resp.status_code


def extract_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Extrai blocos JSON-LD de um documento."""
    results: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            results.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            results.append(data)
    return results


def extract_microdata(soup: BeautifulSoup, base_url: str) -> list[dict[str, Any]]:
    """Extrai microdados (itemscope/itemprop) num formato simples."""
    results: list[dict[str, Any]] = []
    for scope in soup.find_all(attrs={"itemscope": True}):
        item: dict[str, Any] = {}
        for prop in scope.find_all(attrs={"itemprop": True}, recursive=True):
            name = prop.get("itemprop")
            if not name or name in item:
                continue
            if prop.get("itemscope") is not None:
                value = prop.get("itemid")
            elif "href" in prop.attrs:
                value = urljoin(base_url, prop["href"])
            elif "content" in prop.attrs:
                value = prop.get("content")
            elif "src" in prop.attrs:
                value = urljoin(base_url, prop["src"])
            else:
                value = prop.get_text(strip=True)
            if value:
                item[name] = value
        if item:
            results.append(item)
    return results


def first_tag(soup: BeautifulSoup, selectors: list[str]) -> Tag | None:
    """Primeiro elemento correspondente a uma lista de seletores."""
    for selector in selectors:
        tag = soup.select_one(selector)
        if tag is not None:
            return tag
    return None


def tag_text(tag: Tag | None, *selectors: str) -> str | None:
    """Texto de um seletor dentro de um elemento."""
    if tag is None:
        return None
    for selector in selectors:
        found = tag.select_one(selector)
        if found is not None:
            text = found.get_text(" ", strip=True)
            if text:
                return text
    return None


def href_from(tag: Tag | None, base_url: str) -> str | None:
    if tag is None or tag.name != "a":
        return None
    href = tag.get("href")
    if not href:
        return None
    return urljoin(base_url, href)
