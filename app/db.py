import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv('DATABASE_PATH', '/app/data/troflow.db'))

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
 full_name TEXT NOT NULL, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','staff')),
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS properties (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, address TEXT DEFAULT '',
 manager_phone TEXT DEFAULT '', electric_rate INTEGER NOT NULL DEFAULT 3500 CHECK(electric_rate>=0),
 water_rate INTEGER NOT NULL DEFAULT 20000 CHECK(water_rate>=0),
 service_fee INTEGER NOT NULL DEFAULT 100000 CHECK(service_fee>=0),
 created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS rooms (
 id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
 code TEXT NOT NULL, floor TEXT DEFAULT '', area REAL NOT NULL DEFAULT 0 CHECK(area>=0),
 rent INTEGER NOT NULL DEFAULT 0 CHECK(rent>=0), deposit INTEGER NOT NULL DEFAULT 0 CHECK(deposit>=0),
 condition TEXT NOT NULL DEFAULT 'ready' CHECK(condition IN ('ready','maintenance','inactive')),
 notes TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
 UNIQUE(property_id,code)
);
CREATE TABLE IF NOT EXISTS tenants (
 id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, phone TEXT NOT NULL,
 email TEXT DEFAULT '', id_number TEXT DEFAULT '', hometown TEXT DEFAULT '', notes TEXT DEFAULT '',
 created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS contracts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
 tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
 start_date TEXT NOT NULL, end_date TEXT NOT NULL,
 monthly_rent INTEGER NOT NULL CHECK(monthly_rent>=0), deposit INTEGER NOT NULL DEFAULT 0 CHECK(deposit>=0),
 due_day INTEGER NOT NULL DEFAULT 5 CHECK(due_day BETWEEN 1 AND 28),
 occupants INTEGER NOT NULL DEFAULT 1 CHECK(occupants>=1),
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','ended')),
 notes TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_contract_per_room ON contracts(room_id) WHERE status='active';
CREATE TABLE IF NOT EXISTS readings (
 id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
 period TEXT NOT NULL, electric_old REAL NOT NULL DEFAULT 0 CHECK(electric_old>=0),
 electric_new REAL NOT NULL DEFAULT 0 CHECK(electric_new>=electric_old),
 water_old REAL NOT NULL DEFAULT 0 CHECK(water_old>=0),
 water_new REAL NOT NULL DEFAULT 0 CHECK(water_new>=water_old),
 created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')), UNIQUE(room_id,period)
);
CREATE TABLE IF NOT EXISTS invoices (
 id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE RESTRICT,
 room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
 period TEXT NOT NULL, due_date TEXT NOT NULL, rent INTEGER NOT NULL,
 electricity INTEGER NOT NULL, water INTEGER NOT NULL, services INTEGER NOT NULL,
 adjustment INTEGER NOT NULL DEFAULT 0, electric_usage REAL NOT NULL DEFAULT 0,
 water_usage REAL NOT NULL DEFAULT 0, total INTEGER NOT NULL CHECK(total>=0),
 note TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
 UNIQUE(contract_id,period)
);
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE RESTRICT,
 amount INTEGER NOT NULL CHECK(amount>0), method TEXT NOT NULL DEFAULT 'transfer'
 CHECK(method IN ('cash','transfer','other')),
 paid_at TEXT NOT NULL, note TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS expenses (
 id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
 category TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), spent_on TEXT NOT NULL,
 description TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS tickets (
 id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
 title TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'other',
 priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low','medium','high')),
 status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','in_progress','done')),
 description TEXT DEFAULT '', reported_at TEXT NOT NULL DEFAULT (date('now','localtime')),
 resolved_at TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
 action TEXT NOT NULL, entity TEXT NOT NULL, entity_id INTEGER,
 details TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_invoices_period ON invoices(period);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(paid_at);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(spent_on);
CREATE INDEX IF NOT EXISTS idx_contract_dates ON contracts(start_date,end_date);
'''

class ManagedConnection(sqlite3.Connection):
    """Closing context manager, unlike sqlite3's commit-only context manager."""
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=15, isolation_level=None, factory=ManagedConnection)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA busy_timeout=10000')
    return con


def init_db():
    from .migrations import migrate, restore_pending
    existing = DB_PATH.exists()
    restore_pending(DB_PATH)
    with connect() as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.executescript(SCHEMA)
        migrate(con, DB_PATH, existing)


@contextmanager
def tx():
    con = connect()
    try:
        con.execute('BEGIN IMMEDIATE')
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def rows(con, sql, params=()):
    return [dict(x) for x in con.execute(sql, params).fetchall()]


def one(con, sql, params=()):
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None
