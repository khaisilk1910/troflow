"""One-process daily scheduler. Generates draft invoices only; no automatic publication."""
import logging
import os
import threading
from datetime import date, datetime
from .db import connect, tx, one, rows
from . import db as dbmodule
from .billing import create, month_range

log=logging.getLogger('troflow.scheduler')
STOP=threading.Event()
THREAD=None


def run_billing_period(property_id,period,actor=None):
    first,last=month_range(period)
    counts={'created':0,'skipped':0,'warnings':[]}
    with tx() as con:
        contracts=rows(con,'''SELECT c.*,r.code room_code,r.property_id,p.name property_name FROM contracts c
          JOIN rooms r ON r.id=c.room_id JOIN properties p ON p.id=r.property_id
          WHERE r.property_id=? AND c.start_date<=? AND c.end_date>=?''',
          (property_id,last.isoformat(),first.isoformat()))
        for contract in contracts:
            if one(con,'SELECT id FROM invoices WHERE contract_id=? AND period=?',(contract['id'],period)):
                counts['skipped']+=1;continue
            try:
                ident=create(con,contract,period,status='draft',require_reading=True)
                if ident:counts['created']+=1
                if actor:
                    con.execute('INSERT INTO audit_logs(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)',
                                (actor['id'],'create_draft','invoice',ident,period))
            except ValueError as exc:
                message=str(exc)
                counts['warnings'].append({'contract_id':contract['id'],'room_code':contract['room_code'],'message':message})
                con.execute('''INSERT OR IGNORE INTO schedule_events(property_id,period,contract_id,message)
                VALUES(?,?,?,?)''',(property_id,period,contract['id'],message))
        if not counts['warnings']:
            con.execute('''UPDATE invoice_schedules SET last_period=? WHERE property_id=?''',(period,property_id))
    return counts


def tick():
    now=datetime.now()
    today=now.date().isoformat()
    with connect() as con:
        hourrow=one(con,"SELECT value FROM app_settings WHERE key='backup_hour'")
        schedules=rows(con,'SELECT * FROM invoice_schedules WHERE active=1')
        prev=one(con,"SELECT value FROM app_settings WHERE key='backup_last_date'")
    backup_hour=hourrow['value'] if hourrow else '03:00'
    if now.strftime('%H:%M')>=backup_hour and (not prev or prev['value']!=today):
        from scripts.backup_sqlite import make_backup
        make_backup(dbmodule.DB_PATH)
        with tx() as con:
            con.execute("INSERT INTO app_settings(key,value) VALUES('backup_last_date',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(today,))
    try:
        from .notify import process_outbox
        process_outbox()
    except Exception:
        log.exception("Zalo outbox worker failed")
    period=today[:7]
    for item in schedules:
        if now.day>=item['day_of_month'] and item['last_period']!=period:
            try:run_billing_period(item['property_id'],period)
            except Exception:log.exception('Failed to generate scheduled draft for property=%s',item['property_id'])


def _run():
    # Wait 20 seconds after startup; keep one worker, not multiple Uvicorn workers.
    if STOP.wait(20):return
    while not STOP.is_set():
        try:tick()
        except Exception:log.exception('TroFlow background scheduler exception')
        STOP.wait(60)


def start():
    global THREAD
    if os.getenv('TROFLOW_SCHEDULER','1')!='1':return
    STOP.clear()
    THREAD=threading.Thread(target=_run,daemon=True,name='troflow-scheduler')
    THREAD.start()


def stop():
    STOP.set()
    if THREAD:THREAD.join(timeout=2)
