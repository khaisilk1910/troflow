"""Private maintenance tickets shared by staff and tenant portal (V8).

The tenant's room is determined only from the authenticated account's active
contract, never from a room_id submitted by the browser. Photos are private,
normalized JPEGs. Sending Zalo is delegated to the durable outbox.
"""
import os
import re
import secrets
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from .db import connect, tx, one, rows
from .main import authorized, audit, fail, ticket_values, insert, update
from . import tenant_portal
from .tenant_portal import csrf_tenant, session_tenant, mine

router = APIRouter()
CATEGORIES = {'electric','water','internet','furniture','other'}
PRIORITIES = {'low','medium','high'}
MAX_PHOTOS=5


def _room_in_scope(con,user,room_id):
    room=one(con,'SELECT id,property_id FROM rooms WHERE id=?',(room_id,))
    if not room:fail('Không tìm thấy phòng.',404)
    if user['role']!='admin' and room['property_id'] not in user['grant_ids']:
        fail('Phòng ngoài phạm vi được cấp quyền.',403)
    return room


def _ticket_in_scope(con,user,ident):
    ticket=one(con,'''SELECT k.*,r.property_id FROM tickets k JOIN rooms r ON r.id=k.room_id
                        WHERE k.id=?''',(ident,))
    if not ticket or (user['role']!='admin' and ticket['property_id'] not in user['grant_ids']):
        fail('Không tìm thấy yêu cầu trong phạm vi của bạn.',404)
    return ticket


def _tenant_ticket(con,t,ident):
    ticket=one(con,'''SELECT k.*,r.code room_code,r.property_id FROM tickets k
           JOIN rooms r ON r.id=k.room_id WHERE k.id=? AND k.reported_by_tenant_id=?
           AND r.property_id=?''',(ident,t['tenant_id'],t['property_id']))
    if not ticket:fail('Không tìm thấy yêu cầu của bạn.',404)
    return ticket


def _file_photo(photo):
    if not re.fullmatch(r'[0-9a-f]{40}\.jpg',photo['file_name']):fail('Ảnh không tồn tại.',404)
    return tenant_portal.serve_photo(photo['file_name'])


def _store_photos(con,ident,files,created):
    files=[f for f in (files or []) if f and f.filename]
    count=one(con,'SELECT COUNT(*) n FROM ticket_photos WHERE ticket_id=?',(ident,))['n']
    if count+len(files)>MAX_PHOTOS:
        fail('Tối đa 5 ảnh cho mỗi yêu cầu sửa chữa.',400)
    # Validate all uploads BEFORE recording any image. clean_image strips EXIF and
    # rejects spoofed/malformed/decompression-bomb images.
    normalized=[tenant_portal.clean_image(f) for f in files]
    tenant_portal.UPLOADS.mkdir(parents=True,exist_ok=True)
    for blob in normalized:
        name=secrets.token_hex(20)+'.jpg'
        path=tenant_portal.UPLOADS/name
        with path.open('xb') as out:out.write(blob)
        os.chmod(path,0o600)
        created.append(path)
        con.execute('INSERT INTO ticket_photos(ticket_id,file_name) VALUES(?,?)',(ident,name))


def _payload(room_id,category,title,priority,status,description,reported_at):
    return ticket_values({'room_id':room_id,'category':category,'title':title,'priority':priority,
                         'status':status,'description':description,'reported_at':reported_at})


def _cleanup(paths):
    for path in paths:
        path.unlink(missing_ok=True)


@router.post('/api/tenant/tickets')
async def tenant_create_ticket(title:str=Form(...),category:str=Form('other'),
                               priority:str=Form('medium'),description:str=Form(''),
                               photos:list[UploadFile]=File(default=[]),t=Depends(csrf_tenant)):
    if len(photos)>MAX_PHOTOS:fail('Tối đa 5 ảnh.',400)
    created=[]
    try:
        with tx() as con:
            contracts=mine(con,t)
            current=[c for c in contracts if c['start_date']<=date.today().isoformat()<=c['end_date']]
            if not current:fail('Bạn chưa có phòng đang thuê hợp lệ.',403)
            if len(current)!=1:fail('Có nhiều phòng đang thuê; vui lòng liên hệ quản lý để xác định phòng.',409)
            c=current[0]
            recent=one(con,"SELECT COUNT(*) n FROM tickets WHERE reported_by_tenant_id=? AND created_at>=datetime('now','localtime','-1 hour')",(t['tenant_id'],))['n']
            if recent>=5:fail('Bạn đã gửi nhiều yêu cầu, vui lòng thử lại sau một giờ.',429)
            vals=_payload(c['room_id'],category,title,priority,'new',description,date.today().isoformat())
            vals.update(reported_by_tenant_id=t['tenant_id'],reported_contract_id=c['contract_id'])
            ident=insert(con,'tickets',vals)
            _store_photos(con,ident,photos,created)
            from .notify import enqueue_ticket_event
            enqueue_ticket_event(con,ident)
            from .notify import enqueue_ticket_tenant
            enqueue_ticket_tenant(con,ident)
        return {'id':ident,'status':'new','photos':len(created),'queued':True}
    except Exception:
        _cleanup(created)
        raise


@router.get('/api/tenant/tickets')
def tenant_tickets(t=Depends(session_tenant)):
    with connect() as con:
        return rows(con,'''SELECT k.id,k.title,k.category,k.priority,k.description,k.status,
          k.reported_at,k.resolved_at,r.code room_code,p.name property_name,
          (SELECT COUNT(*) FROM ticket_photos f WHERE f.ticket_id=k.id) photo_count
          FROM tickets k JOIN rooms r ON r.id=k.room_id JOIN properties p ON p.id=r.property_id
          WHERE k.reported_by_tenant_id=? AND p.id=? ORDER BY k.id DESC LIMIT 100''',
          (t['tenant_id'],t['property_id']))


@router.get('/api/tenant/tickets/{ident}/photos/{photo_id}')
def tenant_ticket_image(ident:int,photo_id:int,t=Depends(session_tenant)):
    with connect() as con:
        _tenant_ticket(con,t,ident)
        photo=one(con,'SELECT * FROM ticket_photos WHERE id=? AND ticket_id=?',(photo_id,ident))
    if not photo:fail('Ảnh không tồn tại.',404)
    return _file_photo(photo)


@router.get('/api/tenant/tickets/{ident}/photos')
def tenant_ticket_photos(ident:int,t=Depends(session_tenant)):
    with connect() as con:
        _tenant_ticket(con,t,ident)
        return [{'id':p['id'],'url':f'/api/tenant/tickets/{ident}/photos/{p["id"]}'}
                for p in rows(con,'SELECT id FROM ticket_photos WHERE ticket_id=? ORDER BY id',(ident,))]


@router.post('/api/v8/tickets')
async def staff_create_ticket(room_id:int=Form(...),title:str=Form(...),category:str=Form('other'),
                              priority:str=Form('medium'),status:str=Form('new'),
                              reported_at:str=Form(...),description:str=Form(''),
                              photos:list[UploadFile]=File(default=[]),user=Depends(authorized)):
    created=[]
    try:
        with tx() as con:
            _room_in_scope(con,user,room_id)
            vals=_payload(room_id,category,title,priority,status,description,reported_at)
            vals['resolved_at']=date.today().isoformat() if vals['status']=='done' else None
            ident=insert(con,'tickets',vals)
            _store_photos(con,ident,photos,created)
            audit(con,user,'create','ticket',ident)
        return {'id':ident,'photos':len(created)}
    except Exception:
        _cleanup(created)
        raise


@router.put('/api/v8/tickets/{ident}')
async def staff_edit_ticket(ident:int,room_id:int=Form(...),title:str=Form(...),category:str=Form('other'),
                            priority:str=Form('medium'),status:str=Form('new'),
                            reported_at:str=Form(...),description:str=Form(''),
                            photos:list[UploadFile]=File(default=[]),user=Depends(authorized)):
    created=[]
    try:
        with tx() as con:
            old=_ticket_in_scope(con,user,ident)
            _room_in_scope(con,user,room_id)
            if old['reported_by_tenant_id'] and room_id!=old['room_id']:
                fail('Không thể chuyển yêu cầu khách đã gửi sang phòng khác.',409)
            vals=_payload(room_id,category,title,priority,status,description,reported_at)
            vals['resolved_at']=(old['resolved_at'] or date.today().isoformat()) if vals['status']=='done' else None
            update(con,'tickets',ident,vals)
            _store_photos(con,ident,photos,created)
            audit(con,user,'update','ticket',ident)
            if old['status']!=vals['status']:
                from .notify import enqueue_ticket_tenant
                enqueue_ticket_tenant(con,ident,old['status'])
        return {'ok':True,'photos_added':len(created)}
    except Exception:
        _cleanup(created)
        raise


@router.get('/api/v8/tickets/{ident}/photos')
def staff_ticket_photos(ident:int,user=Depends(authorized)):
    with connect() as con:
        _ticket_in_scope(con,user,ident)
        return [{'id':p['id'],'url':f'/api/v8/tickets/{ident}/photos/{p["id"]}'}
                for p in rows(con,'SELECT id FROM ticket_photos WHERE ticket_id=? ORDER BY id',(ident,))]


@router.get('/api/v8/tickets/{ident}/photos/{photo_id}')
def staff_ticket_image(ident:int,photo_id:int,user=Depends(authorized)):
    with connect() as con:
        _ticket_in_scope(con,user,ident)
        photo=one(con,'SELECT * FROM ticket_photos WHERE id=? AND ticket_id=?',(photo_id,ident))
    if not photo:fail('Ảnh không tồn tại.',404)
    return _file_photo(photo)


@router.delete('/api/v8/tickets/{ident}/photos/{photo_id}')
def staff_ticket_image_delete(ident:int,photo_id:int,user=Depends(authorized)):
    if user['role']!='admin' and not user['permissions'].get('tickets.edit'):
        fail('Không được xóa ảnh.',403)
    with tx() as con:
        _ticket_in_scope(con,user,ident)
        photo=one(con,'SELECT * FROM ticket_photos WHERE id=? AND ticket_id=?',(photo_id,ident))
        if not photo:fail('Không tìm thấy ảnh.',404)
        # Do not silently mutate an album already awaiting delivery.
        pending=one(con,"SELECT id FROM zalo_outbox WHERE ticket_id=? AND status IN ('pending','sending') LIMIT 1",(ident,))
        if pending:fail('Chờ gửi thông báo Zalo xong trước khi xóa ảnh.',409)
        con.execute('DELETE FROM ticket_photos WHERE id=?',(photo_id,))
        audit(con,user,'delete','ticket_photo',photo_id)
    (tenant_portal.UPLOADS/photo['file_name']).unlink(missing_ok=True)
    return {'ok':True}

@router.get('/api/integration-ticket-media/{token}')
def ticket_media_for_bot(token:str):
    """Short-lived bearer capability for precisely one ticket photo (not CCCD)."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,60}',token):fail('Ảnh không tồn tại.',404)
    with connect() as con:
        photo=one(con,'''SELECT f.file_name FROM ticket_media_tokens m
             JOIN ticket_photos f ON f.id=m.photo_id
             WHERE m.token=? AND m.expires_at>?''',(token,datetime.now(timezone.utc).isoformat()))
    if not photo:fail('Ảnh không tồn tại hoặc đã hết hạn.',404)
    # Unauthenticated media is accessible only to holders of a high-entropy
    # short-lived token; ensure path cannot escape the uploads directory.
    result=_file_photo(photo)
    result.headers['Cache-Control']='no-store'
    result.headers['Referrer-Policy']='no-referrer'
    return result
