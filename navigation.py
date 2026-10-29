# หน้าที่: เมนูด้านบนและการเปลี่ยนหน้าตามบทบาท
"""STEP 5: เมนูและข้อมูลผู้ใช้ใน Sidebar."""
from pathlib import Path
from html import escape
import streamlit as st
from auth import ROLE_LABELS, logout_user
from image_generator import ASSETS_DIR, create_avatar
from common import image_path
from notifications import render_notifications
from web_ui import render_brand

MENU_LABELS = {
    "calendar": "ปฏิทินอุปกรณ์", "fines": "ค่าปรับ",
    "dashboard": "ภาพรวม", "equipment": "อุปกรณ์", "borrow": "ยืมอุปกรณ์",
    "reservation": "จองอุปกรณ์", "return": "คืนอุปกรณ์", "history": "ประวัติ",
    "approvals": "คำขอ / รับอุปกรณ์", "maintenance": "ซ่อมบำรุง", "reports": "รายงาน",
    "insights": "วิเคราะห์ข้อมูล", "users": "ผู้ใช้งาน", "profile": "โปรไฟล์", "settings": "ตั้งค่า",
}
MENU_ICONS={'dashboard':'space_dashboard','equipment':'inventory_2','borrow':'add_circle','reservation':'event',
            'calendar':'calendar_month','fines':'receipt_long',
            'return':'assignment_return','history':'history','approvals':'fact_check','maintenance':'build',
            'reports':'bar_chart','insights':'lightbulb','users':'group','profile':'account_circle','settings':'settings'}
BASE_PAGES = ("equipment", "dashboard", "borrow", "calendar", "return", "profile")
STAFF_PAGES = ("approvals", "maintenance", "reports", "insights")
ADMIN_PAGES=('dashboard','approvals','return','equipment','maintenance','reports','insights','users','settings','profile')

def menu_label(page,role):
    if role=='admin':return {'dashboard':'ภาพรวมหลังบ้าน','equipment':'จัดการอุปกรณ์','return':'ตรวจรับคืน'}.get(page,MENU_LABELS[page])
    return MENU_LABELS[page]

def allowed_pages(role: str,executive_title='') -> list[str]:
    if executive_title in {'director','deputy'}:return ['approvals']
    if role=='admin':return list(ADMIN_PAGES)
    pages = list(BASE_PAGES)
    if role in {"teacher", "staff", "admin"}:
        pages.extend(STAFF_PAGES)
    if role == "admin":
        pages.extend(("users", "settings"))
    return pages

def navigate_to(page):
    if page=='reservation':page='borrow'
    if page in {'history','fines'}:
        st.session_state['profile_section']='ประวัติการยืม' if page=='history' else 'ค่าปรับ'
        page='profile'
    close_overlays()
    if page!='borrow':
        st.session_state.pop('borrow_draft',None)
    st.session_state['navigation_page']=page


def menu_pages(role):
    """หน้าที่แสดงในเมนู: ยืมผ่านอุปกรณ์/ตะกร้า โปรไฟล์ผ่านบัญชี."""
    return [page for page in allowed_pages(role) if page not in {'borrow','profile'}]

def close_overlays():
    for key in ('command_open','usage_open','equipment_detail_id'):
        st.session_state.pop(key,None)


def open_overlay(key,value=True):
    close_overlays()
    st.session_state[key]=value

def start_borrow(equipment_id):
    st.session_state['borrow_equipment_id']=equipment_id
    st.session_state.pop('borrow_draft',None)
    navigate_to('borrow')


def render_top_navigation(user,page,database_path):
    if user.get('executive_title','') in {'director','deputy'}:
        with st.container(key='top_navigation',gap='small'):
            with st.container(horizontal=True,wrap=False,horizontal_alignment='distribute',vertical_alignment='center'):
                render_brand()
                with st.container(horizontal=True,wrap=False,width='content',vertical_alignment='center'):
                    st.caption(user['full_name']+' · ผู้อนุมัติ',width='content')
                    render_notifications(user,database_path)
                    st.button('ออกจากระบบ',key='top_logout',on_click=logout_user)
            st.button('คำขอรออนุมัติ',key='nav_approvals',type='primary',on_click=navigate_to,args=('approvals',))
        return
    with st.container(key='top_navigation',gap='small'):
        with st.container(horizontal=True,wrap=True,horizontal_alignment='distribute',vertical_alignment='center',gap='small'):
            with st.container(key='top_brand',horizontal=True,width='content',vertical_alignment='center',gap='small'):
                render_brand()
                st.html('<div class="sb-top-context"><span>'+('พื้นที่ผู้ดูแลระบบ' if user['role']=='admin' else 'พื้นที่ทำงานของคุณ')+'</span><strong>'+escape(menu_label(page,user['role']))+'</strong></div>',width='content')
            with st.container(horizontal=True,wrap=False,width='content',vertical_alignment='center',gap='small'):
                st.button('ค้นหาเร็ว',key='top_command',icon=':material/search:',type='tertiary',on_click=open_overlay,args=('command_open',))
                if st.session_state.get('command_open'):show_command_palette(database_path)
                if user['role']!='admin':
                    count=len(st.session_state.get('borrow_cart',{}))
                    st.button(f'ตะกร้า ({count})',key='top_cart',icon=':material/shopping_bag:',on_click=navigate_to,args=('borrow',))
                render_notifications(user,database_path)
                with st.popover('บัญชี',icon=':material/account_circle:',type='tertiary'):
                    st.markdown(f"**{user['full_name']}**")
                    st.caption(ROLE_LABELS[user['role']])
                    st.button('โปรไฟล์และรายการยืม',key='top_profile',on_click=navigate_to,args=('profile',),width='stretch')
                    if user['role']!='admin':
                        st.button('วิธีใช้งานและคีย์ลัด',key='top_help',width='stretch',on_click=open_overlay,args=('usage_open',))
                        if st.session_state.get('usage_open'):show_usage_guide()
                    st.button('ออกจากระบบ',key='top_logout',on_click=logout_user,width='stretch')
        with st.container(key='top_menu',horizontal=True,wrap=True,gap='small'):
            for target in menu_pages(user['role']):
                st.button(menu_label(target,user['role']),key='nav_'+target,icon=f':material/{MENU_ICONS[target]}:',
                          type='primary' if page==target or (page=='borrow' and target=='equipment') else 'tertiary',width='content',on_click=navigate_to,args=(target,))

def render_sidebar(user: dict) -> str:
    """Resolve authorized page; the actual menu is now rendered at the top."""
    pages=allowed_pages(user['role'],user.get('executive_title',''))
    legacy=st.session_state.get('navigation_page')
    if legacy in {'history','fines','reservation'}:navigate_to(legacy)
    if st.session_state.get('navigation_page') not in pages:st.session_state['navigation_page']=pages[0]
    return st.session_state['navigation_page']


@st.dialog('ค้นหาเร็ว',width='large',on_dismiss=close_overlays)
def show_command_palette(database_path):
    from auth import get_current_user
    from services import catalog
    user=get_current_user(database_path)
    if user is None:
        st.info('กรุณาเข้าสู่ระบบอีกครั้ง')
        return
    query=st.text_input('ค้นหาเมนูหรืออุปกรณ์',key='command_query',placeholder='เช่น กล้อง ปฏิทิน ประวัติ…',icon=':material/search:')
    st.caption('พิมพ์แล้วกด Enter เพื่อค้นหา · Esc เพื่อปิด')
    pages=[p for p in menu_pages(user['role']) if not query.strip() or query.strip().casefold() in MENU_LABELS[p].casefold()]
    if pages:
        st.caption('ไปยังหน้า')
        with st.container(key='command_pages',horizontal=True,gap='small'):
            for page in pages:
                if st.button(MENU_LABELS[page],key='command_page_'+page,icon=':material/'+MENU_ICONS[page]+':'):
                    navigate_to(page);st.rerun(scope='app')
    if query.strip():
        rows=catalog(query.strip(),database_path=database_path)
        if rows:
            st.caption('อุปกรณ์ที่พบ')
            for row in rows[:6]:
                if st.button(row['equipment_code']+' · '+row['equipment_name'],key='command_equipment_'+str(row['id']),icon=':material/inventory_2:',width='stretch'):
                    st.session_state['equipment_search']=row['equipment_code']
                    st.session_state['equipment_category']='ทุกหมวดหมู่'
                    st.session_state['equipment_status']='ทั้งหมด'
                    st.session_state['equipment_page']=1
                    navigate_to('equipment');st.rerun(scope='app')
        if not pages and not rows:st.info('ไม่พบรายการ ลองใช้ชื่ออุปกรณ์ รหัส หรือชื่อเมนู')


@st.dialog('เริ่มใช้งาน SmartBorrow',width='large',on_dismiss=close_overlays)
def show_usage_guide():
    st.html('<div class="sb-help-steps"><div><b>01</b><strong>เลือกอุปกรณ์</strong><p>ค้นหา ดูสต็อก และเปิดรายละเอียดของสิ่งที่ต้องใช้</p></div>'
            '<div><b>02</b><strong>ส่งคำขอยืม</strong><p>ใส่ตะกร้า ระบุวันและวัตถุประสงค์ แล้วตรวจสรุปก่อนส่ง</p></div>'
            '<div><b>03</b><strong>รับและคืน</strong><p>ติดตามการอนุมัติ รับอุปกรณ์จากเจ้าหน้าที่ และแจ้งคืนเมื่อใช้เสร็จ</p></div></div>')
    st.caption('เลือกยืมจากหน้าอุปกรณ์และจัดรายการในตะกร้า · ประวัติและค่าปรับอยู่ในบัญชี → โปรไฟล์')
    st.markdown('**คีย์ลัด** · `Ctrl+K` / `⌘K` เปิดค้นหาเร็ว · `/` ไปช่องค้นหาอุปกรณ์ · `Esc` ปิดกล่อง')
    if st.button('เริ่มเลือกอุปกรณ์',type='primary',icon=':material/arrow_forward:'):
        navigate_to('equipment');st.rerun(scope='app')
