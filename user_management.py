# หน้าที่: จัดการผู้ใช้และรีเซ็ตรหัสผ่านโดยเจ้าหน้าที่
"""STEP 21: ผู้ดูแลจัดการบัญชี รหัสผ่านเก็บเป็น PBKDF2 hash."""
import re
import streamlit as st
from auth import ROLE_LABELS,hash_password
from common import DomainError,require_actor,action
from database import DATABASE_PATH,database_connection
from student_ids import format_student_code

def validate_username(username):
    """ชื่อผู้ใช้ใหม่ใช้เฉพาะภาษาอังกฤษและตัวเลข ไม่รับช่องว่างหรือสัญลักษณ์."""
    if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9]{3,15}',username):
        raise DomainError('ชื่อผู้ใช้ต้องยาว 3–15 ตัว ใช้เฉพาะ A–Z, a–z และ 0–9 ไม่ใช้ช่องว่างหรืออักขระพิเศษ')
    return username

def validate_password(password):
    if not isinstance(password,str) or len(password)<8 or len(password.encode('utf-8'))>1024:
        raise DomainError('รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร และขนาดไม่เกิน 1,024 ไบต์')
    return password

def user_rows(actor_id,database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        require_actor(con,actor_id,{'admin'})
        return [dict(r) for r in con.execute('SELECT id,student_code,username,full_name,role,classroom,phone,status,created_at,executive_title FROM users ORDER BY id')]

def save_user(actor_id,values,user_id=None,password=None,confirmed=False,database_path=DATABASE_PATH):
    values=dict(values)
    for key in ('student_code','username','full_name'):
        values[key]=str(values.get(key,'')).strip()
        if not values[key]:
            raise DomainError('กรุณากรอกรหัส Username และชื่อให้ครบ')
    role,status=values.get('role','student'),values.get('status','active')
    if role not in ROLE_LABELS or status not in {'active','inactive'}:
        raise DomainError('บทบาทหรือสถานะบัญชีไม่ถูกต้อง')
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        require_actor(con,actor_id,{'admin'})
        old=con.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone() if user_id else None
        title=values.get('executive_title',old['executive_title'] if old else '')
        if title not in {'','director','deputy'} or (title and role not in {'admin','staff','teacher'}):
            raise DomainError('สิทธิ์ ผอ. หรือรอง ผอ. ต้องใช้บัญชีผู้ดูแล ครู หรือเจ้าหน้าที่')
        if old and old['executive_title']!=title and not confirmed:
            raise DomainError('กรุณายืนยันการเปลี่ยนสิทธิ์อนุมัติสุดท้าย')
        if user_id and old is None:
            raise DomainError('ไม่พบบัญชีผู้ใช้')
        if old is None or old['username']!=values['username']:
            validate_username(values['username'])
        if role in {'student','teacher'} and (old is None or old['role']!=role or old['student_code']!=values['student_code']):
            values['student_code']=format_student_code(values['student_code'])
            if con.execute('SELECT 1 FROM users WHERE (student_code=? OR student_code=?) AND id!=?',
                           (values['student_code'],values['student_code'].replace('-',''),user_id or -1)).fetchone():
                raise DomainError('รหัสประจำตัวนี้มีบัญชีแล้ว')
        if old:
            if (old['role']!=role or old['status']!=status) and not confirmed:
                raise DomainError('กรุณายืนยันการเปลี่ยนบทบาทหรือสถานะบัญชี')
            if user_id==actor_id and status!='active':
                raise DomainError('ไม่สามารถปิดบัญชีที่กำลังใช้งานอยู่')
            if old['role']=='admin' and old['status']=='active' and (role!='admin' or status!='active'):
                others=con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND status='active' AND id!=?",(user_id,)).fetchone()[0]
                if not others:
                    raise DomainError('ต้องมี Admin ที่ใช้งานได้อย่างน้อย 1 บัญชี')
        params=(values['student_code'],values['username'],values['full_name'],role,str(values.get('classroom','')).strip(),str(values.get('phone','')).strip(),status)
        if old:
            con.execute('UPDATE users SET student_code=?,username=?,full_name=?,role=?,classroom=?,phone=?,status=? WHERE id=?',(*params,user_id))
            if old['phone']!=params[5]:
                con.execute('UPDATE users SET phone_verified_at=NULL,auth_version=auth_version+1 WHERE id=?',(user_id,))
        else:
            hashed=hash_password(validate_password(password))
            user_id=con.execute('INSERT INTO users(student_code,username,full_name,role,classroom,phone,status,password) VALUES(?,?,?,?,?,?,?,?)',(*params,hashed)).lastrowid
        con.execute('UPDATE users SET executive_title=? WHERE id=?',(title,user_id))
        if old and old['executive_title']!=title:
            con.execute('UPDATE users SET auth_version=auth_version+1 WHERE id=?',(user_id,))
        return user_id

def reset_password(actor_id,user_id,password,confirmed=False,database_path=DATABASE_PATH):
    if not confirmed:
        raise DomainError('กรุณายืนยันการตั้งรหัสผ่านใหม่')
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        require_actor(con,actor_id,{'admin'})
        if con.execute('SELECT id FROM users WHERE id=?',(user_id,)).fetchone() is None:
            raise DomainError('ไม่พบบัญชีผู้ใช้')
        con.execute('UPDATE users SET password=?,auth_version=auth_version+1 WHERE id=?',(hash_password(validate_password(password)),user_id))

def render_users(user,database_path=DATABASE_PATH):
    st.title('ผู้ใช้งาน')
    if user['role']!='admin':
        st.error('เฉพาะ Admin สามารถจัดการผู้ใช้ได้')
        return
    rows=user_rows(user['id'],database_path)
    search=st.text_input('ค้นหาผู้ใช้งาน')
    visible=[r for r in rows if not search or any(search.casefold() in r[field].casefold() for field in ('full_name','username','student_code'))]
    st.dataframe([{'รหัส':r['student_code'],'ชื่อ':r['full_name'],'Username':r['username'],'บทบาท':ROLE_LABELS[r['role']],
                   'ห้อง':r['classroom'],'สถานะ':'ใช้งาน' if r['status']=='active' else 'ปิดบัญชี'} for r in visible],hide_index=True,width='stretch')
    records={r['id']:r for r in rows}
    selected=st.selectbox('เพิ่ม / แก้ไขบัญชี',[None,*records],key='user_editor_id',format_func=lambda key:'เพิ่มผู้ใช้งานใหม่' if key is None else f"{records[key]['username']} · {records[key]['full_name']}")
    row=records.get(selected,{})
    with st.form(f'user_edit_{selected}'):
        code=st.text_input('รหัสนักเรียน / บุคลากร',value=row.get('student_code',''),
                           help='รหัสนักเรียนและครูใช้รูปแบบ 6xxxxxxxx-x เช่น 683040123-4 ต้องใส่ขีดก่อนหลักสุดท้าย ส่วน Admin คงรหัสเดิม')
        username=st.text_input('Username',value=row.get('username',''),max_chars=max(15,len(row.get('username',''))),help='ชื่อใหม่ใช้เฉพาะภาษาอังกฤษและตัวเลข 3–15 ตัว บัญชีเดิมคงชื่อเดิมได้')
        name=st.text_input('ชื่อ-นามสกุล',value=row.get('full_name',''))
        roles=list(ROLE_LABELS)
        role=st.selectbox('บทบาท',roles,index=roles.index(row.get('role','student')),format_func=ROLE_LABELS.get)
        from executive_approval import TITLES
        title=st.selectbox('สิทธิ์อนุมัติสุดท้าย',list(TITLES),index=list(TITLES).index(row.get('executive_title','')),format_func=TITLES.get,
                           help='เลือก ผอ. หรือรอง ผอ. ร่วมกับบทบาทผู้ดูแล ครู หรือเจ้าหน้าที่ คนใดคนหนึ่งอนุมัติรอบสุดท้ายได้')
        classroom=st.text_input('ห้อง / หน่วยงาน',value=row.get('classroom',''))
        phone=st.text_input('โทรศัพท์',value=row.get('phone',''))
        states=['active','inactive']
        state=st.selectbox('สถานะบัญชี',states,index=states.index(row.get('status','active')),format_func=lambda v:'ใช้งาน' if v=='active' else 'ปิดบัญชี')
        password=None
        if selected is None:
            password=st.text_input('รหัสผ่านเริ่มต้น',type='password',key='user_create_password')
        confirmed=st.checkbox('ยืนยันการเปลี่ยนบทบาทหรือสถานะบัญชี') if selected else False
        if st.form_submit_button('บันทึกผู้ใช้งาน',type='primary'):
            st.session_state.pop('user_create_password',None)
            action(save_user,user['id'],dict(student_code=code,username=username,full_name=name,role=role,classroom=classroom,phone=phone,status=state,executive_title=title),
                   selected,password,confirmed,database_path,success='บันทึกบัญชีผู้ใช้แล้ว')
    if selected:
        with st.expander('ตั้งรหัสผ่านใหม่'):
            with st.form(f'user_reset_{selected}'):
                password=st.text_input('รหัสผ่านใหม่',type='password',key='user_reset_password')
                confirmed=st.checkbox('ยืนยันรีเซ็ตรหัสผ่านของบัญชีนี้')
                if st.form_submit_button('รีเซ็ตรหัสผ่าน'):
                    st.session_state.pop('user_reset_password',None)
                    action(reset_password,user['id'],selected,password,confirmed,database_path,success='ตั้งรหัสผ่านใหม่แล้ว')
