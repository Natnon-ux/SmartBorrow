# หน้าที่: กฎแบบการ์ดสำหรับผู้ใช้ทั่วไป แอดมินไม่ต้องรับทราบ
"""Usage rules shown once per authenticated session before entering the app."""
import streamlit as st
from html import escape
from auth import get_current_user,logout_user
from web_ui import render_brand

RULES=(
    ('ส่งคำขอยืมก่อนรับอุปกรณ์','เลือกจำนวน วันใช้งานและวันคืนให้ถูกต้อง เลือกวันล่วงหน้าได้ในคำขอเดียว'),
    ('แนบเอกสาร PDF ทุกคำขอ','ดาวน์โหลด Word กรอกข้อมูลและลายเซ็นผู้ยืม บันทึกเป็น PDF แล้วแนบให้เจ้าหน้าที่ตรวจ'),
    ('รออนุมัติก่อนรับอุปกรณ์','รับอุปกรณ์จากเจ้าหน้าที่ และตรวจสภาพร่วมกันก่อนนำไปใช้งาน'),
    ('ดูแลและคืนให้ตรงเวลา','รอเจ้าหน้าที่ตรวจรับเพื่อปิดรายการ หากชำรุด สูญหาย หรือคืนไม่ทัน ให้แจ้งเจ้าหน้าที่'),
    ('ค่าปรับและหลักฐานชำระ','คืนช้าคิดตามอัตราที่บันทึกตอนส่งมอบ แนบสลิปแล้วรอเจ้าหน้าที่ตรวจ หากไม่ผ่านให้ส่งใหม่'),
    ('รักษาบัญชีของตัวเอง','ไม่แชร์รหัสผ่าน หากลืมรหัสให้ติดต่อเจ้าหน้าที่ผ่านช่องทางช่วยเหลือ'),
)

def rules_html():
    cards=''.join(f'<li class="sb-usage-rule"><span class="sb-usage-rule-number" aria-hidden="true">{index}</span>'
                  f'<div><h3>{escape(title)}</h3><p>{escape(body)}</p></div></li>'
                  for index,(title,body) in enumerate(RULES,1))
    return '<ol class="sb-usage-rules-grid" aria-label="กฎการใช้งาน 6 ข้อ">'+cards+'</ol>'

def rules_accepted(user):
    return st.session_state.get('usage_rules_accepted_for')==(user['id'],user.get('auth_version',0))

@st.dialog('กฎการใช้งาน SmartBorrow',width='large',dismissible=False,icon=':material/policy:')
def show_usage_rules(database_path):
    user=get_current_user(database_path)
    if user is None:
        st.rerun(scope='app')
        return
    if user['role']=='admin':
        st.rerun(scope='app')
        return
    with st.container(key='usage_rules_panel',gap='small'):
        st.html('<p class="sb-usage-intro">อ่าน 6 ข้อนี้ก่อนเริ่มยืม เพื่อให้อุปกรณ์พร้อมสำหรับทุกคน</p>')
        st.html(rules_html())
        st.caption('อ่านกฎให้ครบทั้ง 6 ข้อ แล้วติ๊กช่องรับทราบด้านล่าง')
        st.checkbox('ฉันอ่านและรับทราบกฎการใช้งานแล้ว',key='usage_rules_acknowledged')
        acknowledged=st.session_state.get('usage_rules_acknowledged',False)
        st.caption('✓ รับทราบแล้ว กดยอมรับและเข้าใช้งานได้เลย' if acknowledged else 'ยังไม่ได้รับทราบ • กรุณาติ๊กช่องด้านบนเพื่อเปิดปุ่มเข้าใช้งาน')
        accept,leave=st.columns([2,1],gap='small')
        if accept.button('ยอมรับและเข้าใช้งาน',type='primary',disabled=not acknowledged,width='stretch'):
            from login_session import accept_rules
            accept_rules(database_path)
            st.session_state['usage_rules_accepted_for']=(user['id'],user.get('auth_version',0))
            st.rerun(scope='app')
        if leave.button('ออกจากระบบ',key='usage_rules_logout',width='stretch'):
            logout_user();st.rerun(scope='app')

def require_usage_rules(user,database_path):
    if user['role']=='admin':return
    if not rules_accepted(user):
        render_brand()
        show_usage_rules(database_path)
        st.stop()
