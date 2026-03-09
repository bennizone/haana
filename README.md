# HAANA — KI-Haushaltsassistent

HAANA ist ein selbst-hostbarer KI-Assistent für Home Assistant mit persistentem Gedächtnis,
Sprachsteuerung und einem integrierten Entwicklungs-Terminal für Selbstanpassung.

## Features

- **Mehrere KI-Provider**: Anthropic, Ollama (lokal), OpenAI-kompatibel, MiniMax
- **Persistentes Gedächtnis**: Qdrant-Vektordatenbank, automatische Konsolidierung (Dream-Prozess)
- **Sprachassistent-Integration**: Verbindet sich mit HA Voice Pipelines
- **Entwicklungs-Terminal**: Claude Code direkt im Browser, mit Safety-Net Agents
- **Setup-Wizard**: Geführte Ersteinrichtung, jederzeit wiederholbar

## Installation (Home Assistant Addon)

1. **HA → Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
2. URL hinzufügen: `https://github.com/[USER]/haana-addons`
3. **HAANA** installieren → Konfigurieren → Starten
4. Webinterface über HA-Seitenleiste öffnen

## Installation (Standalone / Entwicklung)

```bash
git clone https://github.com/[USER]/haana
cd haana
docker compose up -d
# Admin-Interface: http://localhost:8080
# Admin-Token: docker logs haana-admin-interface-1 | grep "Admin Token"
```

## Erste Schritte

Der Setup-Wizard führt durch:
1. **Provider**: Anthropic API-Key oder Ollama-URL
2. **Benutzer**: Name, Sprache, LLM-Zuweisung
3. **Extras**: Voice-Pipeline, MCP, Dream-Prozess

## Datenspeicherung (HA Addon)

| Pfad | Inhalt | HA-Backup |
|------|--------|-----------|
| `/data/` | Config, Auth, Skills | Immer |
| `/media/haana/` | Logs, Qdrant-Vektoren | Optional |

## Entwicklung & Selbstanpassung

HAANA kann sich über das integrierte Terminal selbst weiterentwickeln:
- Tab "Entwicklung" → Claude Code Terminal
- Safety-Net Agents (Reviewer, Webdev, Docs) verhindern fehlerhafte Deployments
- Git-Integration für Versionskontrolle

## Beta-Status

HAANA ist aktuell in der Beta-Phase. Siehe [BETA-GUIDE.md](BETA-GUIDE.md) für Details.
