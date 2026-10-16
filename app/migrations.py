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
 'tenants': {'id_front_path':'TEXT', 'id_back_path':'TEXT'},
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


def _backup_before_upgrade(con, db_path, tag="v4"):
    if not Path(db_path).is_file() or not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='invoices'").fetchone():
        return None
    backup_dir = Path(os.getenv('BACKUP_DIRECTORY','/app/backups')) / 'migrations'
    backup_dir.mkdir(parents=True,exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    destination = backup_dir / f'troflow-before-{tag}-{stamp}.sqlite3'
    with closing(sqlite3.connect(str(destination))) as dest:
        con.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Database snapshot failed integrity check')
    os.chmod(destination,0o600)
    return destination


def migrate(con, db_path, existed_before_init=True):
    version=con.execute('PRAGMA user_version').fetchone()[0]
    if version >= 5:
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
        con.execute('''CREATE TABLE IF NOT EXISTS user_permissions (
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          permission_key TEXT NOT NULL, allowed INTEGER NOT NULL CHECK(allowed IN (0,1)),
          PRIMARY KEY(user_id,permission_key))''')
        con.execute('''CREATE TABLE IF NOT EXISTS rent_prepayment_batches (
          id INTEGER PRIMARY KEY,contract_id INTEGER NOT NULL REFERENCES contracts(id),
          paid_on TEXT NOT NULL,method TEXT NOT NULL CHECK(method IN ('cash','transfer','other')),
          total INTEGER NOT NULL CHECK(total>0),note TEXT NOT NULL DEFAULT '',
          created_by INTEGER REFERENCES users(id),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        con.execute('''CREATE TABLE IF NOT EXISTS rent_coverage (
          id INTEGER PRIMARY KEY,batch_id INTEGER NOT NULL REFERENCES rent_prepayment_batches(id),
          contract_id INTEGER NOT NULL REFERENCES contracts(id),period TEXT NOT NULL,
          amount INTEGER NOT NULL CHECK(amount>0),status TEXT NOT NULL DEFAULT 'active'
          CHECK(status IN ('active','refunded')),refunded_on TEXT,
          CHECK (length(period)=7))''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_rent_coverage_contract ON rent_coverage(contract_id,period)')
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_rent_active_month ON rent_coverage(contract_id,period) WHERE status='active'")
        columns={r[1] for r in con.execute('PRAGMA table_info(tenants)')}
        if 'photo_path' not in columns:
            con.execute('ALTER TABLE tenants ADD COLUMN photo_path TEXT')
        con.execute('''CREATE TABLE IF NOT EXISTS utility_meters (
          id INTEGER PRIMARY KEY,
          property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
          kind TEXT NOT NULL CHECK(kind IN ('electric','water')),
          meter_number TEXT NOT NULL,
          customer_code TEXT NOT NULL,
          supplier TEXT NOT NULL DEFAULT '',
          label TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT '',
          active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(property_id,kind,meter_number))''')
        con.execute('''CREATE TABLE IF NOT EXISTS utility_meter_periods (
          id INTEGER PRIMARY KEY,
          meter_id INTEGER NOT NULL REFERENCES utility_meters(id) ON DELETE RESTRICT,
          period TEXT NOT NULL CHECK(length(period)=7),
          reading_old REAL NOT NULL DEFAULT 0 CHECK(reading_old>=0),
          reading_new REAL NOT NULL DEFAULT 0 CHECK(reading_new>=reading_old),
          billed_usage REAL NOT NULL DEFAULT 0 CHECK(billed_usage>=0),
          bill_amount INTEGER NOT NULL DEFAULT 0 CHECK(bill_amount>=0),
          paid_amount INTEGER NOT NULL DEFAULT 0 CHECK(paid_amount>=0 AND paid_amount<=bill_amount),
          paid_on TEXT,
          note TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(meter_id,period))''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_utility_meter_period ON utility_meter_periods(period,meter_id)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_utility_meter_property ON utility_meters(property_id,kind)')
        con.execute('PRAGMA user_version=5')
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


def migrate_v6(con, db_path, existed_before_init=True):
    """Additive V5->V6 integration schema and legacy bank migration."""
    version=con.execute('PRAGMA user_version').fetchone()[0]
    if version>=6:return
    if existed_before_init:
        _backup_before_upgrade(con,db_path,tag="v6")
    con.execute('BEGIN IMMEDIATE')
    try:
        con.execute('''CREATE TABLE IF NOT EXISTS bank_accounts (
          id INTEGER PRIMARY KEY,property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
          bank_code TEXT NOT NULL,bank_name TEXT NOT NULL,holder TEXT NOT NULL,account_number TEXT NOT NULL,
          is_default INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(property_id,bank_code,account_number))''')
        con.execute('''CREATE TABLE IF NOT EXISTS zalo_config (
          id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
          invoice_enabled INTEGER NOT NULL DEFAULT 0,payment_enabled INTEGER NOT NULL DEFAULT 0,
          bot_url TEXT NOT NULL DEFAULT 'http://host.docker.internal:3000',
          account_selection TEXT NOT NULL DEFAULT '', media_url TEXT NOT NULL DEFAULT '')''')
        con.execute('INSERT OR IGNORE INTO zalo_config(id) VALUES(1)')
        con.execute('''CREATE TABLE IF NOT EXISTS zalo_destinations (
          id INTEGER PRIMARY KEY,name TEXT NOT NULL,thread_id TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('user','group')),
          property_id INTEGER REFERENCES properties(id) ON DELETE SET NULL,
          tenant_id INTEGER REFERENCES tenants(id) ON DELETE SET NULL,
          enabled INTEGER NOT NULL DEFAULT 1,on_invoice INTEGER NOT NULL DEFAULT 1,
          on_payment INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        con.execute('''CREATE TABLE IF NOT EXISTS zalo_outbox (
          id INTEGER PRIMARY KEY,destination_id INTEGER REFERENCES zalo_destinations(id) ON DELETE SET NULL,
          invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
          event TEXT NOT NULL,event_key TEXT NOT NULL,message TEXT NOT NULL,
          include_image INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','failed','sent')),
          attempts INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,sent_at TEXT,
          UNIQUE(event_key,destination_id))''')
        con.execute("CREATE INDEX IF NOT EXISTS idx_zalo_outbox_status ON zalo_outbox(status,id)")
        con.execute('''CREATE TABLE IF NOT EXISTS notification_media (
          token TEXT PRIMARY KEY,invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
          expires_at TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        # Migrate V2 bank fields; keep the previous property fields untouched for rollback.
        for row in con.execute('SELECT id,bank_code,bank_account,bank_name FROM properties').fetchall():
            prop,code,acct,holder=row
            if code and acct:
                con.execute('''INSERT OR IGNORE INTO bank_accounts
                  (property_id,bank_code,bank_name,holder,account_number,is_default,active)
                  VALUES(?,?,?,?,?,1,1)''',
                  (prop,code,code,holder or '',acct))
        con.execute('PRAGMA user_version=6')
        con.commit()
    except Exception:
        con.rollback()
        raise


def migrate_v7(con, db_path, existed_before_init=True):
    """Non-destructive tenant portal schema. Never create weak credentials for old tenants."""
    version=con.execute('PRAGMA user_version').fetchone()[0]
    if version>=7:return
    if existed_before_init:_backup_before_upgrade(con,db_path,tag='v7')
    con.execute('BEGIN IMMEDIATE')
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS tenant_portal_accounts (
          tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
          property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
          username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
          access_code_hash TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE IF NOT EXISTS tenant_portal_sessions (
          token_hash TEXT PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenant_portal_accounts(tenant_id) ON DELETE CASCADE,
          csrf_token TEXT NOT NULL,expires_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS tenant_meter_submissions (
          id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          property_id INTEGER NOT NULL REFERENCES properties(id),
          contract_id INTEGER NOT NULL REFERENCES contracts(id), room_id INTEGER NOT NULL REFERENCES rooms(id),
          period TEXT NOT NULL,electric_old REAL NOT NULL,electric_new REAL NOT NULL,
          water_old REAL NOT NULL,water_new REAL NOT NULL,
          electric_photo TEXT NOT NULL,water_photo TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
          feedback TEXT NOT NULL DEFAULT '',reviewed_by INTEGER REFERENCES users(id),reviewed_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(contract_id,period))""")
        con.execute('CREATE INDEX IF NOT EXISTS idx_tenant_meter_status ON tenant_meter_submissions(status,property_id)')
        con.execute("""CREATE TABLE IF NOT EXISTS owner_profiles (
          property_id INTEGER PRIMARY KEY REFERENCES properties(id) ON DELETE CASCADE,
          name TEXT NOT NULL DEFAULT '',gender TEXT NOT NULL DEFAULT '',age INTEGER,
          photo_path TEXT,address TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',
          show_name INTEGER NOT NULL DEFAULT 1,show_gender INTEGER NOT NULL DEFAULT 0,
          show_age INTEGER NOT NULL DEFAULT 0,show_photo INTEGER NOT NULL DEFAULT 0,
          show_address INTEGER NOT NULL DEFAULT 0,show_phone INTEGER NOT NULL DEFAULT 1,
          show_email INTEGER NOT NULL DEFAULT 0)""")
        con.execute('PRAGMA user_version=7')
        con.commit()
    except Exception:
        con.rollback()
        raise


def migrate_v8(con, db_path, existed_before_init=True):
    """Tenant repair requests, private images and Zalo album delivery; additive migration."""
    if con.execute('PRAGMA user_version').fetchone()[0] >= 8:
        return
    if existed_before_init:
        _backup_before_upgrade(con, db_path, tag='v8')
    con.execute('BEGIN IMMEDIATE')
    try:
        ticket_cols={r[1] for r in con.execute('PRAGMA table_info(tickets)')}
        for name, definition in {'reported_by_tenant_id':'INTEGER REFERENCES tenants(id)',
                                 'reported_contract_id':'INTEGER REFERENCES contracts(id)'}.items():
            if name not in ticket_cols:
                con.execute(f'ALTER TABLE tickets ADD COLUMN {name} {definition}')
        con.execute('''CREATE TABLE IF NOT EXISTS ticket_photos (
          id INTEGER PRIMARY KEY,ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
          file_name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_ticket_photos_ticket ON ticket_photos(ticket_id)')
        con.execute('''CREATE TABLE IF NOT EXISTS ticket_media_tokens (
          token TEXT PRIMARY KEY,photo_id INTEGER NOT NULL REFERENCES ticket_photos(id) ON DELETE CASCADE,
          expires_at TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        for table,column in [('zalo_config','ticket_enabled'),('zalo_destinations','on_ticket')]:
            cols={r[1] for r in con.execute(f'PRAGMA table_info({table})')}
            if column not in cols:
                con.execute(f'ALTER TABLE {table} ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0')
        cols={r[1] for r in con.execute('PRAGMA table_info(zalo_outbox)')}
        if 'ticket_id' not in cols:
            con.execute('ALTER TABLE zalo_outbox ADD COLUMN ticket_id INTEGER REFERENCES tickets(id) ON DELETE SET NULL')
        con.execute('PRAGMA user_version=8')
        con.commit()
    except Exception:
        con.rollback()
        raise


def migrate_v9(con, db_path, existed_before_init=True):
    """Encrypted HA integration mapping and provisional bill provenance."""
    if con.execute('PRAGMA user_version').fetchone()[0] >= 9:return
    if existed_before_init:_backup_before_upgrade(con,db_path,tag='v9')
    con.execute('BEGIN IMMEDIATE')
    try:
        cols={r[1] for r in con.execute('PRAGMA table_info(utility_meter_periods)')}
        if 'origin' not in cols:
            con.execute("ALTER TABLE utility_meter_periods ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'")
        con.execute('''CREATE TABLE IF NOT EXISTS ha_meter_mappings (
            meter_id INTEGER PRIMARY KEY REFERENCES utility_meters(id) ON DELETE CASCADE,
            old_entity TEXT NOT NULL,new_entity TEXT NOT NULL,usage_entity TEXT NOT NULL,amount_entity TEXT NOT NULL,
            period_offset INTEGER NOT NULL DEFAULT 0 CHECK(period_offset IN (-1,0)),
            enabled INTEGER NOT NULL DEFAULT 1,auto_sync INTEGER NOT NULL DEFAULT 0,
            last_sync_at TEXT,last_error TEXT NOT NULL DEFAULT '',last_period TEXT,last_result TEXT)''')
        for table, fields in {
            'zalo_config': {'reading_enabled':'INTEGER NOT NULL DEFAULT 1'},
            'zalo_destinations': {'on_ticket_tenant':'INTEGER NOT NULL DEFAULT 0',
                                  'on_meter_submission':'INTEGER NOT NULL DEFAULT 0'},
            'zalo_outbox': {'submission_id':'INTEGER REFERENCES tenant_meter_submissions(id) ON DELETE SET NULL'},
        }.items():
            present={r[1] for r in con.execute(f'PRAGMA table_info({table})')}
            for column,definition in fields.items():
                if column not in present:
                    con.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
        con.execute('PRAGMA user_version=9')
        con.commit()
    except Exception:
        con.rollback()
        raise
