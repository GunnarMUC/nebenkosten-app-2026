# NebenkostenAbrechnung - Lokale KI-gestützte Betriebskostenabrechnung

> Betriebskostenabrechnung erstellen und prüfen mit lokaler KI.
> Keine Cloud-Anbindung. Alle Daten bleiben auf deinem MacBook.

## Voraussetzungen

- **MacBook Pro M5 mit 24GB RAM** ✅
- **Docker Desktop** installiert und gestartet
- **Ollama** installiert

## Schnellstart

### 1. Qwen 2.5 14B herunterladen

```bash
ollama pull qwen2.5:14b
```

Prüfen, ob das Modell bereit ist:
```bash
ollama list
```

### 2. Ollama im Hintergrund starten

```bash
ollama serve
```

Oder über die Ollama-Desktop-App. Wichtig: Ollama muss auf Port 11434 erreichbar sein.

### 3. Anwendung starten

```bash
cd nebenkosten-app
docker-compose up --build
```

Beim ersten Start werden alle Abhängigkeiten automatisch installiert.

### 4. Im Browser öffnen

```
http://localhost:5000
```

**Demo-Zugang:**
- Benutzername: `demo`
- Passwort: `demo`

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                      Docker Container                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Flask App   │  │   SQLite     │  │   Tesseract  │      │
│  │   (Port 5000) │  │   (app.db)   │  │   (OCR)      │      │
│  └──────┬───────┘  └──────────────┘  └──────────────┘      │
│         │                                                    │
│         │  HTTP API (host.docker.internal:11434)            │
│         └────────────────────────────────────────┐           │
└──────────────────────────────────────────────────┼───────────┘
                                                    │
┌───────────────────────────────────────────────────┼───────────┐
│                 Host (dein MacBook)                │           │
│  ┌──────────────────────────────────────────────┐ │           │
│  │  Ollama (Qwen 2.5 14B) - Port 11434         │◄┘           │
│  └──────────────────────────────────────────────┘             │
│                                                               │
│  Docker Desktop verwaltet: host.docker.internal → localhost   │
└───────────────────────────────────────────────────────────────┘
```

## Funktionen

### Für Vermieter
- **Objektverwaltung**: Wohnobjekte mit Adresse, Fläche, Einheiten
- **Mieterverwaltung**: Einzugsdatum, Wohnfläche, Personen, Vorauszahlungen
- **Belege/Rechnungen**: Manuelle Eingabe oder Upload mit KI-Unterstützung
- **Automatische Verteilung**: Nach qm, Personen, Einheiten oder 50/50 nach BetrKV
- **PDF-Abrechnung**: Professionelles PDF nach BetrKV-Struktur

### Für Mieter
- **Abrechnung prüfen**: Upload oder Texteingabe
- **9 automatische Prüfungen** nach BetrKV & BGB
- **KI-gestützte Analyse** mit Qwen 14B
- **Prüfbericht als PDF**

### KI-Assistent
- Chat-Interface für Fragen zu Betriebskosten
- Kontextbewusst: Zugriff auf hochgeladene Dokumente
- Läuft komplett lokal über Ollama

## KI-Features im Detail

| Feature | Technologie | Beschreibung |
|---------|-------------|--------------|
| OCR | Tesseract (deu) | Text aus PDFs und Bildern |
| Datenextraktion | Qwen 2.5 14B | Anbieter, Betrag, Datum, Kostenart erkennen |
| Klassifikation | Qwen 2.5 14B | Zuordnung zu 17 BetrKV-Kategorien |
| Abrechnungsprüfung | Qwen 2.5 14B | 9 regelbasierte Prüfungen + LLM-Analyse |
| KI-Assistent | Qwen 2.5 14B | Fragbasierte Beratung |

## Dateistruktur

```
nebenkosten-app/
├── app.py                     # Flask-App, alle Routen
├── config.py                  # Konfiguration (.env)
├── requirements.txt           # Python-Abhängigkeiten
├── Dockerfile                 # Container-Definition
├── docker-compose.yml         # Docker Compose Setup
├── .env                       # Umgebungsvariablen
├── database/
│   ├── schema.sql             # SQLite-Schema (BetrKV, etc.)
│   └── app.db                 # Datenbank (persistent via Volume)
├── services/
│   ├── ollama_service.py      # Ollama/Qwen API-Client
│   ├── ocr_service.py         # Tesseract OCR
│   └── pdf_service.py         # PDF-Generierung (WeasyPrint)
├── templates/                 # Jinja2 + HTMX Templates
│   ├── base.html
│   ├── login.html / register.html
│   ├── dashboard.html
│   ├── properties/
│   ├── tenants/
│   ├── invoices/
│   ├── abrechnung/
│   └── assistant/
├── static/css/style.css       # Stylesheet
└── uploads/                   # Hochgeladene Dokumente
```

## Umgebungsvariablen

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `OLLAMA_MODEL` | `qwen2.5:14b` | Verwendetes LLM |
| `OLLAMA_HOST` | `host.docker.internal` | Ollama-Host |
| `OLLAMA_PORT` | `11434` | Ollama-Port |
| `DATABASE_PATH` | `database/app.db` | SQLite-Pfad |
| `FLASK_SECRET_KEY` | - | Session-Schlüssel |

## Troubleshooting

### Ollama nicht erreichbar
```bash
# Prüfen ob Ollama läuft
curl http://localhost:11434/api/tags

# Falls nicht: Ollama neu starten
ollama serve
```

### Modell wechseln
```bash
# In .env oder docker-compose.yml:
OLLAMA_MODEL=qwen2.5:14b
# oder
OLLAMA_MODEL=mistral:7b
# oder
OLLAMA_MODEL=llama3.1:8b
```

### Container neu bauen
```bash
docker-compose down
docker-compose up --build
```

### Datenbank zurücksetzen
```bash
docker-compose down
rm database/app.db
docker-compose up
```

## Technologie-Stack

- **Backend**: Flask 3.x (Python 3.12)
- **Frontend**: HTMX + Jinja2 Templates
- **Datenbank**: SQLite
- **KI/OCR**: Ollama + Qwen 2.5 14B + Tesseract
- **PDF**: WeasyPrint
- **Container**: Docker + Docker Compose

## Lizenz

Privates Projekt. Für lokale, nicht-kommerzielle Nutzung.
