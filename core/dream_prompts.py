"""HAANA Dream Process – LLM-Prompt-Vorlagen."""

_MERGE_PROMPT = """\
Du bist ein Memory-Konsolidierer. Fasse die folgenden ähnlichen Memory-Einträge \
zu EINEM prägnanten Eintrag zusammen. Behalte alle wichtigen Fakten bei, \
entferne Redundanzen.

Einträge:
{entries}

Antworte NUR mit dem zusammengefassten Text (ein Satz oder kurzer Absatz). \
Keine Erklärung, kein JSON, nur der zusammengefasste Fakt.\
"""

_CONTRADICTION_PROMPT = """\
Analysiere die folgenden Memory-Einträge und finde Widersprüche. \
Zwei Einträge widersprechen sich, wenn sie gegensätzliche Aussagen über \
dasselbe Thema machen (z.B. "trinkt gerne Kaffee" vs "trinkt keinen Kaffee").

Einträge (Format: ID | Text):
{entries}

Antworte als JSON-Liste der IDs die entfernt werden sollen (die veralteten/falschen). \
Behalte jeweils den neueren/wahrscheinlich korrekteren Eintrag.
Bei Korrekturen (z.B. "das stimmt nicht, ich trinke keinen Kaffee") ist die \
Korrektur korrekt und der alte Eintrag falsch.

Wenn es keine Widersprüche gibt, antworte mit: []
Antworte NUR mit der JSON-Liste, nichts anderes. Beispiel: ["id1", "id2"]\
"""

_SUMMARY_PROMPT = """\
Erstelle eine kurze Zusammenfassung der folgenden Konversationen vom {date}. \
Fasse die wichtigsten Themen, Anfragen und Ergebnisse zusammen. \
Maximal 3-5 Sätze.

Konversationen:
{conversations}

Antworte NUR mit der Zusammenfassung, keine Überschriften oder Formatierung.\
"""
