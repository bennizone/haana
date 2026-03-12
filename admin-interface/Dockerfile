FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# tmux für Terminal-Session-Persistenz (Claude Code) + Docker CLI (für WhatsApp Bridge Start/Stop via Docker Socket)
RUN apt-get update && apt-get install -y --no-install-recommends tmux git curl ca-certificates gnupg && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list && \
    curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    rm -rf /var/lib/apt/lists/*

COPY . .

ENV PYTHONUNBUFFERED=1
ENV HAANA_ADMIN_PORT=8080

EXPOSE ${HAANA_ADMIN_PORT}

CMD uvicorn main:app --host 0.0.0.0 --port ${HAANA_ADMIN_PORT}
