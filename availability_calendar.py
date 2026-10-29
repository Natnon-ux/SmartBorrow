# หน้าที่: ปฏิทินช่วงวันใช้งานและรายละเอียดรายการ
"""ปฏิทินการใช้อุปกรณ์ แสดงช่วงวันโดยไม่เปิดเผยข้อมูลผู้ยืม."""
import calendar
from datetime import date, datetime, time, timedelta
import pandas as pd
import plotly.express as px
import streamlit as st
from common import DomainError, require_actor, today, thai_date, OUT_STATUSES
from database import DATABASE_PATH, database_connection
from services import catalog, validate_period
from design import style_chart
from calendar_grid import render_month_grid, month_window, event_tone
from html import escape


def calendar_events(actor_id, start, end, equipment_id=None, database_path=DATABASE_PATH):
    start, end = validate_period(start, end, future=False)
    with database_connection(database_path) as con:
        actor=require_actor(con, actor_id)
        borrowed = con.execute("SELECT b.id,b.equipment_id,b.amount,b.borrow_date,b.due_date,b.borrow_status,b.review_stage,e.equipment_name,e.equipment_code, "
                               "CASE WHEN ?='admin' OR b.user_id=? THEN u.full_name ELSE '' END booker_name "
                               "FROM borrow_transactions b JOIN equipment e ON e.id=b.equipment_id JOIN users u ON u.id=b.user_id "
                               "WHERE b.borrow_status IN ('รออนุมัติ','อนุมัติแล้ว','กำลังยืม','เกินกำหนด','รอตรวจสอบการคืน')",(actor['role'],actor_id)).fetchall()
        reservations = con.execute("SELECT r.id,r.equipment_id,r.start_date,r.end_date,r.status,e.equipment_name,e.equipment_code, "
                                   "CASE WHEN ?='admin' OR r.user_id=? THEN u.full_name ELSE '' END booker_name "
                                   "FROM reservations r JOIN equipment e ON e.id=r.equipment_id JOIN users u ON u.id=r.user_id "
                                   "WHERE r.status IN ('รออนุมัติ','ยืนยันแล้ว')",(actor['role'],actor_id)).fetchall()
    events = []
    for row in borrowed:
        last = row['due_date']
        overdue = row['borrow_status'] in OUT_STATUSES and last < today().isoformat()
        if overdue:
            last = max(last, end)
        events.append({'reference':f"ยืม #{row['id']}", 'equipment_id':row['equipment_id'],
                       'equipment_name':row['equipment_name'], 'equipment_code':row['equipment_code'],
                       'start':row['borrow_date'],'end':last,'amount':row['amount'],'status':('รออนุมัติสุดท้าย' if row['borrow_status']=='รออนุมัติ' and row['review_stage']=='รออนุมัติสุดท้าย' else row['borrow_status']),
                       'due_date':row['due_date'],'note':'เลยกำหนดและยังไม่ตรวจรับคืน' if overdue else '', 'booker_name':row['booker_name']})
    for row in reservations:
        events.append({'reference':f"จอง #{row['id']}", 'equipment_id':row['equipment_id'],
                       'equipment_name':row['equipment_name'], 'equipment_code':row['equipment_code'],
                       'start':row['start_date'],'end':row['end_date'],'amount':1,'status':'จอง · '+row['status'],'note':'','booker_name':row['booker_name']})
    return sorted([r for r in events if r['start'] <= end and r['end'] >= start
                   and (equipment_id is None or r['equipment_id']==equipment_id)], key=lambda r:(r['start'],r['equipment_code']))


def pick_day(day):
    st.session_state['calendar_day'] = day


def clear_calendar_day():
    st.session_state.pop('calendar_day', None)
    st.session_state.pop('calendar_reference', None)
    st.session_state.pop('calendar_detail_open', None)


def change_calendar_month(delta):
    month = st.session_state.get('calendar_month', today()).replace(day=1)
    index = month.year * 12 + month.month - 1 + delta
    year, zero_month = divmod(index, 12)
    if 2000 <= year <= 2100:
        st.session_state['calendar_month'] = date(year, zero_month + 1, 1)
        clear_calendar_day()


def calendar_today():
    st.session_state['calendar_month'] = today().replace(day=1)
    st.session_state['calendar_day'] = today()
    st.session_state.pop('calendar_reference', None)
    st.session_state.pop('calendar_detail_open', None)

def choose_calendar_month():
    chosen=st.session_state.get('calendar_month_picker')
    if chosen:
        st.session_state['calendar_month']=chosen.replace(day=1)
        clear_calendar_day()


def calendar_table(rows):
    return [{'รายการ':r['reference'],'อุปกรณ์':r['equipment_name'],'จำนวน':r['amount'],
             'ผู้ยืม / ผู้จอง':r.get('booker_name') or ('ผู้จองรายอื่น' if r['reference'].startswith('จอง') else 'ผู้ยืมรายอื่น'),
             'เริ่ม':thai_date(r['start']),'กำหนดคืน / สิ้นสุด':thai_date(r.get('due_date',r['end'])),
             'สถานะ':r['status'],'หมายเหตุ':r['note']} for r in rows]


def open_calendar_details(reference=''):
    st.session_state['calendar_reference']=reference
    st.session_state['calendar_detail_open']=True


def render_daily_agenda(day,rows):
    with st.container(key='calendar_agenda',border=True):
        st.caption('วันที่เลือก')
        st.subheader(thai_date(day))
        st.caption(f'{len(rows)} รายการในวันนี้')
        if not rows:
            st.info('ไม่มีรายการยืมในวันนี้')
            st.caption('เลือกวันอื่นในปฏิทินเพื่อดูรายการ')
        for row in rows[:5]:
            with st.container(key='calendar_agenda_'+row['reference'],gap='small'):
                st.html('<article class="sb-agenda-event '+event_tone(row)+'">'
                        '<span class="sb-agenda-status">'+escape(row['status'])+'</span>'
                        '<h3>'+escape(row['equipment_name'])+'</h3>'
                        +'<p>'+('ผู้จอง: ' if row['reference'].startswith('จอง') else 'ผู้ยืม: ')+escape(row.get('booker_name') or ('ผู้จองรายอื่น' if row['reference'].startswith('จอง') else 'ผู้ยืมรายอื่น'))+'</p>'+
                        '<p>'+escape(row['equipment_code']+' · '+str(row['amount'])+' ชิ้น')+'</p>'
                        '<p>'+escape(thai_date(row['start'])+' – '+thai_date(row.get('due_date',row['end'])))+'</p>'
                        '</article>')
                st.button('ดูรายละเอียด',key='calendar_details_'+row['reference'],width='stretch',type='primary',
                          on_click=open_calendar_details,args=(row['reference'],))
        if len(rows)>5:
            st.button(f'ดูทั้งหมด {len(rows)} รายการ',key='calendar_all_details',width='stretch',
                      on_click=open_calendar_details)
        st.caption('กดวันหรือรายการบนปฏิทิน เพื่อดูข้อมูลที่นี่')


@st.dialog('รายการในปฏิทิน',width='large')
def show_calendar_day(day, rows, reference):
    st.subheader(thai_date(day))
    focused=next((r for r in rows if r['reference']==reference),None)
    if focused:
        st.html('<div class="sb-calendar-detail"><strong>'+escape(focused['equipment_code']+' · '+focused['equipment_name'])+
                '</strong><p>'+escape(f"{focused['reference']} · {focused['amount']} ชิ้น · {focused['status']}")+'</p></div>')
        st.write(('ผู้จอง: ' if focused['reference'].startswith('จอง') else 'ผู้ยืม: ')+(focused.get('booker_name') or 'รายการของผู้ใช้อื่น'))
    if rows:
        st.caption(f'มีรายการยืม {len(rows)} รายการในวันที่เลือก')
        st.dataframe(calendar_table(rows),hide_index=True,width='stretch')
    else:
        st.info('ไม่มีรายการยืมในวันที่เลือก')


def render_calendar(user, database_path=DATABASE_PATH):
    st.title('ปฏิทินอุปกรณ์')
    st.caption('ดูช่วงวันใช้งานก่อนส่งคำขอยืม • Admin เห็นชื่อผู้ยืมทั้งหมด ผู้ใช้ทั่วไปเห็นชื่อเฉพาะรายการของตัวเอง')
    from navigation import navigate_to
    st.button('ยืมอุปกรณ์',key='calendar_reserve',icon=':material/event_available:',type='primary',
              on_click=navigate_to,args=('borrow',))
    st.session_state.setdefault('calendar_month', today().replace(day=1))
    first = st.session_state['calendar_month'].replace(day=1)
    with st.container(key='calendar_toolbar',horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
        st.html(f'<h2 class="sb-calendar-month">{escape(thai_date(first)[2:])}</h2>')
        with st.container(horizontal=True,width='content',gap='small',vertical_alignment='center'):
            st.button('ก่อนหน้า',icon=':material/chevron_left:',key='calendar_prev',on_click=change_calendar_month,args=(-1,))
            st.button('วันนี้',key='calendar_today',on_click=calendar_today)
            st.button('ถัดไป',icon=':material/chevron_right:',key='calendar_next',on_click=change_calendar_month,args=(1,))
            with st.popover('เลือกเดือน',icon=':material/calendar_month:'):
                # แยกค่า widget ออกจากเดือนที่ callback ของปฏิทินเปลี่ยน
                st.session_state['calendar_month_picker']=first
                st.date_input('เดือนที่ต้องการดู',value=None,key='calendar_month_picker',
                              min_value=date(2000,1,1),max_value=date(2100,12,31),on_change=choose_calendar_month)
    last = date(first.year, first.month, calendar.monthrange(first.year,first.month)[1])
    options = {r['id']:r for r in catalog(database_path=database_path,include_inactive=True)}
    selected = st.selectbox('อุปกรณ์ในปฏิทิน', [None,*options],key='calendar_equipment',
                                   format_func=lambda key:'ทุกอุปกรณ์' if key is None else options[key]['equipment_code']+' · '+options[key]['equipment_name'])
    if selected is not None:
        st.badge(f"พร้อมใช้ขณะนี้ {options[selected]['available_amount']} ชิ้น", color='red')
    window_start,window_end = month_window(first)
    grid_rows = calendar_events(user['id'],window_start,window_end,selected,database_path)
    rows = [r for r in grid_rows if r['start']<=last.isoformat() and r['end']>=first.isoformat()]
    monthly, timeline = st.tabs(['ปฏิทินรายเดือน','ช่วงเวลาการใช้'])
    day=st.session_state.get('calendar_day')
    if not day or not first<=day<=last:
        day=today() if first<=today()<=last else first
        st.session_state['calendar_day']=day
    daily_rows=[r for r in rows if r['start']<=day.isoformat()<=r['end']]
    with monthly:
        grid_column,agenda_column=st.columns([3.1,1],gap='medium')
        with grid_column,st.container(key='calendar_month_panel',border=True):
            st.html('<div class="sb-calendar-legend"><span class="borrowed">ยืม / ส่งมอบแล้ว</span>'
                    '<span class="approved">อนุมัติแล้ว</span><span class="pending">รออนุมัติ</span>'
                    '<span class="overdue">เกินกำหนด</span></div>')
            render_month_grid(first,grid_rows)
            st.caption('กดวันที่หรือแถบรายการเพื่อดูรายละเอียดด้านข้าง · กด + เพื่อเลือกรายการทั้งหมดในวันนั้น')
        with agenda_column:
            render_daily_agenda(day,daily_rows)
    with timeline:
        if rows:
            table = pd.DataFrame([dict(r, chart_start=max(r['start'],first.isoformat()),
                                       chart_end=datetime.combine(min(date.fromisoformat(r['end']),last),time.max),
                                       label=r['equipment_code']+' · '+r['equipment_name']) for r in rows])
            chart = px.timeline(table,x_start='chart_start',x_end='chart_end',y='label',color='status',
                                color_discrete_sequence=['#C82543','#471525','#E26C82','#F2A3B3','#8B4560','#B58997'],
                                hover_data={'reference':True,'amount':True,'note':True,'chart_start':False,'chart_end':False,'label':False},
                                labels={'label':'อุปกรณ์','status':'สถานะ','reference':'รายการ','amount':'จำนวน','note':'หมายเหตุ'})
            chart.update_yaxes(autorange='reversed')
            chart.update_xaxes(title='วันที่',tickformat='%d/%m')
            st.plotly_chart(style_chart(chart,height=max(300,min(650,len(options)*35))),width='stretch')
        else:
            st.info('ไม่มีรายการยืมในเดือนนี้')
    day = st.session_state.get('calendar_day')
    if day and first <= day <= last:
        visible = [r for r in rows if r['start'] <= day.isoformat() <= r['end']]
        list_title='รายการวันที่ '+thai_date(day)
    else:
        visible = rows
        list_title='รายการในเดือนนี้'
    with st.expander(f'{list_title} · {len(visible)} รายการ',icon=':material/list_alt:'):
        if day and first<=day<=last:
            st.button('ดูทั้งเดือน', on_click=clear_calendar_day)
        if visible:
            reference=st.session_state.get('calendar_reference')
            focused=next((r for r in visible if r['reference']==reference),None)
            if focused:
                st.html('<div class="sb-calendar-detail"><strong>'+escape(focused['equipment_code']+' · '+focused['equipment_name'])+
                        '</strong><p>'+escape(f"{focused['reference']} · {focused['amount']} ชิ้น · {focused['status']}")+'</p></div>')
            st.dataframe(calendar_table(visible), hide_index=True,width='stretch')
        else:
            st.info('ไม่มีรายการในช่วงที่เลือก')
    if st.session_state.pop('calendar_detail_open',False) and day and first<=day<=last:
        show_calendar_day(day,visible,st.session_state.get('calendar_reference',''))
    with st.expander('อ่านสถานะในปฏิทิน'):
        st.write('คำขอรออนุมัติยังไม่กันสต็อก จำนวนพร้อมใช้ยึดสต็อกจริง และจะคืนเมื่อเจ้าหน้าที่ตรวจรับ ปฏิทินแสดงช่วงวันตามคำขอ')
        st.write('รายการเกินกำหนดที่ยังไม่ตรวจรับจะแสดงต่อเนื่องในปฏิทิน โดยรายละเอียดแสดงกำหนดคืนเดิม')
