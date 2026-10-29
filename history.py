# หน้าที่: ประวัติการยืมและตัวกรองตามสิทธิ์
"""STEP 15: ประวัติที่จำกัดข้อมูลตามสิทธิ์ พร้อมตัวกรองและ CSV ภาษาไทย."""
from io import StringIO
import csv
from datetime import date
import streamlit as st
from common import thai_date, today, render_transaction, action, image_path
from database import DATABASE_PATH
from services import transactions, cancel_borrow
from borrow_requests import request_code

def filter_history(rows, search='', start=None, end=None, user_id=None, equipment_id=None, status='ทั้งหมด'):
    phrase = search.strip().casefold()
    return [r for r in rows if (not start or r['borrow_date']>=str(start)) and (not end or r['borrow_date']<=str(end))
            and (not user_id or r['user_id']==user_id) and (not equipment_id or r['equipment_id']==equipment_id)
            and (status=='ทั้งหมด' or r['borrow_status']==status)
            and (not phrase or any(phrase in str(r[field]).casefold() for field in ('equipment_name','equipment_code','full_name','purpose')))]

def history_table(rows):
    return [{'เลขที่':r['id'],'ใบคำขอ':request_code(r),'วันที่ยืม':thai_date(r['borrow_date']),'ผู้ยืม':r['full_name'],'อุปกรณ์':r['equipment_name'],
             'รหัส':r['equipment_code'],'จำนวน':r['amount'],'กำหนดคืน':thai_date(r['due_date']),
             'วันที่คืน':thai_date(r['return_date']),'สถานะ':(r['review_stage'] if r['borrow_status']=='รออนุมัติ' and r.get('review_stage') in {'รออนุมัติสุดท้าย','ส่งกลับตรวจเพิ่ม'} else r['borrow_status']),
             'ค่าปรับ (บาท)':r.get('fine_amount_cents',0)/100,'สถานะค่าปรับ':r.get('fine_status','ไม่มีค่าปรับ')} for r in rows]

def csv_bytes(rows):
    output = StringIO(newline='')
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            safe = {k: ("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in row.items()}
            writer.writerow(safe)
    return output.getvalue().encode('utf-8-sig')

def render_history(user, database_path=DATABASE_PATH,own_only=False):
    tracking=st.session_state.get('loan_task_page')=='history'
    st.title('สถานะคำขอยืม' if tracking else 'ประวัติการยืม')
    rows = transactions(user['id'], database_path)
    if own_only:rows=[r for r in rows if r['user_id']==user['id']]
    if not rows:
        st.info('ยังไม่มีประวัติการยืม')
        return
    first = min(date.fromisoformat(r['borrow_date']) for r in rows)
    last = max(today(), max(date.fromisoformat(r['borrow_date']) for r in rows))
    people = {r['user_id']:r['full_name'] for r in rows}
    equipment = {r['equipment_id']:r['equipment_name'] for r in rows}
    focused=st.session_state.get('loan_task_page')=='history' and any(r['id']==st.session_state.get('loan_task_id') for r in rows)
    if focused:
        for key,value in {'history_search':'','history_start':first,'history_end':last,'history_person':None,
                          'history_equipment':None,'history_status':'ทั้งหมด'}.items():
            st.session_state[key]=value
    st.session_state.setdefault('history_start',first)
    st.session_state.setdefault('history_end',last)
    with st.container(key='history_filters',horizontal=True,vertical_alignment='bottom',gap='small'):
        search = st.text_input('ค้นหาผู้ยืม อุปกรณ์ หรือวัตถุประสงค์',key='history_search',
                              placeholder='ค้นหาชื่อ อุปกรณ์ หรือกิจกรรม…',icon=':material/search:',
                              label_visibility='collapsed',width='stretch')
        with st.popover('ตัวกรองประวัติ',icon=':material/tune:'):
            dates = st.columns(2)
            start = dates[0].date_input('ตั้งแต่วันที่ยืม',value=None,key='history_start')
            end = dates[1].date_input('ถึงวันที่ยืม',value=None,key='history_end')
            person = st.selectbox('ผู้ยืม',[None,*people],key='history_person',format_func=lambda key:'ทั้งหมด' if key is None else people[key])
            item = st.selectbox('อุปกรณ์',[None,*equipment],key='history_equipment',format_func=lambda key:'ทั้งหมด' if key is None else equipment[key])
            status = st.selectbox('สถานะการยืม',['ทั้งหมด',*sorted({r['borrow_status'] for r in rows})],key='history_status')
    if start is None or end is None:
        st.info('กรุณาเลือกวันที่เริ่มต้นและสิ้นสุดเพื่อดูประวัติ')
        return
    if end < start:
        st.error('วันที่สิ้นสุดต้องไม่ก่อนวันเริ่ม')
        return
    filtered = filter_history(rows,search,start,end,person,item,status)
    st.caption(f'พบ {len(filtered)} รายการ')
    if not filtered:
        st.info('ไม่พบข้อมูลตามตัวกรอง')
        return
    table = history_table(filtered)
    with st.container(key='admin_history_data' if user['role']=='admin' else 'user_history_data'):
        st.dataframe(table,hide_index=True,width='stretch')
    if user['role']=='admin':
        st.download_button('ดาวน์โหลดประวัติ CSV',csv_bytes(table),file_name='smartborrow-history.csv',mime='text/csv')
    by_id = {r['id']:r for r in filtered}
    with st.expander('สถานะและรายละเอียดรายการ',expanded=True):
        from loan_workspace import focus_loan_choice
        focus_loan_choice(by_id,'history_detail','history')
        selected = st.selectbox('เลขที่รายการ',list(by_id),key='history_detail')
        row = by_id[selected]
        render_transaction(row, user['id'], database_path,show_downloads=user['role']=='admin')
        if row['borrow_status'] in {'กำลังยืม','เกินกำหนด'}:
            from loan_workspace import open_loan_task
            early=date.fromisoformat(row['due_date'])>today()
            st.caption('แจ้งคืนได้ทันที ไม่ต้องรอถึงกำหนด แล้วนำอุปกรณ์ให้เจ้าหน้าที่ตรวจรับ')
            st.button('คืนก่อนกำหนด' if early else 'แจ้งคืนอุปกรณ์',key='history_request_return',
                      icon=':material/assignment_return:',type='primary',
                      on_click=open_loan_task,args=(selected,'return',row['borrow_status']))
        left,right = st.columns(2)
        if row['before_image']:
            left.image(str(image_path(row['before_image'])),caption='สภาพก่อนยืม',width='stretch')
        if row['after_image']:
            right.image(str(image_path(row['after_image'])),caption='สภาพหลังยืม',width='stretch')
        st.write(f"หมายเหตุการคืน: {row['return_note'] or '—'}")
        if row['borrow_status'] in {'รออนุมัติ','อนุมัติแล้ว'}:
            confirmed=st.checkbox('ยืนยันยกเลิกรายการยืมนี้')
            if st.button('ยกเลิกคำขอยืม',disabled=not confirmed):
                action(cancel_borrow,user['id'],selected,database_path,success='ยกเลิกรายการยืมแล้ว')
