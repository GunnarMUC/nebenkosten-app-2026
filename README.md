# 🏠 NebenkostenPro – KI-gestützte Betriebskostenabrechnung

<p align="center">
  <strong>Betriebskostenabrechnungen erstellen, prüfen und analysieren</strong><br>
  <em>100 % lokal – keine Cloud – alle Daten auf Ihrem MacBook</em>
</p>

---

## 📋 Übersicht

**NebenkostenPro** ist eine lokale Web-App zur **Erstellung und KI-gestützten Prüfung** von Betriebskostenabrechnungen nach deutschem Mietrecht (BetrKV, BGB, HeizkostenV).

| 🔧 Für Vermieter / Hausverwaltungen | 🔍 Für Mieter |
|--------------------------------------|---------------|
| Objekte & Mieter verwalten | Abrechnung per Upload prüfen |
| Rechnungen/Belege erfassen | 10 automatisierte Regel-Checks |
| KI-gestützte Belegerkennung | Zusätzliche KI-Analyse via Qwen 14B |
| Autom. Kostenverteilung (qm/Person/Einheit) | Strukturierter Prüfbericht (PDF + MD) |
| Professionelle PDF-Abrechnung | Nächste-Schritte-Empfehlungen |

---

## 🚀 Schnellstart

### 1. Voraussetzungen

| Was | Warum |
|-----|-------|
| **Docker Desktop** | App läuft als Container |
| **Ollama** | Lokale KI für Analysen |
| **~8 GB freier RAM** | 4 GB für Container + ~4 GB für Qwen 14B |

### 2. Ollama-Modell bereitstellen

```bash
# Qwen 2.5 14B herunterladen (empfohlen)
ollama pull qwen2.5:14b

# Alternativ kleinere Modelle (schneller):
# ollama pull llama3.1:8b
# ollama pull mistral:7b

# Prüfen
ollama list
```

### 3. Ollama starten

```bash
ollama serve
```
(Oder die Ollama-Desktop-App – muss auf Port 11434 laufen)

### 4. App starten

```bash
cd nebenkosten-app
docker-compose up --build
```

Erster Start: ~5 Min für Build + Abhängigkeiten.

### 5. Im Browser öffnen

➡️ **http://localhost:5000**

| Benutzer | Passwort |
|----------|----------|
| `demo` | `demo` |
| (Eigenen Account registrieren) | |

## 🖥️ Architektur

```
┌──────────────────────────────────────────────────────────────┐
│                     Docker Container                          │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Flask 3.x   │  │   SQLite     │  │  Tesseract   │      │
│  │   Port 5000   │  │   (app.db)   │  │   (OCR)      │      │
│  └──────┬───────┘  └──────────────┘  └──────────────┘      │
│         │                                                    │
│         │  host.docker.internal:11434                       │
│         └──────────────────┬───────────────────────────────┘│
│                            │                                │
└────────────────────────────┼────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────┐
│          Dein MacBook      │                                │
│  ┌─────────────────────────┴────────────┐                  │
│  │  Ollama (Qwen 14B / llama3 / mistral)│  ← Port 11434   │
│  └──────────────────────────────────────┘                  │
└───────────────────────────────────────────────────────────┘
```

## 🧠 KI-Features

| Feature | Technologie | Beschreibung |
|---------|-------------|--------------|
| 📄 OCR | Tesseract 5 Deutsch | Texterkennung aus PDFs & Bildern |
| 🏷️ Belegerkennung | Qwen 2.5 14B | Anbieter, Betrag, Datum, Kostenart |
| 🗂️ Klassifikation | Qwen 2.5 14B | 17 BetrKV-Kategorien |
| ✅ Prüfung | 10 Checks + LLM | BetrKV, BGB, HKVO, TKG |
| 🤖 Assistent | Qwen 2.5 14B | Chat über Mietrecht |

### Die 10 Prüfungen

1. **Abrechnungszeitraum** – Max. 12 Monate (§556 Abs. 3 BGB)
2. **Kostenarten** – 17 BetrKV-Positionen (§2 BetrKV)
3. **Verteilerschlüssel** – qm/Person/Einheit (§556a BGB)
4. **Heizkosten** – Mind. 30% Verbrauch (§7 HKVO)
5. **Nicht-umlagefähige Kosten** – Instandhaltung, Verwaltung (§1 Abs. 2 BetrKV)
6. **Kabelanschluss** – Seit 01.07.2024 (§58 TKG)
7. **CO₂-Kosten** – 10-Stufen-Modell (CO₂KostAufG)
8. **Grundsteuer** – Neue Hebesätze ab 2025
9. **Transparenz** – Vorauszahlung + Ergebnis
10. **Abrechnungsfrist** – 12 Monate (§556 Abs. 3 BGB)

## 📁 Verzeichnisstruktur

```
nebenkosten-app/
├── app.py                     # Flask-App: Routen, Logik, Worker
├── config.py                  # Konfiguration
├── requirements.txt           # Python-Dependencies
├── Dockerfile                 # Container-Bauplan
├── docker-compose.yml         # Orchestrierung
├── database/
│   ├── schema.sql             # SQLite-Schema
│   └── __init__.py            # DB-Hilfsfunktionen
├── services/
│   ├── ollama_service.py      # LLM-Client
│   ├── ocr_service.py         # Tesseract-OCR
│   └── pdf_service.py         # PDF-Generierung
├── prompts/
│   └── betrkv_legal.json      # Rechtliche Prompt-Vorlagen
├── templates/
│   ├── base.html              # Basis-Layout
│   ├── dashboard.html         # Dashboard
│   ├── login/register.html    # Auth
│   ├── properties/            # Objektverwaltung
│   ├── tenants/               # Mieterverwaltung
│   ├── invoices/              # Rechnungen
│   └── abrechnung/            # Prüfung & Erstellung
├── static/css/
│   └── style.css              # Stylesheet
└── uploads/                   # Dokumente
```

## ⚙️ Umgebungsvariablen

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `OLLAMA_MODEL` | `qwen2.5:14b` | LLM-Modell |
| `OLLAMA_HOST` | `host.docker.internal` | Ollama-Server |
| `OLLAMA_PORT` | `11434` | Ollama-Port |
| `DATABASE_PATH` | `database/app.db` | SQLite-Pfad |
| `FLASK_SECRET_KEY` | auto | Session-Schlüssel |

## 📊 Exportformate

| Format | Beschreibung |
|--------|--------------|
| 📄 PDF | Prüfbericht (WeasyPrint) |
| 📝 Markdown (.md) | Strukturierter Export |
| 📄 PDF-Abrechnung | Vollständige NK-Abrechnung |

## 🔧 Troubleshooting

### Ollama nicht erreichbar
```bash
curl http://localhost:11434/api/tags
ollama serve
```

### App startet nicht
```bash
docker-compose logs -f
docker-compose down && docker-compose up --build
```

### DB zurücksetzen
```bash
docker-compose down
rm -f database/app.db
docker-compose up
```

### Modell wechseln
```yaml
environment:
  - OLLAMA_MODEL=llama3.1:8b   # schneller
  # - OLLAMA_MODEL=qwen2.5:14b  # genauer (Default)
```

## 🧪 Tech-Stack

| Kategorie | Technologie |
|-----------|-------------|
| Backend | Python 3.12 + Flask 3.x |
| Frontend | HTMX + Jinja2 |
| Datenbank | SQLite |
| KI lokal | Ollama + Qwen 2.5 14B |
| OCR | Tesseract 5 + Deutsch |
| PDF | WeasyPrint |
| Container | Docker + Docker Compose |

## 📜 Lizenz

Privates Projekt – lokale, nicht-kommerzielle Nutzung.

---

<p align="center">
  <sub>Mit ❤️ und 🤖 gemacht – läuft komplett lokal auf Ihrem MacBook.</sub><br>
  <sub>Keine Cloud, keine Datenweitergabe, keine versteckten Kosten.</sub>
</p>
