# หน้าที่: หน้าหลัก ตรวจล็อกอินและเลือกหน้าตามสิทธิ์
"""SmartBorrow: ตรวจ session ก่อนเข้าทุกหน้า พร้อม UI จาก HTML/CSS/JavaScript."""
import sqlite3
from pathlib import Path
import streamlit as st
from auth import ensure_demo_users,get_current_user,render_login_page
from database import DATABASE_PATH,initialize_database
from image_generator import ASSETS_DIR,generate_assets
from navigation import render_sidebar, render_top_navigation
from common import show_flash
from dashboard import render_dashboard
from equipment import render_equipment
from borrowing import render_borrow
from approvals import render_approvals
from returns import render_returns
from borrowing_workflow import enable_borrowing_only
from history import render_history
from maintenance import render_maintenance
from services import update_overdue,overdue_rows
from notifications import sync_notifications
from reports import render_reports
from insights import render_insights
from user_management import render_users
from profile_page import render_profile
from settings import render_settings,get_setting
from availability_calendar import render_calendar
from fines import render_fines
from web_ui import apply_web_style, render_footer, render_workspace_header

def configure_page():
    st.set_page_config(page_title='SmartBorrow | ระบบยืม-คืนอุปกรณ์',page_icon=str(ASSETS_DIR/'logo_icon.png'),layout='wide',initial_sidebar_state='auto')

def main(database_path: str|Path=DATABASE_PATH):
    try:
        generate_assets()
    except OSError:
        st.set_page_config(page_title='SmartBorrow',layout='wide')
        st.error('ไม่สามารถสร้างรูปได้ กรุณาตรวจสิทธิ์เขียนโฟลเดอร์ assets')
        st.stop()
    configure_page()
    apply_web_style()
    try:
        initialize_database(database_path)
        ensure_demo_users(database_path)
        enable_borrowing_only(database_path)
        user=get_current_user(database_path)
    except (sqlite3.Error,OSError):
        st.error('ไม่สามารถเตรียมระบบได้ กรุณาตรวจฐานข้อมูลและสิทธิ์เขียนโฟลเดอร์')
        st.stop()
    from login_session import write_cookie
    write_cookie()
    if user is None:
        render_login_page(database_path)
        st.stop()
    from usage_rules import require_usage_rules
    executive=user.get('executive_title','') in {'director','deputy'}
    if not executive:require_usage_rules(user,database_path)
    scanned=st.query_params.get('equipment','')[:100]
    if not executive and scanned and st.session_state.get('scanned_equipment')!=scanned:
        st.session_state['scanned_equipment']=scanned
        st.session_state['navigation_page']='equipment'
        st.session_state['equipment_search']=scanned
    page=render_sidebar(user)
    show_flash()
    update_overdue(database_path)
    sync_notifications(database_path)
    render_top_navigation(user,page,database_path)
    overdue=[] if executive else overdue_rows(user['id'],database_path)
    own=[r for r in overdue if r['user_id']==user['id']]
    if own:
        st.warning(f'คุณมีอุปกรณ์เกินกำหนด {len(own)} รายการ กรุณาติดต่อเจ้าหน้าที่',icon=':material/schedule:')
    elif overdue:
        st.warning(f'เกินกำหนดคืน {len(overdue)} รายการ กรุณาติดตามผู้ยืม',icon=':material/schedule:')
    routes={'dashboard':render_dashboard,'equipment':render_equipment,'borrow':render_borrow,
            'calendar':render_calendar,'fines':render_fines,
            'approvals':render_approvals,'return':render_returns,
            'history':render_history,'maintenance':render_maintenance,'reports':render_reports,'insights':render_insights,'users':render_users,'profile':render_profile,'settings':render_settings}
    renderer=routes.get(page)
    if user['role']=='admin':
        from backoffice import render_admin_dashboard,render_admin_equipment,render_admin_returns
        renderer={'dashboard':render_admin_dashboard,'equipment':render_admin_equipment,'return':render_admin_returns}.get(page,renderer)
    # Replace the page as one unit, including reruns after saves and navigation.
    page_slot=st.empty()
    with page_slot.container():
        if renderer:
            if page=='dashboard':
                renderer(user,database_path)
            else:
                with st.container(key='workspacepage_'+page):
                    if not executive:render_workspace_header(page,user['role'])
                    renderer(user,database_path)
        else:
            st.info('หน้านี้อยู่ระหว่างพัฒนาในขั้นถัดไป')
    render_footer(get_setting('school_name','ระบบบริหารจัดการยืม-คืนอุปกรณ์ภายในโรงเรียน',database_path))

if __name__=='__main__':
    main()
