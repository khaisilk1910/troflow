"""Idempotent, versioned, additive SQLite upgrades for the original TroFlow database.

No legacy data is dropped, no existing table is rebuilt.  SQLite online snapshot is
created BEFORE any schema changes on an existing v1 database.
"""
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

DB_PATH = None  # call migrate(con, actual_database_path)

COLUMNS = {
 'users': {'job_role': "TEXT NOT NULL DEFAULT 'manager'"},
 'contracts': {'prorate': 'INTEGER NOT NULL DEFAULT 0'},
 'readings': {'electric_photo':'TEXT', 'water_photo':'TEXT'},
 'invoices': {'status': "TEXT NOT NULL DEFAULT 'published'", 'discount': 'INTEGER NOT NULL DEFAULT 0',
              'surcharge': 'INTEGER NOT NULL DEFAULT 0', 'carried_debt': 'INTEGER NOT NULL DEFAULT 0',
              'calculation_json': "TEXT NOT NULL DEFAULT '{}'", 'published_at': 'TEXT'},
 'properties': {'bank_code': "TEXT NOT NULL DEFAULT ''", 'bank_account': "TEXT NOT NULL DEFAULT ''",
                'bank_name': "TEXT NOT NULL DEFAULT ''"},
}

TABLES = [
'''CREATE TABLE IF NOT EXISTS property_grants (
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
 PRIMARY KEY(user_id,property_id))''',
'''CREATE TABLE IF NOT EXISTS deposit_transactions (
 id INTEGER PRIMARY KEY, contract_id INTEGER NOT NULL REFERENCES contracts(id),
 kind TEXT NOT NULL CHECK(kind IN ('receive','refund','deduct')),
 amount INTEGER NOT NULL CHECK(amount>0), transacted_on TEXT NOT NULL,
 note TEXT NOT NULL DEFAULT '', created_by INTEGER REFERENCES users(id),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
'''CREATE TABLE IF NOT EXISTS contract_residents (
 id INTEGER PRIMARY KEY, contract_id INTEGER NOT NULL REFERENCES contracts(id),
 tenant_id INTEGER REFERENCES tenants(id), full_name TEXT NOT NULL, phone TEXT DEFAULT '',
 id_number TEXT DEFAULT '', hometown TEXT DEFAULT '', is_primary INTEGER NOT NULL DEFAULT 0,
 moved_in TEXT NOT NULL, moved_out TEXT, notes TEXT DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(contract_id,tenant_id))''',
'''CREATE TABLE IF NOT EXISTS service_catalog (
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id),
 name TEXT NOT NULL, unit TEXT NOT NULL DEFAULT 'thang',
 charge_type TEXT NOT NULL CHECK(charge_type IN ('flat','person','quantity')),
 unit_price INTEGER NOT NULL CHECK(unit_price>=0), active INTEGER NOT NULL DEFAULT 1,
 UNIQUE(property_id,name))''',
'''CREATE TABLE IF NOT EXISTS contract_services (
 id INTEGER PRIMARY KEY, contract_id INTEGER NOT NULL REFERENCES contracts(id),
 service_id INTEGER NOT NULL REFERENCES service_catalog(id),
 quantity REAL NOT NULL DEFAULT 1 CHECK(quantity>=0), active INTEGER NOT NULL DEFAULT 1,
 UNIQUE(contract_id,service_id))''',
'''CREATE TABLE IF NOT EXISTS invoice_lines (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
 label TEXT NOT NULL, code TEXT NOT NULL, quantity REAL NOT NULL DEFAULT 1,
 unit_price INTEGER NOT NULL DEFAULT 0, amount INTEGER NOT NULL)''',
'''CREATE TABLE IF NOT EXISTS invoice_revisions (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
 actor_id INTEGER REFERENCES users(id), before_json TEXT NOT NULL, after_json TEXT NOT NULL,
 reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
'''CREATE TABLE IF NOT EXISTS handovers (
 id INTEGER PRIMARY KEY, contract_id INTEGER NOT NULL REFERENCES contracts(id),
 handover_type TEXT NOT NULL CHECK(handover_type IN ('checkin','checkout')),
 handover_on TEXT NOT NULL, description TEXT DEFAULT '', damage_amount INTEGER NOT NULL DEFAULT 0,
 electric_final REAL, water_final REAL, photo_path TEXT, confirmed_by TEXT DEFAULT '',
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(contract_id,handover_type))''',
'''CREATE TABLE IF NOT EXISTS invoice_schedules (
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL UNIQUE REFERENCES properties(id),
 active INTEGER NOT NULL DEFAULT 0, day_of_month INTEGER NOT NULL DEFAULT 1 CHECK(day_of_month BETWEEN 1 AND 28),
 require_readings INTEGER NOT NULL DEFAULT 1, last_period TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
'''CREATE TABLE IF NOT EXISTS schedule_events (
 id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id),
 period TEXT NOT NULL, contract_id INTEGER REFERENCES contracts(id),
 message TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'warning',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(property_id,period,contract_id,message))''',
'''CREATE TABLE IF NOT EXISTS app_settings (
 key TEXT PRIMARY KEY, value TEXT NOT NULL)''',
]


def _backup_before_upgrade(con, db_path):
    if not Path(db_path).is_file() or not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='invoices'").fetchone():
        return None
    backup_dir = Path(os.getenv('BACKUP_DIRECTORY','/app/backups')) / 'migrations'
    backup_dir.mkdir(parents=True,exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    destination = backup_dir / f'troflow-v1-before-v2-{stamp}.sqlite3'
    with closing(sqlite3.connect(str(destination))) as dest:
        con.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Database snapshot failed integrity check')
    os.chmod(destination,0o600)
    return destination


def migrate(con, db_path, existed_before_init=True):
    version=con.execute('PRAGMA user_version').fetchone()[0]
    if version >= 2:
        return
    # v1 deployments historically had user_version=0; detect existence of legacy tables.
    if existed_before_init:
        _backup_before_upgrade(con,db_path)
    con.execute('BEGIN IMMEDIATE')
    try:
        for table,columns in COLUMNS.items():
            existing={row[1] for row in con.execute(f'PRAGMA table_info({table})')}
            for column,definition in columns.items():
                if column not in existing:
                    con.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
        for statement in TABLES:
            con.execute(statement)
        # Snapshot the contractual lead resident; older contracts remain intact.
        con.execute('''INSERT INTO contract_residents (contract_id,tenant_id,full_name,phone,id_number,hometown,is_primary,moved_in)
         SELECT c.id,t.id,t.full_name,t.phone,t.id_number,t.hometown,1,c.start_date
         FROM contracts c JOIN tenants t ON t.id=c.tenant_id
         WHERE NOT EXISTS (SELECT 1 FROM contract_residents x WHERE x.contract_id=c.id AND x.is_primary=1)''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_residents_contract ON contract_residents(contract_id)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_deposits_contract ON deposit_transactions(contract_id)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_invoice_status ON invoices(status,period)')
        con.execute('PRAGMA user_version=2')
        con.commit()
    except Exception:
        con.rollback()
        raise


def restore_pending(db_path):
    """Apply an administrator-staged backup BEFORE the server opens its database."""
    import json
    path = Path(db_path)
    restore_file = path.parent / '.troflow-restore-request.json'
    if not restore_file.exists():
        return
    data=json.loads(restore_file.read_text())
    backup_dir = Path(os.getenv('BACKUP_DIRECTORY','/app/backups')).resolve()
    name=data['filename']
    if Path(name).name != name or not name.startswith('troflow-') or not name.endswith('.sqlite3'):
        raise RuntimeError('Invalid restore file name')
    target=(backup_dir / name).resolve()
    if target.parent != backup_dir or not target.is_file():
        raise RuntimeError('Requested backup not found')
    with closing(sqlite3.connect(f'file:{target}?mode=ro',uri=True)) as check:
        if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Requested backup failed integrity check')
        if not check.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
            raise RuntimeError('Not a TroFlow database')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        snap = backup_dir / f'troflow-pre-restore-{datetime.now().strftime("%Y%m%d-%H%M%S")}.sqlite3'
        with closing(sqlite3.connect(str(path))) as old,closing(sqlite3.connect(str(snap))) as dst:
            old.backup(dst)
    temporary=path.with_name('.troflow-restoring.sqlite3')
    with closing(sqlite3.connect(f'file:{target}?mode=ro',uri=True)) as src, closing(sqlite3.connect(str(temporary))) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Restore candidate failed integrity check')
    # No API connections exist during this startup operation.
    for suffix in ('-wal','-shm'):
        stale=Path(str(path)+suffix)
        if stale.exists(): stale.unlink()
    os.replace(temporary,path)
    restore_file.unlink()
