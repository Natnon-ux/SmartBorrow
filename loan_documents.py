# หน้าที่: สร้างใบยืม PDF สำหรับเจ้าหน้าที่
"""ใบยืม A4 ภาษาไทย และการอ่านใบคำขอตามสิทธิ์ของผู้ใช้งาน."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

from common import DomainError, MANAGER_ROLES, require_actor, thai_date
from database import DATABASE_PATH, PROJECT_DIR, database_connection
from borrow_requests import request_code

RED = colors.HexColor('#C51F41')
INK = colors.HexColor('#24242B')
MUTED = colors.HexColor('#656570')
PALE = colors.HexColor('#FFF3F5')
LINE = colors.HexColor('#E4E4EA')


def register_fonts():
    if 'BorrowThai' in pdfmetrics.getRegisteredFontNames():
        return
    windows = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    candidates = [
        (windows / 'tahoma.ttf', windows / 'tahomabd.ttf'),
        (PROJECT_DIR / 'assets/fonts/NotoSansThai-Regular.ttf',
         PROJECT_DIR / 'assets/fonts/NotoSansThai-Bold.ttf'),
    ]
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            pdfmetrics.registerFont(TTFont('BorrowThai', str(regular), shapable=True))
            pdfmetrics.registerFont(TTFont('BorrowThaiBold', str(bold), shapable=True))
            pdfmetrics.registerFontFamily('BorrowThai', normal='BorrowThai', bold='BorrowThaiBold')
            return
    raise DomainError('ไม่พบฟอนต์ภาษาไทยสำหรับ PDF กรุณาติดตั้ง Tahoma หรือ Noto Sans Thai')


def borrowing_pdf(rows=None, borrower=None, school='โรงเรียน / หน่วยงาน', code=None):
    """สร้างแบบฟอร์มเปล่า หรือใบคำขอที่มีข้อมูลจริง โดยไม่เขียนฐานข้อมูล."""
    register_fonts()
    rows = rows or []
    borrower = borrower or {}
    blank = not rows
    code = code or (request_code(rows[0]) if rows else '................................')
    normal = ParagraphStyle('BorrowBody', fontName='BorrowThai', fontSize=10,
                            leading=16, textColor=INK, wordWrap='CJK', shaping=True)
    small = ParagraphStyle('BorrowSmall', parent=normal, fontSize=8.5, leading=13, textColor=MUTED)
    heading = ParagraphStyle('BorrowHeading', parent=normal, fontName='BorrowThaiBold',
                             fontSize=11, leading=18, textColor=RED, spaceAfter=7)
    center = ParagraphStyle('BorrowCenter', parent=normal, alignment=TA_CENTER)

    def p(value, style=normal):
        return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)

    def field(label, value=''):
        return Paragraph('<b>' + escape(label) + '</b>  ' +
                         escape(str(value or '............................')).replace('\n', '<br/>'), normal)

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=48, leftMargin=48,
                            topMargin=38, bottomMargin=42, title='SmartBorrow - ใบยืมอุปกรณ์',
                            author='SmartBorrow')
    width = A4[0] - 96
    story = []

    def section(title):
        story.extend([Spacer(1, 10), p(title, heading)])

    title = Paragraph('ใบยืมอุปกรณ์', ParagraphStyle('BorrowTitle', parent=normal,
                      fontName='BorrowThaiBold', fontSize=22, leading=30))
    brand = Paragraph('SmartBorrow', ParagraphStyle('BorrowBrand', parent=heading,
                      fontSize=16, leading=23, alignment=2))
    header = Table([[title, brand], [p(school, small), p('ระบบบริหารจัดการยืม-คืนอุปกรณ์', small)]],
                   colWidths=[width * .57, width * .43])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    story.extend([header, Spacer(1, 12)])
    statuses = {r['borrow_status'] for r in rows}
    status = 'แบบฟอร์มสำหรับกรอกข้อมูล' if blank else (
        next(iter(statuses)) if len(statuses) == 1 else 'สถานะตามรายการด้านล่าง')
    meta = Table([[field('เลขที่ใบคำขอ', code), field('สถานะ', status)]], colWidths=[width * .57, width * .43])
    meta.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), PALE),
                             ('BOX', (0, 0), (-1, -1), .5, LINE),
                             ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                             ('TOPPADDING', (0, 0), (-1, -1), 9),
                             ('BOTTOMPADDING', (0, 0), (-1, -1), 9)]))
    story.append(meta)
    section('01  ข้อมูลผู้ยืม')
    info = Table([
        [field('ชื่อ-นามสกุล', borrower.get('full_name')), field('รหัสนักเรียน / บุคลากร', borrower.get('student_code'))],
        [field('ชั้นเรียน / หน่วยงาน', borrower.get('classroom')), field('เบอร์โทรศัพท์', borrower.get('phone'))],
    ], colWidths=[width * .57, width * .43])
    info.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0),
                             ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                             ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
    story.append(info)
    section('02  กำหนดการและวัตถุประสงค์')
    first = rows[0] if rows else {}
    period = Table([[field('วันที่ยืม', thai_date(first['borrow_date']) if rows else ''),
                     field('กำหนดคืน', thai_date(first['due_date']) if rows else '')]],
                   colWidths=[width * .57, width * .43])
    period.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.extend([period, Spacer(1, 6), field('วัตถุประสงค์', first.get('purpose'))])
    if blank:
        story.append(p('...................................................................................................................................', small))
    section('03  รายการอุปกรณ์')
    cells = [[p(x, small) for x in ['ลำดับ', 'รหัสอุปกรณ์', 'รายการอุปกรณ์', 'จำนวน', 'สถานะ / สภาพ']]]
    for i, row in enumerate(rows, 1):
        state = row['borrow_status']
        if row.get('condition_before'):
            state += '\nก่อนยืม: ' + row['condition_before']
        if row.get('condition_after'):
            state += '\nหลังคืน: ' + row['condition_after']
        cells.append([p(i, center), p(row['equipment_code']), p(row['equipment_name']),
                      p(row['amount'], center), p(state, small)])
    if blank:
        cells += [[p(i, center), '', '', '', ''] for i in range(1, 7)]
    grid = Table(cells, colWidths=[40, 72, width - 266, 42, 112], repeatRows=1,
                 minRowHeights=[29] + [32] * (len(cells) - 1))
    grid.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), PALE),
                             ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAFAFC')]),
                             ('LINEBELOW', (0, 0), (-1, -1), .5, LINE),
                             ('BOX', (0, 0), (-1, -1), .5, LINE),
                             ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                             ('TOPPADDING', (0, 0), (-1, -1), 6),
                             ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    story.append(grid)
    if rows:
        story.extend([Spacer(1, 5), p(f'รวม {len(rows)} รายการ / {sum(r["amount"] for r in rows)} ชิ้น', small)])
        total_fine = sum(r.get('fine_amount_cents', 0) for r in rows)
        if total_fine:
            story.append(p(f'ค่าปรับที่บันทึกในระบบรวม {total_fine / 100:,.2f} บาท (ดูสถานะการชำระในระบบ)', small))
        returned = sorted({thai_date(r['return_date']) for r in rows if r.get('return_date')})
        if returned:
            story.append(p('วันที่ตรวจรับคืนที่บันทึก: ' + ', '.join(returned), small))
    section('04  ข้อตกลงและการส่งมอบ')
    story.extend([
        p('• ยืมฟรี ผู้ยืมตรวจสภาพอุปกรณ์เมื่อรับ และคืนอุปกรณ์ครบตามกำหนด', small),
        p('• คืนเกินกำหนด: ค่าปรับต่อชิ้นต่อวันตามอัตราที่เจ้าหน้าที่แจ้งและบันทึก ณ วันส่งมอบ', small),
        p('• แจ้งเจ้าหน้าที่เมื่ออุปกรณ์ชำรุดหรือสูญหาย และให้เจ้าหน้าที่ตรวจรับคืน', small),
    ])
    if rows:
        rates = sorted({r.get('fine_rate_cents', 0) for r in rows
                        if r['borrow_status'] in {'กำลังยืม', 'เกินกำหนด', 'รอตรวจสอบการคืน', 'คืนแล้ว'}})
        if rates:
            story.append(p('อัตราที่บันทึกตอนส่งมอบ: ' + ' / '.join(f'{r / 100:,.2f}' for r in rates)
                           + ' บาทต่อชิ้นต่อวัน', small))
    signature = []
    for label in ['ผู้ยืม / ผู้รับอุปกรณ์', 'ผู้อนุมัติ / เจ้าหน้าที่ส่งมอบ', 'เจ้าหน้าที่ตรวจรับคืน']:
        signature.append([p('ลงชื่อ ....................................', small),
                          p(label, small), p('วันที่ ........ / ........ / ........', small)])
    signatures = Table([[signature[i][j] for i in range(3)] for j in range(3)], colWidths=[width / 3] * 3)
    signatures.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                   ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                   ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    story.append(KeepTogether([Spacer(1, 24), signatures]))

    def page(canvas, document):
        canvas.saveState()
        canvas.setFillColor(RED)
        canvas.rect(0, A4[1] - 8, A4[0], 8, fill=1, stroke=0)
        canvas.setStrokeColor(LINE)
        canvas.line(48, 34, A4[0] - 48, 34)
        canvas.setFont('BorrowThai', 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(48, 21, 'SmartBorrow | แบบฟอร์มยืมอุปกรณ์' if blank else
                          'SmartBorrow | สำเนาข้อมูล ณ เวลาดาวน์โหลด การอนุมัติให้ยึดสถานะในระบบ')
        canvas.drawRightString(A4[0] - 48, 21, f'หน้า {document.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()


def loan_document(actor_id, transaction_id, database_path=DATABASE_PATH):
    """คืน PDF ทั้งใบคำขอ เฉพาะเจ้าของรายการหรือผู้จัดการที่ยังมีสิทธิ์."""
    with database_connection(database_path) as con:
        actor = require_actor(con, actor_id)
        selected = con.execute('SELECT * FROM borrow_transactions WHERE id=?', (transaction_id,)).fetchone()
        if selected is None or (actor['role'] not in MANAGER_ROLES and selected['user_id'] != actor_id):
            raise DomainError('ไม่พบใบยืม หรือคุณไม่มีสิทธิ์ดาวน์โหลดใบยืมนี้')
        query = ('SELECT b.*,e.equipment_name,e.equipment_code FROM borrow_transactions b '
                 'JOIN equipment e ON e.id=b.equipment_id WHERE ')
        if selected['request_group']:
            rows = [dict(r) for r in con.execute(query + 'b.request_group=? ORDER BY b.id', (selected['request_group'],))]
        else:
            rows = [dict(r) for r in con.execute(query + 'b.id=?', (transaction_id,))]
        if any((r['user_id'], r['borrow_date'], r['due_date']) !=
               (selected['user_id'], selected['borrow_date'], selected['due_date']) for r in rows):
            raise DomainError('ข้อมูลในใบคำขอไม่ตรงกัน กรุณาติดต่อเจ้าหน้าที่')
        borrower = dict(con.execute('SELECT full_name,student_code,classroom,phone FROM users WHERE id=?',
                                   (selected['user_id'],)).fetchone())
        school = con.execute("SELECT value FROM app_settings WHERE key='school_name'").fetchone()
    return borrowing_pdf(rows, borrower, school['value'] if school and school['value'] else 'โรงเรียน / หน่วยงาน')


def render_document_download(row, actor_id, database_path=DATABASE_PATH):
    import streamlit as st
    try:
        data = loan_document(actor_id, row['id'], database_path)
    except DomainError as error:
        st.error(str(error))
        return
    st.download_button('ดาวน์โหลดใบยืม (PDF)', data, file_name=request_code(row) + '.pdf',
                       mime='application/pdf', icon=':material/download:', key=f"loan_pdf_{row['id']}")
