# หน้าที่: เครื่องมือร่วม วันที่ไทย สิทธิ์ รูปและข้อความผลลัพธ์
"""เครื่องมือร่วม: วันที่ไทย การอ่านข้อมูล และข้อความผลการทำงาน."""
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sqlite3
from io import BytesIO
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
import streamlit as st
from database import DATABASE_PATH, PROJECT_DIR, database_connection

TIMEZONE = ZoneInfo("Asia/Bangkok")
MANAGER_ROLES = {"teacher", "staff", "admin"}
HELD_STATUSES = ("อนุมัติแล้ว", "กำลังยืม", "เกินกำหนด", "รอตรวจสอบการคืน")
OUT_STATUSES = ("กำลังยืม", "เกินกำหนด", "รอตรวจสอบการคืน")
USAGE_STATUSES = (*HELD_STATUSES, "คืนแล้ว")

class DomainError(ValueError):
    """ข้อมูลหรือการดำเนินการไม่ผ่านกฎของระบบ."""

def today() -> date:
    return datetime.now(TIMEZONE).date()

def utc_now() -> str:
    from datetime import timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def thai_date(value) -> str:
    if not value:
        return "—"
    current = date.fromisoformat(str(value)[:10])
    months = ("มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
              "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม")
    return f"{current.day} {months[current.month - 1]} {current.year + 543}"

def thai_month(value):
    year,month=map(int,str(value).split('-'))
    labels=('ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.')
    return f'{labels[month-1]} {year+543}'

def require_actor(connection, user_id: int, roles=None, *, allow_executive=False) -> dict:
    user = connection.execute("SELECT id,full_name,role,status,executive_title FROM users WHERE id=?", (user_id,)).fetchone()
    if user is None or user["status"] != "active" or (roles is not None and user["role"] not in roles):
        raise DomainError("คุณไม่มีสิทธิ์ดำเนินการนี้ หรือบัญชีถูกปิดใช้งาน")
    if roles is not None and user['executive_title'] and not allow_executive:
        raise DomainError('บัญชีผู้บริหารใช้พิจารณาคำขอและดูข้อมูลเท่านั้น')
    return dict(user)

def query_rows(sql: str, params=(), database_path=DATABASE_PATH) -> list[dict]:
    with database_connection(database_path) as connection:
        return [dict(row) for row in connection.execute(sql, params)]

def image_path(value: str | None) -> Path:
    fallback = PROJECT_DIR / "assets/equipment/placeholder.png"
    path = (PROJECT_DIR / (value or "")).resolve()
    return path if path.is_relative_to(PROJECT_DIR.resolve()) and path.is_file() else fallback

def action(function, *args, success="บันทึกสำเร็จ", **kwargs):
    try:
        result = function(*args, **kwargs)
    except (DomainError, ValueError) as error:
        st.error(str(error))
        return None
    except sqlite3.IntegrityError:
        st.error("ข้อมูลซ้ำหรือไม่ถูกต้อง กรุณาตรวจรหัสและข้อมูลที่กรอก")
        return None
    except (sqlite3.Error, OSError):
        st.error("ไม่สามารถบันทึกข้อมูลได้ กรุณาลองอีกครั้ง")
        return None
    st.session_state["flash_message"] = success
    st.rerun()

def show_flash():
    # Reserve one root position even when there is no message; later pages keep their delta paths.
    slot = st.empty()
    message = st.session_state.pop("flash_message", None)
    if message:
        st.toast('**ดำเนินการสำเร็จ**\n\n'+str(message), icon=':material/check_circle:',duration='long')

def render_transaction(row, actor_id=None, database_path=DATABASE_PATH,*,show_downloads=True):
    from borrow_requests import request_code, document_file, validate_document_url
    st.subheader(f"#{row['id']} · {row['equipment_name']}")
    st.caption('ใบคำขอ '+request_code(row))
    from web_ui import loan_summary_html,loan_progress_html
    st.html(loan_summary_html(row))
    if row.get('decision_note'):
        st.info('เหตุผลหรือหมายเหตุการพิจารณา: '+row['decision_note'])
    if row.get('document_reviewed_by') or row.get('final_approved_by'):
        with database_connection(database_path) as review_con:
            names={r['id']:r['full_name'] for r in review_con.execute('SELECT id,full_name FROM users WHERE id IN (?,?)',
                   (row.get('document_reviewed_by'),row.get('final_approved_by')))}
        if row.get('document_reviewed_by'):
            st.caption('ตรวจเอกสารโดย '+names.get(row['document_reviewed_by'],'—')+' · '+str(row.get('document_reviewed_at') or ''))
        if row.get('final_approved_by'):
            st.caption('อนุมัติสุดท้ายโดย '+names.get(row['final_approved_by'],'—')+' · '+str(row.get('final_approved_at') or ''))
    progress=loan_progress_html(row)
    if progress:st.html(progress)
    if row.get('document_url') and show_downloads:
        st.link_button('เปิดเอกสาร Google Drive / Docs',validate_document_url(row['document_url']),icon=':material/description:')
    if row.get('document_path') and show_downloads:
        try:
            path=document_file(row['document_path'])
            st.download_button('ดาวน์โหลด PDF ที่ผู้ยืมส่ง' if path.suffix=='.pdf' else 'ดาวน์โหลดเอกสารแนบ',path.read_bytes(),file_name='เอกสาร-'+request_code(row)+path.suffix,
                               mime='application/pdf' if path.suffix=='.pdf' else 'image/png',key=f"document_{row['id']}")
        except (DomainError,OSError):
            st.warning('ไม่พบไฟล์เอกสารแนบ กรุณาติดต่อเจ้าหน้าที่')
    if row.get('fine_amount_cents',0):
        st.write(f"ค่าปรับ: {row['fine_amount_cents']/100:,.2f} บาท · {row['fine_status']}")
        if row.get('fine_resolved_at'):
            st.caption(f"ผู้บันทึก #{row['fine_resolved_by']} · {row['fine_resolved_at']} · {row['fine_note']}")

def save_upload(upload, category="equipment") -> str | None:
    """ถอดรหัสรูปและบันทึก PNG ด้วยชื่อสุ่ม ไม่ใช้ชื่อไฟล์ที่ผู้ใช้อัปโหลด."""
    if upload is None:
        return None
    content = upload if isinstance(upload, bytes) else upload.getvalue()
    if len(content) > 5 * 1024 * 1024:
        raise DomainError("รูปต้องมีขนาดไม่เกิน 5 MB")
    if category not in {"equipment", "conditions", "profile", "maintenance", "documents"}:
        raise DomainError("ประเภทไฟล์ไม่ถูกต้อง")
    try:
        with Image.open(BytesIO(content)) as original:
            if original.format not in {"PNG", "JPEG", "WEBP"} or original.width * original.height > 20_000_000:
                raise DomainError("กรุณาใช้ภาพ PNG, JPEG หรือ WebP ขนาดไม่เกิน 20 ล้านพิกเซล")
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((1600, 1600))
            directory = PROJECT_DIR / "data/uploads" / category
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{uuid4().hex}.png"
            image.save(path, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise DomainError("ไม่สามารถอ่านรูปนี้ได้ กรุณาเลือกไฟล์ภาพที่ถูกต้อง") from error
    return path.relative_to(PROJECT_DIR).as_posix()

def validate_evidence(value):
    if not isinstance(value, str) or not value:
        raise DomainError("กรุณาถ่ายรูปหรืออัปโหลดรูปสภาพอุปกรณ์")
    candidate = (PROJECT_DIR / value).resolve()
    if not candidate.is_relative_to(PROJECT_DIR.resolve()) or not candidate.is_file():
        raise DomainError("ไม่พบรูปสภาพอุปกรณ์")
    try:
        with Image.open(candidate) as image:
            image.verify()
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise DomainError("รูปสภาพอุปกรณ์ไม่ถูกต้อง") from error

def evidence_input(label, key):
    source = st.radio("แหล่งรูปภาพ", ["อัปโหลดรูป", "ถ่ายรูป"], horizontal=True, key=f"source_{key}")
    if source == "ถ่ายรูป":
        return st.camera_input(label, key=f"camera_{key}")
    return st.file_uploader(label + " (ไม่เกิน 5 MB)", type=["png", "jpg", "jpeg", "webp"], key=f"upload_{key}", max_upload_size=5)
