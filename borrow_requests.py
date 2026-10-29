# หน้าที่: ตรวจตะกร้าและสร้างคำขอยืมพร้อมเอกสาร
"""ตะกร้าและใบคำขอหลายรายการ ใช้กฎสต็อกเดิมและ commit พร้อมกัน."""
from uuid import uuid4
from urllib.parse import urlsplit
from pathlib import Path
from io import BytesIO
from pypdf import PdfReader
from common import DomainError, MANAGER_ROLES, require_actor, today, utc_now, save_upload
from database import DATABASE_PATH, PROJECT_DIR, database_connection
from services import validate_period, equipment_record, reservation_guard, refresh_stock


def request_code(row):
    group = row.get('request_group', '')
    return 'SB-' + group[:12].upper() if group else f"SB-{row['id']:06d}"


def normalize_items(items):
    if not isinstance(items, list) or not items or len(items) > 50:
        raise DomainError('กรุณาเลือกอุปกรณ์ 1–50 รายการ')
    merged = {}
    for item in items:
        if not isinstance(item, dict):
            raise DomainError('รายการในตะกร้าไม่ถูกต้อง')
        eid, amount = item.get('equipment_id'), item.get('amount')
        if type(eid) is not int or eid < 1 or type(amount) is not int or amount < 1:
            raise DomainError('รหัสอุปกรณ์และจำนวนต้องเป็นจำนวนเต็มมากกว่า 0')
        merged[eid] = merged.get(eid, 0) + amount
    return [{'equipment_id': eid, 'amount': amount} for eid, amount in merged.items()]


def validate_document_url(value):
    value = str(value or '').strip()
    if not value:
        return ''
    try:
        url = urlsplit(value)
        valid = (len(value) <= 2048 and not any(c.isspace() for c in value)
                 and url.scheme == 'https' and url.hostname in {'drive.google.com', 'docs.google.com'}
                 and not url.username and not url.password and url.port in {None, 443} and url.path not in {'', '/'})
    except ValueError:
        valid = False
    if not valid:
        raise DomainError('ใช้ลิงก์เอกสาร HTTPS จาก Google Drive หรือ Google Docs เท่านั้น')
    return value


def document_file(value):
    if not value:
        return None
    candidate = (PROJECT_DIR / value).resolve()
    root = (PROJECT_DIR / 'data/uploads/documents').resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file() or candidate.suffix not in {'.pdf', '.png'}:
        raise DomainError('ไม่พบเอกสารแนบที่ถูกต้อง')
    return candidate


def validate_pdf(content):
    if len(content) > 10 * 1024 * 1024 or not content:
        raise DomainError('เอกสารต้องมีขนาด 1 ไบต์–10 MB')
    try:
        if not content.startswith(b'%PDF-'):raise ValueError()
        reader=PdfReader(BytesIO(content),strict=True)
        if reader.is_encrypted or not len(reader.pages):raise ValueError()
    except Exception:
        raise DomainError('กรุณาแนบ PDF ที่เปิดอ่านได้และไม่ตั้งรหัสผ่าน') from None

def validate_pdf_upload(upload):
    if upload is None:raise DomainError('กรุณาดาวน์โหลด Word กรอกข้อมูลและลายเซ็นผู้ยืม แล้วแนบ PDF ก่อนส่งคำขอ')
    if Path(upload.name).suffix.lower()!='.pdf':raise DomainError('รับเฉพาะไฟล์ PDF กรุณาบันทึก Word เป็น PDF ก่อนแนบ')
    validate_pdf(upload.getvalue())

def required_document(value):
    path=document_file(value)
    if path is None or path.suffix!='.pdf':raise DomainError('คำขอยืมต้องแนบ PDF ที่กรอกเรียบร้อยแล้ว')
    validate_pdf(path.read_bytes())
    return path

def save_document(upload):
    """Store a required readable PDF under a random filename."""
    validate_pdf_upload(upload)
    directory=PROJECT_DIR/'data/uploads/documents';directory.mkdir(parents=True,exist_ok=True)
    path=directory/(uuid4().hex+'.pdf');path.write_bytes(upload.getvalue())
    return path.relative_to(PROJECT_DIR).as_posix()


def validate_cart(con, actor_id, items, start, end):
    checked = []
    for item in items:
        equipment = equipment_record(con, item['equipment_id'])
        if equipment['status'] != 'พร้อมใช้งาน' or item['amount'] > equipment['available_amount']:
            raise DomainError(f"{equipment['equipment_name']}: พร้อมใช้ไม่เพียงพอ (เหลือ {equipment['available_amount']} ชิ้น)")
        linked = reservation_guard(con, actor_id, equipment, item['amount'], start, end, item.get('reservation_id'))
        checked.append((item, linked))
    return checked


def preview_cart(actor_id, items, start, end, purpose, document_url='', database_path=DATABASE_PATH):
    items = normalize_items(items)
    start, end = validate_period(start, end)
    if not str(purpose).strip():
        raise DomainError('กรุณาระบุวัตถุประสงค์')
    document_url = validate_document_url(document_url)
    with database_connection(database_path) as con:
        require_actor(con, actor_id)
        validate_cart(con, actor_id, items, start, end)
    return dict(items=items, start=start, end=end, purpose=str(purpose).strip(), document_url=document_url)


def request_cart(actor_id, items, start, end, purpose, document_url='', document_path='', database_path=DATABASE_PATH):
    items = normalize_items(items)
    start, end = validate_period(start, end)
    if not str(purpose).strip():
        raise DomainError('กรุณาระบุวัตถุประสงค์')
    document_url = validate_document_url(document_url)
    required_document(document_path)
    group = uuid4().hex
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        require_actor(con, actor_id)
        checked = validate_cart(con, actor_id, items, start, end)
        ids = []
        for item, linked in checked:
            ids.append(con.execute('INSERT INTO borrow_transactions(user_id,equipment_id,amount,borrow_date,due_date,purpose,'
                                   'reservation_id,request_group,document_url,document_path) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                   (actor_id, item['equipment_id'], item['amount'], start, end, str(purpose).strip(),
                                    linked, group, document_url, document_path)).lastrowid)
        from notifications import notify_admins
        notify_admins(con,ids[0])
    return {'request_group': group, 'transaction_ids': ids}


def decide_group(actor_id, group, approved, database_path=DATABASE_PATH, *, reason=''):
    if not group:
        raise DomainError('ไม่พบใบคำขอ')
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        actor=require_actor(con, actor_id, MANAGER_ROLES, allow_executive=True)
        rows = [dict(r) for r in con.execute('SELECT * FROM borrow_transactions WHERE request_group=?', (group,))]
        if not rows or any(r['borrow_status'] != 'รออนุมัติ' for r in rows):
            raise DomainError('ใบคำขอนี้มีรายการที่พิจารณาแล้ว กรุณาตรวจรายการเป็นรายชิ้น')
        if len({(r['user_id'], r['borrow_date'], r['due_date'], r['equipment_id']) for r in rows}) != len(rows):
            raise DomainError('รายการในใบคำขอซ้ำ')
        if len({(r['user_id'], r['borrow_date'], r['due_date']) for r in rows}) != 1:
            raise DomainError('ข้อมูลใบคำขอไม่ตรงกัน')
        if approved:
            if rows[0]['document_path']:required_document(rows[0]['document_path'])
            if rows[0]['due_date'] < today().isoformat():
                raise DomainError('ใบคำขอนี้เลยกำหนดคืนแล้ว กรุณาส่งคำขอใหม่')
            checked = validate_cart(con, rows[0]['user_id'], rows, rows[0]['borrow_date'], rows[0]['due_date'])
            for _, linked in checked:
                if linked:
                    con.execute("UPDATE reservations SET status='สิ้นสุดแล้ว' WHERE id=?", (linked,))
        from executive_approval import prepare_decision
        if prepare_decision(con,actor,rows,approved,reason):return
        con.execute('UPDATE borrow_transactions SET borrow_status=?,approved_by=?,approved_at=? WHERE request_group=?',
                    ('อนุมัติแล้ว' if approved else 'ไม่อนุมัติ', actor_id, utc_now(), group))
        for row in rows:
            refresh_stock(con, row['equipment_id'])
            from notifications import notify_decision
            notify_decision(con,row['id'],approved)
