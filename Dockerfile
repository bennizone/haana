FROM python:3.13-slim

# Non-root user – bypassPermissions (--dangerously-skip-permissions) ist als root verboten
RUN useradd -m -u 1000 haana

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ ./core/
COPY skills/ ./skills/

# Verzeichnisse die der Agent zur Laufzeit beschreiben muss
RUN mkdir -p /data /root/.claude && chown -R haana:haana /app /data

ENV PYTHONUNBUFFERED=1

USER haana

# CLAUDE.md wird per Volume gemountet (instanzen/{name}/CLAUDE.md → /app/CLAUDE.md)
# HAANA_INSTANCE muss per Environment Variable gesetzt sein

CMD ["python3", "-m", "core.agent"]
