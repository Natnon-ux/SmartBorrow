# หน้าที่: บัญชีรับเงิน แนบสลิป และตรวจหลักฐาน
"""Manual bank transfer evidence; only staff can settle a fine after review."""
from pathlib import Path
from io import BytesIO
from uuid import uuid4
from PIL import Image
import streamlit as st
from database import DATABASE_PATH, PROJECT_DIR, database_connection
from common import DomainError, require_actor, MANAGER_ROLES, utc_now, action

def payment_settings(database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        return {key: (con.execute('SELECT value FROM app_settings WHERE key=?', ('payment_'+key,)).fetchone() or [''])[0]
                for key in ('bank','account','recipient')}

def save_payment_settings(actor_id, bank, account, recipient, database_path=DATABASE_PATH):
    values=[str(v).strip() for v in (bank,account,recipient)]
    if not all(values) or any(len(v)>200 for v in values):
        raise DomainError('กรอกธนาคาร เลขบัญชี และชื่อผู้รับให้ครบ (ไม่เกิน 200 ตัวอักษร)')
    with database_connection(database_path) as con:
        require_actor(con,actor_id,{'admin'})
        for key,value in zip(('bank','account','recipient'),values):
            con.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('payment_'+key,value))

def slip_file(value):
    path=(PROJECT_DIR/str(value)).resolve()
    if not value or not path.is_relative_to((PROJECT_DIR/'data/uploads/payments').resolve()) or not path.is_file():
        raise DomainError('ไม่พบหลักฐานการชำระเงิน')
    return path

def validate_slip(upload):
    if upload is None:raise DomainError('กรุณาแนบสลิปก่อนส่ง')
    content=upload.getvalue();suffix=Path(upload.name).suffix.lower()
    if not content or len(content)>5*1024*1024:raise DomainError('สลิปต้องมีขนาดไม่เกิน 5 MB')
    if suffix=='.pdf':
        from borrow_requests import validate_pdf
        validate_pdf(content)
    elif suffix in {'.jpg','.jpeg','.png'}:
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format not in {'JPEG','PNG'} or image.width*image.height>20000000:raise ValueError()
                image.verify()
        except Exception:raise DomainError('ไฟล์รูปสลิปไม่ถูกต้อง ใช้ JPG หรือ PNG ที่เปิดอ่านได้') from None
    else:raise DomainError('รับเฉพาะ JPG, PNG หรือ PDF')
    return content,suffix

def submit_slip(actor_id, transaction_id, upload, database_path=DATABASE_PATH):
    content,suffix=validate_slip(upload)
    path=None
    try:
        with database_connection(database_path) as con:
            con.execute('BEGIN IMMEDIATE');require_actor(con,actor_id)
            row=con.execute('SELECT * FROM borrow_transactions WHERE id=?',(transaction_id,)).fetchone()
            if not row or row['user_id']!=actor_id or row['fine_status']!='ค้างชำระ' or row['borrow_status']!='คืนแล้ว':
                raise DomainError('ส่งสลิปได้เฉพาะค่าปรับค้างชำระของคุณที่คืนแล้ว')
            if row['payment_review']=='รอตรวจสอบ':raise DomainError('ส่งหลักฐานแล้ว กรุณารอเจ้าหน้าที่ตรวจสอบ')
            directory=PROJECT_DIR/'data/uploads/payments';directory.mkdir(parents=True,exist_ok=True)
            path=directory/(uuid4().hex+suffix);path.write_bytes(content)
            con.execute("UPDATE borrow_transactions SET payment_slip=?,payment_review='รอตรวจสอบ',payment_submitted_at=?,payment_review_note='' WHERE id=?",
                        (path.relative_to(PROJECT_DIR).as_posix(),utc_now(),transaction_id))
            for admin in con.execute("SELECT id FROM users WHERE role='admin' AND status='active'").fetchall():
                con.execute('INSERT INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                            (admin['id'],f"payment:{path.stem}:{admin['id']}",f'มีสลิปค่าปรับรายการ #{transaction_id} รอตรวจสอบในหน้าค่าปรับ',transaction_id,'fines'))
    except BaseException:
        if path:path.unlink(missing_ok=True)
        raise

def reject_slip(actor_id, transaction_id, note, database_path=DATABASE_PATH):
    if not str(note).strip():raise DomainError('ระบุเหตุผลให้ผู้ยืมแก้ไขหลักฐาน')
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE');require_actor(con,actor_id,MANAGER_ROLES)
        row=con.execute('SELECT * FROM borrow_transactions WHERE id=?',(transaction_id,)).fetchone()
        if not row or row['fine_status']!='ค้างชำระ' or row['payment_review']!='รอตรวจสอบ':raise DomainError('ไม่มีสลิปรอตรวจสอบ')
        reason=str(note).strip()[:1000]
        con.execute("UPDATE borrow_transactions SET payment_review='ไม่ผ่าน',payment_review_note=? WHERE id=?",(reason,transaction_id))
        con.execute('INSERT INTO notifications(user_id,event_key,message,reference_id,target_page) VALUES(?,?,?,?,?)',
                    (row['user_id'],f"payment_rejected:{transaction_id}:{Path(row['payment_slip']).stem}",
                     f'สลิปชำระค่าปรับรายการ #{transaction_id} ไม่ผ่าน · เหตุผล: {reason} · กรุณาส่งสลิปใหม่ในหน้าค่าปรับ',transaction_id,'fines'))

def render_payment_settings(user, database_path):
    config=payment_settings(database_path)
    st.subheader('บัญชีรับชำระค่าปรับ')
    with st.form('payment_settings'):
        bank=st.text_input('ธนาคาร',config['bank'])
        account=st.text_input('เลขบัญชี',config['account'])
        recipient=st.text_input('ชื่อบัญชี',config['recipient'])
        if st.form_submit_button('บันทึกช่องทางชำระเงิน',type='primary'):
            action(save_payment_settings,user['id'],bank,account,recipient,database_path,success='บันทึกบัญชีรับเงินแล้ว')

def render_payments(user, due, database_path):
    config=payment_settings(database_path)
    if due:
        st.subheader('ชำระค่าปรับ')
        if all(config.values()):
            with st.container(border=True):
                st.markdown('**โอนผ่านบัญชีธนาคาร**')
                st.text(f"{config['bank']}\nเลขบัญชี {config['account']}\nชื่อบัญชี {config['recipient']}")
                st.caption('โอนตามยอดค่าปรับของรายการ แล้วแนบสลิป เจ้าหน้าที่จะตรวจสอบก่อนเปลี่ยนสถานะเป็นชำระแล้ว')
        else:st.info('ยังไม่ได้ตั้งค่าบัญชีรับเงิน กรุณาติดต่อเจ้าหน้าที่')
    for row in due:
        own=row['user_id']==user['id'];manager=user['role'] in MANAGER_ROLES
        with st.expander(f"#{row['id']} · {row['equipment_name']} · {row['fine_amount_cents']/100:,.2f} บาท",expanded=own):
            if row['payment_review']:
                st.info('หลักฐาน: '+row['payment_review'])
            if row['payment_review_note']:st.warning(row['payment_review_note'])
            if row['payment_slip'] and (own or manager):
                try:
                    path=slip_file(row['payment_slip']);content=path.read_bytes()
                    st.download_button('ดาวน์โหลดสลิป',content,file_name='payment-slip'+path.suffix,key=f"slip_download_{row['id']}")
                    if path.suffix=='.pdf':st.pdf(content,height=420,key=f"slip_pdf_{row['id']}")
                    else:st.image(content,width=400)
                except (DomainError,OSError):st.error('เปิดสลิปไม่ได้ กรุณาติดต่อผู้ยืมส่งหลักฐานใหม่')
            if own and row['payment_review']!='รอตรวจสอบ':
                with st.form(f"upload_slip_{row['id']}"):
                    upload=st.file_uploader('แนบสลิปชำระค่าปรับ',type=['jpg','jpeg','png','pdf'],max_upload_size=5,key=f"slip_{row['id']}")
                    st.caption('JPG / PNG / PDF · ไม่เกิน 5 MB · ส่งสลิปแยกตามรายการ')
                    if st.form_submit_button('ส่งสลิปให้เจ้าหน้าที่ตรวจสอบ',type='primary'):
                        action(submit_slip,user['id'],row['id'],upload,database_path,success='ส่งสลิปแล้ว รอเจ้าหน้าที่ตรวจสอบ')
            if manager and row['payment_review']=='รอตรวจสอบ':
                with st.form(f"reject_slip_{row['id']}"):
                    note=st.text_input('เหตุผลที่หลักฐานไม่ผ่าน')
                    if st.form_submit_button('ขอให้ส่งสลิปใหม่'):
                        action(reject_slip,user['id'],row['id'],note,database_path,success='แจ้งให้ผู้ยืมส่งสลิปใหม่แล้ว')
