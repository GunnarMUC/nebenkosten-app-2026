-- Nebenkosten-Abrechnung Datenbankschema
-- SQLite, angelehnt an BetrKV (Betriebskostenverordnung)

-- Benutzer (Vermieter, Mieter, Admin)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('vermieter', 'mieter', 'admin')),
    display_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Wohnobjekte / Immobilien
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT,
    address TEXT NOT NULL,
    total_sqm REAL NOT NULL,
    units INTEGER DEFAULT 1,
    construction_year INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Mieter
CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    name TEXT NOT NULL,
    email TEXT,
    move_in_date DATE NOT NULL,
    move_out_date DATE,
    sqm REAL NOT NULL,
    persons INTEGER DEFAULT 1,
    vorauszahlung REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- BetrKV Kostenarten (Referenz)
CREATE TABLE IF NOT EXISTS betrkv_kostenarten (
    nr INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    default_key TEXT NOT NULL CHECK(default_key IN ('qm', 'person', 'verbrauch', 'einheit', ' QM_50_VERBRAUCH_50', 'tagesanteilig'))
);

-- Rechnungen / Belege
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    betrkv_nr INTEGER NOT NULL,
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    date DATE NOT NULL,
    vendor TEXT,
    document_path TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Verteilung der Kosten auf Mieter
CREATE TABLE IF NOT EXISTS allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    amount REAL NOT NULL,
    allocation_key TEXT NOT NULL,
    sqm_factor REAL,
    person_factor REAL,
    days_factor REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Abrechnungen (pro Jahr und Objekt)
CREATE TABLE IF NOT EXISTS abrechnungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    year INTEGER NOT NULL,
    status TEXT DEFAULT 'entwurf' CHECK(status IN ('entwurf', 'fertig', 'versendet')),
    pdf_path TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pruefberichte (fuer Mieter)
CREATE TABLE IF NOT EXISTS pruefberichte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    abrechnung_upload_path TEXT,
    findings_json TEXT,
    status TEXT DEFAULT 'laeuft' CHECK(status IN ('laeuft', 'fertig', 'fehler')),
    pdf_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chat-Verlauf mit KI-Assistent
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    context_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Async Jobs (fuer Hintergrundverarbeitung von OCR + LLM)
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    job_type TEXT NOT NULL CHECK(job_type IN ('pruefung')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued', 'running', 'done', 'error')),
    payload_json TEXT NOT NULL,
    result_json TEXT,
    pruefbericht_id INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- BetrKV Kostenarten befuellen (§2 BetrKV)
INSERT OR IGNORE INTO betrkv_kostenarten (nr, name, description, default_key) VALUES
(1, 'Grundsteuer', 'Grundsteuer A und B auf das Mietobjekt', 'qm'),
(2, 'Versicherungen', 'Gebauede-, Haftpflicht-, Glasversicherung', 'qm'),
(3, 'Heizung', 'Heizungskosten (ohne Warmwasser)', ' QM_50_VERBRAUCH_50'),
(4, 'Warmwasser', 'Warmwasserbereitung und -versorgung', ' QM_50_VERBRAUCH_50'),
(5, 'Wasserversorgung', 'Kaltwasser und Abwasser', 'person'),
(6, 'Entwaesserung', 'Niederschlagswasser, Straßenentwaesserung', 'qm'),
(7, 'Gartenpflege', 'Garten- und Landschaftspflege', 'qm'),
(8, 'Beleuchtung', 'Straßenbeleuchtung, Gartenbeleuchtung', 'einheit'),
(9, 'Aufzug', 'Aufzugsbetrieb und -wartung', 'einheit'),
(10, 'Muellbeseitigung', 'Muellabfuhr und -entsorgung', 'einheit'),
(11, 'Gebaeudereinigung', 'Treppenhausreinigung, Fensterreinigung', 'qm'),
(12, 'Schornstein', 'Schornsteinfeger, Kehrung', 'einheit'),
(13, 'Sachverstand', 'Sachverstaendigenkosten, Wartung', 'qm'),
(14, 'Kabelanschluss', 'Kabel-TV / Satellit (nur bis 30.06.2024)', 'qm'),
(15, 'Rauchmelder', 'Wartung und Pruefung Rauchmelder', 'einheit'),
(16, 'Energie Hausflur', 'Strom Versorgung Gemeinschaftsflaechen', 'qm'),
(17, 'Internet/Telefon', 'Gemeinschaftsantenne, Internet-Grundversorgung', 'qm');
