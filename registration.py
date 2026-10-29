# หน้าที่: สมัครสมาชิกและตรวจข้อมูลที่จำเป็น
"""สมัครบัญชีนักเรียนด้วยตนเอง ไม่เปิดให้เลือกรับสิทธิ์ผู้ดูแล."""
import sqlite3
import re
import streamlit as st
from auth import hash_password
from common import DomainError,utc_now
from database import DATABASE_PATH,database_connection
from user_management import validate_password,validate_username
from student_ids import format_student_code

def register_student(student_code,username,full_name,classroom,phone,password,password_confirm,database_path=DATABASE_PATH,*,email='',proofs=None):
    from otp_service import normalize_destination,consume_proof
    code=format_student_code(student_code)
    username=str(username).strip()
    name=str(full_name).strip()
    classroom=str(classroom).strip()
    phone=str(phone).strip()
    if not str(email).strip():raise DomainError('กรุณากรอกอีเมลก่อนสมัครสมาชิก')
    email=normalize_destination('email',email)
    proofs=proofs or {}
    if not code or not name or not classroom:
        raise DomainError('กรุณากรอกรหัสนักเรียน ชื่อ-นามสกุล และห้องเรียนให้ครบ')
    if not 2<=len(name)<=100:
        raise DomainError('ชื่อ-นามสกุลต้องยาว 2–100 ตัวอักษร')
    if not 2<=len(classroom)<=6:
        raise DomainError('ห้องเรียนต้องยาว 2–6 ตัวอักษร เช่น ม.4/1')
    if phone and not re.fullmatch(r'0[0-9]{9}',phone):
        raise DomainError('เบอร์โทรศัพท์ต้องเป็นตัวเลข 10 หลัก เริ่มด้วย 0 หรือเว้นว่างได้')
    validate_username(username)
    validate_password(password)
    if len(password)>64:
        raise DomainError('รหัสผ่านต้องยาว 8–64 ตัวอักษร')
    if not password.strip():
        raise DomainError('รหัสผ่านต้องไม่เป็นช่องว่างทั้งหมด')
    if password!=password_confirm:
        raise DomainError('รหัสผ่านทั้งสองช่องไม่ตรงกัน')
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        setting=con.execute("SELECT value FROM app_settings WHERE key='otp_registration_otp_mode'").fetchone()
        from otp_delivery import registration_channels
        required=registration_channels(setting['value'] if setting else 'email')
        email_verified=phone_verified=None
        import otp_policy
        for channel in (set(required)|set(proofs) if otp_policy.OTP_ENABLED else set()):
            destination=normalize_destination(channel,email if channel=='email' else phone)
            consume_proof(con,proofs.get(channel,''),'register',channel,destination,None,'')
            if channel=='email':email=destination;email_verified=utc_now()
            else:phone=destination;phone_verified=utc_now()
        if con.execute('SELECT 1 FROM users WHERE username=? COLLATE NOCASE',(username,)).fetchone():
            raise DomainError('ชื่อผู้ใช้นี้ถูกใช้แล้ว กรุณาเลือกชื่อใหม่')
        if con.execute('SELECT 1 FROM users WHERE trim(email)=? COLLATE NOCASE',(email,)).fetchone():
            raise DomainError('อีเมลนี้ถูกใช้แล้ว กรุณาใช้อีเมลอื่น หรือเข้าสู่ระบบด้วยบัญชีเดิม')
        if con.execute('SELECT 1 FROM users WHERE student_code=? COLLATE NOCASE OR student_code=?',(code,code.replace('-',''))).fetchone():
            raise DomainError('รหัสนักเรียนนี้มีบัญชีแล้ว กรุณาเข้าสู่ระบบหรือติดต่อเจ้าหน้าที่')
        return con.execute("INSERT INTO users(student_code,username,password,full_name,role,classroom,phone,status,email,email_verified_at,phone_verified_at) "
                           "VALUES(?,?,?,?,'student',?,?,'active',?,?,?)",
                           (code,username,hash_password(password),name,classroom,phone,email,email_verified,phone_verified)).lastrowid

def handle_registration(database_path=DATABASE_PATH):
    keys=('student_code','username','full_name','classroom','phone','password','password_confirm')
    values={key:st.session_state.get('register_'+key,'') for key in keys}
    values['email']=st.session_state.get('register_email','')
    proofs={channel:st.session_state['signup_otp_'+channel+'_proof'] for channel in ('email','sms') if st.session_state.get('signup_otp_'+channel+'_proof')}
    st.session_state['register_password']=''
    st.session_state['register_password_confirm']=''
    st.session_state.pop('registration_error',None)
    try:
        register_student(database_path=database_path,proofs=proofs,**values)
    except DomainError as error:
        st.session_state['registration_error']=str(error)
    except (sqlite3.Error,OSError):
        st.session_state['registration_error']='ไม่สามารถสมัครได้ กรุณาตรวจสอบข้อมูลแล้วลองใหม่'
    else:
        st.session_state['auth_view']='เข้าสู่ระบบ'
        st.session_state['login_username']=values['username'].strip()
        st.session_state['auth_notice']='สมัครสมาชิกสำเร็จ เข้าสู่ระบบด้วยบัญชีใหม่ได้เลย'
        st.session_state.pop('login_error',None)
        for key in (*keys,'email'):
            if key not in ('password','password_confirm'):
                st.session_state.pop('register_'+key,None)
        for key in list(st.session_state):
            if key.startswith('signup_otp_'):st.session_state.pop(key,None)

def render_registration(database_path=DATABASE_PATH):
    import otp_policy
    if not otp_policy.OTP_ENABLED:
        render_registration_without_otp(database_path)
        return
    st.subheader('สร้างบัญชีของคุณ')
    st.caption('สำหรับนักเรียน • กรอกอีเมล → ยืนยัน OTP → สร้างบัญชี')
    from otp_delivery import delivery_settings,registration_channels,channel_ready
    from account_security import registration_verification
    mode=delivery_settings(database_path)['registration_otp_mode']
    required=registration_channels(mode)
    same_destination=lambda c:st.session_state.get('signup_otp_'+c+'_destination')==st.session_state.get('register_email' if c=='email' else 'register_phone','').strip()
    step=3 if all(st.session_state.get('signup_otp_'+c+'_proof') and same_destination(c) for c in required) else 2 if st.session_state.get('signup_otp_email_challenge') and same_destination('email') else 1
    st.html('<ol class="sb-signup-steps" aria-label="ขั้นตอนสมัครสมาชิก">'+''.join(
        f'<li class="{"current" if i==step else "done" if i<step else ""}"'+(' aria-current="step"' if i==step else '')+
        f'><span>{i:02d}</span>{label}</li>' for i,label in enumerate(['อีเมล','ยืนยัน OTP','สร้างบัญชี'],1))+'</ol>')
    st.text_input('อีเมล (ต้องยืนยัน OTP)',key='register_email',max_chars=254,placeholder='name@example.com',help='ใช้อีเมลที่เข้าถึงได้ เพื่อยืนยันบัญชีและกู้คืนรหัสผ่าน')
    st.text_input('โทรศัพท์'+(' (ต้องยืนยัน OTP)' if 'sms' in required else ' (ไม่บังคับ)'),key='register_phone',max_chars=50)
    for channel in required:
        registration_verification(channel,'register_email' if channel=='email' else 'register_phone',database_path)
    if not all(channel_ready(channel,database_path) for channel in required):
        st.info('การสมัครใหม่ต้องยืนยันอีเมลด้วย OTP กรุณารอ Admin เชื่อมบริการส่งใน ตั้งค่า → OTP และบัญชี')
    verified=all(st.session_state.get('signup_otp_'+channel+'_proof') for channel in required)
    if not verified:st.caption('ยืนยัน OTP ให้ครบก่อนกดสมัครสมาชิก')
    with st.form('registration_form',border=False):
        left,right=st.columns(2)
        left.text_input('รหัสนักเรียน',key='register_student_code',placeholder='683040123-4',max_chars=11,
                        help='ครบ 11 ตัว รูปแบบ 6xxxxxxxx-x ต้องใส่ขีดก่อนหลักสุดท้าย')
        right.text_input('ห้องเรียน',key='register_classroom',placeholder='เช่น ม.4/1',max_chars=6,help='2–6 ตัวอักษร')
        st.text_input('ชื่อ-นามสกุล',key='register_full_name',placeholder='กรอกชื่อและนามสกุล',max_chars=100,help='2–100 ตัวอักษร')
        left,right=st.columns(2)
        left.text_input('ชื่อผู้ใช้',key='register_username',placeholder='ภาษาอังกฤษและตัวเลขเท่านั้น',help='3–15 ตัว ใช้ A–Z, a–z และ 0–9 ไม่ใช้ช่องว่าง จุด ขีด หรือขีดล่าง',max_chars=15)
        left,right=st.columns(2)
        left.text_input('รหัสผ่าน',key='register_password',type='password',placeholder='8–64 ตัวอักษร',max_chars=64)
        right.text_input('ยืนยันรหัสผ่าน',key='register_password_confirm',type='password',max_chars=64)
        st.form_submit_button('สมัครสมาชิก',type='primary',width='stretch',disabled=not verified,on_click=handle_registration,args=(database_path,))
    if st.session_state.get('registration_error'):
        st.error(st.session_state['registration_error'])
    st.caption('บัญชีครู เจ้าหน้าที่ และผู้ดูแล ให้ติดต่อ Admin ของโรงเรียน')

def render_registration_without_otp(database_path=DATABASE_PATH):
    st.subheader('สร้างบัญชีของคุณ')
    st.caption('สำหรับนักเรียน • กรอกข้อมูลและตั้งรหัสผ่านเพื่อเริ่มใช้งาน')
    with st.form('registration_form',border=False):
        left,right=st.columns(2)
        left.text_input('รหัสนักเรียน',key='register_student_code',placeholder='683040123-4',max_chars=11,help='ต้องครบ 11 ตัว: เลข 9 หลัก ขีด - และเลข 1 หลัก เริ่มด้วย 6 ห้ามละขีด')
        right.text_input('ห้องเรียน',key='register_classroom',placeholder='เช่น ม.4/1',max_chars=6,help='2–6 ตัวอักษร')
        st.text_input('ชื่อ-นามสกุล',key='register_full_name',max_chars=100,help='2–100 ตัวอักษร')
        st.text_input('อีเมล',key='register_email',max_chars=254,placeholder='name@example.com',help='ใช้อีเมลที่ไม่เคยสมัครบัญชีอื่นในระบบ')
        st.text_input('โทรศัพท์ (ไม่บังคับ)',key='register_phone',max_chars=10,placeholder='0xxxxxxxxx',help='ตัวเลข 10 หลัก เริ่มด้วย 0 หรือเว้นว่าง')
        st.text_input('ชื่อผู้ใช้',key='register_username',help='3–15 ตัว ใช้เฉพาะภาษาอังกฤษและตัวเลข ไม่ใช้ช่องว่างหรืออักขระพิเศษ',max_chars=15)
        left,right=st.columns(2)
        left.text_input('รหัสผ่าน',key='register_password',type='password',placeholder='8–64 ตัวอักษร',max_chars=64,help='อย่างน้อย 8 และไม่เกิน 64 ตัวอักษร')
        right.text_input('ยืนยันรหัสผ่าน',key='register_password_confirm',type='password',max_chars=64,help='กรอกให้ตรงกับรหัสผ่าน')
        st.form_submit_button('สมัครสมาชิก',type='primary',width='stretch',on_click=handle_registration,args=(database_path,))
    if st.session_state.get('registration_error'):st.error(st.session_state['registration_error'])
    st.caption('บัญชีครูและเจ้าหน้าที่ให้ติดต่อ Admin • หากลืมรหัสผ่าน ให้ติดต่อเจ้าหน้าที่ของโรงเรียน')
