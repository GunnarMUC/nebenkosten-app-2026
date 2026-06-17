import sqlite3
import os
from flask import g, current_app
from werkzeug.security import generate_password_hash

def get_db():
    """Get database connection for current request context."""
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE_PATH', 'database/app.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """Close database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def seed_demo_user():
    """Seed default demo user if not exists."""
    user = query_db('SELECT id FROM users WHERE username = ?', ['demo'], one=True)
    if not user:
        execute_db(
            'INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)',
            ['demo', generate_password_hash('demo'), 'vermieter', 'Demo User']
        )
        current_app.logger.info("Demo user seeded (demo/demo)")

def init_db(app):
    """Initialize database with schema and seed demo user."""
    db_path = app.config.get('DATABASE_PATH', 'database/app.db')
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with app.app_context():
        db = get_db()
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        with open(schema_path, 'r') as f:
            db.executescript(f.read())
        db.commit()
        seed_demo_user()
        current_app.logger.info("Database initialized")

def init_app(app):
    """Register database teardown handler."""
    app.teardown_appcontext(close_db)

def query_db(query, args=(), one=False):
    """Execute a query and return results."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    """Execute an insert/update/delete and return lastrowid."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid
