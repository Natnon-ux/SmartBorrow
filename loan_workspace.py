# หน้าที่: งานรออนุมัติ รับอุปกรณ์ และตรวจคืน
"""Borrow/return task board, using actor-filtered transactions and native actions."""
from html import escape
import streamlit as st
from common import MANAGER_ROLES,thai_date,today
from services import transactions
from navigation import navigate_to


def task_board_data(records,day):
    day=str(day)
    out=[r for r in records if r['borrow_status'] in {'กำลังยืม','เกินกำหนด'}]
    pending=[r for r in records if r['borrow_status']=='รออนุมัติ']
    pickup=sorted([r for r in records if r['borrow_status']=='อนุมัติแล้ว'],key=lambda r:(r['borrow_date'],r['id']))
    waiting=[r for r in records if r['borrow_status']=='รอตรวจสอบการคืน']
    out.sort(key=lambda r:(r['due_date'],r['id']))
    return {'pending':pending,'pickup':pickup,'out':out,'waiting':waiting,
            'due_today':sum(r['due_date']==day for r in out),
            'overdue':sum(r['due_date']<day for r in out)}


def open_loan_task(transaction_id,page,status):
    st.session_state['loan_task_id']=transaction_id
    st.session_state['loan_task_page']=page
    if page=='approvals':
        st.session_state['approval_stage']='รอรับอุปกรณ์' if status=='อนุมัติแล้ว' else 'รอพิจารณา'
    elif page=='return':
        st.session_state['return_stage']='รายการรอตรวจรับ' if status=='รอตรวจสอบการคืน' else 'แจ้งคืน'
    navigate_to(page)


def focus_loan_choice(options,key,page):
    if st.session_state.get(key) not in options:
        st.session_state.pop(key,None)
    selected=st.session_state.get('loan_task_id')
    if st.session_state.get('loan_task_page')==page and selected in options:
        st.session_state[key]=selected
        st.session_state.pop('loan_task_id',None)
        st.session_state.pop('loan_task_page',None)


def task_card(row,tone):
    status='รออนุมัติสุดท้าย' if row['borrow_status']=='รออนุมัติ' and row.get('review_stage')=='รออนุมัติสุดท้าย' else row['borrow_status']
    return ('<article class="sb-task '+tone+'"><div class="sb-task-top"><span>#'+str(row['id'])+
            '</span><b>'+escape(status)+'</b></div><strong>'+escape(row['equipment_name'])+
            '</strong><p>'+escape(row['equipment_code'])+' · '+str(row['amount'])+' ชิ้น · '+escape(row['full_name'])+
            '</p><div class="sb-task-dates"><span>รับ '+escape(thai_date(row['borrow_date']))+
            '</span><span>คืน '+escape(thai_date(row['due_date']))+'</span></div></article>')


def render_task_board(user,database_path):
    records=transactions(user['id'],database_path)
    board=task_board_data(records,today())
    manager=user['role'] in MANAGER_ROLES
    st.caption('งานที่ต้องดูแลตามสิทธิ์ของคุณ · '+thai_date(today()))
    with st.container(key='task_kpis',horizontal=True,gap='small'):
        for key,label,value in [('pending','รออนุมัติ',len(board['pending'])),('pickup','พร้อมรับ',len(board['pickup'])),
                                ('due','กำหนดคืนวันนี้',board['due_today']),('late','เกินกำหนด',board['overdue'])]:
            with st.container(key='task_metric_'+key,width='stretch'):
                st.metric(label,value,border=True)
    left,right=st.columns(2,gap='large')
    with left,st.container(key='task_pickup_lane',border=True):
        st.subheader('คำขอและรับอุปกรณ์')
        st.caption('อนุมัติคำขอ → ผู้ยืมมารับ → บันทึกการรับอุปกรณ์')
        items=[*board['pending'],*board['pickup']]
        if not items:st.info('ไม่มีคำขอหรือรายการรอรับ')
        for row in items[:4]:
            pending=row['borrow_status']=='รออนุมัติ'
            page='approvals' if manager else 'history'
            label=('พิจารณาคำขอ' if pending else 'บันทึกผู้ยืมรับอุปกรณ์') if manager else 'ดูสถานะคำขอ'
            if pending and manager:
                final=row.get('review_stage')=='รออนุมัติสุดท้าย'
                executive=user.get('executive_title','') in {'director','deputy'}
                if final!=executive:
                    page='history';label='รอผู้บริหารอนุมัติ' if final else 'รอเจ้าหน้าที่ตรวจเอกสาร'
            with st.container(key=f'task_request_item_{row["id"]}',border=True,gap='small'):
                st.html(task_card(row,'pending' if pending else 'pickup'))
                st.button(label,key=f'task_pickup_{row["id"]}',icon=':material/arrow_forward:',width='stretch',
                          on_click=open_loan_task,args=(row['id'],page,row['borrow_status']))
        if len(items)>4:st.caption(f'อีก {len(items)-4} รายการในเมนูคำขอ / รับอุปกรณ์' if manager else f'อีก {len(items)-4} รายการในประวัติ')
    with right,st.container(key='task_return_lane',border=True):
        st.subheader('คืนและตรวจรับ')
        st.caption('ผู้ยืมแจ้งคืน → เจ้าหน้าที่ตรวจสภาพ → คืนเข้าสต็อก')
        items=[*board['waiting'],*board['out']]
        if not items:st.info('ไม่มีอุปกรณ์ที่กำลังยืมหรือรอตรวจรับ')
        for row in items[:4]:
            waiting=row['borrow_status']=='รอตรวจสอบการคืน'
            late=not waiting and row['due_date']<today().isoformat()
            label=('ตรวจรับอุปกรณ์' if manager else 'ดูสถานะการคืน') if waiting else 'เปิดรายการคืน'
            # หลังบ้านตรวจรับได้เมื่อผู้ยืมแจ้งคืนแล้วเท่านั้น รายการที่ยังใช้งานเปิดดูรายละเอียดแทน
            page='history' if manager and not waiting else 'return'
            if manager and not waiting:label='ดูรายการกำลังยืม'
            with st.container(key=f'task_return_item_{row["id"]}',border=True,gap='small'):
                st.html(task_card(row,'late' if late else 'return'))
                st.button(label,key=f'task_return_{row["id"]}',icon=':material/arrow_forward:',width='stretch',
                          on_click=open_loan_task,args=(row['id'],page,row['borrow_status']))
        if len(items)>4:st.caption(f'อีก {len(items)-4} รายการในเมนูคืนอุปกรณ์')
