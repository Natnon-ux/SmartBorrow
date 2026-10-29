# หน้าที่: ช่องทางติดต่อเจ้าหน้าที่
"""User-provided public support contacts for account assistance."""
import streamlit as st

def render_support_contacts():
    st.html('''<section class="sb-support-card" aria-label="ติดต่อเจ้าหน้าที่">
      <div><span class="sb-support-kicker">ช่วยเหลือและรีเซ็ตรหัสผ่าน</span>
      <h3>ติดต่อเจ้าหน้าที่</h3><p>ณัฐนนนท์ รุกขชาติ</p></div>
      <div class="sb-support-links">
        <a href="https://www.instagram.com/natnonplai/" target="_blank" rel="noopener noreferrer">Instagram · @natnonplai ↗</a>
        <a href="https://www.facebook.com/natthanon.rookkachard" target="_blank" rel="noopener noreferrer">Facebook ↗</a>
        <a href="tel:0933790701">โทร 0933790701</a>
      </div></section>''')
