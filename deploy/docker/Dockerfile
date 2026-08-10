# syntax=docker/dockerfile:1
# Monitor Imobiliário — imagem base (dashboard e coletor)
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Lisbon

WORKDIR /app

# tzdata para o zoneinfo do agendador; binutils já vem no slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Dependências Python (cache separada para reutilização)
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

# Chromium do Playwright + dependências do sistema.
# Defina --build-arg INSTALL_BROWSER=0 para saltar (útil se o CDN estiver
# inacessível; o painel continua a funcionar, o Citius deixa de recolher).
# PLAYWRIGHT_BROWSERS_PATH coloca os browsers fora de /root para que o
# contentor possa correr como utilizador não-root (UID/GID do host).
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/tmp
ARG INSTALL_BROWSER=1
RUN if [ "$INSTALL_BROWSER" = "1" ]; then \
        python -m playwright install --with-deps chromium \
    && python -m playwright install-deps chromium; \
    fi

COPY . /app

# Diretórios de dados (montados como volumes no compose)
RUN mkdir -p data backups logs exports screenshots snapshots

# Garante o import do pacote monitor quando se corre scripts por caminho
# (ex.: deploy/docker/collector_scheduler.py)
ENV PYTHONPATH=/app

# Painel Streamlit (o serviço "collector" sobrepõe este comando)
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
