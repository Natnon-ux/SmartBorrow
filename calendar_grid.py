# หน้าที่: เตรียมข้อมูลปฏิทินและเรียกหน้าตา JavaScript
"""ข้อมูลปฏิทินและ component รายเดือน โดยส่งเฉพาะข้อมูลการใช้อุปกรณ์."""
from datetime import date, timedelta
from pathlib import Path
from hashlib import sha256
import streamlit as st
from common import today, thai_date

UI_DIR = Path(__file__).resolve().parent / 'ui'
PUBLIC_EVENT_FIELDS = ('reference', 'equipment_name', 'equipment_code', 'amount', 'status', 'note', 'booker_name')


def month_window(month):
    first = month.replace(day=1)
    start = first - timedelta(days=first.weekday())
    return start, start + timedelta(days=41)


def event_tone(event):
    if event['status'] == 'เกินกำหนด' or event.get('note'):
        return 'overdue'
    if event['status'].startswith('จอง'):
        return 'reserved'
    if event['status'].startswith('รออนุมัติ'):
        return 'pending'
    if event['status'] == 'อนุมัติแล้ว':
        return 'approved'
    return 'borrowed'


def calendar_payload(month, rows, selected=None, current=None):
    first = month.replace(day=1)
    start, _ = month_window(first)
    current = current or today()
    days = []
    for offset in range(42):
        day = start + timedelta(days=offset)
        active = [r for r in rows if r['start'] <= day.isoformat() <= r['end']]
        events = [dict({k: r.get(k, '') for k in PUBLIC_EVENT_FIELDS}, tone=event_tone(r)) for r in active]
        priority={'reserved':0,'pending':1,'approved':2,'borrowed':3,'overdue':4}
        events.sort(key=lambda event:(priority[event['tone']],event['equipment_code'],event['reference']))
        days.append({'date': day.isoformat(), 'number': day.day, 'label': thai_date(day),
                     'in_month': day.month == first.month and day.year == first.year,
                     'is_today': day == current, 'selected': day == selected, 'events': events})
    return {'title': thai_date(first)[2:], 'weekdays': ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์'],
            'days': days}


def validated_selection(value, month):
    if not isinstance(value, dict) or not isinstance(value.get('day'), str):
        return None
    try:
        day = date.fromisoformat(value['day'])
    except ValueError:
        return None
    first, last = month_window(month)
    if not first <= day <= last or not 2000 <= day.year <= 2100:
        return None
    reference = value.get('reference', '')
    if not isinstance(reference, str) or len(reference) > 80:
        return None
    return day, reference


def selected_from_calendar():
    state = st.session_state.get('calendar_grid', {})
    value = state.get('selection') if isinstance(state, dict) else None
    selected = validated_selection(value, st.session_state.get('calendar_month', today()))
    if selected:
        day, reference = selected
        st.session_state['calendar_day'] = day
        st.session_state['calendar_reference'] = reference
        st.session_state['calendar_month'] = day.replace(day=1)
        st.session_state.pop('calendar_detail_open',None)


def _month_component(css,js):
    # ลงทะเบียนกับ runtime ปัจจุบันทุกครั้ง ไม่เก็บ callable จาก runtime เก่า
    version=sha256((css+js).encode('utf-8')).hexdigest()[:12]
    return st.components.v2.component('smartborrow_month_calendar_'+version,
        html='<div class="sb-calendar" role="grid"></div>',
        css=css,js=js)


def render_month_grid(month, rows):
    component=_month_component((UI_DIR/'calendar.css').read_text(encoding='utf-8'),
                               (UI_DIR/'calendar.js').read_text(encoding='utf-8'))
    component(key='calendar_grid', data=calendar_payload(month, rows, st.session_state.get('calendar_day')),
              on_selection_change=selected_from_calendar)
