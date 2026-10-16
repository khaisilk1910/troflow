"""V10 administrator-only invoice cancellation and auditable reissuance.

Keep the original invoice ID, payment receipts and revision snapshots.  Cancellation
is a non-destructive financial hold; reissue must never cause an overpayment to
be silently erased.  An administrator must explicitly reconcile it first.
"""
import json
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends
from .db import tx, one, rows
from .main import admin_user, fail, trim, positive, audit, json_ok
from .billing import calculate
from .advanced import get_contract

router=APIRouter(prefix='/api/v10')


def snapshot(con, ident):
    invoice=one(con,'SELECT * FROM invoices WHERE id=?',(ident,))
    if not invoice:fail('Không tìm thấy hóa đơn.',404)
    invoice['lines']=rows(con,'SELECT label,code,quantity,unit_price,amount FROM invoice_lines WHERE invoice_id=? ORDER BY id',(ident,))
    invoice['payments']=rows(con,'SELECT id,amount,method,paid_at FROM payments WHERE invoice_id=? ORDER BY id',(ident,))
    return invoice


def revision(con, before, after, user, reason):
    return con.execute('''INSERT INTO invoice_revisions(invoice_id,actor_id,before_json,after_json,reason)
        VALUES(?,?,?,?,?)''',(before['id'],user['id'],json.dumps(before,ensure_ascii=False),
                                json.dumps(after,ensure_ascii=False),reason)).lastrowid


@router.post('/invoices/{ident}/void')
def void_invoice(ident:int,data:dict,user=Depends(admin_user)):
    reason=trim(data.get('reason'),'Lý do hủy hóa đơn',500,True)
    confirmed=data.get('acknowledge_payments') is True
    with tx() as con:
        before=snapshot(con,ident)
        if before['status']=='void':fail('Hóa đơn này đã được hủy.',409)
        if before['payments'] and not confirmed:
            fail('Hóa đơn đã thu tiền. Cần xác nhận giữ nguyên giao dịch và đối soát khi phát hành lại.',409)
        con.execute('''UPDATE invoices SET status='void',voided_at=?,void_reason=? WHERE id=?''',
                    (datetime.now(timezone.utc).isoformat(),reason,ident))
        # Unsent invoice/payment notifications are now invalid; keep sent logs.
        con.execute("UPDATE zalo_outbox SET status='failed',error='Hóa đơn bị hủy; nội dung thông báo không còn hiệu lực.' WHERE invoice_id=? AND status='pending'",(ident,))
        revision(con,before,snapshot(con,ident),user,'HỦY: '+reason)
        audit(con,user,'void','invoice',ident,reason)
    return json_ok(id=ident,payments_preserved=len(before['payments']))


@router.post('/invoices/{ident}/reissue')
def reissue_invoice(ident:int,data:dict,user=Depends(admin_user)):
    reason=trim(data.get('reason'),'Lý do phát hành lại',500,True)
    try: adjustment=int(data.get('adjustment',0))
    except (ValueError,TypeError):fail('Điều chỉnh phải là số nguyên VND.')
    if abs(adjustment)>100_000_000:fail('Điều chỉnh quá giới hạn.')
    discount=positive(data.get('discount',0),'Giảm giá')
    surcharge=positive(data.get('surcharge',0),'Phụ thu')
    with tx() as con:
        before=snapshot(con,ident)
        contract=get_contract(con,before['contract_id'])
        try: calc=calculate(con,contract,before['period'],adjustment,discount,surcharge)
        except ValueError as exc:fail(str(exc),409)
        received=sum(p['amount'] for p in before['payments'])
        surplus=max(0,received-calc['total'])
        if surplus and data.get('acknowledge_credit') is not True:
            fail(f'Hóa đơn mới thấp hơn số đã thu {surplus:,} đ. '
                 'Hãy xác nhận ghi nhận tiền thu thừa chờ đối soát, không tự động hoàn hay xóa giao dịch.',409)
        note=trim(data.get('note',before['note']),'Ghi chú',1000)
        fields={k:v for k,v in calc.items() if k!='lines'}
        fields.update(status='published',note=note,published_at=date.today().isoformat(),voided_at=None,void_reason='')
        con.execute('UPDATE invoices SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),ident))
        con.execute('DELETE FROM invoice_lines WHERE invoice_id=?',(ident,))
        for line in calc['lines']:
            con.execute('''INSERT INTO invoice_lines(invoice_id,label,code,quantity,unit_price,amount)
                           VALUES(?,?,?,?,?,?)''',(ident,line['label'],line['code'],line['quantity'],line['unit_price'],line['amount']))
        rev_id=revision(con,before,snapshot(con,ident),user,'PHÁT HÀNH LẠI: '+reason)
        audit(con,user,'reissue','invoice',ident,reason)
        from .notify import enqueue_invoice_event
        # Cancel unsent legacy events and issue an idempotent event for THIS version.
        con.execute("UPDATE zalo_outbox SET status='failed',error='Đã thay bằng hóa đơn phát hành lại.' WHERE invoice_id=? AND status='pending'",(ident,))
        enqueue_invoice_event(con,ident,'invoice',revision_key=f':r{rev_id}')
    return json_ok(id=ident,total=calc['total'],paid=received,unapplied_credit=surplus,utility_period=calc['utility_period'])
