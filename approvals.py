# หน้าที่: ตรวจเอกสาร อนุมัติ และส่งมอบอุปกรณ์
"""STEP 10: พิจารณาคำขอยืมสำหรับครู เจ้าหน้าที่ และผู้ดูแล."""
import streamlit as st
from contextlib import nullcontext
from common import MANAGER_ROLES, action, render_transaction
from database import DATABASE_PATH
from services import transactions, decide_borrow, cancel_borrow
from services import handoff_borrow
from common import evidence_input, save_upload, DomainError
from borrow_requests import decide_group,request_code,required_document
from fines import configured_rate
from database import database_connection
from loan_workspace import focus_loan_choice

def render_approvals(user, database_path=DATABASE_PATH):
    executive=user.get('executive_title','') in {'director','deputy'}
    if executive:
        from executive_workspace import render_executive_workspace
        render_executive_workspace(user,database_path)
        return
    st.title('คำขอรออนุมัติสุดท้าย' if executive else 'คำขอและรับอุปกรณ์')
    st.caption('เจ้าหน้าที่ตรวจเอกสาร → ผอ. หรือรอง ผอ. อนุมัติสุดท้าย → ส่งมอบอุปกรณ์')
    if user["role"] not in MANAGER_ROLES:
        st.error("คุณไม่มีสิทธิ์เข้าหน้านี้")
        return
    records = transactions(user["id"], database_path)
    if executive:st.info('สิทธิ์อนุมัติสุดท้าย คนใดคนหนึ่งอนุมัติได้ โดยต้องผ่านการตรวจเอกสารก่อน')
    if executive:
        pending_tab,handoff_tab=nullcontext(),None
    else:
        pending_tab, handoff_tab = st.tabs(["รอพิจารณา", "รอรับอุปกรณ์"],key='approval_stage',on_change='rerun')
    with pending_tab:
        pending = {r["id"]: r for r in records if r["borrow_status"] == "รออนุมัติ" and
                   (r.get('review_stage')=='รออนุมัติสุดท้าย')==executive}
        if not executive:
            waiting=sum(r['borrow_status']=='รออนุมัติ' and r.get('review_stage')=='รออนุมัติสุดท้าย' for r in records)
            if waiting:st.info(f'{waiting} รายการผ่านการตรวจเอกสารแล้ว รอ ผอ. หรือรอง ผอ. อนุมัติสุดท้าย')
        if not pending:
            st.info("ไม่มีคำขอรออนุมัติ")
        else:
            focus_loan_choice(pending,'approval_pending','approvals')
            selected = st.selectbox("คำขอยืม", list(pending),key='approval_pending', format_func=lambda key: f"#{key} · {pending[key]['full_name']} · {pending[key]['equipment_name']}")
            render_transaction(pending[selected], user['id'], database_path)
            document_checked=True
            if pending[selected].get('document_path'):
                with st.expander('เปิดตรวจ PDF ใบยืม',expanded=True,icon=':material/picture_as_pdf:'):
                    try:
                        pdf=required_document(pending[selected]['document_path'])
                        st.pdf(pdf.read_bytes(),height=550,key=f'approval_pdf_{selected}')
                    except (DomainError,OSError):
                        st.error('ไม่สามารถเปิด PDF ใบยืมได้ กรุณาให้ผู้ยืมตรวจเอกสารก่อนอนุมัติ')
                        document_checked=False
                checked=st.checkbox('ตรวจข้อมูลและลายเซ็นผู้ยืมใน PDF แล้ว',key=f'approval_document_checked_{selected}')
                document_checked=document_checked and checked
            else:
                st.caption('รายการเดิมก่อนบังคับแนบ PDF ไม่มีไฟล์ใบยืม')
            group=pending[selected].get('request_group')
            grouped=[r for r in records if group and r.get('request_group')==group]
            if len(grouped)>1 and all(r['borrow_status']=='รออนุมัติ' and r.get('review_stage','')==pending[selected].get('review_stage','') for r in grouped):
                st.caption('ใบคำขอ '+request_code(pending[selected]))
                st.dataframe([{'อุปกรณ์':r['equipment_name'],'จำนวน':r['amount']} for r in grouped],hide_index=True,width='stretch')
                approve,reject=st.columns(2)
                if approve.button('อนุมัติสุดท้ายทั้งใบคำขอ' if executive else 'ผ่านการตรวจและส่งต่อทั้งใบคำขอ',type='primary',disabled=not document_checked):
                    action(decide_group,user['id'],group,True,database_path,success='อนุมัติสุดท้ายและกันสต็อกแล้ว' if executive else 'ส่งให้ ผอ. หรือรอง ผอ. อนุมัติสุดท้ายแล้ว')
                if reject.button('ไม่อนุมัติทั้งใบคำขอ'):
                    action(decide_group,user['id'],group,False,database_path,success='ปฏิเสธทุกชิ้นในใบคำขอแล้ว')
                st.caption('หรือพิจารณาเฉพาะรายการที่เลือกด้านล่าง')
            left, right = st.columns(2)
            if left.button('อนุมัติสุดท้าย' if executive else 'ผ่านการตรวจและส่งอนุมัติสุดท้าย', type="primary",disabled=not document_checked):
                action(decide_borrow, user["id"], selected, True, database_path, success='อนุมัติสุดท้ายและสำรองอุปกรณ์แล้ว' if executive else 'ส่งให้ ผอ. หรือรอง ผอ. อนุมัติสุดท้ายแล้ว')
            if right.button("ไม่อนุมัติ"):
                action(decide_borrow, user["id"], selected, False, database_path, success="ปฏิเสธคำขอแล้ว")
    if executive:return
    with handoff_tab:
        approved = {r["id"]: r for r in records if r["borrow_status"] == "อนุมัติแล้ว"}
        if not approved:
            st.info("ไม่มีรายการรอรับอุปกรณ์")
        else:
            focus_loan_choice(approved,'approval_handoff','approvals')
            selected = st.selectbox("รายการรอรับอุปกรณ์", list(approved),key='approval_handoff', format_func=lambda key: f"#{key} · {approved[key]['full_name']} · {approved[key]['equipment_name']}")
            render_transaction(approved[selected], user['id'], database_path)
            with database_connection(database_path) as con:
                rate=configured_rate(con)
            st.info(f'ยืมฟรี · หากคืนเกินกำหนด ค่าปรับ {rate/100:,.2f} บาทต่อชิ้นต่อวัน ถึงวันที่ตรวจรับจริง')
            photo = evidence_input("รูปสภาพก่อนยืม", f"before_{selected}")
            condition = st.selectbox("สภาพก่อนยืม", ["ปกติ", "มีรอยเล็กน้อย", "มีตำหนิ"])
            if st.button("ยืนยันผู้ยืมรับอุปกรณ์แล้ว", type="primary"):
                try:
                    image = save_upload(photo, "conditions")
                except DomainError as error:
                    st.error(str(error))
                else:
                    action(handoff_borrow, user["id"], selected, condition, image, database_path, success="ส่งมอบอุปกรณ์และบันทึกสภาพก่อนยืมแล้ว")
            confirmed = st.checkbox("ยืนยันยกเลิกการอนุมัติและคืนจำนวนเข้าสต็อก")
            if st.button("ยกเลิกรายการก่อนส่งมอบ", disabled=not confirmed):
                action(cancel_borrow, user["id"], selected, database_path, success="ยกเลิกและคืนจำนวนเข้าสต็อกแล้ว")
