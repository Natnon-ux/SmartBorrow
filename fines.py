# หน้าที่: คำนวณและบันทึกสถานะค่าปรับ
"""ค่าปรับคืนเกินกำหนดเก็บเป็นสตางค์และบันทึกผู้ดำเนินการ."""
from datetime import date
from decimal import Decimal, InvalidOperation
from common import DomainError, MANAGER_ROLES, require_actor, today, utc_now, action, render_transaction
from database import DATABASE_PATH, database_connection
import streamlit as st


def money_cents(value):
    try:
        number = Decimal(str(value))
        cents = number * 100
        if not number.is_finite() or number < 0 or number > 1000000 or cents != cents.to_integral_value():
            raise ValueError()
        return int(cents)
    except (InvalidOperation, ValueError, TypeError):
        raise DomainError('ระบุจำนวนเงิน 0–1,000,000 บาท และทศนิยมไม่เกิน 2 ตำแหน่ง') from None


def configured_rate(con):
    row = con.execute("SELECT value FROM app_settings WHERE key='fine_rate_cents'").fetchone()
    return int(row['value']) if row else 0


def save_fine_rate(actor_id, baht, database_path=DATABASE_PATH):
    rate = money_cents(baht)
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        require_actor(con, actor_id, {'admin'})
        con.execute("INSERT INTO app_settings(key,value) VALUES('fine_rate_cents',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(rate),))


def fine_estimate(row, returned_on=None):
    end = date.fromisoformat(str(returned_on or row.get('return_date') or today()))
    days = max(0, (end - date.fromisoformat(row['due_date'])).days)
    return {'days': days, 'amount_cents': days * row['amount'] * row.get('fine_rate_cents', 0)}


def resolve_fine(actor_id, transaction_id, status, note='', database_path=DATABASE_PATH):
    if status not in {'ชำระแล้ว', 'ยกเว้น'} or not str(note).strip():
        raise DomainError('ระบุสถานะและหมายเหตุ เช่น เลขที่ใบเสร็จหรือเหตุผลยกเว้น')
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        require_actor(con, actor_id, MANAGER_ROLES)
        row = con.execute('SELECT * FROM borrow_transactions WHERE id=?', (transaction_id,)).fetchone()
        if row is None or row['borrow_status'] != 'คืนแล้ว' or row['fine_status'] != 'ค้างชำระ':
            raise DomainError('บันทึกได้เฉพาะค่าปรับค้างชำระของรายการที่คืนแล้ว')
        if status=='ชำระแล้ว' and row['payment_review']=='รอตรวจสอบ':
            from fine_payments import slip_file
            slip_file(row['payment_slip'])
        con.execute('UPDATE borrow_transactions SET fine_status=?,fine_note=?,fine_resolved_by=?,fine_resolved_at=? WHERE id=?',
                    (status, str(note).strip(), actor_id, utc_now(), transaction_id))
        if status=='ชำระแล้ว' and row['payment_review']=='รอตรวจสอบ':
            con.execute("UPDATE borrow_transactions SET payment_review='ยืนยันแล้ว' WHERE id=?",(transaction_id,))


def render_fines(user, database_path=DATABASE_PATH):
    from services import transactions
    st.title('ค่าปรับ')
    st.caption('ยืมฟรี · ค่าปรับเกินกำหนด = จำนวนชิ้น × วันที่เกินกำหนด × อัตราตอนส่งมอบ')
    st.caption('โอนเงินและแนบสลิปเพื่อให้เจ้าหน้าที่ตรวจสอบการชำระค่าปรับ')
    rows = transactions(user['id'], database_path)
    due = [r for r in rows if r['fine_status'] == 'ค้างชำระ']
    st.metric('ค่าปรับค้างชำระ', f"{sum(r['fine_amount_cents'] for r in due)/100:,.2f} บาท")
    active = [r for r in rows if r['borrow_status'] in {'กำลังยืม','เกินกำหนด','รอตรวจสอบการคืน'} and fine_estimate(r)['amount_cents']]
    if active:
        st.subheader('ประมาณการจนถึงวันนี้')
        st.dataframe([{'รายการ':r['id'],'อุปกรณ์':r['equipment_name'],'ผู้ยืม':r['full_name'],
                       'วันเกินกำหนด':fine_estimate(r)['days'],'ประมาณการ (บาท)':fine_estimate(r)['amount_cents']/100}
                      for r in active], hide_index=True, width='stretch')
    settled = [r for r in rows if r['fine_amount_cents'] > 0]
    if not settled:
        st.info('ยังไม่มีค่าปรับที่ตรวจรับแล้ว')
        return
    st.dataframe([{'รายการ':r['id'],'อุปกรณ์':r['equipment_name'],'ผู้ยืม':r['full_name'],
                   'วันเกินกำหนด':r['fine_days'],'ค่าปรับ (บาท)':r['fine_amount_cents']/100,
                   'สถานะ':r['fine_status'],'หมายเหตุ':r['fine_note']} for r in settled], hide_index=True, width='stretch')
    from fine_payments import render_payments
    render_payments(user,due,database_path)
    if user['role'] in MANAGER_ROLES and due:
        options = {r['id']:r for r in due}
        selected = st.selectbox('รายการค่าปรับค้างชำระ', list(options), format_func=lambda key:f"#{key} · {options[key]['full_name']} · {options[key]['equipment_name']}")
        render_transaction(options[selected])
        with st.form('resolve_fine'):
            status = st.radio('ดำเนินการ', ['ชำระแล้ว','ยกเว้น'], horizontal=True)
            note = st.text_input('เลขที่ใบเสร็จ / เหตุผลยกเว้น')
            confirmed = st.checkbox('ตรวจสอบการชำระหรืออนุมัติยกเว้นแล้ว')
            if st.form_submit_button('บันทึกค่าปรับ', type='primary'):
                if not confirmed:
                    st.error('กรุณายืนยันการตรวจสอบก่อนบันทึก')
                else:
                    action(resolve_fine, user['id'], selected, status, note, database_path, success='บันทึกสถานะค่าปรับแล้ว')
