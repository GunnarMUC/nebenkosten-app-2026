import os
import tempfile
from flask import current_app

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    HTML = None
    CSS = None

from jinja2 import Template

class PDFService:
    """Service for generating PDF documents from HTML templates."""

    # BetrKV Kostenart names for reference
    BETRKV_NAMES = {
        1: 'Grundsteuer', 2: 'Versicherungen', 3: 'Heizung', 4: 'Warmwasser',
        5: 'Wasserversorgung', 6: 'Entwaesserung', 7: 'Gartenpflege',
        8: 'Beleuchtung', 9: 'Aufzug', 10: 'Muellbeseitigung',
        11: 'Gebaeudereinigung', 12: 'Schornstein', 13: 'Sachverstand',
        14: 'Kabelanschluss', 15: 'Rauchmelder', 16: 'Energie Hausflur',
        17: 'Internet/Telefon'
    }

    def generate_abrechnung_pdf(self, abrechnung_data, output_path):
        """Generate a Betriebskostenabrechnung PDF.
        
        Args:
            abrechnung_data: dict with property, tenants, invoices, allocations
            output_path: path to save the PDF
        """
        html_content = self._render_abrechnung_html(abrechnung_data)
        if WEASYPRINT_AVAILABLE and HTML:
            HTML(string=html_content).write_pdf(output_path)
        else:
            # Fallback: save as HTML
            html_path = output_path.replace('.pdf', '.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            current_app.logger.warning(f"WeasyPrint not available, saved HTML to {html_path}")
        return output_path

    def generate_pruefbericht_pdf(self, findings, output_path, context=None):
        """Generate a Pruefbericht PDF.
        
        Args:
            findings: list of check results
            output_path: path to save the PDF
            context: optional context dict
        """
        html_content = self._render_pruefbericht_html(findings, context)
        if WEASYPRINT_AVAILABLE and HTML:
            HTML(string=html_content).write_pdf(output_path)
        else:
            html_path = output_path.replace('.pdf', '.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            current_app.logger.warning(f"WeasyPrint not available, saved HTML to {html_path}")
        return output_path

    def _render_abrechnung_html(self, data):
        """Render HTML for Betriebskostenabrechnung."""
        property_info = data.get('property', {})
        tenants = data.get('tenants', [])
        invoices = data.get('invoices', [])
        allocations = data.get('allocations', [])
        year = data.get('year', 2025)

        tenant_rows = ""
        for t in tenants:
            tenant_rows += f"""
            <tr>
                <td>{t.get('name', '')}</td>
                <td>{t.get('sqm', '')} qm</td>
                <td>{t.get('persons', 1)} Pers.</td>
                <td>{t.get('vorauszahlung', 0):.2f} EUR</td>
            </tr>"""

        invoice_rows = ""
        for inv in invoices:
            betrkv_name = self.BETRKV_NAMES.get(inv.get('betrkv_nr', 0), 'Sonstiges')
            invoice_rows += f"""
            <tr>
                <td>{inv.get('date', '')}</td>
                <td>{betrkv_name} ({inv.get('betrkv_nr', '')})</td>
                <td>{inv.get('vendor', '')}</td>
                <td>{inv.get('description', '')}</td>
                <td style="text-align:right">{inv.get('amount', 0):.2f} EUR</td>
            </tr>"""

        total = sum(inv.get('amount', 0) for inv in invoices)

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {{ size: A4; margin: 2cm; }}
                body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 11pt; color: #333; }}
                h1 {{ font-size: 18pt; color: #37474F; border-bottom: 2px solid #546E7A; padding-bottom: 8px; }}
                h2 {{ font-size: 14pt; color: #546E7A; margin-top: 24px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
                th {{ background: #ECEFF1; text-align: left; padding: 8px; font-weight: bold; font-size: 10pt; }}
                td {{ padding: 8px; border-bottom: 1px solid #CFD8DC; font-size: 10pt; }}
                .total {{ font-weight: bold; font-size: 12pt; text-align: right; margin-top: 16px; color: #37474F; }}
                .header {{ margin-bottom: 24px; }}
                .address {{ color: #78909C; font-size: 10pt; margin-bottom: 16px; }}
                .footer {{ margin-top: 40px; font-size: 9pt; color: #78909C; border-top: 1px solid #CFD8DC; padding-top: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Betriebskostenabrechnung {year}</h1>
                <div class="address">
                    <strong>{property_info.get('name', 'Wohnobjekt')}</strong><br>
                    {property_info.get('address', '')}
                </div>
            </div>

            <h2>Mieter</h2>
            <table>
                <tr><th>Name</th><th>Flaeche</th><th>Personen</th><th>Vorauszahlung</th></tr>
                {tenant_rows}
            </table>

            <h2>Kostenuebersicht</h2>
            <table>
                <tr><th>Datum</th><th>Kostenart</th><th>Anbieter</th><th>Beschreibung</th><th style="text-align:right">Betrag</th></tr>
                {invoice_rows}
            </table>

            <div class="total">Gesamtkosten: {total:.2f} EUR</div>

            <div class="footer">
                Diese Abrechnung wurde automatisch erstellt und ist ohne Unterschrift gueltig.<br>
                Erstellt am: {data.get('created_at', '')} | Status: {data.get('status', 'Entwurf')}
            </div>
        </body>
        </html>
        """

    def _render_pruefbericht_html(self, findings, context=None):
        """Render HTML for Pruefbericht."""
        status_colors = {
            'OK': '#4A6741',
            'WARNUNG': '#8D6E63',
            'FEHLER': '#B71C1C'
        }

        finding_rows = ""
        for f in findings:
            status = f.get('status', 'OK')
            color = status_colors.get(status, '#78909C')
            finding_rows += f"""
            <tr>
                <td style="color:{color};font-weight:bold">{status}</td>
                <td>{f.get('check', '')}</td>
                <td>{f.get('detail', '')}</td>
            </tr>"""

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {{ size: A4; margin: 2cm; }}
                body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 11pt; color: #333; }}
                h1 {{ font-size: 18pt; color: #37474F; border-bottom: 2px solid #546E7A; padding-bottom: 8px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
                th {{ background: #ECEFF1; text-align: left; padding: 10px; font-weight: bold; }}
                td {{ padding: 10px; border-bottom: 1px solid #CFD8DC; vertical-align: top; }}
                .summary {{ background: #f5f7f8; padding: 16px; border-radius: 4px; margin: 16px 0; }}
                .footer {{ margin-top: 40px; font-size: 9pt; color: #78909C; border-top: 1px solid #CFD8DC; padding-top: 12px; }}
            </style>
        </head>
        <body>
            <h1>Pruefbericht Nebenkostenabrechnung</h1>
            
            <div class="summary">
                <strong>Zusammenfassung:</strong> {len([f for f in findings if f.get('status') == 'OK'])} von {len(findings)} 
                Pruefungen bestanden.<br>
                {len([f for f in findings if f.get('status') == 'WARNUNG'])} Warnungen, 
                {len([f for f in findings if f.get('status') == 'FEHLER'])} Fehler festgestellt.
            </div>

            <table>
                <tr><th style="width:100px">Status</th><th style="width:250px">Pruefung</th><th>Hinweis</th></tr>
                {finding_rows}
            </table>

            <div class="footer">
                Dieser Bericht wurde automatisch erstellt und stellt keine Rechtsberatung dar.<br>
                Erstellt: Automatisch
            </div>
        </body>
        </html>
        """
