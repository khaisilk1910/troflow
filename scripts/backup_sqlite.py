"""Online SQLite backup, integrity verification, retention. Files under /opt/troflow/backups on host."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

SOURCE = Path(os.getenv('DATABASE_PATH', '/app/data/troflow.db'))
BACKUPS = Path(os.getenv('BACKUP_DIRECTORY', '/app/backups'))
KEEP = int(os.getenv('BACKUP_KEEP', '14'))


def make_backup(source=None, backup_dir=None):
    source=Path(source) if source else Path(os.getenv('DATABASE_PATH', '/app/data/troflow.db'))
    backup_dir=Path(backup_dir) if backup_dir else Path(os.getenv('BACKUP_DIRECTORY','/app/backups'))
    if not source.is_file(): raise RuntimeError(f'Database not found: {source}')
    backup_dir.mkdir(parents=True,exist_ok=True)
    os.umask(0o077)
    ts=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    dest=backup_dir/f'troflow-{ts}.sqlite3'
    tmp=backup_dir/f'.troflow-{ts}.tmp'
    try:
        with closing(sqlite3.connect(f'file:{source}?mode=ro',uri=True)) as src:
            with closing(sqlite3.connect(str(tmp))) as target:
                src.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise RuntimeError('Backup integrity check failed')
        os.replace(tmp,dest)
        for old in sorted(backup_dir.glob('troflow-*.sqlite3'),reverse=True)[max(1,KEEP):]:old.unlink()
        return dest
    finally:
        if tmp.exists():tmp.unlink()


def main():
    backup=make_backup()
    print(f'Backup created: {backup} ({backup.stat().st_size} bytes)')


if __name__=='__main__':main()
