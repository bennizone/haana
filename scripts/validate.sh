#!/usr/bin/env bash
# HAANA Pre-Commit Validation
# Prüft Code-Qualität, Tests, und bekannte Probleme vor einem Commit.
# Exit-Code 0 = alles OK, 1 = Probleme gefunden.

set -uo pipefail
cd "$(dirname "$0")/.."

ERRORS=0
WARNINGS=0

red()    { echo -e "\033[31m$1\033[0m"; }
green()  { echo -e "\033[32m$1\033[0m"; }
yellow() { echo -e "\033[33m$1\033[0m"; }

echo "=== HAANA Validation ==="
echo ""

# Erkennen ob wir im Docker-Container oder auf dem Host laufen
IN_CONTAINER=0
if [ -f /.dockerenv ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    IN_CONTAINER=1
fi

# 1. Python Syntax Check
echo -n "Python Syntax ... "
SYNTAX_ERRORS=""
while IFS= read -r -d '' f; do
    if ! python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" "$f" 2>/dev/null; then
        SYNTAX_ERRORS="$SYNTAX_ERRORS $f"
    fi
done < <(find core/ admin-interface/ tests/ -name '*.py' -print0 2>/dev/null)
if [ -z "$SYNTAX_ERRORS" ]; then
    green "OK"
else
    red "FEHLER: $SYNTAX_ERRORS"
    ERRORS=$((ERRORS + 1))
fi

# 2. Tests
echo -n "Unit Tests ... "
if [ "$IN_CONTAINER" -eq 0 ]; then
    yellow "ÜBERSPRUNGEN (Host-Umgebung, läuft im Container)"
elif [ -d "tests" ] && ls tests/test_*.py 1>/dev/null 2>&1; then
    if TEST_OUTPUT=$(python3 -m pytest tests/ -q --tb=short 2>&1); then
        PASSED=$(echo "$TEST_OUTPUT" | tail -1)
        green "OK ($PASSED)"
    else
        red "FEHLER"
        echo "$TEST_OUTPUT" | tail -10
        ERRORS=$((ERRORS + 1))
    fi
else
    yellow "SKIP (keine Tests)"
fi

# 3. Legacy-Referenzen (bnd_memory etc.)
echo -n "Legacy-Referenzen ... "
LEGACY=$(grep -rn 'bnd_memory\|bnd_' --include='*.py' --include='*.js' core/ admin-interface/ whatsapp-bridge/ 2>/dev/null || true)
if [ -z "$LEGACY" ]; then
    green "OK"
else
    red "FEHLER: bnd_ Referenzen gefunden:"
    echo "$LEGACY"
    ERRORS=$((ERRORS + 1))
fi

# 4. Import-Check core/memory.py
echo -n "Memory-Modul Import ... "
if ! python3 -c "import mem0" 2>/dev/null; then
    yellow "ÜBERSPRUNGEN (mem0 nicht installiert)"
elif python3 -c "import core.memory" 2>/dev/null; then
    green "OK"
else
    red "FEHLER: core.memory Import fehlgeschlagen"
    ERRORS=$((ERRORS + 1))
fi

# 5. Import-Check core/api.py
echo -n "API-Modul Import ... "
if [ "$IN_CONTAINER" -eq 0 ]; then
    yellow "ÜBERSPRUNGEN (Host-Umgebung)"
elif python3 -c "import core.api" 2>/dev/null; then
    green "OK"
else
    red "FEHLER: core.api Import fehlgeschlagen"
    ERRORS=$((ERRORS + 1))
fi

# 6. Import-Check admin-interface
echo -n "Admin-Interface Import ... "
if [ "$IN_CONTAINER" -eq 0 ]; then
    yellow "ÜBERSPRUNGEN (Host-Umgebung)"
elif python3 -c "import importlib.util; spec = importlib.util.spec_from_file_location('main', 'admin-interface/main.py'); mod = importlib.util.module_from_spec(spec)" 2>/dev/null; then
    green "OK"
else
    yellow "WARN (ggf. fehlende Dependencies im Host)"
    WARNINGS=$((WARNINGS + 1))
fi

# 7. HAANA_EXTRACT_MODEL (deprecated)
echo -n "Deprecated Env-Vars ... "
DEPRECATED=$(grep -rn 'HAANA_EXTRACT_MODEL' --include='*.py' --include='*.js' --include='*.yml' core/ admin-interface/ whatsapp-bridge/ docker-compose*.yml 2>/dev/null || true)
if [ -z "$DEPRECATED" ]; then
    green "OK"
else
    yellow "WARN: HAANA_EXTRACT_MODEL noch referenziert:"
    echo "$DEPRECATED"
    WARNINGS=$((WARNINGS + 1))
fi

# 8. Secrets in staged files
echo -n "Secrets-Check ... "
STAGED=$(git diff --cached --name-only 2>/dev/null || true)
SECRETS_FOUND=""
for f in $STAGED; do
    if echo "$f" | grep -qE '\.(env|key|pem|secret)$'; then
        SECRETS_FOUND="$SECRETS_FOUND $f"
    fi
done
if [ -z "$SECRETS_FOUND" ]; then
    green "OK"
else
    red "FEHLER: Potenzielle Secrets staged: $SECRETS_FOUND"
    ERRORS=$((ERRORS + 1))
fi

# 9. JSON Syntax (Context-Dateien)
echo -n "JSON-Dateien ... "
JSON_ERRORS=""
while IFS= read -r -d '' f; do
    if ! python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$f" 2>/dev/null; then
        JSON_ERRORS="$JSON_ERRORS $f"
    fi
done < <(find data/context/ -name '*.json' -print0 2>/dev/null)
if [ -z "$JSON_ERRORS" ]; then
    green "OK"
else
    red "FEHLER: Ungültiges JSON: $JSON_ERRORS"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "=== Ergebnis: $ERRORS Fehler, $WARNINGS Warnungen ==="

if [ $ERRORS -gt 0 ]; then
    red "Validation FEHLGESCHLAGEN"
    exit 1
fi

if [ $WARNINGS -gt 0 ]; then
    yellow "Validation OK (mit Warnungen)"
else
    green "Validation OK"
fi
exit 0
