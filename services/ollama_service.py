import os
import json
import requests
from flask import current_app

# Load legal knowledge base at module level for RAG
_LEGAL_KB = None

def _load_legal_kb():
    """Load the BetrKV legal knowledge base (RAG context)."""
    global _LEGAL_KB
    if _LEGAL_KB is not None:
        return _LEGAL_KB
    
    kb_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'prompts', 'betrkv_legal.json'),
        '/app/prompts/betrkv_legal.json',
        'prompts/betrkv_legal.json',
    ]
    for p in kb_paths:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    _LEGAL_KB = json.load(f)
                    current_app.logger.info(f"Loaded legal KB from {p}")
                    return _LEGAL_KB
            except Exception as e:
                current_app.logger.warning(f"Failed to load KB from {p}: {e}")
    
    _LEGAL_KB = {}
    return _LEGAL_KB


class OllamaService:
    """Service for communicating with local Ollama instance."""

    def __init__(self, model=None):
        self.host = current_app.config.get('OLLAMA_HOST', 'host.docker.internal')
        self.port = current_app.config.get('OLLAMA_PORT', '11434')
        self.model = model or current_app.config.get('OLLAMA_MODEL', 'qwen2.5:14b')
        self.base_url = f"http://{self.host}:{self.port}"
        self._kb = None

    def set_model(self, model_name):
        """Switch to a different model at runtime."""
        self.model = model_name
        current_app.config['OLLAMA_MODEL'] = model_name
        return self.model

    def get_model(self):
        """Get current active model."""
        return self.model

    def _get_kb(self):
        """Lazy-load legal knowledge base."""
        if self._kb is None:
            self._kb = _load_legal_kb()
        return self._kb

    def is_available(self):
        """Check if Ollama is reachable."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception as e:
            current_app.logger.warning(f"Ollama not available: {e}")
            return False

    def list_models(self):
        """List available models."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return [m['name'] for m in data.get('models', [])]
            return []
        except Exception as e:
            current_app.logger.error(f"Error listing models: {e}")
            return []

    def chat(self, messages, temperature=0.3, stream=False):
        """Send chat request to Ollama."""
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "options": {
                    "temperature": temperature,
                    "num_predict": 2048
                }
            }
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                current_app.logger.error(f"Ollama error {resp.status_code}: {resp.text}")
                return None
        except Exception as e:
            current_app.logger.error(f"Ollama request failed: {e}")
            return None

    def generate(self, prompt, system=None, temperature=0.3):
        """Simple generation endpoint."""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 2048
                }
            }
            if system:
                payload["system"] = system
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            current_app.logger.error(f"Ollama generate failed: {e}")
            return None

    # ========================================================================
    # RAG-ENHANCED SYSTEM PROMPT
    # ========================================================================

    def _get_legal_system_prompt(self):
        """Build comprehensive system prompt with RAG legal knowledge."""
        kb = self._get_kb()
        co2 = kb.get('co2_kosten', {})
        fristen = kb.get('fristen', {})
        nicht_umlage = kb.get('nicht_umlagefaehige_kosten', [])
        
        # Build CO2 stages summary
        co2_stages = ""
        for s in co2.get('stufenmodell', []):
            co2_stages += f"  Stufe {s['stufe']}: {s['co2_von_kg']}-{s['co2_bis_kg']} kg CO2/m2/a -> Mieter {s['mieter_anteil']}%, Vermieter {s['vermieter_anteil']}%\n"
        
        # Build non-allocatable costs summary
        nicht_umlage_text = ""
        for item in nicht_umlage:
            nicht_umlage_text += f"  - {item['kategorie']}: {item['hinweis']}\n"
        
        # Build deadlines
        abr_frist = fristen.get('abrechnungsfrist', {})
        beispiele = abr_frist.get('beispiele', {})
        
        return f"""Du bist ein Experte fuer Betriebskostenabrechnungen nach deutschem Mietrecht. Dein Wissen basiert auf folgenden aktuellen Rechtsgrundlagen (Stand Juni 2026):

## BetrKV - 17 umlagefaehige Kostenarten (§2 BetrKV)
1. Grundsteuer | 2. Versicherungen | 3. Heizung | 4. Warmwasser | 5. Wasserversorgung
6. Entwaesserung | 7. Gartenpflege | 8. Beleuchtung/Strassenreinigung | 9. Aufzug
10. Muellbeseitigung | 11. Gebaeudereinigung | 12. Schornsteinfeger | 13. Sachverstaendige
14. Kabelanschluss (SEIT 01.07.2024 NICHT mehr umlagefaehig!) | 15. Rauchmelder
16. Energie Gemeinschaftsflaechen | 17. Internet/Breitband (nur wenn im Mietvertrag benannt)

## WICHTIGE AENDERUNGEN ab 2024/2025

### Kabelanschluss-Streichung (seit 01.07.2024)
Durch die TKG-Novelle sind Kabelanschlusskosten seit dem 1. Juli 2024 grundsaetzlich NICHT mehr umlagefaehig.
Ausnahme: Der Mieter hat VOR dem 30.06.2024 schriftlich zugestimmt.

### CO2-Kostenaufteilungsgesetz (seit 2023)
CO2-Kosten werden nach dem 10-Stufen-Modell aufgeteilt (je nach Energieeffizienz des Gebaeudes):
{co2_stages}
CO2-Preise: 2023=30 EUR/t, 2024=45 EUR/t, 2025=55 EUR/t, 2026=65 EUR/t

### Grundsteuerreform 2025
- Neue Hebesaetze der Kommunen gelten ab 01.01.2025
- Umlage auf Mieter nur wenn im Mietvertrag ausdruecklich vereinbart
- Nachforderung der erhoehten Grundsteuer nur innerhalb 3 Monate nach Bekanntgabe zulaessig

### Heizkostenverordnung 2024
- 30-70% Verbrauchsanteil, Rest Flaeche
- Monatliche Verbrauchsinformationen Pflicht
- Fernablesbare Zaehler ab 01.2024 fuer Neuanlagen
- Bestandszaehler bis Ende 2026 nachzuruesten

## FRISTEN
- Abrechnung muss innerhalb 12 Monate nach Abrechnungszeitraum beim Mieter eingegangen sein
- Abrechnung 2024 -> Stichtag 31.12.2025 | 2025 -> 31.12.2026 | 2026 -> 31.12.2027
- Bei Verspaetung: Nachforderungsanspruch gefaerdet
- Mieter kann 12 Monate nach Zugang Einwendungen erheben

## NICHT umlagefaehige Kosten (haeufige Fehler!)
{nicht_umlage_text}

## ANWEISUNG
Analysiere die Abrechnung systematisch. Antworte NUR mit einem JSON-Array:
[{{"check": "Name der Pruefung", "status": "OK/WARNUNG/FEHLER", "detail": "Konkrete Beschreibung mit Paragraphenangabe"}}]

Sei praezise, nenne konkrete Gesetzesstellen, unterscheide zwischen gesicherten Aussagen und Hinweisen.
Niemals Rechtsberatung im Einzelfall - nur allgemeine Informationen."""

    def extract_invoice_data(self, ocr_text):
        """Extract structured invoice data from OCR text using Qwen."""
        kb = self._get_kb()
        kostenarten = kb.get('betrkv_kostenarten', {})
        
        # Build category hints from KB
        kat_hints = ""
        for nr, data in sorted(kostenarten.items(), key=lambda x: int(x[0])):
            kat_hints += f"{nr}={data['name']} "
        
        system_prompt = f"""Du bist ein Experte fuer die Verarbeitung von Betriebskostenrechnungen in Deutschland.
Extrahiere aus dem folgenden OCR-Text einer Rechnung die relevanten Daten.

WICHTIGE REGELN FUER DIE ZUORDNUNG:
- Kabelanschluss/TV (Nr.14) ist SEIT 01.07.2024 NICHT mehr umlagefaehig
- Instandhaltung/Reparatur ist generell NICHT umlagefaehig
- Verwaltungskosten sind NICHT umlagefaehig
- Nur Kostenarten aus der BetrKV sind umlagefaehig

BetrKV-Kategorien: {kat_hints}

Antworte NUR mit einem JSON-Objekt im folgenden Format:
{{
  "vendor": "Name des Anbieters/Versorgers",
  "date": "YYYY-MM-DD",
  "amount": 123.45,
  "description": "Kurze Beschreibung der Leistung",
  "betrkv_category": "Passende BetrKV-Kategorie (1-17)",
  "betrkv_name": "Name der Kostenart nach BetrKV",
  "umlagefaehig": true/false,
  "hinweis": "Optionaler Hinweis zur Kostenart"
}}

Betrag als Zahl (mit Punkt als Dezimaltrenner). Wenn keine Kategorie passt: betrkv_category=17 (sonstige)."""

        result = self.generate(f"OCR-Text der Rechnung:\n\n{ocr_text}", system=system_prompt, temperature=0.1)
        if result and 'response' in result:
            try:
                text = result['response'].strip()
                if '```json' in text:
                    text = text.split('```json')[1].split('```')[0].strip()
                elif '```' in text:
                    text = text.split('```')[1].split('```')[0].strip()
                return json.loads(text)
            except Exception as e:
                current_app.logger.error(f"Failed to parse LLM response: {e}")
                return {"raw_response": result['response']}
        return None

    def check_abrechnung(self, abrechnung_text, context=None):
        """Check a Betriebskostenabrechnung with RAG-enhanced legal knowledge."""
        system = self._get_legal_system_prompt()
        
        prompt = f"Nebenkostenabrechnung:\n\n{abrechnung_text[:8000]}"
        if context:
            ctx_str = "\n".join(f"{k}: {v}" for k, v in context.items() if v)
            if ctx_str:
                prompt += f"\n\nKontext (Mieter):\n{ctx_str}"

        result = self.generate(prompt, system=system, temperature=0.2)
        if result and 'response' in result:
            try:
                text = result['response'].strip()
                if '```json' in text:
                    text = text.split('```json')[1].split('```')[0].strip()
                elif '```' in text:
                    text = text.split('```')[1].split('```')[0].strip()
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict) and 'checks' in parsed:
                    return parsed['checks']
                else:
                    return [{"check": "KI-Analyse", "status": "WARNUNG", "detail": str(parsed)[:500]}]
            except:
                return [{"check": "KI-Analyse", "status": "WARNUNG", "detail": result['response'][:500]}]
        return None

    def get_assistant_system_prompt(self):
        """System prompt for the KI assistant with RAG knowledge."""
        kb = self._get_kb()
        co2 = kb.get('co2_kosten', {})
        fristen = kb.get('fristen', {})
        
        # Get CO2 price for current year
        current_year = 2025
        co2_price = co2.get('preise_pro_tonne', {}).get(str(current_year), 55)
        
        abr = fristen.get('abrechnungsfrist', {})
        
        return f"""Du bist ein Experten-Assistent fuer Betriebskostenabrechnungen in Deutschland. Dein Wissen ist auf Stand Juni 2026.

KERNWISSEN:
- 17 umlagefaehige Kostenarten nach §2 BetrKV
- HeizkostenV: 30-70% Verbrauchsanteil
- Abrechnungsfrist: 12 Monate nach Abrechnungszeitraum

AKTUElle AENDERUNGEN:
- Kabelanschluss SEIT 01.07.2024 nicht mehr umlagefaehig (TKG-Novelle)
- CO2-Kosten: 10-Stufen-Modell, Preis 2025={co2_price} EUR/t
- Grundsteuerreform 2025: Neue Hebesaetze, Nachforderung nur innerhalb 3 Monate
- HKVO 2024: Monatliche Verbrauchsinfos Pflicht, Zaehler bis Ende 2026 nachruesten

FRISTEN:
{json.dumps(abr.get('beispiele', {}), indent=2, ensure_ascii=False)}

Grenzen:
- Gib praezise, korrekte Informationen mit Paragraphenangaben
- Keine Rechtsberatung im Einzelfall - nur allgemeine Informationen
- Verweise bei Bedarf auf Mieterverein oder Anwalt
- Antworte auf Deutsch"""
