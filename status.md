# Monitor Imobiliário — Estado do projeto

> Última atualização: 10-08-2026 · Branch: `main` (1 commit inicial)

## Objetivo

Pipeline automático que recolhe, normaliza, filtra e pontua oportunidades
imobiliárias em fontes públicas portuguesas (leilões judiciais e sites de
leilões), focado na região da Póvoa de Varzim (raio de 30 km) e até 140 000 €.

## Arquitetura

```
┌──────────────────────────────────────────────────────────────────────┐
│ Fontes: Citius · Leilosoc · LeilOn · (stubs: eleiloes, financas, ...) │
└────────────────────────────────┬─────────────────────────────────────┘
                                 ▼
   monitor/orchestration/pipeline.py  →  run_collection() (ciclo por fonte)
                                 │
    RawPropertyListing ──► monitor/services/pipeline.py::normalize_listing()
                                 │
                                 ▼
    monitor/services/filtering.py  →  apply_filters()  (preço, tipo, jurídico,
    │                                  ocupação, ruína, raio 30 km / concelhos)
    ▼
    monitor/services/scoring.py  →  score_property()  (0–100, configurável)
    ▼
    monitor/services/history.py  →  upsert()  (novo / atualizado / removido)
    ▼
    SQLite (data/imoveis.db)  ◄── observações de preço, eventos, source runs
    │
    ├── CLI Typer (main.py): init · collect · export · backup · restore ·
    │                        status · sources · health · dashboard
    └── Dashboard Streamlit (app.py): KPIs, filtros, tabela, detalhes,
                                      eventos recentes, estado por fonte
```

## Feito

### Fontes
- **Citius** — coletor real (Playwright, `channel=auto`/Chrome do sistema).
  - Formulário ASP.NET postback protegido por Dynatrace → só Playwright funciona;
    httpx falha sempre.
  - Detalhe via AJAX `ConsultasVenda.aspx/GetHtmlDetails` (`'{htmlId:N}'` +
    headers JSON). Filtros: `ddlTiposBem=1`, `ddlEstados=927`, `chkDatas=on`,
    `btnSearch`. Seleção de tribunal obrigatória.
  - Smoke test real aprovado: Vila do Conde 1 imóvel, Porto 10 imóveis.
- **Leilosoc** e **LeilOn** — coletores implementados (dados server-rendered /
  `__NEXT_DATA__`).
- **Stubs** (`CollectorNotImplementedError`) para: eleiloes, financas, leilosil,
  leiloversatil, caixa_imobiliario, imovirtual, idealista, olx.

### Pipeline e serviços
- `monitor/services/pipeline.py` — `normalize_listing()`: Raw → Normalized
  (tipologia, tipo de imóvel, preço/área, classificações, geocoding,
  `haversine_km`, `price_per_m2`, URL normalizado, `canonical_fingerprint`).
- `monitor/orchestration/pipeline.py` — `run_collection()`: ciclo por fonte,
  isolamento de falhas (rollback + `FAILED`), `mark_missing_properties_removed`,
  eventos, notificações e stats por fonte.
- `monitor/services/filtering.py` — preço máx, tipos aceites, exclusões
  jurídicas (`AUTOMATICALLY_REJECTED`), ocupação/ruína opcionais, raio 30 km da
  Póvoa de Varzim + concelhos explícitos.
- `monitor/services/scoring.py` — pontuação 0–100 totalmente configurável
  (pesos, bónus e penalidades em `config.yaml`).
- `monitor/services/{deduplication,status_detection,geocoding,export,backup,
  notifications,history}.py` — fingerprints, remoção de imóveis desaparecidos,
  geocoding via `data/geo_pt.json` (92 concelhos), exportação XLSX/CSV, backups
  diários com retenção, notificações (NoopNotifier; reservado).

### CLI (`main.py`)
`init` · `collect --source X --source Y` (com `ExecutionLock`) · `export --format
xlsx|csv` · `backup --compress` · `restore --confirm` · `status` · `sources` ·
`health` · `dashboard --port`.

### Dashboard (`app.py`)
KPIs, filtros (fonte/classificação/preço), tabela com barra de score e link,
detalhes por imóvel (razões, alertas, descrição), eventos recentes e estado das
últimas execuções por fonte.

### Bugs corrigidos nesta fase
- `notifications.py:27` — `del events` antes de `len(events)`.
- `normalization.py` — `parse_price`/`parse_area` falhavam em milhares com
  espaço/ponto ("140 000,00 €" → `None`); reescritos com `_parse_decimal`.
  `find()`/classificadores passaram a comparar com `normalize_text(pattern)`.
  `detect_property_type` aceita "fracao autonoma"; alvos `_LEGAL_REJECT` e
  `_NON_RESIDENTIAL` corrigidos.
- `filtering.py` — `FilterResult.accepted` default `False`; `.value` em vez de
  `str()` para enums (`OccupancyStatus`, `RenovationLevel`).
- `scoring.py` — `.value` em vez de `str()` para `OCCUPIED*` e
  `PRIVATE_NEGOTIATION`.
- `orchestration/pipeline.py` — `run_collection()` agora chama
  `initialize_database()`; `start_source_run` é persistida com commit antes do
  trabalho (a run deixava de existir no rollback de falha).

### Verificação
- **81 testes a passar** (`tests/`): normalization, pipeline, filtering, scoring,
  deduplication, notifications, orchestration (3 novos: persistência+filter,
  segunda recolha atualiza, falha isolada).
- `ruff` limpo nos ficheiros tocados; `compileall` OK.
- Smoke CLI: `init`, `status`, `sources`, `export --format csv`, `backup
  --compress` funcionam.
- Nota: `datetime.utcnow()` em `models/events.py`, `models.py`, `repository.py`,
  `history.py` gera DeprecationWarning (migrar para `datetime.now(UTC)`).

## Por fazer (roadmap)

### Curto prazo
- [ ] **Docker Compose**: `deploy/docker/` com serviços `collector` (cron) e
      `dashboard`; volumes para `data/`, `backups/`, `logs/`.
- [ ] **Deploy Ubuntu**: `deploy/ubuntu/` — systemd units
      (`monitor-collector.service` via `OnCalendar`, `monitor-dashboard.service`)
      e script de instalação.
- [ ] `scripts/windows/` — scripts de agendamento para Windows (Task Scheduler).
- [ ] CI/CD: `.github/workflows/` — lint (ruff) + testes (pytest) por PR.
- [ ] Push inicial do projeto (ver secção Git) — **pendente até este documento**.

### Funcionalidades
- [ ] Coletores restantes: eleiloes, financas (Portal das Finanças), leilosil,
      leiloversatil, caixa_imobiliario, imovirtual, idealista, olx.
- [ ] Notificações reais (email/Telegram) quando `NOTIFICATIONS_ENABLED=true`.
- [ ] Autenticação no Streamlit via `STREAMLIT_PASSWORD` (base já prevista no
      `.env.example`).
- [ ] Agendador interno (`schedule.daily_time`) ou documentar cron no deploy.
- [ ] Migrar `datetime.utcnow()` → `datetime.now(UTC)` e eliminar warnings.
- [ ] Correr `mypy` no projeto (config já presente no `pyproject.toml`).
- [ ] Limpar 36 lints pré-existentes fora dos ficheiros tocados (`enums.py`,
      `backup.py`, `deduplication.py`, `history.py`, `status_detection.py`).
- [ ] Verificação `run_collection` contra as fontes reais (Citius exige Chrome +
      Playwright; Chromium do Playwright indisponível por rede → `channel=auto`).

### Qualidade / operação
- [ ] Testes de integração marcados `integration`/`live` contra fontes reais.
- [ ] Screenshots e HTML de erro já guardados em `screenshots/`/`snapshots/`
      (configurado em `browser.*`).
- [ ] Revisão de retenção de backups (dias) no `config.yaml`.

## Git

- Repositório: **privado**, owner `thiagocmps` (GitHub), SSH.
- Estado: sem commits até à data deste documento; todos os ficheiros untracked.
- Estrutura de um primeiro commit:
  `status.md` + `README.md` + `.github/` + `deploy/` + `scripts/` + `config.example.yaml`
  + `monitor/` + `main.py` + `app.py` + `tests/` + `pyproject.toml` + `requirements*`
  + `.env.example` + ficheiros de config (`.editorconfig`, `.gitattributes`, `.gitignore`).
- **Ignorados** (`.gitignore`): `.env`, `config.yaml`, `data/*.db`, `logs/`,
  `exports/`, `backups/`, `screenshots/`, `snapshots/`, `.venv/`, caches.
