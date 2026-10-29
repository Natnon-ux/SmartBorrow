# หน้าที่: เครื่องมือ URL และ QR เดิมที่ส่วนตั้งค่ายังใช้
"""STEP 14: QR เปิดรายละเอียดอุปกรณ์ และแผ่นป้าย PDF จาก Python."""
from io import BytesIO
from urllib.parse import urlencode, urlsplit, urlunsplit
import qrcode
from PIL import Image, ImageDraw
import streamlit as st
from image_generator import load_logo_font
from common import DomainError

DEFAULT_BASE_URL = 'http://127.0.0.1:8501'

def validate_base_url(value):
    parts = urlsplit(str(value).strip())
    if parts.scheme not in {'http','https'} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise DomainError('URL ต้องเป็น http หรือ https และไม่มีรหัสผ่าน query หรือ fragment')
    try:
        parts.port
    except ValueError as error:
        raise DomainError('พอร์ตใน URL ไม่ถูกต้อง') from error
    return urlunsplit(parts).rstrip('/')

def equipment_url(code, base_url=DEFAULT_BASE_URL):
    return validate_base_url(base_url) + '/?' + urlencode({'equipment':code})

def qr_png(code, base_url=DEFAULT_BASE_URL):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(equipment_url(code, base_url))
    qr.make(fit=True)
    image = qr.make_image(fill_color='#12345B', back_color='white').convert('RGB')
    output = BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()

def label_pdf(code, base_url=DEFAULT_BASE_URL):
    page = Image.new('RGB', (1240, 1754), 'white')
    draw = ImageDraw.Draw(page)
    draw.text((620,200), 'SmartBorrow', font=load_logo_font(64), fill='#12345B', anchor='mm')
    qr = Image.open(BytesIO(qr_png(code,base_url)))
    qr.thumbnail((820,820))
    page.paste(qr, ((1240-qr.width)//2,400))
    draw.text((620,1280), str(code), font=load_logo_font(48), fill='#12345B', anchor='mm')
    output = BytesIO()
    page.save(output, 'PDF', resolution=150)
    return output.getvalue()

def render_qr(row, base_url=DEFAULT_BASE_URL):
    with st.expander('QR สำหรับอุปกรณ์'):
        code = row['equipment_code']
        st.image(qr_png(code,base_url), width=240)
        st.caption(f"รหัสอุปกรณ์: {code}")
        st.link_button('เปิดรายละเอียดจาก QR', equipment_url(code,base_url))
        st.download_button('ดาวน์โหลด QR (PNG)', qr_png(code,base_url), file_name=f'QR-{row["id"]}.png', mime='image/png', key=f'qr_png_{row["id"]}')
        st.download_button('ดาวน์โหลดป้ายสำหรับพิมพ์ (PDF)', label_pdf(code,base_url), file_name=f'QR-{row["id"]}.pdf', mime='application/pdf', key=f'qr_pdf_{row["id"]}')
        st.caption('เปิด PDF แล้วสั่งพิมพ์ ขณะใช้ URL localhost อุปกรณ์ที่สแกนต้องเปิดระบบบนเครื่องนี้ได้')
