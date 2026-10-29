# หน้าที่: ปิด OTP ในระบบปัจจุบัน เก็บส่วนเดิมไว้สำหรับอนาคต
"""Archived OTP functionality. Restore only through an explicit future change."""
from common import DomainError

OTP_ENABLED=False

def require_otp_enabled():
    if not OTP_ENABLED:
        raise DomainError('กรุณาติดต่อเจ้าหน้าที่เพื่อรีเซ็ตรหัสผ่าน')

def render_staff_recovery(show_contacts=True):
    import streamlit as st
    st.info('ลืมรหัสผ่าน? ติดต่อเจ้าหน้าที่หรือผู้ดูแลระบบของโรงเรียนเพื่อขอรีเซ็ตรหัสผ่าน')
    st.write('แจ้งชื่อผู้ใช้ รหัสนักเรียนหรือบุคลากร และชื่อ-นามสกุล เพื่อให้เจ้าหน้าที่ตรวจสอบตัวตนก่อนดำเนินการ')
    st.caption('เจ้าหน้าที่จะตั้งรหัสผ่านใหม่ผ่านเมนูผู้ใช้งาน โดยไม่ต้องแจ้งรหัสผ่านเดิม')
    if show_contacts:
        from support_contacts import render_support_contacts
        render_support_contacts()
