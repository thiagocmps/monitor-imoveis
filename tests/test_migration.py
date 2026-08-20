"""Testes da migração de URLs do Citius."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from monitor.migrations.fix_citius_urls import migrate


def _create_test_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE properties (
            id INTEGER PRIMARY KEY,
            url TEXT,
            legal_process TEXT,
            source TEXT
        )
    """)
    conn.execute(
        "INSERT INTO properties (url, legal_process, source) VALUES (?, ?, ?)",
        (
            "https://www.citius.mj.pt/Portal/consultas/consultaPublicaDetalhe.asp?tipo_pesquisa=1&nprocesso=85056",
            "3960/03.6TVPRT",
            "citius",
        ),
    )
    conn.execute(
        "INSERT INTO properties (url, legal_process, source) VALUES (?, ?, ?)",
        (
            "https://www.citius.mj.pt/Portal/consultas/consultaPublicaDetalhe.asp?tipo_pesquisa=1&nprocesso=525939",
            "4017/04.8TVPRT",
            "citius",
        ),
    )
    conn.execute(
        "INSERT INTO properties (url, legal_process, source) VALUES (?, ?, ?)",
        (
            "https://www.citius.mj.pt/portal/consultas/consultasvenda.aspx",
            "4206/17.5T8PRT",
            "citius",
        ),
    )
    conn.execute(
        "INSERT INTO properties (url, legal_process, source) VALUES (?, ?, ?)",
        (
            "https://www.leilosoc.com/some-listing",
            "1234/23.4T8PRT",
            "leilosoc",
        ),
    )
    conn.commit()
    conn.close()


def test_migrate_updates_old_urls() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        _create_test_db(db_path)
        count = migrate(db_path)
        assert count == 2

        conn = sqlite3.connect(str(db_path))
        cur = conn.execute("SELECT url, legal_process, source FROM properties ORDER BY rowid")
        rows = cur.fetchall()
        conn.close()

        assert "consultaPublicaDetalhe" not in rows[0][0]
        assert "consultasvenda.aspx?nprocesso=3960/03.6TVPRT" in rows[0][0]
        assert "consultaPublicaDetalhe" not in rows[1][0]
        assert "consultasvenda.aspx?nprocesso=4017/04.8TVPRT" in rows[1][0]
        assert rows[2][0] == "https://www.citius.mj.pt/portal/consultas/consultasvenda.aspx"
        assert rows[3][0] == "https://www.leilosoc.com/some-listing"
    finally:
        db_path.unlink(missing_ok=True)


def test_migrate_nonexistent_db() -> None:
    count = migrate("/tmp/nonexistent_test_db_12345.db")
    assert count == 0


def test_migrate_idempotent() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        _create_test_db(db_path)
        migrate(db_path)
        count = migrate(db_path)
        assert count == 0
    finally:
        db_path.unlink(missing_ok=True)
