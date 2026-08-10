# Monitor Imobiliário

Pipeline automático que recolhe, normaliza, filtra e pontua oportunidades
imobiliárias em **fontes públicas portuguesas** (leilões judiciais e sites de
leilões), focado na região da **Póvoa de Varzim** (raio de 30 km) com preço até
**140 000 €**.

Cada imóvel é classificado (tipologia, tipo, estado jurídico, ocupação, obra,
método de venda), filtrado segundo os critérios definidos em `config.yaml`,
pontuado de **0 a 100** e mantido num histórico com alertas de **novo**,
**atualizado** e **removido**.

## Funcionalidades

- **Recolha real**: Citius (leilões judiciais, via Playwright), Leilosoc e
  LeilOn; restantes fontes como stubs prontos a implementar.
- **Filtros configuráveis**: preço máximo, tipos aceites (apartamentos/moradias),
  exclusões jurídicas automáticas, ocupação/ruína opcionais, raio de 30 km da
  Póvoa de Varzim + concelhos explícitos.
- **Pontuação 0–100** totalmente configurável (pesos, bónus e penalidades).
- **Histórico de preço**: observações diárias, deteção de quedas de preço e
  remoção de imóveis que desaparecem das fontes.
- **CLI** completa (Typer) e **dashboard** web (Streamlit).
- **Exportação** para Excel/CSV e **backups** automáticos com retenção.
- **Deploy** via Docker Compose (dashboard + coletor agendado); systemd em roadmap.

## Arquitetura

```
Fontes (Citius · Leilosoc · LeilOn) ──► recolha (run_collection)
                                            │
RawPropertyListing ──► normalize_listing() ─► filtros ─► scoring (0–100)
                                            │
                                            ▼
                                    SQLite (data/imoveis.db)
                                            │
                            CLI (main.py) · Dashboard (app.py)
```

Módulos principais (`monitor/`):

| Módulo | Responsabilidade |
| --- | --- |
| `collectors/` | Coletores por fonte (implementados e stubs) |
| `orchestration/` | `run_collection()` — ciclo de recolha, falhas isoladas, lock |
| `services/pipeline.py` | `normalize_listing()` — Raw → Normalized |
| `services/filtering.py` | Aplicação dos critérios de pesquisa |
| `services/scoring.py` | Pontuação 0–100 |
| `services/history.py` | Upsert de imóveis, observações, remoções |
| `services/deduplication.py` | Fingerprints e similaridade cross-fonte |
| `services/{export,backup}.py` | Exportação XLSX/CSV e backups |
| `database/` | Modelos, repositório, sessão e migrações (SQLAlchemy + SQLite) |
| `models/` | `RawPropertyListing`, `NormalizedProperty`, enums, eventos |

## Fontes

| Fonte | Estado | Tipo |
| --- | --- | --- |
| `citius` | Implementado | Leilões judiciais (Playwright) |
| `leilosoc` | Implementado | Leilões (server-rendered) |
| `leilon` | Implementado | Leilões (`__NEXT_DATA__`) |
| `eleiloes`, `financas`, `leilosil`, `leiloversatil`, `caixa_imobiliario`, `imovirtual`, `idealista`, `olx` | Stub | Por implementar |

> O Citius é um formulário ASP.NET postback protegido por Dynatrace; apenas
> Playwright funciona. Usa o Chrome do sistema (`channel=auto`).

## Requisitos

- Python **3.11+** (testado com 3.14)
- [Chrome](https://www.google.com/chrome/) instalado (para o coletor Citius)
- Acesso a internet para as fontes

## Instalação

```bash
git clone git@github.com:thiagocmps/monitor-imoveis.git
cd monitor-imoveis

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt        # runtime
pip install -r requirements-dev.txt    # testes/lint (opcional)
```

## Docker (recomendado)

O Compose sobe dois serviços: **dashboard** (Streamlit em `:8501`) e
**collector** (recolha diária). Dados persistentes em `data/`, `backups/`,
`logs/`, `exports/`, `screenshots/`, `snapshots/`.

```bash
docker compose up --build -d
```

- Painel: http://localhost:8501
- Primeira recolha: imediata no arranque; depois diária às `07:30`
  (`schedule.daily_time`).
- Sem `config.yaml` o Compose usa `config.example.yaml`; crie um para ajustar.
- Variáveis de ambiente (`.env`): `TZ`, `APP_ENV`, `STREAMLIT_PASSWORD`,
  `COLLECTOR_RUN_ON_START` (default `true`), `USER_ID`/`GROUP_ID` (default `1000`).
- Os contentores correm como o UID do host para não criar ficheiros `root`.
- Logs: `docker compose logs -f collector`.
- `INSTALL_BROWSER=0` no build salta o Chromium do Playwright (útil sem acesso
  ao CDN; o painel funciona, o Citius deixa de recolher).

Para manter tudo a correr e reconstruir: `docker compose up -d --build`.

## Configuração

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

Edite `config.yaml` com os seus critérios (preço máximo, concelhos, raio,
pesos do score, fontes ativas). `config.yaml` e `.env` estão fora do Git.

No **dashboard**, o painel lateral **"Configuração da recolha"** permite
ajustar preço máximo, raio, tipos aceites e outros critérios sem editar o
`config.yaml` — são guardados na base de dados (`SettingsOverride`) e aplicados
na próxima recolha automática.

## Uso rápido

```bash
python main.py init        # cria a base de dados e as tabelas
python main.py collect     # recolhe as fontes ativas
python main.py status      # resumo dos imóveis ativos
python main.py dashboard   # painel em http://localhost:8501
```

### CLI

| Comando | Descrição |
| --- | --- |
| `init` | Cria a base de dados e tabelas |
| `collect [--source citius --source leilosoc ...]` | Recolhe as fontes |
| `export --format xlsx\|csv [--filename NOME]` | Exporta os imóveis ativos |
| `backup [--compress]` | Cria um backup da base de dados |
| `restore <caminho> --confirm` | Restaura um backup |
| `status` | Imóveis ativos/totais e última execução |
| `sources` | Estado das fontes (ativada/implementada) |
| `health [--source X]` | Verifica a disponibilidade das fontes |
| `dashboard [--port 8501]` | Lança o painel Streamlit |

## Testes e lint

```bash
python -m pytest tests/ -q
ruff check main.py app.py tests/ monitor/services monitor/orchestration
```

## Estrutura do projeto

```
monitor-imoveis/
├── main.py                  # CLI (Typer)
├── app.py                   # Dashboard (Streamlit)
├── config.example.yaml      # Configuração de exemplo
├── monitor/
│   ├── collectors/          # Citius, Leilosoc, LeilOn + stubs
│   ├── orchestration/       # run_collection(), ExecutionLock
│   ├── services/            # pipeline, filtering, scoring, history, ...
│   ├── database/            # modelos, repository, migrations
│   ├── models/              # raw, normalized, enums, eventos
│   └── browser/             # Playwright/Chrome, snapshots
├── tests/                   # 100 testes unitários
├── data/geo_pt.json         # concelhos e coordenadas
├── deploy/docker/           # Dockerfile + agendador do coletor
├── docker-compose.yml       # Compose principal (dashboard + collector)
├── deploy/ubuntu/           # systemd (roadmap)
├── scripts/                 # scripts de agendamento (roadmap)
└── .github/workflows/       # CI (roadmap)
```

## Roadmap

Ver [`status.md`](status.md) para o estado detalhado e lista de próximos passos
(systemd no Ubuntu, CI, coletores em falta, notificações).

## Licença

Proprietário. Uso pessoal.
