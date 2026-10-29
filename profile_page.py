# หน้าที่: ข้อมูลส่วนตัว พร้อมแท็บประวัติและค่าปรับ
"""STEP 22: โปรไฟล์และสถิติการคืนของตนเอง."""
import sqlite3
import streamlit as st
from auth import ROLE_LABELS,PUBLIC_USER_FIELDS
from common import USAGE_STATUSES,DomainError,require_actor,validate_evidence,image_path
from database import DATABASE_PATH,database_connection

def profile_data(actor_id,database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        require_actor(con,actor_id)
        user=dict(con.execute(f"SELECT {','.join(PUBLIC_USER_FIELDS)} FROM users WHERE id=?",(actor_id,)).fetchone())
        rows=[dict(r) for r in con.execute('SELECT borrow_status,due_date,return_date FROM borrow_transactions WHERE user_id=?',(actor_id,))]
    user['stats']={'borrowed':sum(r['borrow_status'] in USAGE_STATUSES for r in rows),
                   'on_time':sum(r['borrow_status']=='คืนแล้ว' and r['return_date']<=r['due_date'] for r in rows),
                   'late':sum(r['borrow_status']=='คืนแล้ว' and r['return_date']>r['due_date'] for r in rows)}
    return user

def update_profile(actor_id,full_name,classroom,phone,image=None,database_path=DATABASE_PATH):
    if not str(full_name).strip() or len(str(full_name))>200 or len(str(classroom))>100 or len(str(phone))>50:
        raise DomainError('กรุณากรอกชื่อ และตรวจความยาวข้อมูลโปรไฟล์')
    if image:
        validate_evidence(image)
    with database_connection(database_path) as con:
        require_actor(con,actor_id)
        old=con.execute('SELECT phone,phone_verified_at FROM users WHERE id=?',(actor_id,)).fetchone()
        if old['phone_verified_at'] and str(phone).strip()!=old['phone']:
            raise DomainError('เปลี่ยนเบอร์ที่ยืนยันแล้วในส่วนความปลอดภัยของบัญชี')
        con.execute('UPDATE users SET full_name=?,classroom=?,phone=? WHERE id=?',(str(full_name).strip(),str(classroom).strip(),str(phone).strip(),actor_id))
        if image:
            con.execute('UPDATE users SET profile_image=? WHERE id=?',(image,actor_id))


def save_profile_form(actor_id,database_path):
    """Runs before rendering, so both the sidebar and page read the updated profile once."""
    st.session_state.pop('profile_error',None)
    try:
        update_profile(actor_id,st.session_state['profile_full_name'],st.session_state['profile_classroom'],
                       st.session_state['profile_phone'],database_path=database_path)
    except DomainError as error:
        st.session_state['profile_error']=str(error)
    except (sqlite3.Error,OSError):
        st.session_state['profile_error']='ไม่สามารถบันทึกข้อมูลได้ กรุณาลองอีกครั้ง'
    else:
        st.session_state['flash_message']='บันทึกโปรไฟล์แล้ว'

def render_profile(user,database_path=DATABASE_PATH):
    tabs=st.tabs(['ข้อมูลส่วนตัว','ประวัติการยืม','ค่าปรับ','กำลังยืม'],key='profile_section',on_change='rerun')
    section=st.session_state.get('profile_section','ข้อมูลส่วนตัว')
    if section=='กำลังยืม':
        from my_loans import render_my_loans
        with tabs[3]:render_my_loans(user,database_path)
    elif section=='ประวัติการยืม':
        from history import render_history
        with tabs[1]:render_history(user,database_path,own_only=user['role']=='student')
    elif section=='ค่าปรับ':
        from fines import render_fines
        with tabs[2]:render_fines(user,database_path)
    else:
        with tabs[0]:render_profile_details(user,database_path)

def render_profile_details(user,database_path):
    st.title('โปรไฟล์ของฉัน')
    row=profile_data(user['id'],database_path)
    left,right=st.columns([1,3])
    with left,st.container(key='profile_avatar'):
        st.image(str(image_path(row['profile_image'])),width=160)
        if st.button('เปลี่ยนรูปโปรไฟล์',icon=':material/photo_camera:',key='profile_change_photo'):
            from photo_editor import show_photo_editor
            show_photo_editor(user['id'],database_path)
    right.subheader(row['full_name'])
    right.write(f"รหัสนักเรียน / บุคลากร: {row['student_code']}")
    right.write(f"ห้อง / หน่วยงาน: {row['classroom'] or '—'} · บทบาท: {ROLE_LABELS[row['role']]}")
    right.write(f"โทรศัพท์: {row['phone'] or '—'}")
    columns=st.columns(3)
    for column,label,key in zip(columns,('จำนวนครั้งที่ยืม','คืนตรงเวลา','คืนช้า'),('borrowed','on_time','late')):
        column.metric(label,row['stats'][key])
    with st.expander('แก้ไขข้อมูลส่วนตัว'):
        with st.form('profile_edit'):
            st.text_input('ชื่อ-นามสกุล',value=row['full_name'],key='profile_full_name')
            st.text_input('ห้อง / หน่วยงาน',value=row['classroom'],key='profile_classroom')
            st.text_input('โทรศัพท์',value=row['phone'],key='profile_phone',disabled=bool(row['phone_verified_at']))
            st.form_submit_button('บันทึกโปรไฟล์',type='primary',on_click=save_profile_form,
                                  args=(user['id'],database_path))
        if st.session_state.get('profile_error'):
            st.error(st.session_state['profile_error'])
    from account_security import render_account_security
    import otp_policy
    with st.expander('อีเมล เบอร์โทร และความปลอดภัย' if otp_policy.OTP_ENABLED else 'ช่วยเหลือบัญชีและรหัสผ่าน',icon=':material/verified_user:'):
        render_account_security(user['id'],database_path)
