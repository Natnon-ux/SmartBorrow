# หน้าที่: ล็อกอินและสลับฟอร์มผู้ใช้กับผู้ดูแล
"""ระบบเข้าสู่ระบบ SmartBorrow — STEP 4.

ใช้ PBKDF2-HMAC-SHA256 จาก Python standard library และ salt สุ่มต่อบัญชี
รหัสผ่านตัวอย่างใน DEMO_ACCOUNTS มีไว้สำหรับต้นแบบเท่านั้น; ฐานข้อมูลเก็บเฉพาะแฮช
"""

import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3

import streamlit as st

from database import DATABASE_PATH, database_connection
from image_generator import ASSETS_DIR


PASSWORD_ITERATIONS = 600_000
MAX_PASSWORD_BYTES = 1024
PUBLIC_USER_FIELDS = ("id", "student_code", "username", "full_name", "role", "classroom", "phone", "profile_image",
                      "email", "email_verified_at", "phone_verified_at", "auth_version", "executive_title")
ROLE_LABELS = {"admin": "ผู้ดูแลระบบ", "teacher": "ครู", "student": "นักเรียน", "staff": "เจ้าหน้าที่"}
LOGIN_ERROR = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง หรือบัญชีถูกปิดใช้งาน"
DEMO_ACCOUNTS = (
    {"student_code": "DEMO-ADMIN", "username": "admin", "password": "admin123",
     "full_name": "ผู้ดูแลระบบตัวอย่าง", "role": "admin", "classroom": ""},
    {"student_code": "DEMO-TEACHER", "username": "teacher", "password": "teacher123",
     "full_name": "ครูณัฐกานต์ ศรีสุข", "role": "teacher", "classroom": ""},
    {"student_code": "DEMO-STUDENT", "username": "student", "password": "student123",
     "full_name": "กฤตภาส ใจดี", "role": "student", "classroom": "ม.4/1"},
)
# ใช้การคำนวณในอัตราเดียวกันแม้ไม่พบชื่อบัญชี เพื่อลดความต่างของเวลาตรวจรหัสผ่าน
DUMMY_PASSWORD_HASH = f"pbkdf2_sha256${PASSWORD_ITERATIONS}${'00' * 16}${'00' * 32}"


def hash_password(password: str) -> str:
    """สร้างแฮชพร้อมชนิดอัลกอริทึม จำนวนรอบ salt และ digest ที่ตรวจย้อนหลังได้."""
    if not isinstance(password, str) or not password:
        raise ValueError("กรุณาระบุรหัสผ่าน")
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        raise ValueError("รหัสผ่านยาวเกินขนาดที่รองรับ")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, PASSWORD_ITERATIONS, dklen=32)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """คำนวณแฮชใหม่และเทียบแบบ constant-time; ข้อมูลแฮชผิดรูปแบบจะไม่ผ่าน."""
    if not isinstance(password, str) or not isinstance(stored_hash, str) or not password:
        return False
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        return False
    try:
        algorithm, iteration_text, salt_text, digest_text = stored_hash.split("$")
        iterations = int(iteration_text)
        if algorithm != "pbkdf2_sha256" or not PASSWORD_ITERATIONS <= iterations <= 2_000_000:
            return False
        if len(salt_text) != 32 or len(digest_text) != 64:
            return False
        salt = bytes.fromhex(salt_text)
        expected_digest = bytes.fromhex(digest_text)
        if len(salt) != 16 or len(expected_digest) != 32:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, iterations, dklen=32)
        return hmac.compare_digest(digest, expected_digest)
    except (ValueError, OverflowError):
        return False


def ensure_demo_users(database_path: str | Path = DATABASE_PATH) -> int:
    """เพิ่มบัญชีทดลองที่ขาด โดยไม่แก้รหัสผ่าน Role หรือสถานะของบัญชีที่มีอยู่."""
    created = 0
    with database_connection(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        for account in DEMO_ACCOUNTS:
            existing = connection.execute("SELECT id FROM users WHERE username = ?",
                                          (account["username"],)).fetchone()
            if existing is not None:
                continue
            connection.execute(
                "INSERT INTO users (student_code, username, password, full_name, role, classroom) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (account["student_code"], account["username"], hash_password(account["password"]),
                 account["full_name"], account["role"], account["classroom"]),
            )
            created += 1
    return created


def authenticate_user(username: str, password: str,
                      database_path: str | Path = DATABASE_PATH) -> dict | None:
    """อ่าน users ด้วย parameterized SQL และคืนเฉพาะข้อมูลบัญชี active ที่ตรวจผ่าน."""
    if not isinstance(username, str) or not isinstance(password, str) or not username.strip() or not password:
        return None
    with database_connection(database_path) as connection:
        row = connection.execute(
            f"SELECT {', '.join(PUBLIC_USER_FIELDS)}, password, status FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    password_matches = verify_password(password, row["password"] if row else DUMMY_PASSWORD_HASH)
    if row is None or not password_matches or row["status"] != "active":
        return None
    return {field: row[field] for field in PUBLIC_USER_FIELDS}


def logout_user(notice: str = "ออกจากระบบเรียบร้อยแล้ว") -> None:
    """ล้าง session รวมข้อมูลผู้ใช้และค่าจากฟอร์ม แล้วแสดงข้อความบนหน้าเข้าสู่ระบบ."""
    from login_session import revoke
    revoke()
    for key in list(st.session_state):
        del st.session_state[key]
    st.session_state['_restore_attempted']=True
    st.session_state['_cookie_write']=''
    st.session_state["auth_notice"] = notice


def get_current_user(database_path: str | Path = DATABASE_PATH) -> dict | None:
    """อ่านข้อมูลบัญชีปัจจุบันใหม่ทุกครั้ง เพื่อใช้ Role และสถานะล่าสุดจากฐานข้อมูล."""
    session_user = st.session_state.get("user")
    if session_user is None:
        from login_session import restore
        session_user=restore(database_path)
    if session_user is None:
        return None
    if not isinstance(session_user, dict) or type(session_user.get("id")) is not int:
        logout_user("กรุณาเข้าสู่ระบบอีกครั้ง")
        return None
    with database_connection(database_path) as connection:
        row = connection.execute(
            f"SELECT {', '.join(PUBLIC_USER_FIELDS)} FROM users WHERE id = ? AND status = 'active'",
            (session_user["id"],),
        ).fetchone()
    if row is None:
        logout_user("บัญชีนี้ไม่สามารถใช้งานได้ กรุณาติดต่อผู้ดูแลระบบ")
        return None
    user = {field: row[field] for field in PUBLIC_USER_FIELDS}
    if session_user.get('auth_version',0)!=user['auth_version']:
        logout_user('ข้อมูลความปลอดภัยของบัญชีเปลี่ยนแล้ว กรุณาเข้าสู่ระบบใหม่')
        return None
    st.session_state["user"] = user
    return user


def handle_login(database_path: str | Path = DATABASE_PATH,admin_portal=None) -> None:
    """Callback ของฟอร์ม อ่านค่าล่าสุด ล้างรหัสผ่าน และบันทึก session เมื่อผ่าน."""
    username = st.session_state.get("login_username", "")
    password = st.session_state.get("login_password", "")
    # Callback ทำงานก่อนวาด widget รอบถัดไป จึงล้างช่องรหัสผ่านได้อย่างถูกต้อง
    st.session_state["login_password"] = ""
    st.session_state.pop("auth_notice", None)
    st.session_state.pop("user", None)
    if not username.strip() or not password:
        st.session_state["login_error"] = "กรุณากรอกชื่อผู้ใช้และรหัสผ่าน"
        return
    try:
        user = authenticate_user(username, password, database_path)
    except (sqlite3.Error, OSError):
        st.session_state["login_error"] = "ไม่สามารถตรวจสอบบัญชีได้ กรุณาลองอีกครั้ง"
        return
    if user is None:
        st.session_state["login_error"] = LOGIN_ERROR
        return
    if admin_portal is None:admin_portal=st.session_state.get('auth_view')=='ผู้ดูแลระบบ'
    if (user['role']=='admin')!=admin_portal:
        st.session_state['login_error']='กรุณาใช้หน้าเข้าสู่ระบบผู้ดูแลระบบ' if user['role']=='admin' else 'หน้านี้สำหรับบัญชี Admin เท่านั้น กรุณาใช้หน้าเข้าสู่ระบบทั่วไป'
        return
    st.session_state["user"] = user
    st.session_state['navigation_page']='dashboard' if user['role']=='admin' else 'equipment'
    from login_session import issue
    issue(user,database_path)
    st.session_state.pop('usage_rules_accepted_for',None)
    st.session_state.pop('usage_rules_acknowledged',None)
    st.session_state.pop("login_error", None)
    st.session_state.pop("login_username", None)


def auth_view_changed():
    st.session_state.pop('login_error',None)
    st.session_state['login_password']=''

def switch_login_portal(admin_portal):
    if admin_portal:st.query_params['portal']='admin'
    else:st.query_params.pop('portal',None)
    st.session_state['auth_view']='ผู้ดูแลระบบ' if admin_portal else 'เข้าสู่ระบบ'
    auth_view_changed()

def render_login_page(database_path: str | Path = DATABASE_PATH) -> None:
    """หน้าต้อนรับและสมัครสมาชิก พร้อมสไตล์ HTML/CSS และฟอร์มฝั่งเซิร์ฟเวอร์."""
    from registration import render_registration
    from web_ui import render_brand,render_auth_carousel
    admin_portal=st.query_params.get('portal')=='admin'
    with st.container(key='auth_header',horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
        render_brand()
        st.button('กลับหน้าเข้าสู่ระบบทั่วไป' if admin_portal else 'ผู้ดูแลระบบ',
                  key='auth_admin_entry',icon=':material/arrow_back:' if admin_portal else ':material/admin_panel_settings:',
                  help='กลับเข้าสู่ระบบสำหรับผู้ใช้ทั่วไป' if admin_portal else 'เข้าสู่ระบบผู้ดูแลระบบ',
                  type='tertiary',on_click=switch_login_portal,args=(not admin_portal,))
    st.space('small')
    welcome_column, form_column = st.columns([1.1, 1], gap="large", vertical_alignment="center")
    with welcome_column,st.container(key='auth_welcome'):
        st.badge('พื้นที่การเรียนรู้ของโรงเรียน',icon=':material/school:',color='red')
        st.title("SmartBorrow")
        st.subheader('อุปกรณ์พร้อม ความคิดสร้างสรรค์ก็พร้อม')
        st.caption('ค้นหา ยืม และคืนอุปกรณ์โรงเรียนได้ในที่เดียว')
        render_auth_carousel()
        with st.container(horizontal=True,gap='medium'):
            st.badge('ค้นหาอุปกรณ์',icon=':material/search:',color='gray')
            st.badge('ยืมล่วงหน้า',icon=':material/event:',color='gray')
            st.badge('ติดตามการคืน',icon=':material/task_alt:',color='gray')
    with form_column, st.container(key='auth_form'):
        admin_portal=st.query_params.get('portal')=='admin'
        if admin_portal:
            st.session_state['auth_view']='ผู้ดูแลระบบ'
            view='ผู้ดูแลระบบ'
        else:
            if st.session_state.get('auth_view') not in {'เข้าสู่ระบบ','สมัครสมาชิก'}:st.session_state['auth_view']='เข้าสู่ระบบ'
            view=st.segmented_control('บัญชีผู้ใช้',['เข้าสู่ระบบ','สมัครสมาชิก'],required=True,
                                      key='auth_view',label_visibility='collapsed',width='stretch',on_change=auth_view_changed)
        if view=='สมัครสมาชิก':
            render_registration(database_path)
            return
        admin_portal=view=='ผู้ดูแลระบบ'
        if admin_portal:st.badge('ADMIN PORTAL',icon=':material/admin_panel_settings:',color='red')
        st.subheader('เข้าสู่ระบบผู้ดูแลระบบ' if admin_portal else 'ยินดีต้อนรับกลับ')
        st.caption('สำหรับ Admin เพื่อจัดการคำขอ ผู้ใช้งาน และตั้งค่าระบบ' if admin_portal else 'สำหรับนักเรียน ครู และเจ้าหน้าที่')
        notice = st.session_state.pop("auth_notice", None)
        if notice:
            st.success(notice,icon=':material/check_circle:')
        with st.form('admin_login_form' if admin_portal else 'login_form',border=False):
            st.text_input("ชื่อผู้ใช้", key="login_username", placeholder="กรอกชื่อผู้ใช้", max_chars=100)
            st.text_input("รหัสผ่าน", key="login_password", type="password", placeholder="กรอกรหัสผ่าน")
            st.form_submit_button("เข้าสู่ระบบ", type="primary", width="stretch",
                                  on_click=handle_login, args=(database_path,admin_portal))
        if st.session_state.get("login_error"):
            st.error(st.session_state["login_error"], icon=':material/error:')
        from account_security import render_recovery
        with st.expander('ลืมรหัสผ่าน?',icon=':material/lock_reset:'):
            render_recovery(database_path)


def render_session_header(user: dict) -> None:
    """แสดงผู้ที่เข้าสู่ระบบและปุ่มออกจากระบบ เพื่อทดสอบ session ใน STEP 4."""
    user_column, logout_column = st.columns([4, 1], vertical_alignment="center")
    with user_column:
        st.success(f"สวัสดี, {user['full_name']} — เข้าสู่ระบบสำเร็จ", icon=':material/check_circle:')
        st.caption(f"ชื่อผู้ใช้: {user['username']} • ประเภทบัญชี: {ROLE_LABELS[user['role']]}")
    with logout_column:
        st.button("ออกจากระบบ", on_click=logout_user, width="stretch")
    st.divider()
