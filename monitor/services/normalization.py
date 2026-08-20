"""Normalização de dados extraídos de fontes heterogéneas.

Todas as funções preservam o texto original em campos próprios e usam
texto "limpo" apenas para comparação. Nunca inventamos informação:
o que não for reconhecido fica como UNKNOWN/None.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from monitor.models.enums import (
    KeyDeliveryStatus,
    LegalOwnershipType,
    LegalStatus,
    OccupancyStatus,
    PropertyType,
    RenovationLevel,
    SaleMethod,
    VisitStatus,
)

_NUMBER_RE = re.compile(r"-?\d[\d\s.,]*\d|\d")
_AREA_RE = re.compile(r"(\d[\d\s.,]*\d)\s*(?:m2|m²|mq|metros?\s+quadrados?)", re.IGNORECASE)
_TYPO_RE = re.compile(r"\b[Tt][0-9](\+[0-9])?\b")
_NON_NUMERIC = re.compile(r"[^\d.,-]")
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "ref",
    "srsltid",
    "mc_cid",
    "mc_eid",
}


def strip_accents(text: str) -> str:
    """Remove acentos para comparação (preserva o texto original em separado)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_text(text: str | None) -> str:
    """Colapsa espaços e normaliza para minúsculas sem acentos (comparação)."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", strip_accents(text).strip()).lower()


def clean_display_text(text: str | None) -> str | None:
    """Texto apresentável: colapsa espaços, mantém acentos e caso."""
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned or None


def parse_price(text: str | None) -> float | None:
    """Converte texto de preço em EUR num float.

    Suporta os formatos portugueses e internacionais:
    "140 000,00 €", "140.000 €", "€140.000", "140000 EUR",
    "57 090,00 €", "1.250,50 €", "1,000.50 €".
    """
    if not text:
        return None
    cleaned = text.replace("€", " ").replace("EUR", " ").replace("euros", " ")
    cleaned = re.sub(r"[^0-9.,\-]", " ", cleaned).strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace(" ", "").replace("\u00a0", "")
    if "-" in cleaned:
        return None
    return _parse_decimal(cleaned)


def _parse_decimal(value: str) -> float | None:
    """Interpreta um número com separadores de milhar e de decimais."""
    has_comma = "," in value
    has_dot = "." in value
    if has_comma and has_dot:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif has_comma:
        parts = value.split(",")
        if len(parts) == 2 and len(parts[1]) in {1, 2}:
            value = parts[0] + "." + parts[1]
        else:
            value = value.replace(",", "")
    elif has_dot:
        parts = value.split(".")
        if len(parts) == 2 and len(parts[1]) in {1, 2}:
            value = parts[0] + "." + parts[1]
        else:
            value = value.replace(".", "")
    try:
        number = float(value)
    except ValueError:
        return None
    return number if number >= 0 else None


def parse_area(text: str | None) -> float | None:
    """Converte "73,90 m2", "73.90 m²", "74 metros quadrados" em float."""
    if not text:
        return None
    match = _AREA_RE.search(text)
    if not match:
        raw = _NON_NUMERIC.sub("", text)
        if not raw:
            return None
    else:
        raw = match.group(1)
    raw = raw.strip().replace(" ", "").replace("\u00a0", "")
    has_comma = "," in raw
    if has_comma:
        parts = raw.split(",")
        if len(parts) == 2 and len(parts[1]) in {1, 2}:
            raw = parts[0].replace(".", "") + "." + parts[1]
        else:
            raw = raw.replace(",", "")
    elif "." in raw:
        parts = raw.split(".")
        if len(parts) == 2 and len(parts[1]) in {1, 2}:
            raw = parts[0] + "." + parts[1]
        else:
            raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def identify_typology(text: str | None) -> str | None:
    """Extrai tipologias tipo T0, T1+1, T2, T3..."""
    if not text:
        return None
    match = _TYPO_RE.search(text)
    if not match:
        return None
    return match.group(0).upper()


def normalize_municipality(value: str | None) -> str | None:
    """Devolve o nome do concelho normalizado para comparação."""
    if not value:
        return None
    name = normalize_text(value)
    return name or None


def municipalities_equal(a: str | None, b: str | None) -> bool:
    return bool(a and b and normalize_municipality(a) == normalize_municipality(b))


def normalize_url(url: str) -> str:
    """Remove parâmetros de rastreamento e normaliza o URL."""
    try:
        parts = urlsplit(url)
        query = parse_qs(parts.query, keep_blank_values=True)
        clean_query = {
            k: v for k, v in query.items() if k.lower() not in _TRACKING_PARAMS
        }
        query_string = urlencode(clean_query, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, query_string, ""))
    except ValueError:
        return url


def compute_price_per_m2(price: float | None, area_m2: float | None) -> float | None:
    if not price or not area_m2 or area_m2 <= 0:
        return None
    return round(price / area_m2, 2)


def detect_property_type(
    title: str | None = None,
    description: str | None = None,
    typology: str | None = None,
) -> PropertyType:
    """Classifica o tipo de imóvel a partir de texto."""
    combined = " ".join(x for x in (title, description, typology) if x)
    haystack = normalize_text(combined)

    # Se o título indica claramente um tipo residencial (apartamento, moradia),
    # esse sinal prevalece sobre menções pontuais a "escritório" na descrição.
    title_norm = normalize_text(title or "")
    if any(normalize_text(p) in title_norm for p in _COMMERCIAL):
        return PropertyType.COMMERCIAL
    if "moradia" in title_norm or "vivenda" in title_norm or "casa" in title_norm:
        return PropertyType.HOUSE
    if "apartamento" in title_norm:
        return PropertyType.APARTMENT

    # Usos não habitacionais têm prioridade: uma "fração autónoma destinada a
    # escritório" é comercial, não um apartamento.
    if any(normalize_text(p) in haystack for p in _COMMERCIAL):
        return PropertyType.COMMERCIAL
    if (
        "terreno" in haystack
        or "lote" in haystack
        or "rústico" in haystack
        or "rustico" in haystack
        or "solo" in haystack
    ):
        return PropertyType.LAND
    if "moradia" in haystack or "vivenda" in haystack or "casa" in haystack:
        return PropertyType.HOUSE
    if "fracao autonoma" in haystack or "apartamento" in haystack:
        return PropertyType.APARTMENT
    return PropertyType.UNKNOWN


_COMMERCIAL = [
    "loja",
    "escritório",
    "escritorio",
    "armazém",
    "armazem",
    "garagem",
    "lugar de estacionamento",
    "arrecadação",
    "arrecadacao",
    "sala comercial",
    "espaço comercial",
    "espaço de serviços",
    "espaço de servicos",
    "comércio",
    "comercio",
    "destinada a escritório",
    "destinado a escritório",
    "destinada a escritorio",
    "destinado a escritorio",
    "serviços",
    "servicos",
]


# ---------------------------------------------------------------
# Obras / estado de conservação
# ---------------------------------------------------------------

_LIGHT_WORKS = [
    "pequenas obras",
    "obras ligeiras",
    "obras leves",
    "remodelação ligeira",
    "leves obras",
]
_MEDIUM_WORKS = [
    "obras médias",
    "obras medias",
    "obras de conservação",
    "obras de manutenção",
    "pequenas remodelações",
    "pintura",
]
_FULL_RENOVATION = [
    "remodelação total",
    "remodelacao total",
    "para remodelar",
    "a remodelar",
    "para recuperar",
    "a recuperar",
    "para restauro",
    "restauro",
    "reabilitação",
    "reabilitacao",
    "reconstrução",
    "reconstrucao",
    "renovação total",
    "renovacao total",
]
_STRUCTURAL = [
    "obras estruturais",
    "intervenção estrutural",
    "intervencao estrutural",
    "estrutural",
    "estrutura",
]
_RUIN = [
    "ruína",
    "ruina",
    "devoluto",
    "em ruinas",
    "em ruínas",
    "estado de degradação",
    "derrocada",
]


def classify_renovation_level(
    text: str | None, condition_text: str | None = None
) -> tuple[RenovationLevel, str | None]:
    """Classifica o nível das obras e devolve o texto usado para a decisão."""
    source_text = " ".join(x for x in (text, condition_text) if x)
    haystack = normalize_text(source_text)
    used: list[str] = []

    def found(patterns: list[str]) -> bool:
        for pattern in patterns:
            if normalize_text(pattern) in haystack:
                used.append(pattern)
                return True
        return False

    if found(_RUIN):
        return RenovationLevel.RUIN_OR_RECONSTRUCTION, _text_used(source_text, used)
    if found(_STRUCTURAL):
        return RenovationLevel.POSSIBLE_STRUCTURAL_WORKS, _text_used(source_text, used)
    if found(_FULL_RENOVATION):
        return RenovationLevel.FULL_RENOVATION, _text_used(source_text, used)
    if found(_MEDIUM_WORKS):
        return RenovationLevel.MEDIUM_WORKS, _text_used(source_text, used)
    if found(_LIGHT_WORKS):
        return RenovationLevel.LIGHT_WORKS, _text_used(source_text, used)
    return RenovationLevel.NOT_IDENTIFIED, None


def _text_used(source_text: str, used: list[str]) -> str:
    return " ; ".join(dict.fromkeys(used)) if used else source_text


# ---------------------------------------------------------------
# Direitos e estado jurídico
# ---------------------------------------------------------------

_LEGAL_REJECT = {
    "direito à meação": LegalOwnershipType.MARITAL_SHARE,
    "meação": LegalOwnershipType.MARITAL_SHARE,
    "metade indivisa": LegalOwnershipType.UNDIVIDED_SHARE,
    "quota indivisa": LegalOwnershipType.UNDIVIDED_SHARE,
    "parte indivisa": LegalOwnershipType.UNDIVIDED_SHARE,
    "fração indivisa": LegalOwnershipType.UNDIVIDED_SHARE,
    "fracao indivisa": LegalOwnershipType.UNDIVIDED_SHARE,
    "quinhão hereditário": LegalOwnershipType.HEREDITARY_RIGHT,
    "quinhão hereditario": LegalOwnershipType.HEREDITARY_RIGHT,
    "direito hereditário": LegalOwnershipType.HEREDITARY_RIGHT,
    "usufruto": LegalOwnershipType.USUFRUCT,
    "nua-propriedade": LegalOwnershipType.BARE_OWNERSHIP,
    "nua propriedade": LegalOwnershipType.BARE_OWNERSHIP,
    "direito de superfície": LegalOwnershipType.SURFACE_RIGHT,
    "direito de superficie": LegalOwnershipType.SURFACE_RIGHT,
    "cessão de posição": LegalOwnershipType.HEREDITARY_RIGHT,
    "direito de crédito": LegalOwnershipType.HEREDITARY_RIGHT,
    "direito litigioso": LegalOwnershipType.HEREDITARY_RIGHT,
    "percentagem do imóvel": LegalOwnershipType.UNDIVIDED_SHARE,
    "trespasse": LegalOwnershipType.HEREDITARY_RIGHT,
}

_NON_RESIDENTIAL = [
    "terreno",
    "lote",
    "loja",
    "escritório",
    "escritorio",
    "armazém",
    "armazem",
    "garagem",
    "lugar de estacionamento",
    "arrecadação",
    "arrecadacao",
    "anexo",
    "sala comercial",
    "espaço comercial",
]


def classify_legal_ownership(
    title: str | None, description: str | None
) -> tuple[LegalOwnershipType, LegalStatus, list[str]]:
    """Identifica o tipo de propriedade, o estado jurídico e alertas.

    Distingue "fração autónoma destinada a habitação" (aceite) de
    "fração indivisa" (rejeitada).
    """
    combined = " ".join(x for x in (title, description) if x)
    haystack = normalize_text(combined)
    alerts: list[str] = []

    if "fração autónoma" in haystack or "fracao autonoma" in haystack:
        return LegalOwnershipType.AUTONOMOUS_UNIT, LegalStatus.ACCEPTED, alerts

    for pattern, ownership in sorted(_LEGAL_REJECT.items(), key=lambda kv: -len(kv[0])):
        if normalize_text(pattern) in haystack:
            alerts.append(f"Direito parcial ou limitado identificado: '{pattern}'")
            return ownership, LegalStatus.AUTOMATICALLY_REJECTED, alerts

    if "fração" in haystack or "fracao" in haystack:
        return LegalOwnershipType.UNDIVIDED_SHARE, LegalStatus.REQUIRES_REVIEW, alerts

    return LegalOwnershipType.FULL_OWNERSHIP, LegalStatus.ACCEPTED, alerts


def detect_non_residential_exclusion(
    title: str | None, description: str | None, property_type: PropertyType | None
) -> tuple[bool, list[str]]:
    """Deteta exclusões de tipo não-habitacional (terrenos, lojas, etc.)."""
    if property_type is PropertyType.COMMERCIAL or property_type is PropertyType.LAND:
        return True, [f"Tipo não aceite: {property_type.value}"]
    combined = " ".join(x for x in (title, description) if x)
    haystack = normalize_text(combined)
    title_norm = normalize_text(title or "")
    for pattern in _NON_RESIDENTIAL:
        pat_norm = normalize_text(pattern)
        if pat_norm in haystack and pat_norm in title_norm:
            return True, [f"Menção não habitacional: '{pattern}'"]
    return False, []


# ---------------------------------------------------------------
# Ocupação, visita e entrega de chaves
# ---------------------------------------------------------------

def classify_occupancy(text: str | None) -> tuple[OccupancyStatus, str | None]:
    if not text:
        return OccupancyStatus.UNKNOWN, None
    haystack = normalize_text(text)
    vacant = ["desocupado", "livre de pessoas e bens", "livre e devoluto", "vazio"]
    if any(normalize_text(p) in haystack for p in vacant):
        return OccupancyStatus.VACANT, text
    occupied_by_owner = [
        "ocupado pelo executado",
        "ocupado pelo proprietário",
        "ocupado pelo proprietario",
    ]
    if any(normalize_text(p) in haystack for p in occupied_by_owner):
        return OccupancyStatus.OCCUPIED_BY_OWNER, text
    occupied_by_tenant = ["arrendado", "com inquilino", "ocupado por inquilino"]
    if any(normalize_text(p) in haystack for p in occupied_by_tenant):
        return OccupancyStatus.OCCUPIED_BY_TENANT, text
    if any(normalize_text(p) in haystack for p in ["ocupado", "ocupação"]):
        return OccupancyStatus.OCCUPIED_UNKNOWN, text
    return OccupancyStatus.UNKNOWN, text


def classify_visit(text: str | None) -> tuple[VisitStatus, str | None]:
    if not text:
        return VisitStatus.UNKNOWN, None
    haystack = normalize_text(text)
    available = [
        "visita disponível",
        "visita disponivel",
        "visitas disponíveis",
        "visitas disponiveis",
    ]
    if any(normalize_text(p) in haystack for p in available):
        return VisitStatus.AVAILABLE, text
    by_appointment = [
        "visita mediante marcação",
        "visita mediante marcacao",
        "visita com marcação",
        "visita com marcacao",
        "marcação prévia",
        "marcacao previa",
    ]
    if any(normalize_text(p) in haystack for p in by_appointment):
        return VisitStatus.BY_APPOINTMENT, text
    not_available = [
        "não é possível visitar",
        "nao e possivel visitar",
        "não é possível a visita",
        "sem visita",
        "visita não disponível",
        "visita nao disponivel",
    ]
    if any(normalize_text(p) in haystack for p in not_available):
        return VisitStatus.NOT_AVAILABLE, text
    return VisitStatus.UNKNOWN, text


def classify_key_delivery(text: str | None) -> tuple[KeyDeliveryStatus, str | None]:
    if not text:
        return KeyDeliveryStatus.UNKNOWN, None
    haystack = normalize_text(text)
    immediate = ["entrega de chaves", "entrega das chaves", "chaves entregues"]
    if any(normalize_text(p) in haystack for p in immediate):
        return KeyDeliveryStatus.IMMEDIATE, text
    scheduled = ["chaves mediante", "entrega das chaves mediante"]
    if any(normalize_text(p) in haystack for p in scheduled):
        return KeyDeliveryStatus.SCHEDULED, text
    return KeyDeliveryStatus.UNKNOWN, text


def classify_sale_method(text: str | None) -> SaleMethod:
    if not text:
        return SaleMethod.UNKNOWN
    haystack = normalize_text(text)
    electronic = ["leilão eletrónico", "leilao eletronico", "leilão online"]
    if any(normalize_text(p) in haystack for p in electronic):
        return SaleMethod.ELECTRONIC_AUCTION
    auction = ["leilão", "leilao", "licitação", "licitacao"]
    if any(normalize_text(p) in haystack for p in auction):
        return SaleMethod.AUCTION
    sealed = ["carta fechada", "proposta em carta fechada", "propostas em carta fechada"]
    if any(normalize_text(p) in haystack for p in sealed):
        return SaleMethod.SEALED_PROPOSAL
    private = [
        "negociação particular",
        "negociacao particular",
        "venda direta",
        "venda directa",
    ]
    if any(normalize_text(p) in haystack for p in private):
        return SaleMethod.PRIVATE_NEGOTIATION
    return SaleMethod.UNKNOWN
