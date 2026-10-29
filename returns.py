# หน้าที่: แจ้งคืนพร้อมรูปและตรวจรับอุปกรณ์
"""STEP 12: แจ้งคืนและตรวจรับ พร้อมหลักฐานก่อน/หลังใช้งาน."""
import streamlit as st
from common import MANAGER_ROLES, action, render_transaction, evidence_input, save_upload, DomainError, image_path,thai_date,today
from datetime import date
from html import escape
from database import DATABASE_PATH
from services import transactions, request_return, confirm_return
from fines import fine_estimate
from loan_workspace import focus_loan_choice


def return_empty(title,message,key):
    from navigation import navigate_to
    with st.container(key=key,border=True):
        st.html('<div class="sb-return-empty-icon" aria-hidden="true">verified_user</div>')
        st.subheader(title)
        st.caption(message)
        with st.container(horizontal=True,horizontal_alignment='center',gap='small'):
            st.button('เลือกอุปกรณ์',key=key+'_equipment',icon=':material/inventory_2:',
                      on_click=navigate_to,args=('equipment',))
            st.button('ดูประวัติ',key=key+'_history',icon=':material/history:',
                      on_click=navigate_to,args=('history',))


def return_summary(row):
    st.html('<div class="sb-return-selected"><strong>'+escape(row['equipment_name'])+'</strong>'
            '<span>'+escape(row['equipment_code']+' · '+str(row['amount'])+' ชิ้น')+'</span>'
            '<p>กำหนดคืน '+escape(thai_date(row['due_date']))+'</p></div>')


def days_before_due(row):
    """จำนวนวันที่เหลือ ใช้สื่อสารการคืนก่อนกำหนด ไม่ปิดกั้นวันแจ้งคืน."""
    return max(0,(date.fromisoformat(row['due_date'])-today()).days)

def render_returns(user, database_path=DATABASE_PATH):
    st.title("คืนอุปกรณ์")
    st.caption("คืนก่อนกำหนดได้ทันทีหลังรับอุปกรณ์ · ส่งรูปและสภาพหลังใช้ แล้วนำส่งเจ้าหน้าที่ตรวจรับ")
    records = transactions(user["id"], database_path)
    loans = {r["id"]: r for r in records if r["borrow_status"] in {"กำลังยืม", "เกินกำหนด"}}
    waiting = {r["id"]: r for r in records if r["borrow_status"] == "รอตรวจสอบการคืน"}
    completed=sum(r['borrow_status']=='คืนแล้ว' for r in records)
    with st.container(key='return_summary',horizontal=True,gap='small'):
        for label,value in [('ต้องแจ้งคืน',len(loans)),('รอตรวจรับ',len(waiting)),('คืนเรียบร้อย',completed)]:
            with st.container(width='stretch'):
                st.metric(label,value,border=True)
    request_tab, check_tab = st.tabs(["แจ้งคืน", "รายการรอตรวจรับ"],key='return_stage',on_change='rerun')
    with request_tab:
        if not loans:
            return_empty('ไม่มีอุปกรณ์ค้างแจ้งคืน',
                         'รายการที่แจ้งคืนแล้วอยู่ในแท็บรอตรวจรับ' if waiting else 'ตอนนี้ไม่มีรายการที่ต้องแจ้งคืน ดูรายการที่ผ่านมาได้ในประวัติ',
                         'return_empty_request')
        else:
            form,guide=st.columns([3,1],gap='medium')
            with form,st.container(key='return_request_panel',border=True):
                st.subheader('เลือกและแจ้งคืนอุปกรณ์')
                focus_loan_choice(loans,'return_loan','return')
                selected = st.selectbox("รายการที่ต้องการคืน", list(loans),key='return_loan', format_func=lambda key: f"#{key} · {loans[key]['equipment_name']} · {loans[key]['full_name']}")
                return_summary(loans[selected])
                early_days=days_before_due(loans[selected])
                if early_days:
                    st.info(f'คืนก่อนกำหนดได้ · เหลืออีก {early_days} วันถึงกำหนดคืน ส่งคำขอได้เลยโดยไม่ต้องรอครบวัน',icon=':material/event_available:')
                with st.expander('ข้อมูลใบยืมและเอกสาร',icon=':material/description:'):
                    render_transaction(loans[selected], user['id'], database_path)
                photo = evidence_input("รูปสภาพหลังใช้งาน", f"after_{selected}")
                condition = st.selectbox("สภาพหลังใช้งาน", ["ปกติ", "ชำรุด", "สูญหาย"])
                note = st.text_area("หมายเหตุการคืน",placeholder='เช่น อุปกรณ์มีรอยหรืออุปกรณ์เสริมที่ต้องแจ้งเจ้าหน้าที่')
                if st.button("ส่งคำขอคืนก่อนกำหนด" if early_days else "ส่งคำขอคืน", type="primary",width='stretch',icon=':material/assignment_return:'):
                    try:
                        image = save_upload(photo, "conditions")
                    except DomainError as error:
                        st.error(str(error))
                    else:
                        action(request_return, user["id"], selected, condition, image, note, database_path, success="ส่งคำขอคืนแล้ว กรุณานำอุปกรณ์ให้เจ้าหน้าที่ตรวจรับ")
            with guide,st.container(key='return_guide',border=True):
                st.subheader('คืนอย่างไร')
                st.html('<ol class="sb-return-steps"><li><span>1</span><div><strong>ตรวจอุปกรณ์</strong><p>เช็กจำนวนและอุปกรณ์เสริมให้ครบ</p></div></li>'
                        '<li><span>2</span><div><strong>ส่งรูปหลังใช้งาน</strong><p>ระบุสภาพและหมายเหตุ แล้วส่งคำขอคืน</p></div></li>'
                        '<li><span>3</span><div><strong>นำส่งเจ้าหน้าที่</strong><p>รอตรวจรับก่อนสถานะเปลี่ยนเป็นคืนแล้ว</p></div></li></ol>')
    with check_tab:
        if not waiting:
            return_empty('ไม่มีรายการรอตรวจรับ','รายการจะปรากฏที่นี่หลังผู้ยืมส่งคำขอคืน','return_empty_waiting')
        else:
            with st.container(key='return_inspection_panel',border=True):
                st.subheader('เปรียบเทียบสภาพและตรวจรับ')
                focus_loan_choice(waiting,'return_waiting','return')
                selected = st.selectbox("รายการรอตรวจรับ", list(waiting),key='return_waiting', format_func=lambda key: f"#{key} · {waiting[key]['full_name']} · {waiting[key]['equipment_name']}")
                row = waiting[selected]
                return_summary(row)
                with st.expander('ข้อมูลใบยืมและเอกสาร',icon=':material/description:'):
                    render_transaction(row, user['id'], database_path)
                left, right = st.columns(2)
                left.image(str(image_path(row["before_image"])), caption=f"ก่อนใช้ · {row['condition_before']}", width="stretch")
                right.image(str(image_path(row["after_image"])), caption=f"หลังใช้ · {row['condition_after']}", width="stretch")
                st.write(f"หมายเหตุ: {row['return_note'] or '—'}")
                fine=fine_estimate(row)
                st.info(f"เกินกำหนด {fine['days']} วัน · อัตรา {row['fine_rate_cents']/100:,.2f} บาท/ชิ้น/วัน · ค่าปรับเมื่อตรวจรับวันนี้ {fine['amount_cents']/100:,.2f} บาท")
                if row["condition_after"] != "ปกติ":
                    st.warning("จำนวนที่ชำรุดหรือสูญหายจะถูกกันออกจากสต็อกพร้อมใช้ และสร้างประวัติซ่อมบำรุง")
                if user["role"] in MANAGER_ROLES:
                    confirmed = st.checkbox("ตรวจรับอุปกรณ์และตรวจสภาพจริงแล้ว")
                    if st.button("ยืนยันการคืน", disabled=not confirmed, type="primary",width='stretch'):
                        action(confirm_return, user["id"], selected, database_path, success="ตรวจรับและบันทึกการคืนแล้ว")
                else:
                    st.info("รอเจ้าหน้าที่ตรวจรับและยืนยันการคืน")
