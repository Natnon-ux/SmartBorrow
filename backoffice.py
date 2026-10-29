# หน้าที่: หน้าจัดการสำหรับแอดมินโดยเฉพาะ
"""Admin workspaces without public borrowing/catalog actions."""
import streamlit as st
from database import database_connection
from common import require_actor,action,render_transaction,image_path
from services import transactions,catalog,confirm_return

def require_admin(user,database_path):
    with database_connection(database_path) as con:require_actor(con,user['id'],{'admin'})

def render_admin_dashboard(user,database_path):
    require_admin(user,database_path)
    st.title('ภาพรวมหลังบ้าน')
    st.caption('ติดตามคำขอ การส่งมอบ การตรวจรับคืน และค่าปรับ')
    from loan_workspace import render_task_board
    work,overview=st.tabs(['งานหลังบ้าน','ภาพรวมระบบ'])
    with work:
        render_task_board(user,database_path)
        rows=transactions(user['id'],database_path)
        st.metric('ค่าปรับค้างชำระทั้งหมด',f"{sum(r['fine_amount_cents'] for r in rows if r['fine_status']=='ค้างชำระ')/100:,.2f} บาท")
    with overview:
        from dashboard import render_statistics
        render_statistics(user,database_path)

def render_admin_equipment(user,database_path):
    require_admin(user,database_path)
    st.title('จัดการอุปกรณ์')
    rows=catalog(database_path=database_path,include_inactive=True)
    st.dataframe([{'รหัส':r['equipment_code'],'ชื่อ':r['equipment_name'],'หมวดหมู่':r['category'],'ทั้งหมด':r['total_amount'],
                   'พร้อมใช้':r['available_amount'],'ไม่พร้อมใช้':r['unavailable_amount'],'สถานะ':r['status']} for r in rows],hide_index=True,width='stretch')
    from equipment import render_editor
    render_editor(user,database_path)

def render_admin_returns(user,database_path):
    require_admin(user,database_path)
    st.title('ตรวจรับคืนอุปกรณ์')
    rows=transactions(user['id'],database_path)
    waiting={r['id']:r for r in rows if r['borrow_status']=='รอตรวจสอบการคืน'}
    if not waiting:
        st.info('ไม่มีรายการรอตรวจรับ')
    else:
        from loan_workspace import focus_loan_choice
        focus_loan_choice(waiting,'return_waiting','return')
        selected=st.selectbox('รายการรอตรวจรับ',list(waiting),key='return_waiting',format_func=lambda key:f"#{key} · {waiting[key]['full_name']} · {waiting[key]['equipment_name']}")
        row=waiting[selected]
        render_transaction(row,user['id'],database_path)
        before,after=st.columns(2)
        before.image(str(image_path(row['before_image'])),caption='ก่อนยืม',width='stretch')
        after.image(str(image_path(row['after_image'])),caption='หลังใช้งาน',width='stretch')
        st.write('หมายเหตุ: '+(row['return_note'] or '—'))
        from fines import fine_estimate
        estimate=fine_estimate(row)
        st.info(f"เกินกำหนด {estimate['days']} วัน · ค่าปรับ {estimate['amount_cents']/100:,.2f} บาท")
        checked=st.checkbox('ตรวจรับอุปกรณ์และตรวจสภาพจริงแล้ว')
        if st.button('ยืนยันการคืน',disabled=not checked,type='primary'):
            action(confirm_return,user['id'],selected,database_path,success='ตรวจรับและบันทึกการคืนแล้ว')
    with st.expander('รายการกำลังยืมและเกินกำหนด'):
        st.dataframe([{'รายการ':r['id'],'ผู้ยืม':r['full_name'],'อุปกรณ์':r['equipment_name'],'กำหนดคืน':r['due_date'],'สถานะ':r['borrow_status']}
                      for r in rows if r['borrow_status'] in {'กำลังยืม','เกินกำหนด'}],hide_index=True,width='stretch')
