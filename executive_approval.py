# หน้าที่: ตรวจเอกสารก่อนส่ง ผอ หรือรอง ผอ อนุมัติสุดท้าย
from common import DomainError,utc_now,require_actor,MANAGER_ROLES
from database import DATABASE_PATH,database_connection

TITLES={'':'ไม่มี','director':'ผู้อำนวยการ','deputy':'รองผู้อำนวยการ'}
FINAL_STAGE='รออนุมัติสุดท้าย'

def record_event(con,actor,row,action,reason=''):
    """เก็บชื่อและตำแหน่งขณะดำเนินการ เพื่อคงประวัติแม้เปลี่ยนบัญชีภายหลัง."""
    return con.execute('INSERT INTO approval_events(transaction_id,actor_id,actor_name,actor_title,action,reason,created_at) VALUES(?,?,?,?,?,?,?)',
        (row['id'],actor['id'],actor['full_name'],actor.get('executive_title',''),action,reason,utc_now())).lastrowid


def require_executive(con,actor_id):
    actor=require_actor(con,actor_id,MANAGER_ROLES,allow_executive=True)
    if actor.get('executive_title') not in {'director','deputy'}:
        raise DomainError('เฉพาะ ผอ. หรือรอง ผอ. เท่านั้น')
    return actor


def decision_reason(reason,required=False):
    value=str(reason or '').strip()
    if required and not value:raise DomainError('กรุณาระบุเหตุผลเพื่อแจ้งผู้เกี่ยวข้อง')
    if len(value)>1000:raise DomainError('เหตุผลต้องไม่เกิน 1,000 ตัวอักษร')
    return value


def prepare_decision(con,actor,rows,approved,reason=''):
    """คืน True เมื่อเป็นการส่งต่อ ไม่ใช่การอนุมัติสุดท้าย ทุกงานอยู่ใน transaction เดียวกัน"""
    stages={r.get('review_stage','') for r in rows}
    if len(stages)!=1:raise DomainError('รายการอยู่คนละขั้นตอน กรุณาพิจารณาแยกทีละรายการ')
    final=stages=={FINAL_STAGE}
    executive=actor.get('executive_title','') in {'director','deputy'}
    if executive and any(row['user_id']==actor['id'] for row in rows):
        raise DomainError('ผู้บริหารไม่สามารถพิจารณาคำขอของตนเองได้')
    if final and not executive:
        raise DomainError('ขั้นสุดท้ายต้องให้ผู้อำนวยการหรือรองผู้อำนวยการอนุมัติ')
    if not final and executive:
        raise DomainError('กรุณาให้เจ้าหน้าที่ตรวจเอกสารและส่งต่อก่อนอนุมัติสุดท้าย')
    timestamp=utc_now()
    reason=decision_reason(reason,required=executive and not approved)
    if not approved:
        for row in rows:
            event=record_event(con,actor,row,'rejected',reason)
            con.execute("UPDATE borrow_transactions SET review_stage='ไม่อนุมัติ',decision_note=? WHERE id=?",(reason,row['id']))
            if executive:
                for manager in con.execute("SELECT id FROM users WHERE status='active' AND role IN ('admin','staff','teacher') AND executive_title='' "):
                    con.execute('INSERT INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                        (manager['id'],f'final-rejected:{event}:{manager["id"]}',f'คำขอ #{row["id"]} ไม่อนุมัติ: {reason}',row['id'],'approvals'))
        return False
    if final:
        for row in rows:
            if not row.get('document_reviewed_by'):raise DomainError('ยังไม่ได้ตรวจเอกสารรอบแรก')
            if row['document_reviewed_by']==actor['id']:raise DomainError('ผู้ตรวจเอกสารกับผู้อนุมัติสุดท้ายต้องเป็นคนละบัญชี')
            con.execute("UPDATE borrow_transactions SET review_stage='อนุมัติแล้ว',final_approved_by=?,final_approved_at=? WHERE id=?",(actor['id'],timestamp,row['id']))
            con.execute('UPDATE borrow_transactions SET decision_note=? WHERE id=?',(reason,row['id']))
            event=record_event(con,actor,row,'approved',reason)
            for manager in con.execute("SELECT id FROM users WHERE status='active' AND role IN ('admin','staff','teacher') AND executive_title='' "):
                con.execute('INSERT INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                    (manager['id'],f'final-approved:{event}:{manager["id"]}',f'คำขอ #{row["id"]} อนุมัติแล้ว รอนัดส่งมอบอุปกรณ์',row['id'],'approvals'))
        return False
    executives=con.execute("SELECT id FROM users WHERE status='active' AND role IN ('admin','staff','teacher') AND executive_title IN ('director','deputy')").fetchall()
    if not executives:raise DomainError('ยังไม่มีบัญชี ผอ. หรือรอง ผอ. ที่ใช้งานได้ กรุณาให้ Admin กำหนดสิทธิ์ในเมนูผู้ใช้งาน')
    for row in rows:
        con.execute('UPDATE borrow_transactions SET review_stage=?,document_reviewed_by=?,document_reviewed_at=? WHERE id=?',(FINAL_STAGE,actor['id'],timestamp,row['id']))
        con.execute("UPDATE borrow_transactions SET decision_note='' WHERE id=?",(row['id'],))
        event=record_event(con,actor,row,'reviewed',reason)
        # รอบแรกคงรหัสแจ้งเตือนเดิม รอบส่งกลับใช้รหัสรอบใหม่เพื่อไม่ถูกกลืนด้วย UNIQUE
        repeat=con.execute("SELECT 1 FROM approval_events WHERE transaction_id=? AND action='returned' LIMIT 1",(row['id'],)).fetchone()
        suffix=f':{event}' if repeat else ''
        for executive in executives:
            con.execute('INSERT OR IGNORE INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                        (executive['id'],f'final-review:{row["id"]}:{executive["id"]}{suffix}',f'คำขอยืม #{row["id"]} ผ่านการตรวจเอกสาร รออนุมัติสุดท้าย',row['id'],'approvals'))
        con.execute('INSERT OR IGNORE INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                    (row['user_id'],f'document-reviewed:{row["id"]}{suffix}',f'คำขอยืม #{row["id"]} ผ่านการตรวจเอกสารแล้ว รอ ผอ. หรือรอง ผอ. อนุมัติสุดท้าย',row['id'],'history'))
    return True


def return_for_review(actor_id,transaction_id,reason,database_path=DATABASE_PATH,*,whole_group=False):
    """ส่งกลับเฉพาะคำขอที่รออนุมัติสุดท้าย ไม่ยกเลิก ไม่กันสต็อก และเก็บรอบตรวจเดิม."""
    reason=decision_reason(reason,required=True)
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        actor=require_executive(con,actor_id)
        row=con.execute('SELECT * FROM borrow_transactions WHERE id=?',(transaction_id,)).fetchone()
        if row is None:raise DomainError('ไม่พบคำขอ')
        rows=[dict(row)]
        if whole_group and row['request_group']:
            rows=[dict(r) for r in con.execute('SELECT * FROM borrow_transactions WHERE request_group=?',(row['request_group'],))]
        if any(r['borrow_status']!='รออนุมัติ' or r['review_stage']!=FINAL_STAGE for r in rows):
            raise DomainError('ส่งกลับได้เฉพาะคำขอที่รออนุมัติสุดท้าย กรุณาโหลดรายการใหม่')
        if any(r['user_id']==actor_id for r in rows):raise DomainError('ผู้บริหารไม่สามารถพิจารณาคำขอของตนเองได้')
        for r in rows:
            event=record_event(con,actor,r,'returned',reason)
            con.execute("UPDATE borrow_transactions SET review_stage='ส่งกลับตรวจเพิ่ม',decision_note=?,document_reviewed_by=NULL,document_reviewed_at=NULL WHERE id=?",(reason,r['id']))
            for manager in con.execute("SELECT id FROM users WHERE status='active' AND role IN ('admin','staff','teacher') AND executive_title='' "):
                con.execute('INSERT INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                    (manager['id'],f'review-returned:{event}:{manager["id"]}',f'ผู้บริหารส่งคำขอ #{r["id"]} กลับให้ตรวจเพิ่ม: {reason}',r['id'],'approvals'))
            con.execute('INSERT INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                (r['user_id'],f'review-returned:{event}:borrower',f'คำขอ #{r["id"]} อยู่ระหว่างตรวจเพิ่มเติม: {reason}',r['id'],'history'))


def approval_history(actor_id,database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        require_executive(con,actor_id)
        return [dict(r) for r in con.execute('''SELECT a.*,b.equipment_id,b.request_group,b.borrow_status,
            e.equipment_name,u.full_name AS borrower_name FROM approval_events a
            JOIN borrow_transactions b ON b.id=a.transaction_id JOIN equipment e ON e.id=b.equipment_id
            JOIN users u ON u.id=b.user_id ORDER BY a.created_at DESC,a.id DESC''')]


def executive_overview(actor_id,database_path=DATABASE_PATH):
    from common import today
    with database_connection(database_path) as con:
        require_executive(con,actor_id)
        loans=dict(con.execute('''SELECT COUNT(CASE WHEN borrow_status='รออนุมัติ' AND review_stage='รออนุมัติสุดท้าย' THEN 1 END) pending,
            COALESCE(SUM(CASE WHEN borrow_status IN ('กำลังยืม','เกินกำหนด','รอตรวจสอบการคืน') THEN amount ELSE 0 END),0) borrowed,
            COUNT(CASE WHEN borrow_status IN ('กำลังยืม','เกินกำหนด','รอตรวจสอบการคืน') AND due_date<? THEN 1 END) overdue,
            COUNT(CASE WHEN borrow_status='รอตรวจสอบการคืน' THEN 1 END) awaiting_return
            FROM borrow_transactions''',(today().isoformat(),)).fetchone())
        loans['unavailable']=con.execute('SELECT COALESCE(SUM(unavailable_amount),0) FROM equipment').fetchone()[0]
        loans['equipment']=[dict(r) for r in con.execute('SELECT category,SUM(total_amount) total,SUM(available_amount) available,SUM(unavailable_amount) unavailable FROM equipment GROUP BY category ORDER BY category')]
        return loans
