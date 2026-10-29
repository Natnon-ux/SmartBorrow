# หน้าที่: หน้าตา HTML และเรียก CSS/JavaScript
"""HTML presentation with escaped database text; actions remain server validated."""
import base64
from functools import lru_cache
from html import escape
from pathlib import Path
import mimetypes
import streamlit as st
from database import PROJECT_DIR
from design import hero_image, equipment_image
from common import thai_date,today

UI_DIR = PROJECT_DIR / 'ui'


@lru_cache(maxsize=64)
def _image_data(path, modified):
    file = Path(path)
    mime = mimetypes.guess_type(file.name)[0] or 'image/png'
    return f'data:{mime};base64,' + base64.b64encode(file.read_bytes()).decode('ascii')


def image_data(path):
    file = Path(path).resolve()
    if not file.is_relative_to(PROJECT_DIR.resolve()) or not file.is_file():
        raise ValueError('Image must be inside the project')
    return _image_data(str(file), file.stat().st_mtime_ns)


def apply_web_style():
    font=PROJECT_DIR/'assets/fonts/NotoSansThai.ttf'
    if font.is_file():
        st.html('<style>@font-face{font-family:"SmartBorrow Thai";src:url("'+
                _image_data(str(font),font.stat().st_mtime_ns)+'") format("truetype");font-weight:100 900;font-display:swap;}</style>')
    st.html(UI_DIR / 'styles.css')
    st.html(UI_DIR / 'liquid-glass.css')
    st.html(UI_DIR / 'sparkle.css')
    # ใช้ Noto Sans Thai แบบไม่มีหัวทั้งระบบ รวมถึงหน้าต่างที่เปิดนอก stApp
    st.html(UI_DIR/'typography.css')
    # This script is a trusted repository asset, never user-entered content.
    st.html('<script>' + (UI_DIR / 'interactions.js').read_text(encoding='utf-8') + '</script>',
            unsafe_allow_javascript=True)
    st.html('<script>'+(UI_DIR/'auth-carousel.js').read_text(encoding='utf-8')+'</script>',
            unsafe_allow_javascript=True)


def render_auth_carousel():
    import json
    source=PROJECT_DIR/'assets/equipment/products/sources.json'
    paths={p['code']:PROJECT_DIR/p['path'] for p in json.loads(source.read_text(encoding='utf-8'))} if source.is_file() else {}
    photos=[(paths[code],title,caption) for code,title,caption in [
            ('CAM001','Sony A7 IV','กล้องและเลนส์สำหรับทุกไอเดีย'),
            ('LEN001','Sony FE 24-70mm GM II','เลือกอุปกรณ์และวันใช้งานได้ในคำขอเดียว'),
            ('LEN002','Viltrox 50mm F1.4 Pro FE','พร้อมสร้างสรรค์ภาพในแบบของคุณ'),
            ('NB002','อุปกรณ์สำหรับการเรียน','ทำงาน นำเสนอ และเรียนรู้ร่วมกัน'),
            ('PJ001','นำเสนอผลงานของคุณ','ตรวจอุปกรณ์และรับจากเจ้าหน้าที่'),
            ('MIC001','ทุกเสียงมีความหมาย','ใช้ด้วยความใส่ใจ แล้วคืนให้พร้อมใช้ต่อ')]
            if code in paths]
    if not photos:photos=[(hero_image(),'พร้อมสำหรับทุกไอเดีย','เลือกอุปกรณ์สำหรับการเรียนและกิจกรรม')]
    photos=[p for p in photos if p[0].is_file()]
    slides=''.join(f'<figure class="sb-auth-slide" aria-hidden="{str(i!=0).lower()}">'
                   f'<img src="{image_data(path)}" alt="{escape(title,quote=True)}" draggable="false">'
                   f'<figcaption><strong>{escape(title)}</strong><span>{escape(caption)}</span></figcaption></figure>'
                   for i,(path,title,caption) in enumerate(photos))
    dots=''.join(f'<button type="button" data-slide="{i}" aria-label="แสดงภาพ{escape(title,quote=True)}" '
                 f'aria-pressed="{str(i==0).lower()}"></button>' for i,(_,title,_) in enumerate(photos))
    st.html('<section class="sb-auth-carousel is-product-carousel" data-sb-carousel data-index="0" aria-roledescription="สไลด์ภาพ" aria-label="อุปกรณ์ของ SmartBorrow">'
            '<div class="sb-auth-viewport"><div class="sb-auth-track">'+slides+'</div>'
            '<span class="sb-auth-photo-tag">อุปกรณ์พร้อมให้ยืม</span></div>'
            '<div class="sb-auth-carousel-controls"><button type="button" data-carousel="prev" aria-label="ภาพก่อนหน้า">‹</button>'
            '<div class="sb-auth-dots" aria-label="เลือกภาพ">'+dots+'</div>'
            '<button type="button" data-carousel="next" aria-label="ภาพถัดไป">›</button>'
            '<button type="button" data-carousel="pause" aria-pressed="false">หยุดสไลด์</button></div></section>')


def render_brand():
    st.html('<div class="sb-brand" aria-label="SmartBorrow">'
            '<span class="sb-brand-mark" aria-hidden="true">S</span>'
            '<span class="sb-brand-name">Smart<span>Borrow</span></span></div>', width='content')


def render_hero_visual():
    st.html(f'<div class="sb-hero-visual"><img src="{image_data(hero_image())}" '
            'alt="กล้อง คอมพิวเตอร์ ไมโครโฟน และโปรเจกเตอร์สำหรับกิจกรรมโรงเรียน">'
            '<div class="sb-visual-badge"><span aria-hidden="true"></span>ยืมฟรีทุกอุปกรณ์</div>'
            '<div class="sb-visual-caption"><small>YOUR NEXT IDEA STARTS HERE</small>'
            '<strong>พร้อมให้ไอเดียของคุณเกิดขึ้นจริง</strong></div></div>')


def dashboard_visual_html(records):
    available=sum(r['available_amount'] for r in records if r['status']=='พร้อมใช้งาน')
    day=today()
    # Decorative illustration uses local vector shapes; numbers are real stock and date.
    return ('<div class="sb-dashboard-art" aria-label="อุปกรณ์พร้อมใช้ '+str(available)+' ชิ้น">'
            '<span class="sb-art-orbit orbit-one" aria-hidden="true"></span><span class="sb-art-orbit orbit-two" aria-hidden="true"></span>'
            '<div class="sb-art-calendar"><span>สร้างสรรค์ได้ทุกวัน</span><strong>'+str(day.day)+
            '</strong><small>'+escape(thai_date(day))+'</small><div class="sb-art-dots" aria-hidden="true">'+
            '<i></i>'*7+'</div></div><div class="sb-art-stock"><span class="material-symbols-rounded" aria-hidden="true">inventory_2</span>'
            '<div><strong>'+str(available)+'</strong><small>ชิ้นพร้อมให้ยืม</small></div></div>'
            '<div class="sb-art-spark" aria-hidden="true">✦</div><div class="sb-art-tag">เลือก · ยืม · สร้างสรรค์</div></div>')


def equipment_card_html(row):
    ready = row['available_amount'] > 0 and row['status'] == 'พร้อมใช้งาน'
    stock = f"พร้อมใช้ {row['available_amount']} / {row['total_amount']} ชิ้น" if row['status']=='พร้อมใช้งาน' else row['status']
    extra = '<p class="sb-card-reservation">มีการจองล่วงหน้า</p>' if row.get('has_reservation') else ''
    tone = {'กล้อง':'rose','เลนส์':'rose','คอมพิวเตอร์':'blue','แท็บเล็ต':'blue','ไมโครโฟน':'purple',
            'ลำโพง':'purple','โปรเจกเตอร์':'amber','อุปกรณ์เสริม':'teal',
            'สายสัญญาณ':'teal','อุปกรณ์ไฟฟ้า':'amber'}.get(row['category'],'blue')
    percent=max(0,min(100,round(row['available_amount']/row['total_amount']*100))) if row['total_amount'] else 0
    return (f'<article class="sb-equipment {tone}" aria-label="{escape(row["equipment_name"], quote=True)}">'
            f'<div class="sb-card-visual{" is-product-photo" if str(row.get("image", "")).startswith("assets/equipment/products/") else ""}"><img src="{image_data(equipment_image(row))}" '
            f'alt="{escape(row["equipment_name"], quote=True)}" loading="lazy">'
            f'<span class="sb-card-code">{escape(row["equipment_code"])}</span></div>'
            f'<div class="sb-card-content"><p class="sb-card-category">{escape(row["category"])}</p>'
            f'<h3 class="sb-card-name">{escape(row["equipment_name"])}</h3>'
            f'<span class="sb-card-stock{" is-unavailable" if not ready else ""}">{escape(stock)}</span>'
            f'<div class="sb-stock-track" aria-hidden="true"><span style="width:{percent if ready else 0}%"></span></div>'
            f'<p class="sb-card-location">จัดเก็บ: {escape(str(row.get("storage_location") or "ยังไม่ระบุ"))}</p>'
            f'{extra}</div></article>')


def render_footer(school):
    import re
    footer='<footer class="sb-footer"><div><strong>SmartBorrow</strong>' \
            f'<span class="sb-footer-dot" aria-hidden="true"></span>{escape(school)}</div>' \
            '<div class="sb-footer-contact"><span class="sb-footer-contact-name">ติดต่อ ณัฐนนนท์ รุกขชาติ</span>' \
            '<div class="sb-footer-socials">'
    footer+=(''
            '<a href="tel:0933790701" aria-label="โทรหาเจ้าหน้าที่ 0933790701"><span class="sb-footer-social-icon sb-phone-icon">'
            '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.6 10.8a15.3 15.3 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.24c1.1.36 2.3.54 3.6.54a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1C10.6 21 3 13.4 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.3.18 2.5.54 3.6a1 1 0 0 1-.24 1z"/></svg></span><span>0933790701</span></a>'
            '<a href="https://www.instagram.com/natnonplai/" target="_blank" rel="noopener noreferrer" aria-label="Instagram natnonplai"><span class="sb-footer-social-icon sb-instagram-icon">'
            '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2"/><circle cx="17.5" cy="6.5" r="1.2" fill="currentColor"/></svg></span><span>Instagram</span></a>'
            '<a href="https://www.facebook.com/natthanon.rookkachard" target="_blank" rel="noopener noreferrer" aria-label="Facebook ณัฐนนนท์ รุกขชาติ"><span class="sb-footer-social-icon sb-facebook-icon">'
            '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 22v-9h3l.5-4H14V6.5c0-1.2.3-2 2-2h2V1.2C17.4 1.1 16.2 1 14.8 1 11.6 1 9.5 3 9.5 6.7V9H6v4h3.5v9z"/></svg></span><span>Facebook</span></a>'
            '</div></div></footer>')
    def svg_image(match):
        svg=match.group(0).replace('currentColor','#ffffff')
        svg=svg.replace('<svg ','<svg xmlns="http://www.w3.org/2000/svg" '+('' if 'fill="none"' in svg else 'fill="#ffffff" '),1)
        return '<img alt="" aria-hidden="true" src="data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()+'">'
    st.html(re.sub(r'<svg\b.*?</svg>',svg_image,footer,flags=re.S))


def render_workspace_header(page,role='student'):
    from navigation import menu_label, navigate_to
    with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center',gap='small'):
        st.html('<div class="sb-breadcrumb"><span>SmartBorrow</span><span aria-hidden="true">/</span>'
                f'<strong>{escape(menu_label(page,role))}</strong></div>',width='content')
        st.button('กลับภาพรวมหลังบ้าน' if role=='admin' else 'กลับหน้าแรก',key='workspace_home',icon=':material/home:',type='tertiary',
                  on_click=navigate_to,args=('dashboard' if role=='admin' else 'equipment',))


def render_borrow_steps(active):
    steps = []
    for index, label in enumerate(['เลือกอุปกรณ์', 'รายละเอียดคำขอ', 'ตรวจสอบและส่ง'], 1):
        state=' is-active' if index==active else (' is-done' if index<active else '')
        steps.append(f'<div class="sb-step{state}"><span>{index}</span><strong>{label}</strong></div>')
    st.html('<div class="sb-steps" aria-label="ขั้นตอนการยืม">'+''.join(steps)+'</div>')


def loan_summary_html(row):
    status=loan_status(row)
    tone={'รออนุมัติ':'pending','อนุมัติแล้ว':'approved','กำลังยืม':'active','เกินกำหนด':'danger',
          'รอตรวจสอบการคืน':'pending','คืนแล้ว':'complete'}.get(status,'muted')
    cells=[('ผู้ยืม',escape(row['full_name'])),('จำนวน',escape(str(row['amount']))+' ชิ้น'),
           ('วันที่ยืม',escape(thai_date(row['borrow_date']))),('กำหนดคืน',escape(thai_date(row['due_date'])))]
    fields=''.join(f'<div><span>{label}</span><strong>{value}</strong></div>' for label,value in cells)
    guidance={
        'รออนุมัติ':'รอเจ้าหน้าที่ตรวจเอกสาร ยังไม่สามารถรับอุปกรณ์ได้',
        'รออนุมัติสุดท้าย':'เอกสารผ่านแล้ว รอ ผอ. หรือรอง ผอ. อนุมัติสุดท้าย',
        'ส่งกลับตรวจเพิ่ม':'ผู้บริหารส่งกลับให้เจ้าหน้าที่ตรวจเพิ่มเติม อ่านเหตุผลด้านล่างและติดต่อเจ้าหน้าที่',
        'อนุมัติแล้ว':'ติดต่อเจ้าหน้าที่เพื่อรับอุปกรณ์ตามวันที่นัดหมาย',
        'กำลังยืม':'ใช้งานและดูแลอุปกรณ์ แจ้งคืนก่อนกำหนดได้เมื่อใช้งานเสร็จ',
        'เกินกำหนด':'นำอุปกรณ์ส่งคืนและติดต่อเจ้าหน้าที่เพื่อตรวจรับโดยเร็ว',
        'รอตรวจสอบการคืน':'แจ้งคืนแล้ว กรุณานำอุปกรณ์ให้เจ้าหน้าที่ตรวจรับ ไม่ต้องส่งคำขอซ้ำ',
        'คืนแล้ว':'เจ้าหน้าที่ตรวจรับแล้ว ตรวจค่าปรับเพิ่มเติมถ้ามี',
        'ไม่อนุมัติ':'คำขอไม่ผ่านการพิจารณา ติดต่อเจ้าหน้าที่ก่อนส่งคำขอใหม่',
        'ยกเลิก':'รายการถูกยกเลิกแล้ว สามารถเลือกอุปกรณ์เพื่อส่งคำขอใหม่ได้',
    }.get(status,'ตรวจรายละเอียดหรือติดต่อเจ้าหน้าที่')
    if status in {'รออนุมัติสุดท้าย','ส่งกลับตรวจเพิ่ม'}:tone='pending'
    return (f'<div class="sb-loan-summary"><div class="sb-status-heading"><div><span class="sb-status-eyebrow">สถานะปัจจุบัน</span>'
            f'<div class="sb-loan-status {tone}">{escape(status)}</div></div>'
            f'<div class="sb-loan-next"><strong>ขั้นตอนถัดไป</strong><span>{escape(guidance)}</span></div></div>'
            f'<div class="sb-loan-fields">{fields}</div><p><span>วัตถุประสงค์</span>'
            f'{escape(row["purpose"]).replace(chr(10), "<br>")}</p></div>')


def loan_status(row):
    if row['borrow_status']=='รออนุมัติ' and row.get('review_stage')=='ส่งกลับตรวจเพิ่ม':return 'ส่งกลับตรวจเพิ่ม'
    return 'รออนุมัติสุดท้าย' if row['borrow_status']=='รออนุมัติ' and row.get('review_stage')=='รออนุมัติสุดท้าย' else row['borrow_status']

def loan_progress_html(status):
    if isinstance(status,dict):status=loan_status(status)
    active={'รออนุมัติ':0,'ส่งกลับตรวจเพิ่ม':0,'รออนุมัติสุดท้าย':1,'อนุมัติแล้ว':2,'กำลังยืม':3,'เกินกำหนด':3,'รอตรวจสอบการคืน':4,'คืนแล้ว':5}.get(status)
    if active is None:return ''
    steps=[]
    for index,label in enumerate(['ตรวจเอกสาร','อนุมัติสุดท้าย','พร้อมรับ','กำลังยืม','ตรวจรับคืน','คืนแล้ว']):
        state='done' if index<active else ('current' if index==active else 'future')
        current=' aria-current="step"' if index==active else ''
        state_text='ผ่านแล้ว' if index<active else ('เสร็จสิ้น' if index==active==5 else ('ขั้นตอนปัจจุบัน' if index==active else 'ยังไม่ถึงขั้นตอน'))
        steps.append(f'<li class="{state}"{current}><span>{index+1}</span><div><strong>{label}</strong><small>{state_text}</small></div></li>')
    return '<ol class="sb-loan-progress" aria-label="ขั้นตอนรายการยืม">'+''.join(steps)+'</ol>'
