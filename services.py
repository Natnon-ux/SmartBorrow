# หน้าที่: กฎการยืม ส่งมอบ คืน และคำนวณสต็อก
"""กฎและการดำเนินงานของระบบ ใช้ธุรกรรม SQLite และตรวจสิทธิ์จากฐานข้อมูล."""
from common import DomainError, MANAGER_ROLES, HELD_STATUSES, OUT_STATUSES, query_rows, require_actor, today, utc_now
from database import DATABASE_PATH, database_connection
from datetime import date
from common import validate_evidence
import math

def validate_period(start, end, future=True):
    try:
        first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    except (ValueError, TypeError) as error:
        raise DomainError("วันที่ไม่ถูกต้อง") from error
    if last < first or (future and first < today()):
        raise DomainError("วันที่สิ้นสุดต้องไม่ก่อนวันเริ่ม และวันเริ่มต้องไม่เป็นวันที่ผ่านมาแล้ว")
    return first.isoformat(), last.isoformat()

def transaction_record(connection, transaction_id):
    row = connection.execute("SELECT * FROM borrow_transactions WHERE id=?", (transaction_id,)).fetchone()
    if row is None:
        raise DomainError("ไม่พบรายการยืม")
    return dict(row)

def transactions(actor_id, database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        actor = require_actor(con, actor_id)
        sql = ("SELECT b.*,u.full_name,u.username,e.equipment_name,e.equipment_code,e.image,e.category "
               "FROM borrow_transactions b JOIN users u ON u.id=b.user_id JOIN equipment e ON e.id=b.equipment_id ")
        params = ()
        if actor["role"] not in MANAGER_ROLES:
            sql += "WHERE b.user_id=? "
            params = (actor_id,)
        return [dict(row) for row in con.execute(sql + "ORDER BY b.id DESC", params)]

def update_overdue(database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        result=con.execute("UPDATE borrow_transactions SET borrow_status='เกินกำหนด' WHERE borrow_status='กำลังยืม' AND due_date<?",(today().isoformat(),))
        con.execute("UPDATE reservations SET status='สิ้นสุดแล้ว' WHERE status IN ('รออนุมัติ','ยืนยันแล้ว') AND end_date<?",(today().isoformat(),))
        return result.rowcount

def overdue_rows(actor_id, database_path=DATABASE_PATH):
    return [r for r in transactions(actor_id,database_path) if r['borrow_status'] in OUT_STATUSES and r['due_date']<today().isoformat()]

def reservation_guard(con, actor_id, equipment, amount, start, end, linked_id=None):
    from borrowing_workflow import borrowing_only
    if borrowing_only(con):return None
    overlaps = [dict(r) for r in con.execute("SELECT * FROM reservations WHERE equipment_id=? "
                   "AND status IN ('รออนุมัติ','ยืนยันแล้ว') AND start_date<=? AND end_date>=?", (equipment['id'], end, start))]
    owned = next((r for r in overlaps if r['user_id']==actor_id and r['start_date']<=start and r['end_date']>=end), None)
    if owned and owned.get('document_path') and owned['status']=='รออนุมัติ':
        raise DomainError('คำขอจองนี้รอ Admin ตรวจเอกสารและยืนยันก่อนส่งคำขอยืม')
    if linked_id and (owned is None or owned['id'] != linked_id):
        raise DomainError("การจองที่เชื่อมกับคำขอนี้สิ้นสุดแล้ว กรุณาส่งคำขอใหม่")
    if overlaps and not owned and equipment['available_amount'] - amount < 1:
        raise DomainError("จำนวนไม่เพียงพอ เนื่องจากมีการจองในช่วงวันที่เลือก")
    return owned['id'] if owned else None

def request_borrow(actor_id, equipment_id, amount, start, end, purpose, database_path=DATABASE_PATH):
    start, end = validate_period(start, end)
    if type(amount) is not int or amount < 1:
        raise DomainError("จำนวนที่ยืมต้องเป็นจำนวนเต็มมากกว่า 0")
    if not str(purpose).strip():
        raise DomainError("กรุณาระบุวัตถุประสงค์")
    with database_connection(database_path) as con:
        con.execute("BEGIN IMMEDIATE")
        require_actor(con, actor_id)
        equipment = equipment_record(con, equipment_id)
        if equipment["status"] != "พร้อมใช้งาน" or amount > equipment["available_amount"]:
            raise DomainError("จำนวนอุปกรณ์พร้อมใช้ไม่เพียงพอ")
        linked = reservation_guard(con, actor_id, equipment, amount, start, end)
        transaction_id=con.execute("INSERT INTO borrow_transactions(user_id,equipment_id,amount,borrow_date,due_date,purpose,reservation_id) "
                           "VALUES(?,?,?,?,?,?,?)", (actor_id, equipment_id, amount, start, end, str(purpose).strip(), linked)).lastrowid
        from notifications import notify_admins
        notify_admins(con,transaction_id)
        return transaction_id

def decide_borrow(actor_id, transaction_id, approved, database_path=DATABASE_PATH, *, reason=''):
    with database_connection(database_path) as con:
        con.execute("BEGIN IMMEDIATE")
        actor=require_actor(con, actor_id, MANAGER_ROLES, allow_executive=True)
        row = transaction_record(con, transaction_id)
        if row["borrow_status"] != "รออนุมัติ":
            raise DomainError("รายการนี้ได้รับการพิจารณาแล้ว")
        if approved:
            if row.get('document_path'):
                from borrow_requests import required_document
                required_document(row.get('document_path',''))
            equipment = equipment_record(con, row["equipment_id"])
            if equipment["status"] != "พร้อมใช้งาน" or row["amount"] > equipment["available_amount"]:
                raise DomainError("จำนวนอุปกรณ์พร้อมใช้ไม่เพียงพอ กรุณาตรวจรายการใหม่")
            if row["due_date"] < today().isoformat():
                raise DomainError("คำขอนี้เลยกำหนดคืนแล้ว กรุณาส่งคำขอใหม่")
            linked = reservation_guard(con, row['user_id'], equipment, row['amount'], row['borrow_date'], row['due_date'], row['reservation_id'])
            if linked:
                con.execute("UPDATE reservations SET status='สิ้นสุดแล้ว' WHERE id=?", (linked,))
        from executive_approval import prepare_decision
        if prepare_decision(con,actor,[row],approved,reason):return
        con.execute("UPDATE borrow_transactions SET borrow_status=?,approved_by=?,approved_at=? WHERE id=?",
                    ("อนุมัติแล้ว" if approved else "ไม่อนุมัติ", actor_id, utc_now(), transaction_id))
        refresh_stock(con, row["equipment_id"])
        from notifications import notify_decision
        notify_decision(con,transaction_id,approved)

def reserve_equipment(actor_id, equipment_id, start, end, purpose, database_path=DATABASE_PATH,*,document_path=None):
    from borrowing_workflow import borrowing_only
    with database_connection(database_path) as con:
        if borrowing_only(con):raise DomainError('ใช้คำขอยืมและเลือกวันที่ต้องการใช้งานได้เลย ไม่ต้องจองแยก')
    start, end = validate_period(start, end)
    if not str(purpose).strip():
        raise DomainError("กรุณาระบุวัตถุประสงค์การจอง")
    if document_path is not None:
        from borrow_requests import required_document
        required_document(document_path)
    with database_connection(database_path) as con:
        con.execute("BEGIN IMMEDIATE")
        require_actor(con, actor_id)
        equipment = equipment_record(con, equipment_id)
        if equipment['status'] != 'พร้อมใช้งาน' or equipment['available_amount'] < 1:
            raise DomainError("ไม่มีจำนวนพร้อมใช้สำหรับจอง")
        if con.execute("SELECT 1 FROM reservations WHERE equipment_id=? AND status IN ('รออนุมัติ','ยืนยันแล้ว') "
                       "AND start_date<=? AND end_date>=?", (equipment_id, end, start)).fetchone():
            raise DomainError("อุปกรณ์นี้ถูกจองในช่วงเวลาดังกล่าวแล้ว")
        result=con.execute("INSERT INTO reservations(user_id,equipment_id,start_date,end_date,purpose,status,document_path) VALUES(?,?,?,?,?,?,?)",
                           (actor_id, equipment_id, start, end, str(purpose).strip(),'รออนุมัติ' if document_path is not None else 'ยืนยันแล้ว',document_path or '')).lastrowid
        if document_path is not None:
            for admin in con.execute("SELECT id FROM users WHERE role='admin' AND status='active'"):
                con.execute("INSERT OR IGNORE INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)",
                            (admin['id'],f"reservation:{result}:{admin['id']}",f'มีคำขอจอง #{result} พร้อม PDF รอตรวจเอกสาร',result,'reservation'))
        return result

def reservation_rows(actor_id, database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        actor = require_actor(con, actor_id)
        sql = ("SELECT r.*,e.equipment_name,e.equipment_code,u.full_name FROM reservations r "
               "JOIN equipment e ON e.id=r.equipment_id JOIN users u ON u.id=r.user_id ")
        params = ()
        if actor['role'] not in MANAGER_ROLES:
            sql += "WHERE r.user_id=? "
            params = (actor_id,)
        return [dict(r) for r in con.execute(sql + 'ORDER BY r.id DESC', params)]

def cancel_reservation(actor_id, reservation_id, database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        actor = require_actor(con, actor_id)
        row = con.execute('SELECT * FROM reservations WHERE id=?', (reservation_id,)).fetchone()
        if row is None or (row['user_id']!=actor_id and actor['role'] not in MANAGER_ROLES):
            raise DomainError('ไม่มีสิทธิ์ยกเลิกการจองนี้')
        if row['status'] not in {'รออนุมัติ','ยืนยันแล้ว'}:
            raise DomainError('การจองนี้สิ้นสุดแล้ว')
        con.execute("UPDATE reservations SET status='ยกเลิก' WHERE id=?", (reservation_id,))

def cancel_borrow(actor_id, transaction_id, database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        con.execute("BEGIN IMMEDIATE")
        actor = require_actor(con, actor_id)
        if actor.get('executive_title'):raise DomainError('ผู้บริหารไม่มีสิทธิ์ยกเลิกหรือแก้ไขคำขอยืม')
        row = transaction_record(con, transaction_id)
        if row["user_id"] != actor_id and actor["role"] not in MANAGER_ROLES:
            raise DomainError("ไม่มีสิทธิ์ยกเลิกรายการนี้")
        if row["borrow_status"] not in {"รออนุมัติ", "อนุมัติแล้ว"}:
            raise DomainError("ยกเลิกได้เฉพาะรายการที่ยังไม่ได้ส่งมอบ")
        con.execute("UPDATE borrow_transactions SET borrow_status='ยกเลิก' WHERE id=?", (transaction_id,))
        refresh_stock(con, row["equipment_id"])

def handoff_borrow(actor_id, transaction_id, condition, image, database_path=DATABASE_PATH):
    validate_evidence(image)
    if condition not in {"ปกติ", "มีรอยเล็กน้อย", "มีตำหนิ"}:
        raise DomainError("สภาพอุปกรณ์ก่อนยืมไม่ถูกต้อง")
    with database_connection(database_path) as con:
        con.execute("BEGIN IMMEDIATE")
        require_actor(con, actor_id, MANAGER_ROLES)
        row = transaction_record(con, transaction_id)
        if row["borrow_status"] != "อนุมัติแล้ว":
            raise DomainError("ส่งมอบได้เฉพาะรายการที่อนุมัติแล้ว")
        if row["borrow_date"] > today().isoformat() or row["due_date"] < today().isoformat():
            raise DomainError("ยังไม่ถึงวันที่ยืม หรือเลยกำหนดคืนแล้ว")
        from fines import configured_rate
        con.execute("UPDATE borrow_transactions SET borrow_status='กำลังยืม',condition_before=?,before_image=?,fine_rate_cents=? WHERE id=?",
                    (condition, image, configured_rate(con), transaction_id))

def request_return(actor_id, transaction_id, condition, image, note="", database_path=DATABASE_PATH):
    """ผู้ยืมแจ้งคืนได้ทุกวันหลังรับอุปกรณ์ รวมก่อนกำหนด; เจ้าหน้าที่ต้องตรวจรับก่อนคืนสต็อก."""
    validate_evidence(image)
    if condition not in {"ปกติ", "ชำรุด", "สูญหาย"}:
        raise DomainError("สภาพหลังใช้งานไม่ถูกต้อง")
    with database_connection(database_path) as con:
        con.execute("BEGIN IMMEDIATE")
        actor = require_actor(con, actor_id)
        row = transaction_record(con, transaction_id)
        if row["user_id"] != actor_id and actor["role"] not in MANAGER_ROLES:
            raise DomainError("คุณไม่มีสิทธิ์คืนรายการของผู้ใช้อื่น")
        if row["borrow_status"] not in {"กำลังยืม", "เกินกำหนด"}:
            raise DomainError("รายการนี้ไม่ได้กำลังยืม หรือส่งคำขอคืนแล้ว")
        con.execute("UPDATE borrow_transactions SET borrow_status='รอตรวจสอบการคืน',condition_after=?,after_image=?,"
                    "return_note=?,return_requested_at=? WHERE id=?", (condition, image, str(note).strip(), utc_now(), transaction_id))
        from notifications import notify_return_requested
        notify_return_requested(con,transaction_id)

def confirm_return(actor_id, transaction_id, database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        con.execute("BEGIN IMMEDIATE")
        require_actor(con, actor_id, MANAGER_ROLES)
        row = transaction_record(con, transaction_id)
        if row["borrow_status"] != "รอตรวจสอบการคืน":
            raise DomainError("ยืนยันได้เฉพาะรายการที่รอตรวจสอบการคืน")
        validate_evidence(row["after_image"])
        if row["condition_after"] in {"ชำรุด", "สูญหาย"}:
            con.execute("UPDATE equipment SET unavailable_amount=unavailable_amount+? WHERE id=?",
                        (row["amount"], row["equipment_id"]))
            con.execute("INSERT INTO maintenance(equipment_id,issue,repair_detail,status,amount,stock_locked,source_transaction_id,image,sent_date) "
                        "VALUES(?,?,?,?,?,1,?,?,?)", (row["equipment_id"], f"พบ{row['condition_after']}จากการคืน #{transaction_id}",
                        row["return_note"], "ไม่สามารถซ่อมได้" if row["condition_after"] == "สูญหาย" else "รอตรวจสอบ", row["amount"], transaction_id,row['after_image'],today().isoformat()))
        from fines import fine_estimate
        fine = fine_estimate(row)
        con.execute("UPDATE borrow_transactions SET borrow_status='คืนแล้ว',return_date=?,fine_days=?,fine_amount_cents=?,fine_status=? WHERE id=?",
                    (today().isoformat(), fine['days'], fine['amount_cents'], 'ค้างชำระ' if fine['amount_cents'] else 'ไม่มีค่าปรับ', transaction_id))
        refresh_stock(con, row["equipment_id"])
        from notifications import notify_return_confirmed
        notify_return_confirmed(con,transaction_id)

def validate_cost(value):
    if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:
        raise DomainError('ค่าใช้จ่ายต้องเป็นตัวเลขไม่ติดลบ')
    return float(value)

def maintenance_rows(actor_id,database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        require_actor(con,actor_id,MANAGER_ROLES)
        return [dict(r) for r in con.execute('SELECT m.*,e.equipment_name,e.equipment_code FROM maintenance m JOIN equipment e ON e.id=m.equipment_id ORDER BY m.id DESC')]

def create_maintenance(actor_id,equipment_id,amount,issue,detail='',image=None,cost=0,sent_date=None,use_blocked=False,database_path=DATABASE_PATH):
    cost=validate_cost(cost)
    sent_date,_=validate_period(sent_date or today(),sent_date or today(),future=False)
    if sent_date>today().isoformat() or type(amount) is not int or amount<1 or not str(issue).strip():
        raise DomainError('กรุณาระบุอาการ จำนวนมากกว่า 0 และวันส่งซ่อมที่ไม่ใช่วันในอนาคต')
    if image:
        validate_evidence(image)
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        require_actor(con,actor_id,MANAGER_ROLES)
        equipment=equipment_record(con,equipment_id)
        if equipment['status']=='ปิดใช้งาน':
            raise DomainError('อุปกรณ์ปิดใช้งานแล้ว')
        if use_blocked:
            tracked=con.execute('SELECT COALESCE(SUM(amount),0) FROM maintenance WHERE equipment_id=? AND stock_locked=1',(equipment_id,)).fetchone()[0]
            if amount>equipment['unavailable_amount']-tracked:
                raise DomainError('จำนวนที่ไม่พร้อมใช้ถูกเชื่อมกับงานซ่อมแล้ว หรือจำนวนไม่เพียงพอ')
        else:
            if amount>equipment['available_amount']:
                raise DomainError('จำนวนพร้อมใช้ไม่เพียงพอสำหรับแจ้งซ่อม')
            reserved=con.execute("SELECT 1 FROM reservations WHERE equipment_id=? AND status IN ('รออนุมัติ','ยืนยันแล้ว') AND end_date>=?",(equipment_id,today().isoformat())).fetchone()
            if reserved and equipment['available_amount']-amount<1:
                raise DomainError('มีการจองอุปกรณ์นี้ กรุณาจัดการการจองก่อนส่งซ่อม')
            con.execute('UPDATE equipment SET available_amount=available_amount-?,unavailable_amount=unavailable_amount+? WHERE id=?',(amount,amount,equipment_id))
        con.execute("UPDATE equipment SET status='ซ่อมบำรุง' WHERE id=?",(equipment_id,))
        result=con.execute('INSERT INTO maintenance(equipment_id,amount,issue,repair_detail,image,repair_cost,sent_date,stock_locked) VALUES(?,?,?,?,?,?,?,1)',
                           (equipment_id,amount,str(issue).strip(),str(detail).strip(),image,cost,sent_date)).lastrowid
        refresh_stock(con,equipment_id)
        return result

def update_maintenance(actor_id,maintenance_id,status,detail,cost,completed_date=None,database_path=DATABASE_PATH):
    cost=validate_cost(cost)
    if status not in {'รอตรวจสอบ','กำลังซ่อม','ซ่อมเสร็จ','ไม่สามารถซ่อมได้'}:
        raise DomainError('สถานะงานซ่อมไม่ถูกต้อง')
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        require_actor(con,actor_id,MANAGER_ROLES)
        row=con.execute('SELECT * FROM maintenance WHERE id=?',(maintenance_id,)).fetchone()
        if row is None or row['status'] in {'ซ่อมเสร็จ','ไม่สามารถซ่อมได้'}:
            raise DomainError('งานซ่อมนี้สิ้นสุดแล้ว หรือไม่พบรายการ')
        finished=status in {'ซ่อมเสร็จ','ไม่สามารถซ่อมได้'}
        day=None
        if finished:
            _,day=validate_period(row['sent_date'] or row['created_at'][:10],completed_date or today(),future=False)
            if day>today().isoformat():
                raise DomainError('วันซ่อมเสร็จต้องไม่อยู่ในอนาคต')
        locked=row['stock_locked']
        if status=='ซ่อมเสร็จ' and locked:
            equipment=equipment_record(con,row['equipment_id'])
            if equipment['unavailable_amount']<row['amount']:
                raise DomainError('จำนวนงานซ่อมไม่สอดคล้องกับจำนวนอุปกรณ์')
            con.execute('UPDATE equipment SET unavailable_amount=unavailable_amount-? WHERE id=?',(row['amount'],row['equipment_id']))
            locked=0
        con.execute('UPDATE maintenance SET status=?,repair_detail=?,repair_cost=?,completed_at=?,repaired_date=?,stock_locked=? WHERE id=?',
                    (status,str(detail).strip(),cost,utc_now() if finished else None,day,locked,maintenance_id))
        refresh_stock(con,row['equipment_id'])

def held_amount(connection, equipment_id):
    marks = ",".join("?" for _ in HELD_STATUSES)
    return connection.execute(f"SELECT COALESCE(SUM(amount),0) FROM borrow_transactions WHERE equipment_id=? "
                              f"AND borrow_status IN ({marks})", (equipment_id, *HELD_STATUSES)).fetchone()[0]

def equipment_record(connection, equipment_id):
    row = connection.execute("SELECT * FROM equipment WHERE id=?", (equipment_id,)).fetchone()
    if row is None:
        raise DomainError("ไม่พบอุปกรณ์")
    return dict(row)

def refresh_stock(connection, equipment_id):
    equipment = equipment_record(connection, equipment_id)
    available = equipment["total_amount"] - equipment["unavailable_amount"] - held_amount(connection, equipment_id)
    if available < 0:
        raise DomainError("จำนวนอุปกรณ์ไม่สอดคล้องกับรายการยืม")
    status = equipment["status"]
    if status != "ปิดใช้งาน":
        if available > 0:
            status = "พร้อมใช้งาน"
        elif equipment["unavailable_amount"]:
            status = "ซ่อมบำรุง" if status == "ซ่อมบำรุง" else "ชำรุด"
        else:
            status = "ถูกยืม" if held_amount(connection, equipment_id) else "พร้อมใช้งาน"
    connection.execute("UPDATE equipment SET available_amount=?,status=? WHERE id=?", (available, status, equipment_id))

def save_equipment(actor_id, values, equipment_id=None, database_path=DATABASE_PATH):
    values = dict(values)
    for field in ("equipment_code", "equipment_name", "category", "storage_location"):
        values[field] = str(values.get(field, "")).strip()
        if not values[field]:
            raise DomainError("กรุณากรอกรหัส ชื่อ หมวดหมู่ และสถานที่จัดเก็บให้ครบ")
    total = values.get("total_amount")
    if type(total) is not int or total < 0:
        raise DomainError("จำนวนอุปกรณ์ต้องเป็นจำนวนเต็มที่ไม่ติดลบ")
    state = values.get("status", "พร้อมใช้งาน")
    if state not in {"พร้อมใช้งาน", "ชำรุด", "ซ่อมบำรุง", "ปิดใช้งาน"}:
        raise DomainError("สถานะอุปกรณ์ไม่ถูกต้อง")
    with database_connection(database_path) as con:
        con.execute("BEGIN IMMEDIATE")
        require_actor(con, actor_id, {"admin"})
        old = equipment_record(con, equipment_id) if equipment_id else None
        held = held_amount(con, equipment_id) if equipment_id else 0
        blocked = old["unavailable_amount"] if old else 0
        if total < held + blocked:
            raise DomainError("จำนวนทั้งหมดต้องไม่น้อยกว่าจำนวนที่ถูกยืมและจำนวนที่ไม่พร้อมใช้")
        if state == "ปิดใช้งาน" and held:
            raise DomainError("อุปกรณ์นี้ยังมีรายการยืม ต้องคืนหรือยกเลิกการอนุมัติก่อนปิดใช้งาน")
        if state in {"ชำรุด", "ซ่อมบำรุง"}:
            blocked = total - held
        available = total - held - blocked
        reserved=con.execute("SELECT 1 FROM reservations WHERE equipment_id=? AND status IN ('รออนุมัติ','ยืนยันแล้ว') AND end_date>=?",(equipment_id,today().isoformat())).fetchone() if equipment_id else None
        if reserved and (available<1 or state=='ปิดใช้งาน'):
            raise DomainError('ยังมีการจอง ต้องยกเลิกการจองก่อนลดจำนวนหรือปิดใช้งาน')
        params = (values["equipment_code"], values["equipment_name"], values["category"],
                  values.get("description", "").strip(), total, available,
                  values.get("image") or (old["image"] if old else "assets/equipment/placeholder.png"),
                  values["storage_location"], state, blocked)
        if equipment_id:
            con.execute("UPDATE equipment SET equipment_code=?,equipment_name=?,category=?,description=?,total_amount=?,"
                        "available_amount=?,image=?,storage_location=?,status=?,unavailable_amount=? WHERE id=?", (*params, equipment_id))
        else:
            equipment_id = con.execute("INSERT INTO equipment(equipment_code,equipment_name,category,description,total_amount,"
                                       "available_amount,image,storage_location,status,unavailable_amount) VALUES(?,?,?,?,?,?,?,?,?,?)", params).lastrowid
        refresh_stock(con, equipment_id)
    return equipment_id

def deactivate_equipment(actor_id, equipment_id, confirmed=False, database_path=DATABASE_PATH):
    if not confirmed:
        raise DomainError("กรุณายืนยันการปิดใช้งาน")
    with database_connection(database_path) as con:
        con.execute("BEGIN IMMEDIATE")
        require_actor(con, actor_id, {"admin"})
        equipment_record(con, equipment_id)
        if held_amount(con, equipment_id):
            raise DomainError("ยังมีรายการยืมที่ไม่สิ้นสุด จึงปิดใช้งานไม่ได้")
        if con.execute("SELECT 1 FROM reservations WHERE equipment_id=? AND status IN ('รออนุมัติ','ยืนยันแล้ว')", (equipment_id,)).fetchone():
            raise DomainError("ยังมีการจองที่ไม่สิ้นสุด จึงปิดใช้งานไม่ได้")
        con.execute("UPDATE equipment SET status='ปิดใช้งาน' WHERE id=?", (equipment_id,))

def catalog(search="", status="ทั้งหมด", database_path=DATABASE_PATH, include_inactive=False):
    rows = query_rows("SELECT e.*,EXISTS(SELECT 1 FROM reservations r WHERE r.equipment_id=e.id AND r.status IN ('รออนุมัติ','ยืนยันแล้ว') AND r.end_date>=?) has_reservation "
                      "FROM equipment e ORDER BY equipment_name,equipment_code",(today().isoformat(),),database_path)
    phrase = search.strip().casefold()
    return [row for row in rows if (include_inactive or row["status"] != "ปิดใช้งาน")
            and (status == "ทั้งหมด" or row["status"] == status or (status=='จอง' and row['has_reservation']))
            and (not phrase or any(phrase in str(row[field]).casefold() for field in ("equipment_name", "equipment_code", "category")))]
