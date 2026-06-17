import os
import json
import uuid
import threading
import time
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, g, send_file, current_app
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from database import init_app, init_db, query_db, execute_db, get_db
from services.ollama_service import OllamaService
from services.ocr_service import OCRService
from services.pdf_service import PDFService

# Flask App
app = Flask(__name__)
app.config.from_object(Config)
init_app(app)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'tiff', 'webp'}

# BetrKV names mapping
BETRKV_NAMES = {
    1: 'Grundsteuer', 2: 'Versicherungen', 3: 'Heizung', 4: 'Warmwasser',
    5: 'Wasserversorgung', 6: 'Entwaesserung', 7: 'Gartenpflege',
    8: 'Beleuchtung/Straßenreinigung', 9: 'Aufzug', 10: 'Müllbeseitigung',
    11: 'Gebäudereinigung', 12: 'Schornsteinfeger', 13: 'Sachverständige',
    14: 'Kabelanschluss', 15: 'Rauchmelder', 16: 'Energie Hausflur',
    17: 'Internet/Telefon'
}

# ============================================================================
# HELPERS
# ============================================================================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.headers.get('HX-Request'):
                return '<div class="alert alert-error">Bitte einloggen.</div>', 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'user_id' in session:
        return query_db('SELECT * FROM users WHERE id = ?', [session['user_id']], one=True)
    return None

def save_upload(file):
    """Save uploaded file and return path."""
    if file and allowed_file(file.filename):
        filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        upload_dir = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        return filepath
    return None

# ============================================================================
# CONTEXT PROCESSORS
# ============================================================================

@app.context_processor
def inject_globals():
    return {
        'betrkv_names': BETRKV_NAMES,
        'current_user': get_current_user(),
        'now': datetime.now()
    }

# ============================================================================
# AUTH ROUTES
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Erfolgreich eingeloggt.', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Ungültige Anmeldedaten.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'vermieter')
        display_name = request.form.get('display_name', '').strip()
        
        if not username or not password:
            flash('Benutzername und Passwort sind erforderlich.', 'error')
            return render_template('register.html')
        
        existing = query_db('SELECT id FROM users WHERE username = ?', [username], one=True)
        if existing:
            flash('Benutzername bereits vergeben.', 'error')
            return render_template('register.html')
        
        pw_hash = generate_password_hash(password)
        user_id = execute_db(
            'INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)',
            [username, pw_hash, role, display_name]
        )
        flash('Account erstellt. Bitte einloggen.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Ausgeloggt.', 'info')
    return redirect(url_for('login'))

# ============================================================================
# DASHBOARD
# ============================================================================

@app.route('/')
@login_required
def dashboard():
    user = get_current_user()
    stats = {}
    
    if user['role'] in ('vermieter', 'admin'):
        stats['properties'] = query_db(
            'SELECT COUNT(*) as cnt FROM properties WHERE user_id = ?', [user['id']], one=True
        )['cnt']
        stats['tenants'] = query_db(
            'SELECT COUNT(*) as cnt FROM tenants t JOIN properties p ON t.property_id = p.id WHERE p.user_id = ?',
            [user['id']], one=True
        )['cnt']
        stats['abrechnungen'] = query_db(
            'SELECT COUNT(*) as cnt FROM abrechnungen a JOIN properties p ON a.property_id = p.id WHERE p.user_id = ?',
            [user['id']], one=True
        )['cnt']
    
    # Ollama status
    ollama = OllamaService()
    ollama_available = ollama.is_available()
    ollama_models = ollama.list_models() if ollama_available else []
    
    return render_template('dashboard.html', stats=stats, 
                           ollama_available=ollama_available, 
                           ollama_models=ollama_models,
                           selected_model=app.config['OLLAMA_MODEL'])

# ============================================================================
# PROPERTIES
# ============================================================================

@app.route('/properties')
@login_required
def properties_list():
    user = get_current_user()
    properties = query_db('SELECT * FROM properties WHERE user_id = ? ORDER BY created_at DESC', [user['id']])
    return render_template('properties/list.html', properties=properties)

@app.route('/properties/new', methods=['GET', 'POST'])
@login_required
def property_new():
    if request.method == 'POST':
        user = get_current_user()
        name = request.form.get('name', '').strip()
        address = request.form.get('address', '').strip()
        total_sqm = float(request.form.get('total_sqm', 0))
        units = int(request.form.get('units', 1) or 1)
        construction_year = request.form.get('construction_year') or None
        
        pid = execute_db(
            'INSERT INTO properties (user_id, name, address, total_sqm, units, construction_year) VALUES (?, ?, ?, ?, ?, ?)',
            [user['id'], name, address, total_sqm, units, construction_year]
        )
        flash('Objekt angelegt.', 'success')
        return redirect(url_for('properties_list'))
    
    return render_template('properties/new.html')

@app.route('/properties/<int:pid>')
@login_required
def property_detail(pid):
    prop = query_db('SELECT * FROM properties WHERE id = ?', [pid], one=True)
    tenants = query_db('SELECT * FROM tenants WHERE property_id = ? ORDER BY name', [pid])
    invoices = query_db('''
        SELECT i.*, b.name as betrkv_name 
        FROM invoices i 
        LEFT JOIN betrkv_kostenarten b ON i.betrkv_nr = b.nr 
        WHERE i.property_id = ? ORDER BY i.date DESC
    ''', [pid])
    abrechnungen = query_db('SELECT * FROM abrechnungen WHERE property_id = ? ORDER BY year DESC', [pid])
    return render_template('properties/detail.html', property=prop, tenants=tenants, 
                           invoices=invoices, abrechnungen=abrechnungen)

@app.route('/properties/<int:pid>/delete', methods=['POST'])
@login_required
def property_delete(pid):
    execute_db('DELETE FROM properties WHERE id = ?', [pid])
    flash('Objekt gelöscht.', 'info')
    return redirect(url_for('properties_list'))

# ============================================================================
# TENANTS
# ============================================================================

@app.route('/properties/<int:pid>/tenants/new', methods=['GET', 'POST'])
@login_required
def tenant_new(pid):
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        move_in_date = request.form.get('move_in_date')
        move_out_date = request.form.get('move_out_date') or None
        sqm = float(request.form.get('sqm', 0))
        persons = int(request.form.get('persons', 1))
        vorauszahlung = float(request.form.get('vorauszahlung', 0))
        
        tid = execute_db(
            'INSERT INTO tenants (property_id, name, email, move_in_date, move_out_date, sqm, persons, vorauszahlung) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            [pid, name, email, move_in_date, move_out_date, sqm, persons, vorauszahlung]
        )
        flash('Mieter hinzugefügt.', 'success')
        return redirect(url_for('property_detail', pid=pid))
    
    return render_template('tenants/new.html', property_id=pid)

# ============================================================================
# INVOICES
# ============================================================================

@app.route('/properties/<int:pid>/invoices/new', methods=['GET', 'POST'])
@login_required
def invoice_new(pid):
    if request.method == 'POST':
        betrkv_nr = int(request.form.get('betrkv_nr', 1))
        amount = float(request.form.get('amount', 0))
        date = request.form.get('date')
        vendor = request.form.get('vendor', '').strip()
        description = request.form.get('description', '').strip()
        
        # Handle file upload
        document_path = None
        if 'document' in request.files:
            file = request.files['document']
            if file.filename:
                document_path = save_upload(file)
        
        category = BETRKV_NAMES.get(betrkv_nr, 'Sonstiges')
        
        iid = execute_db(
            'INSERT INTO invoices (property_id, betrkv_nr, category, amount, date, vendor, description, document_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            [pid, betrkv_nr, category, amount, date, vendor, description, document_path]
        )
        
        # If document uploaded and Ollama available, try AI extraction
        if document_path:
            flash('Rechnung gespeichert. KI-Analyse wird im Hintergrund gestartet...', 'info')
        else:
            flash('Rechnung gespeichert.', 'success')
        
        return redirect(url_for('property_detail', pid=pid))
    
    betrkv_list = query_db('SELECT * FROM betrkv_kostenarten ORDER BY nr')
    return render_template('invoices/new.html', property_id=pid, betrkv_list=betrkv_list)

@app.route('/api/invoices/<int:iid>/analyze', methods=['POST'])
@login_required
def invoice_analyze(iid):
    """HTMX endpoint: Analyze invoice document with OCR + LLM."""
    invoice = query_db('SELECT * FROM invoices WHERE id = ?', [iid], one=True)
    if not invoice or not invoice['document_path']:
        return '<span class="text-error">Kein Dokument vorhanden.</span>'
    
    # OCR
    ocr = OCRService()
    ocr_result = ocr.extract_text(invoice['document_path'])
    
    if not ocr_result['success']:
        return f'<span class="text-error">OCR fehlgeschlagen: {ocr_result["error"]}</span>'
    
    # LLM extraction
    ollama = OllamaService()
    extracted = ollama.extract_invoice_data(ocr_result['text'])
    
    if extracted:
        # Update invoice with extracted data if fields are empty
        updates = []
        params = []
        if extracted.get('vendor') and not invoice['vendor']:
            updates.append('vendor = ?')
            params.append(extracted['vendor'])
        if extracted.get('amount') and invoice['amount'] == 0:
            updates.append('amount = ?')
            params.append(extracted['amount'])
        if extracted.get('date') and not invoice['date']:
            updates.append('date = ?')
            params.append(extracted['date'])
        if extracted.get('betrkv_category'):
            try:
                bnr = int(extracted['betrkv_category'])
                updates.append('betrkv_nr = ?')
                params.append(bnr)
                updates.append('category = ?')
                params.append(BETRKV_NAMES.get(bnr, 'Sonstiges'))
            except:
                pass
        
        if updates:
            params.append(iid)
            execute_db(f"UPDATE invoices SET {', '.join(updates)} WHERE id = ?", params)
        
        html = f"""
        <div class="alert alert-success">
            <strong>KI-Analyse abgeschlossen:</strong><br>
            Anbieter: {extracted.get('vendor', 'n/a')}<br>
            Betrag: {extracted.get('amount', 'n/a')} EUR<br>
            Datum: {extracted.get('date', 'n/a')}<br>
            Kategorie: {extracted.get('betrkv_name', 'n/a')}
        </div>
        """
        return html
    
    return '<span class="text-warning">KI konnte keine Daten extrahieren.</span>'

# ============================================================================
# ABRECHNUNG ERSTELLEN
# ============================================================================

@app.route('/abrechnung/erstellen', methods=['GET', 'POST'])
@login_required
def abrechnung_erstellen():
    user = get_current_user()
    
    if request.method == 'POST':
        property_id = int(request.form.get('property_id'))
        year = int(request.form.get('year', datetime.now().year))
        
        prop = query_db('SELECT * FROM properties WHERE id = ?', [property_id], one=True)
        tenants = query_db('SELECT * FROM tenants WHERE property_id = ?', [property_id])
        invoices = query_db('SELECT * FROM invoices WHERE property_id = ?', [property_id])
        
        if not tenants:
            flash('Keine Mieter für dieses Objekt vorhanden.', 'error')
            return redirect(url_for('abrechnung_erstellen'))
        
        if not invoices:
            flash('Keine Rechnungen für dieses Objekt vorhanden.', 'error')
            return redirect(url_for('abrechnung_erstellen'))
        
        # Calculate allocations
        total_sqm = sum(t['sqm'] for t in tenants if not t['move_out_date'])
        total_persons = sum(t['persons'] for t in tenants if not t['move_out_date'])
        total_days = 365  # simplified
        
        for inv in invoices:
            betrkv = query_db('SELECT * FROM betrkv_kostenarten WHERE nr = ?', [inv['betrkv_nr']], one=True)
            key = betrkv['default_key'] if betrkv else 'qm'
            
            for tenant in tenants:
                if tenant['move_out_date']:
                    continue  # Skip moved-out tenants for now (simplified)
                
                if key == 'qm':
                    share = tenant['sqm'] / total_sqm if total_sqm > 0 else 0
                elif key == 'person':
                    share = tenant['persons'] / total_persons if total_persons > 0 else 0
                elif key == 'einheit':
                    share = 1.0 / len([t for t in tenants if not t['move_out_date']])
                else:
                    share = tenant['sqm'] / total_sqm if total_sqm > 0 else 0
                
                amount = round(inv['amount'] * share, 2)
                execute_db(
                    'INSERT INTO allocations (invoice_id, tenant_id, amount, allocation_key) VALUES (?, ?, ?, ?)',
                    [inv['id'], tenant['id'], amount, key]
                )
        
        # Create abrechnung record
        ab_id = execute_db(
            'INSERT INTO abrechnungen (property_id, year, status) VALUES (?, ?, ?)',
            [property_id, year, 'fertig']
        )
        
        # Generate PDF
        pdf_service = PDFService()
        pdf_filename = f"abrechnung_{property_id}_{year}_{uuid.uuid4().hex[:8]}.pdf"
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
        
        abrechnung_data = {
            'property': dict(prop),
            'tenants': [dict(t) for t in tenants],
            'invoices': [dict(i) for i in invoices],
            'year': year,
            'status': 'fertig',
            'created_at': datetime.now().strftime('%d.%m.%Y')
        }
        
        pdf_service.generate_abrechnung_pdf(abrechnung_data, pdf_path)
        execute_db('UPDATE abrechnungen SET pdf_path = ? WHERE id = ?', [pdf_path, ab_id])
        
        flash('Abrechnung erstellt.', 'success')
        return redirect(url_for('abrechnung_detail', ab_id=ab_id))
    
    properties = query_db('SELECT * FROM properties WHERE user_id = ? ORDER BY name', [user['id']])
    return render_template('abrechnung/erstellen.html', properties=properties)

@app.route('/abrechnungen/<int:ab_id>')
@login_required
def abrechnung_detail(ab_id):
    ab = query_db('''
        SELECT a.*, p.name as property_name, p.address 
        FROM abrechnungen a 
        JOIN properties p ON a.property_id = p.id 
        WHERE a.id = ?
    ''', [ab_id], one=True)
    
    allocations = query_db('''
        SELECT al.*, t.name as tenant_name, i.category, i.amount as invoice_amount, i.vendor
        FROM allocations al
        JOIN tenants t ON al.tenant_id = t.id
        JOIN invoices i ON al.invoice_id = i.id
        WHERE i.property_id = ?
        ORDER BY t.name, i.category
    ''', [ab['property_id']])
    
    return render_template('abrechnung/detail.html', abrechnung=ab, allocations=allocations)

@app.route('/abrechnungen/<int:ab_id>/download')
@login_required
def abrechnung_download(ab_id):
    ab = query_db('SELECT * FROM abrechnungen WHERE id = ?', [ab_id], one=True)
    if ab and ab['pdf_path'] and os.path.exists(ab['pdf_path']):
        return send_file(ab['pdf_path'], as_attachment=True, 
                        download_name=f"Nebenkostenabrechnung_{ab['year']}.pdf")
    flash('PDF nicht gefunden.', 'error')
    return redirect(url_for('dashboard'))

# ============================================================================
# ABRECHNUNG PRUEFEN
# ============================================================================

@app.route('/abrechnung/pruefen', methods=['GET', 'POST'])
@login_required
def abrechnung_pruefen():
    if request.method == 'POST':
        try:
            # ========================================================================
            # STEP 1: Handle multiple file uploads
            # ========================================================================
            uploaded_paths = []

            if 'abrechnung_files' in request.files:
                files = request.files.getlist('abrechnung_files')
                for file in files:
                    if file and file.filename:
                        filepath = save_upload(file)
                        if filepath:
                            uploaded_paths.append(filepath)

            # ========================================================================
            # STEP 2: Collect input (text has priority over files)
            # ========================================================================
            abrechnung_text = request.form.get('abrechnung_text', '').strip()
            context = {
                'wohnflaeche': request.form.get('wohnflaeche', ''),
                'personen': request.form.get('personen', ''),
                'vorauszahlung': request.form.get('vorauszahlung', ''),
                'mietvertrag_keys': request.form.get('mietvertrag_keys', '')
            }

            # If no text but files uploaded, do quick OCR check
            if not abrechnung_text and uploaded_paths:
                # Quick OCR with timeout protection - just check first file
                try:
                    ocr = OCRService()
                    ocr_result = ocr.extract_text(uploaded_paths[0])
                    if ocr_result.get('success') and ocr_result.get('text', '').strip():
                        abrechnung_text = ocr_result['text']
                    else:
                        return redirect(url_for('abrechnung_pruefen'))
                except Exception:
                    return redirect(url_for('abrechnung_pruefen'))

            if not abrechnung_text:
                flash('Bitte geben Sie eine Abrechnung ein oder laden Sie eine Datei hoch.', 'error')
                return redirect(url_for('abrechnung_pruefen'))

            # ========================================================================
            # STEP 3: Create job and enqueue
            # ========================================================================
            user = get_current_user()
            payload = {
                'text': abrechnung_text,
                'uploaded_paths': uploaded_paths,
                'context': context
            }

            job_id = execute_db(
                'INSERT INTO jobs (user_id, job_type, status, payload_json) VALUES (?, ?, ?, ?)',
                [user['id'], 'pruefung', 'queued', json.dumps(payload)]
            )

            # Trigger background worker if not running
            _ensure_worker_running()

            flash('Pruefung gestartet. Analyse laeuft im Hintergrund.', 'info')
            return redirect(url_for('pruefen_job_status', job_id=job_id))

        except Exception as e:
            app.logger.error(f"Job creation error: {e}", exc_info=True)
            flash(f"Fehler beim Starten: {str(e)[:200]}", 'error')
            return redirect(url_for('abrechnung_pruefen'))

    return render_template('abrechnung/pruefen.html')


@app.route('/abrechnung/pruefen/job/<int:job_id>')
@login_required
def pruefen_job_status(job_id):
    """Show job progress page (HTMX polls this for updates)."""
    user = get_current_user()
    job = query_db(
        'SELECT * FROM jobs WHERE id = ? AND user_id = ?',
        [job_id, user['id']], one=True
    )

    if not job:
        flash('Job nicht gefunden.', 'error')
        return redirect(url_for('abrechnung_pruefen'))

    # HTMX poll request: nur den inneren Content der Card liefern
    # (ohne den Container mit hx-trigger, damit das Polling stabil bleibt)
    if request.headers.get('HX-Request'):
        return render_template('abrechnung/pruefen_job_content.html', job=job)

    # Vollständige Seite (initialer Aufruf)
    return render_template('abrechnung/pruefen_job.html', job=job)


# ========================================================================
# BACKGROUND WORKER
# ========================================================================

_worker_thread = None
_worker_lock = threading.Lock()


def _ensure_worker_running():
    """Start background worker thread if not already running."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(target=_job_worker, daemon=True)
            _worker_thread.start()
            app.logger.info("Background worker started")


def _job_worker():
    """Background worker that processes queued jobs."""
    with app.app_context():
        while True:
            try:
                # Find next queued job
                job = query_db(
                    "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1",
                    one=True
                )

                if not job:
                    time.sleep(3)
                    continue

                # Mark as running
                execute_db(
                    "UPDATE jobs SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    [job['id']]
                )

                # Process the job
                try:
                    payload = json.loads(job['payload_json'])
                    _process_pruefung_job(job['id'], payload)
                except Exception as e:
                    error_msg = str(e)[:500]
                    execute_db(
                        "UPDATE jobs SET status = 'error', error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        [error_msg, job['id']]
                    )
                    app.logger.error(f"Job {job['id']} failed: {e}", exc_info=True)

            except Exception as e:
                app.logger.error(f"Worker loop error: {e}")
                time.sleep(5)


def _process_pruefung_job(job_id, payload):
    """Process a single pruefung job."""
    text = payload.get('text', '')
    uploaded_paths = payload.get('uploaded_paths', [])
    context = payload.get('context', {})

    # Step 1: OCR remaining files (first one was done in request)
    if uploaded_paths:
        try:
            ocr = OCRService()
            for i, path in enumerate(uploaded_paths):
                if i == 0:
                    continue  # First file already OCR'd
                try:
                    ocr_result = ocr.extract_text(path)
                    if ocr_result.get('success') and ocr_result.get('text', '').strip():
                        text += "\n\n--- NEUES DOKUMENT ---\n\n" + ocr_result['text']
                except Exception:
                    pass  # Skip failed OCR files
        except Exception:
            pass

    # Step 2: Run keyword checks (fast, always works)
    findings = run_abrechnung_checks(text, context)

    # Step 3: Try LLM enhancement (slow, may timeout)
    try:
        ollama = OllamaService()
        if ollama.is_available():
            llm_findings = ollama.check_abrechnung(text[:4000], context)
            if llm_findings and isinstance(llm_findings, list):
                findings.extend(llm_findings)
    except Exception as e:
        app.logger.warning(f"LLM enhancement failed for job {job_id}: {e}")
        findings.append({
            'check': 'KI-Analyse (LLM)',
            'status': 'WARNUNG',
            'detail': 'KI-Analyse nicht verfuegbar (CPU-Modus kann langsamer sein). Keyword-Pruefungen sind vollstaendig.'
        })

    # Step 4: Save pruefbericht
    user_id = query_db('SELECT user_id FROM jobs WHERE id = ?', [job_id], one=True)['user_id']

    pb_id = execute_db(
        'INSERT INTO pruefberichte (user_id, findings_json, status) VALUES (?, ?, ?)',
        [user_id, json.dumps(findings), 'fertig']
    )

    # Step 5: Try PDF generation (optional)
    try:
        pdf_service = PDFService()
        pdf_filename = f"pruefbericht_{pb_id}_{uuid.uuid4().hex[:8]}.pdf"
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
        pdf_service.generate_pruefbericht_pdf(findings, pdf_path, context)
        execute_db('UPDATE pruefberichte SET pdf_path = ? WHERE id = ?', [pdf_path, pb_id])
    except Exception as e:
        app.logger.warning(f"PDF generation failed for job {job_id}: {e}")

    # Step 6: Mark job as done
    execute_db(
        "UPDATE jobs SET status = 'done', result_json = ?, pruefbericht_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        [json.dumps(findings), pb_id, job_id]
    )


def run_abrechnung_checks(text, context=None):
    """Run comprehensive checks on a Betriebskostenabrechnung.

    Uses keyword-based analysis as fallback when LLM is unavailable.
    Incorporates current legal framework as of 2025/2026.
    """
    findings = []
    text_lower = text.lower()

    # ========================================================================
    # CHECK 1: Abrechnungszeitraum (§556 Abs. 3 BGB)
    # ========================================================================
    has_zeitraum = any(k in text_lower for k in ['abrechnungszeitraum', 'zeitraum', '01.01.', '31.12.', 'abrechnungsjahr'])
    findings.append({
        'check': 'Abrechnungszeitraum (§556 Abs. 3 BGB)',
        'status': 'OK' if has_zeitraum else 'WARNUNG',
        'detail': 'Zeitraum erkannt.' if has_zeitraum else 'Kein Abrechnungszeitraum erkannt. Muss max. 12 Monate umfassen. Abrechnung 2025 muss bis 31.12.2026 beim Mieter eingegangen sein.'
    })

    # ========================================================================
    # CHECK 2: BetrKV Kostenarten (§2 BetrKV)
    # ========================================================================
    betrkv_mentioned = any(name.lower() in text_lower for name in BETRKV_NAMES.values())
    has_kostenarten = any(k in text_lower for k in ['kostenart', 'position', 'grundsteuer', 'heizung', 'wasser', 'versicherung'])
    findings.append({
        'check': 'Kostenarten nach BetrKV (§2 BetrKV)',
        'status': 'OK' if (betrkv_mentioned or has_kostenarten) else 'WARNUNG',
        'detail': 'Kostenarten sind nach BetrKV strukturiert.' if (betrkv_mentioned or has_kostenarten) else 'Kostenarten sollten nach den 17 BetrKV-Positionen gegliedert sein (§2 BetrKV).'
    })

    # ========================================================================
    # CHECK 3: Verteilerschluessel (§556a BGB)
    # ========================================================================
    has_verbrauch = 'verbrauch' in text_lower or 'verbrauchsanteil' in text_lower
    has_qm = 'wohnfläche' in text_lower or ' qm' in text_lower or 'm²' in text
    has_personen = 'personen' in text_lower or 'personenanzahl' in text_lower
    has_einheit = 'wohneinheit' in text_lower or 'nutzeinheit' in text_lower

    if has_verbrauch and has_qm:
        vert_detail = 'Verbrauchs-/Flächenanteil erkannt (Standard: 30-70% Verbrauch nach HKVO).'
    elif has_qm:
        vert_detail = 'Flächenanteil (qm) erkannt. Bei Heizung muss mind. 30% Verbrauchsanteil sein (§7 HKVO).'
    elif has_verbrauch:
        vert_detail = 'Verbrauchsanteil erkannt.'
    else:
        vert_detail = 'Verteilerschluessel muessen angegeben und im Mietvertrag vereinbart sein (§556a BGB).'

    findings.append({
        'check': 'Verteilerschluessel (§556a BGB)',
        'status': 'OK' if (has_verbrauch or has_qm or has_personen or has_einheit) else 'WARNUNG',
        'detail': vert_detail
    })

    # ========================================================================
    # CHECK 4: Heizkosten nach HeizkostenV (§4-7 HKVO)
    # ========================================================================
    has_heizung = 'heizung' in text_lower or 'heizkosten' in text_lower or 'wärme' in text_lower
    has_hkvo = any(k in text_lower for k in ['heizkostenverordnung', 'heizkostenv', 'hkvo', 'gradtag', 'verbrauchsanteil'])

    if has_heizung:
        if has_hkvo or has_verbrauch:
            findings.append({
                'check': 'Heizkosten nach HeizkostenV',
                'status': 'OK',
                'detail': 'Heizkosten nach HKVO aufgeteilt. Verbrauchsanteil muss 30-70% betragen (§7 HKVO).'
            })
        else:
            findings.append({
                'check': 'Heizkosten nach HeizkostenV',
                'status': 'WARNUNG',
                'detail': 'Heizkosten vorhanden, aber keine HKVO-konforme Aufteilung erkannt. Mind. 30% Verbrauchsanteil erforderlich (§7 HKVO).'
            })
    else:
        findings.append({
            'check': 'Heizkosten nach HeizkostenV',
            'status': 'OK',
            'detail': 'Keine Heizkosten in dieser Abrechnung.'
        })

    # ========================================================================
    # CHECK 5: KEINE nicht-umlagefaehigen Kosten (§1 Abs. 2 BetrKV)
    # ========================================================================
    forbidden_keywords = {
        'instandhaltung': 'Instandhaltung ist nicht umlagefähig (§1 Abs. 2 BetrKV)',
        'instandsetzung': 'Instandsetzung ist nicht umlagefähig (§1 Abs. 2 BetrKV)',
        'reparatur': 'Reparaturen sind nicht umlagefähig (§1 Abs. 2 BetrKV)',
        'modernisierung': 'Modernisierung ist nicht umlagefähig (§1 Abs. 2 BetrKV)',
        'sanierung': 'Sanierung ist nicht umlagefähig (§1 Abs. 2 BetrKV)',
        'verwaltungskosten': 'Verwaltungskosten sind nicht umlagefähig',
        'hausverwaltung': 'Kosten für Hausverwaltung sind nicht umlagefähig',
        'kreditzinsen': 'Finanzierungskosten sind nicht umlagefähig',
        'darlehen': 'Darlehenskosten sind nicht umlagefähig',
    }

    found_forbidden = []
    for keyword, description in forbidden_keywords.items():
        if keyword in text_lower:
            found_forbidden.append(description)

    if found_forbidden:
        findings.append({
            'check': 'Nicht-umlagefähige Kosten (§1 Abs. 2 BetrKV)',
            'status': 'FEHLER',
            'detail': 'GEFUNDEN: ' + '; '.join(found_forbidden) + '. Diese Kosten dürfen nicht auf Mieter umgelegt werden!'
        })
    else:
        findings.append({
            'check': 'Nicht-umlagefähige Kosten (§1 Abs. 2 BetrKV)',
            'status': 'OK',
            'detail': 'Keine unzulässigen Kosten (Instandhaltung, Reparatur, Verwaltung, Finanzierung) erkannt.'
        })

    # ========================================================================
    # CHECK 6: Kabelanschluss seit 01.07.2024 (TKG §58)
    # ========================================================================
    has_kabel = any(k in text_lower for k in ['kabel', 'kabelanschluss', 'tv-gebühr', 'fernseh', 'sky', 'vodafone kabel', 'pyur'])

    if has_kabel:
        findings.append({
            'check': 'Kabelanschluss (TKG §58 - seit 01.07.2024)',
            'status': 'FEHLER',
            'detail': 'Kabelanschlusskosten sind seit 01.07.2024 durch die TKG-Novelle grundsätzlich NICHT mehr umlagefähig! Ausnahme nur bei schriftlicher Zustimmung vor dem 30.06.2024.'
        })
    else:
        findings.append({
            'check': 'Kabelanschluss (TKG §58)',
            'status': 'OK',
            'detail': 'Keine Kabelanschlusskosten erkannt.'
        })

    # ========================================================================
    # CHECK 7: CO2-Kosten (CO2KostAufG - seit 2023)
    # ========================================================================
    has_co2 = any(k in text_lower for k in ['co2', 'co 2', 'kohlendioxid', 'emissionshandel'])

    if has_co2:
        findings.append({
            'check': 'CO2-Kosten (CO2KostAufG)',
            'status': 'WARNUNG',
            'detail': 'CO2-Kosten erkannt. Prüfen Sie die Aufteilung nach dem 10-Stufen-Modell (2025: 55 EUR/t). Bei effizienten Gebäuden trägt der Vermieter mehr, bei ineffizienten der Mieter.'
        })
    else:
        findings.append({
            'check': 'CO2-Kosten (CO2KostAufG)',
            'status': 'OK',
            'detail': 'Keine CO2-Kostenposition erkannt (oder im Heizkostenposten enthalten).'
        })

    # ========================================================================
    # CHECK 8: Grundsteuer (GrStReform 2025)
    # ========================================================================
    has_grundsteuer = 'grundsteuer' in text_lower
    if has_grundsteuer:
        findings.append({
            'check': 'Grundsteuer (GrStReform 2025)',
            'status': 'OK',
            'detail': 'Grundsteuer ist umlagefähig (§2 Nr.1 BetrKV). Hinweis: Neue Hebesätze seit 01.01.2025. Nachforderung nur innerhalb 3 Monate nach Bekanntgabe zulässig.'
        })

    # ========================================================================
    # CHECK 9: Transparenzangaben (§556 Abs. 3 BGB)
    # ========================================================================
    has_vorauszahlung = any(k in text_lower for k in ['vorauszahlung', 'abschlag', 'geleistete zahlung', 'voraus'])
    has_ergebnis = any(k in text_lower for k in ['nachzahlung', 'guthaben', 'ergebnis', 'saldo', 'differenz'])

    transparenz_ok = has_vorauszahlung and has_ergebnis
    findings.append({
        'check': 'Transparenzangaben (§556 Abs. 3 BGB)',
        'status': 'OK' if transparenz_ok else 'WARNUNG',
        'detail': 'Vorauszahlungen und Ergebnis (Nachzahlung/Guthaben) vorhanden.' if transparenz_ok 
                  else 'Pflichtangaben fehlen: Vorauszahlungen und/oder Abrechnungsergebnis (Nachzahlung/Guthaben).'
    })

    # ========================================================================
    # CHECK 10: Abrechnungsfrist
    # ========================================================================
    findings.append({
        'check': 'Abrechnungsfrist (§556 Abs. 3 BGB)',
        'status': 'OK',
        'detail': 'Prüfen Sie: Abrechnung muss innerhalb 12 Monate nach Abrechnungszeitraum beim Mieter eingegangen sein. Abrechnung 2025 -> bis 31.12.2026. Bei Verspätung entfällt Nachforderungsanspruch.'
    })

    # ========================================================================
    # CHECK 11: Leerstandskosten (§2 Abs. 2 BetrKV)
    # ========================================================================
    has_leerstand = any(k in text_lower for k in ['leerstand', 'leerstehend', 'nicht vermietet'])
    if has_leerstand:
        findings.append({
            'check': 'Leerstandskosten (§2 Abs. 2 BetrKV)',
            'status': 'FEHLER',
            'detail': 'Leerstandskosten dürfen NICHT auf die Mieter umgelegt werden (§2 Abs. 2 BetrKV)!'
        })

    # ========================================================================
    # LLM-Enhanced Checks (if Ollama available)
    # ========================================================================
    try:
        ollama = OllamaService()
        if ollama.is_available():
            llm_findings = ollama.check_abrechnung(text, context)
            if llm_findings and isinstance(llm_findings, list):
                findings.extend(llm_findings)
    except Exception as e:
        app.logger.warning(f"LLM check failed: {e}")

    return findings

@app.route('/pruefberichte/<int:pb_id>')
@login_required
def pruefbericht_detail(pb_id):
    pb = query_db('SELECT * FROM pruefberichte WHERE id = ?', [pb_id], one=True)
    if pb and pb['findings_json']:
        findings = json.loads(pb['findings_json'])
    else:
        findings = []
    return render_template('abrechnung/pruefbericht_detail.html', pruefbericht=pb, findings=findings)

@app.route('/pruefberichte/<int:pb_id>/download')
@login_required
def pruefbericht_download(pb_id):
    pb = query_db('SELECT * FROM pruefberichte WHERE id = ?', [pb_id], one=True)
    if pb and pb['pdf_path'] and os.path.exists(pb['pdf_path']):
        return send_file(pb['pdf_path'], as_attachment=True, download_name="Pruefbericht.pdf")
    flash('PDF nicht gefunden.', 'error')
    return redirect(url_for('dashboard'))


@app.route('/pruefberichte/<int:pb_id>/export-md')
@login_required
def pruefbericht_export_md(pb_id):
    """Export pruefbericht as structured Markdown file."""
    pb = query_db('SELECT * FROM pruefberichte WHERE id = ?', [pb_id], one=True)
    if not pb or not pb['findings_json']:
        flash('Prüfbericht nicht gefunden.', 'error')
        return redirect(url_for('dashboard'))

    findings = json.loads(pb['findings_json'])

    # Count results
    ok_count = sum(1 for f in findings if f['status'] == 'OK')
    warn_count = sum(1 for f in findings if f['status'] == 'WARNUNG')
    err_count = sum(1 for f in findings if f['status'] == 'FEHLER')

    # Build Markdown content
    md = f"""# Prüfbericht – Nebenkostenabrechnung

**Erstellt am:** {pb['created_at']}  
**Status:** {pb['status']}

---

## Zusammenfassung

| Ergebnis | Anzahl |
|----------|-------:|
| ✅ Bestanden | {ok_count} |
| ⚠️ Warnungen | {warn_count} |
| ❌ Fehler | {err_count} |

---

## Einzelprüfungen

"""
    for f in findings:
        if f['status'] == 'OK':
            icon = '✅'
        elif f['status'] == 'WARNUNG':
            icon = '⚠️'
        else:
            icon = '❌'

        md += f"""### {icon} {f['check']}
**Status:** {f['status']}

{f['detail']}

"""

    md += """---

*Erstellt mit NebenkostenPro – KI-gestützte Betriebskostenprüfung*
"""

    # Send as downloadable .md file
    from io import BytesIO
    mem = BytesIO(md.encode('utf-8'))
    return send_file(
        mem,
        as_attachment=True,
        download_name=f"Pruefbericht_{pb['id']}.md",
        mimetype='text/markdown'
    )

# ============================================================================
# KI ASSISTANT
# ============================================================================

@app.route('/assistant')
@login_required
def assistant():
    """KI Assistant page."""
    return render_template('assistant/chat.html')

@app.route('/api/assistant/chat', methods=['POST'])
@login_required
def assistant_chat():
    """HTMX endpoint: Send message to AI assistant."""
    message = request.form.get('message', '').strip()
    if not message:
        return '<div class="text-error">Bitte eine Nachricht eingeben.</div>'
    
    user = get_current_user()
    
    # Save user message
    execute_db(
        'INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)',
        [user['id'], 'user', message]
    )
    
    # Get conversation history
    history = query_db(
        'SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY created_at DESC LIMIT 10',
        [user['id']]
    )
    
    # Build RAG-enhanced system prompt
    ollama = OllamaService()
    system_content = ollama.get_assistant_system_prompt()

    messages = [
        {"role": "system", "content": system_content}
    ]
    
    for h in reversed(history):
        messages.append({"role": h['role'], "content": h['content']})
    
    # Get AI response
    ollama = OllamaService()
    result = ollama.chat(messages, temperature=0.4)
    
    if result and 'message' in result:
        assistant_msg = result['message']['content']
        
        # Save assistant response
        execute_db(
            'INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)',
            [user['id'], 'assistant', assistant_msg]
        )
        
        # Format response with simple markdown-like formatting
        formatted = assistant_msg.replace('\n\n', '</p><p>').replace('\n', '<br>')
        return f'<div class="assistant-message"><p>{formatted}</p></div>'
    
    return '<div class="text-error">KI-Antwort konnte nicht generiert werden. Prüfen Sie die Ollama-Verbindung.</div>'

@app.route('/api/assistant/clear', methods=['POST'])
@login_required
def assistant_clear():
    """Clear chat history."""
    user = get_current_user()
    execute_db('DELETE FROM chat_messages WHERE user_id = ?', [user['id']])
    return '<div class="text-muted">Gespräch zurückgesetzt.</div>'

# ============================================================================
# API / HTMX ENDPOINTS
# ============================================================================

@app.route('/api/ollama/status')
@login_required
def ollama_status():
    """HTMX endpoint: Check Ollama status."""
    ollama = OllamaService()
    if ollama.is_available():
        models = ollama.list_models()
        current = app.config['OLLAMA_MODEL']
        html = '<span class="badge badge-success">Verbunden</span>'
        html += f'<span class="text-muted ml-2">Modell: {current}</span>'
        if current not in models and models:
            html += f'<div class="alert alert-warning mt-2">Modell "{current}" nicht gefunden. Verfügbar: {", ".join(models[:5])}</div>'
        return html
    return '<span class="badge badge-error">Nicht verbunden</span><div class="text-small text-muted">Prüfen Sie ob Ollama läuft: ollama serve</div>'

@app.route('/api/ollama/switch-model', methods=['POST'])
@login_required
def switch_model():
    """Switch the active LLM model."""
    new_model = request.form.get('model', '').strip()
    if not new_model:
        return '<span class="text-error">Kein Modell ausgewählt.</span>'
    
    try:
        ollama = OllamaService()
        # Verify model is available
        available_models = ollama.list_models()
        if new_model not in available_models:
            return f'<span class="text-warning">Modell "{new_model}" nicht in Ollama gefunden. Verfügbar: {", ".join(available_models[:5])}</span>'
        
        ollama.set_model(new_model)
        app.config['OLLAMA_MODEL'] = new_model
        return f'<span class="badge badge-success">Aktiv</span> Modell gewechselt zu <strong>{new_model}</strong>'
    except Exception as e:
        return f'<span class="text-error">Fehler: {str(e)}</span>'

@app.route('/api/properties/<int:pid>/stats')
@login_required
def property_stats(pid):
    """HTMX endpoint: Get property stats."""
    tenant_count = query_db('SELECT COUNT(*) as cnt FROM tenants WHERE property_id = ?', [pid], one=True)['cnt']
    invoice_sum = query_db('SELECT COALESCE(SUM(amount), 0) as total FROM invoices WHERE property_id = ?', [pid], one=True)['total']
    invoice_count = query_db('SELECT COUNT(*) as cnt FROM invoices WHERE property_id = ?', [pid], one=True)['cnt']
    
    return f"""
    <div class="stats-grid">
        <div class="stat-box"><div class="stat-value">{tenant_count}</div><div class="stat-label">Mieter</div></div>
        <div class="stat-box"><div class="stat-value">{invoice_count}</div><div class="stat-label">Rechnungen</div></div>
        <div class="stat-box"><div class="stat-value">{invoice_sum:.2f} €</div><div class="stat-label">Gesamt</div></div>
    </div>
    """

# ============================================================================
# INIT DATABASE (also for Gunicorn/Docker – runs before if __name__)
# ============================================================================
with app.app_context():
    init_db(app)

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    if request.headers.get('HX-Request'):
        return '<div class="alert alert-error">Seite nicht gefunden.</div>', 404
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(e):
    app.logger.error(f"Server error: {e}")
    if request.headers.get('HX-Request'):
        return '<div class="alert alert-error">Interner Serverfehler.</div>', 500
    return render_template('errors/500.html'), 500

# ============================================================================
# INIT
# ============================================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
