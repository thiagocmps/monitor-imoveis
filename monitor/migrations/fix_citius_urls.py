"""Migra URLs do Citius na base de dados.

Os URLs antigos usavam ``consultaPublicaDetalhe.asp?tipo_pesquisa=1&nprocesso=``
com IDs internos do DOM que já não funcionam. Atualiza para o formato correto
``consultasvenda.aspx?nprocesso={legal_process}``.

Executar com: .venv/bin/python -m monitor.migrations.fix_citius_urls
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from monitor.collectors.citius import FORM_URL, _detail_url

logger = logging.getLogger(__name__)

_OLD_PATTERN = "consultaPublicaDetalhe.asp"
_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "imoveis.db"


def migrate(db_path: str | Path | None = None) -> int:
    """Atualiza URLs do Citius que ainda usam o formato antigo.

    Devolve o número de registos atualizados.
    """
    path = Path(db_path) if db_path else _DB_PATH
    if not path.exists():
        logger.warning("Base de dados não encontrada: %s", path)
        return 0

    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(
            "SELECT rowid, url, legal_process FROM properties WHERE source = ?",
            ("citius",),
        )
        updates = 0
        for rowid, url, legal_process in cur:
            if not url or _OLD_PATTERN not in url:
                continue
            new_url = _detail_url(None, legal_process) if legal_process else FORM_URL
            conn.execute("UPDATE properties SET url = ? WHERE rowid = ?", (new_url, rowid))
            updates += 1
            logger.info(
                "URL atualizada (rowid=%d): %s -> %s", rowid, url, new_url
            )
        conn.commit()
        logger.info("Migração concluída: %d URLs atualizadas", updates)
        return updates
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    count = migrate()
    print(f"{count} URLs do Citius atualizadas.")
