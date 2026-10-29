# หน้าที่: แจ้งเตือนคำขอ กำหนดคืน และผลตรวจสลิป
"""STEP 17: แจ้งเตือนรายผู้ใช้ บันทึกและป้องกันการสร้างซ้ำ."""
from datetime import date
from html import escape
import streamlit as st
from common import OUT_STATUSES, today, require_actor, utc_now, action, DomainError, MANAGER_ROLES
from database import DATABASE_PATH, database_connection

def notify_admins(connection,transaction_id):
    row=connection.execute('SELECT b.*,u.full_name,e.equipment_name FROM borrow_transactions b JOIN users u ON u.id=b.user_id JOIN equipment e ON e.id=b.equipment_id WHERE b.id=?',(transaction_id,)).fetchone()
    if row is None:return
    if row['review_stage']=='รออนุมัติสุดท้าย':return
    group=row['request_group']
    if group:
        items=connection.execute('SELECT COUNT(*) total,SUM(amount) amount,MIN(id) reference FROM borrow_transactions WHERE request_group=?',(group,)).fetchone()
        description=f"{items['total']} รายการ รวม {items['amount']} ชิ้น"
        reference=items['reference'];key='request:'+group
    else:
        description=f"{row['equipment_name']} {row['amount']} ชิ้น"
        reference=row['id'];key='borrow:'+str(reference)
    message=f"{row['full_name']} ส่งคำขอยืม {description} · รอพิจารณา"
    for admin in connection.execute("SELECT id FROM users WHERE role='admin' AND status='active' AND executive_title=''").fetchall():
        connection.execute("INSERT OR IGNORE INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)",
                           (admin['id'],f"admin:{admin['id']}:{key}",message,reference,'approvals'))

def notify_decision(connection,transaction_id,approved):
    row=connection.execute('SELECT b.user_id,b.decision_note,e.equipment_name FROM borrow_transactions b JOIN equipment e ON e.id=b.equipment_id WHERE b.id=?',(transaction_id,)).fetchone()
    if row is None:return
    event='approved' if approved else 'rejected'
    message=(f"รายการยืม {row['equipment_name']} ของคุณได้รับการอนุมัติแล้ว" if approved else f"คำขอยืม {row['equipment_name']} ถูกปฏิเสธ")
    if row['decision_note']:message+=' · '+row['decision_note']
    connection.execute('INSERT OR IGNORE INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                       (row['user_id'],f'borrow:{transaction_id}:{event}',message,transaction_id,'history'))

def notify_return_requested(connection,transaction_id):
    """แจ้งเจ้าหน้าที่ทันทีในธุรกรรมเดียวกับการแจ้งคืน."""
    row=connection.execute('SELECT b.user_id,u.full_name,e.equipment_name FROM borrow_transactions b JOIN users u ON u.id=b.user_id JOIN equipment e ON e.id=b.equipment_id WHERE b.id=?',(transaction_id,)).fetchone()
    if row is None:return
    for manager in connection.execute("SELECT id FROM users WHERE status='active' AND role IN ('admin','staff','teacher') AND executive_title='' AND id<>?",(row['user_id'],)).fetchall():
        connection.execute('INSERT OR IGNORE INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                           (manager['id'],f'return-requested:{transaction_id}:{manager["id"]}',f'{row["full_name"]} แจ้งคืน {row["equipment_name"]} · รอเจ้าหน้าที่ตรวจรับ',transaction_id,'return'))


def notify_return_confirmed(connection,transaction_id):
    row=connection.execute('SELECT b.user_id,b.fine_amount_cents,e.equipment_name FROM borrow_transactions b JOIN equipment e ON e.id=b.equipment_id WHERE b.id=?',(transaction_id,)).fetchone()
    if row is None:return
    fine=row['fine_amount_cents']
    message=f'เจ้าหน้าที่ตรวจรับคืน {row["equipment_name"]} เรียบร้อยแล้ว'
    if fine:message+=f' · มีค่าปรับ {fine/100:,.2f} บาท กรุณาแนบสลิปในหน้าค่าปรับ'
    connection.execute('INSERT OR IGNORE INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                       (row['user_id'],f'return-confirmed:{transaction_id}',message,transaction_id,'fines' if fine else 'history'))


def sync_notifications(database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        rows=con.execute("""SELECT b.*,e.equipment_name FROM borrow_transactions b JOIN equipment e ON e.id=b.equipment_id
            WHERE b.borrow_status IN ('รออนุมัติ','อนุมัติแล้ว','ไม่อนุมัติ','กำลังยืม','เกินกำหนด','รอตรวจสอบการคืน')
            OR (b.approved_at IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM notifications n WHERE n.user_id=b.user_id AND n.event_key='borrow:'||b.id||':approved'))""").fetchall()
        for row in rows:
            if row['borrow_status']=='รออนุมัติ':notify_admins(con,row['id'])
            events=[]
            name=row['equipment_name']
            if row['borrow_status']=='อนุมัติแล้ว' or (row['approved_at'] and row['borrow_status'] not in {'รออนุมัติ','ไม่อนุมัติ'}):
                notify_decision(con,row['id'],True)
            elif row['borrow_status']=='ไม่อนุมัติ':
                notify_decision(con,row['id'],False)
            if row['borrow_status'] in OUT_STATUSES:
                remaining=(date.fromisoformat(row['due_date'])-today()).days
                if remaining==0:
                    events.append((f'due_today:{row["due_date"]}',f'{name} ต้องคืนภายในวันนี้'))
                elif remaining==1:
                    events.append((f'due_tomorrow:{row["due_date"]}',f'{name} เหลือเวลาอีก 1 วันก่อนครบกำหนด'))
                elif remaining<0:
                    events.append((f'overdue:{row["due_date"]}',f'{name} เกินกำหนดคืน กรุณาติดต่อเจ้าหน้าที่'))
            for event,message in events:
                con.execute('INSERT OR IGNORE INTO notifications(user_id,event_key,message) VALUES(?,?,?)',
                            (row['user_id'],f'borrow:{row["id"]}:{event}',message))

def notification_rows(actor_id,database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        require_actor(con,actor_id)
        return [dict(r) for r in con.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC',(actor_id,))]

def mark_read(actor_id,notification_id=None,database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        require_actor(con,actor_id)
        if notification_id is None:
            con.execute('UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL',(utc_now(),actor_id))
        else:
            result=con.execute('UPDATE notifications SET read_at=? WHERE user_id=? AND id=?',(utc_now(),actor_id,notification_id))
            if result.rowcount!=1:
                raise DomainError('ไม่พบแจ้งเตือนของคุณ')

def open_fine_notification(actor_id, notification_id, database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        actor=require_actor(con,actor_id)
        notice=con.execute("SELECT * FROM notifications WHERE id=? AND user_id=? AND target_page='fines'",(notification_id,actor_id)).fetchone()
        loan=con.execute('SELECT user_id FROM borrow_transactions WHERE id=?',(notice['reference_id'],)).fetchone() if notice else None
        if not loan or (loan['user_id']!=actor_id and actor['role'] not in MANAGER_ROLES):
            raise DomainError('ไม่พบรายการค่าปรับที่คุณมีสิทธิ์ดู')
        con.execute('UPDATE notifications SET read_at=? WHERE id=?',(utc_now(),notification_id))
        return notice['reference_id']

@st.fragment(run_every=15)
def render_notifications(user,database_path=DATABASE_PATH):
    from auth import get_current_user
    current=get_current_user(database_path)
    if current is None:
        if st.button('เข้าสู่ระบบใหม่',key='notification_session_expired'):st.rerun(scope='app')
        return
    user=current
    # ผลอนุมัติถูกสร้างพร้อมธุรกรรมแล้ว ไม่สแกนประวัติทั้งหมดทุก 15 วินาที
    day_key=today().isoformat()
    if st.session_state.get('_notice_sync_day')!=day_key:
        sync_notifications(database_path)
        st.session_state['_notice_sync_day']=day_key
    rows=notification_rows(user['id'],database_path)
    count=sum(r['read_at'] is None for r in rows)
    with st.popover(f'แจ้งเตือน ({count})',icon=':material/notifications:',type='tertiary'):
        if not rows:
            st.info('ยังไม่มีแจ้งเตือน')
        for row in rows[:30]:
            if row['read_at'] is None:
                st.html('<article class="sb-notice is-unread"><span class="sb-notice-badge">ยังไม่อ่าน</span><p>'+escape(row['message'])+'</p></article>')
            else:
                st.html('<article class="sb-notice"><p>'+escape(row['message'])+'</p></article>')
            if row.get('reference_id') and row.get('target_page'):
                if st.button('เปิดรายการ',key=f'notification_open_{row["id"]}',width='stretch'):
                    if row['target_page']=='fines':
                        try:
                            open_fine_notification(user['id'],row['id'],database_path)
                        except DomainError as error:
                            st.info(str(error))
                        else:
                            from navigation import navigate_to
                            navigate_to('fines');st.rerun(scope='app')
                        continue
                    if row['target_page']=='reservation':
                        with database_connection(database_path) as con:
                            reservation=con.execute('SELECT user_id FROM reservations WHERE id=?',(row['reference_id'],)).fetchone()
                        if reservation and (user['role']=='admin' or reservation['user_id']==user['id']):
                            from navigation import navigate_to
                            mark_read(user['id'],row['id'],database_path)
                            st.session_state['reservation_focus_id']=row['reference_id']
                            navigate_to('reservation');st.rerun(scope='app')
                        else:st.info('ไม่พบรายการจองที่คุณมีสิทธิ์ดู')
                        continue
                    with database_connection(database_path) as con:
                        loan=con.execute('SELECT borrow_status FROM borrow_transactions WHERE id=?',(row['reference_id'],)).fetchone()
                    if loan:
                        from loan_workspace import open_loan_task
                        if user.get('executive_title') in {'director','deputy'}:
                            mark_read(user['id'],row['id'],database_path)
                            st.session_state['executive_section']='คำขอรออนุมัติ' if loan['borrow_status']=='รออนุมัติ' else 'ประวัติการพิจารณา'
                            open_loan_task(row['reference_id'],'approvals',loan['borrow_status'])
                            st.rerun(scope='app')
                        target='approvals' if row['target_page']=='approvals' and user['role'] in MANAGER_ROLES and loan['borrow_status'] in {'รออนุมัติ','อนุมัติแล้ว'} else 'return' if row['target_page']=='return' and user['role'] in MANAGER_ROLES and loan['borrow_status']=='รอตรวจสอบการคืน' else 'history'
                        mark_read(user['id'],row['id'],database_path)
                        open_loan_task(row['reference_id'],target,loan['borrow_status'])
                        st.rerun(scope='app')
                    else:st.info('รายการนี้ไม่มีอยู่แล้ว')
        if count and st.button('ทำเครื่องหมายว่าอ่านทั้งหมดแล้ว'):
            action(mark_read,user['id'],database_path=database_path,success='อ่านแจ้งเตือนทั้งหมดแล้ว')
