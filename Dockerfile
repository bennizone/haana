FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ ./core/
COPY skills/ ./skills/

ENV PYTHONUNBUFFERED=1

# CLAUDE.md wird per Volume gemountet (instanzen/{name}/CLAUDE.md → /app/CLAUDE.md)
# HAANA_INSTANCE muss per Environment Variable gesetzt sein

CMD ["python3", "-m", "core.agent"]
