# หน้าที่: เชื่อมข้อมูลจองเดิมเป็นขั้นตอนยืมเดียว
"""Unify future bookings with borrowing while retaining legacy booking records."""
from database import DATABASE_PATH,database_connection
from common import today,utc_now

def borrowing_only(con):
    row=con.execute("SELECT value FROM app_settings WHERE key='borrowing_only'").fetchone()
    return bool(row and row['value']=='yes')

def enable_borrowing_only(database_path=DATABASE_PATH):
    from services import refresh_stock
    from notifications import notify_admins
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        if borrowing_only(con):return 0
        converted=0
        admin=con.execute("SELECT id FROM users WHERE role='admin' AND status='active' ORDER BY id LIMIT 1").fetchone()
        for row in con.execute("SELECT * FROM reservations WHERE status IN ('รออนุมัติ','ยืนยันแล้ว') ORDER BY id").fetchall():
            con.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)',
                        (f"legacy_reservation_{row['id']}_status",row['status']))
            existing=con.execute('SELECT id FROM borrow_transactions WHERE reservation_id=? ORDER BY id LIMIT 1',(row['id'],)).fetchone()
            if row['end_date']>=today().isoformat() and not existing:
                eq=con.execute('SELECT available_amount,status FROM equipment WHERE id=?',(row['equipment_id'],)).fetchone()
                approved=(row['status']=='ยืนยันแล้ว' and admin and eq['available_amount']>=1 and eq['status']=='พร้อมใช้งาน')
                loan_id=con.execute("INSERT INTO borrow_transactions(user_id,equipment_id,amount,borrow_date,due_date,purpose,reservation_id,document_path,borrow_status,approved_by,approved_at) VALUES(?,?,1,?,?,?,?,?,?,?,?)",
                        (row['user_id'],row['equipment_id'],row['start_date'],row['end_date'],row['purpose'],row['id'],row['document_path'],
                         'อนุมัติแล้ว' if approved else 'รออนุมัติ',(row['reviewed_by'] or admin['id']) if approved else None,
                         (row['reviewed_at'] or utc_now()) if approved else None)).lastrowid
                converted+=1
                refresh_stock(con,row['equipment_id'])
                if not approved:notify_admins(con,loan_id)
            else:loan_id=existing['id'] if existing else None
            if loan_id:
                con.execute("UPDATE notifications SET reference_id=?,target_page='history' WHERE target_page='reservation' AND reference_id=?",(loan_id,row['id']))
            con.execute("UPDATE reservations SET status='สิ้นสุดแล้ว' WHERE id=?",(row['id'],))
        con.execute("INSERT INTO app_settings(key,value) VALUES('borrowing_only','yes') ON CONFLICT(key) DO UPDATE SET value='yes'")
        return converted
