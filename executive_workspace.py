# หน้าที่: พื้นที่ผู้บริหารสำหรับพิจารณา ดูประวัติ และติดตามภาพรวมแบบอ่านอย่างเดียว
from datetime import date
import streamlit as st
from common import DomainError,action,render_transaction,thai_date,today,TIMEZONE
from database import DATABASE_PATH,database_connection
from services import transactions,decide_borrow
from borrow_requests import decide_group,request_code,required_document
from executive_approval import (require_executive,return_for_review,approval_history,
                                executive_overview,FINAL_STAGE,TITLES)
from loan_workspace import focus_loan_choice

ACTION_LABELS={'reviewed':'ตรวจเอกสารและส่งต่อ','approved':'อนุมัติสุดท้าย',
               'rejected':'ไม่อนุมัติ','returned':'ส่งกลับตรวจเพิ่ม'}


def render_executive_workspace(user,database_path=DATABASE_PATH):
    try:
        with database_connection(database_path) as con:user=require_executive(con,user['id'])
    except DomainError as error:
        st.error(str(error));return
    st.title('พื้นที่อนุมัติของผู้บริหาร')
    st.caption('ผอ. หรือรอง ผอ. คนใดคนหนึ่งพิจารณาสุดท้ายได้ หลังเจ้าหน้าที่ตรวจเอกสารแล้ว')
    st.session_state.setdefault('executive_section','คำขอรออนุมัติ')
    section=st.segmented_control('งานผู้บริหาร',['คำขอรออนุมัติ','ประวัติการพิจารณา','ภาพรวม'],
        key='executive_section',selection_mode='single') or 'คำขอรออนุมัติ'
    if section=='ประวัติการพิจารณา':
        render_decision_history(user,database_path);return
    if section=='ภาพรวม':
        render_executive_overview(user,database_path);return
    records=transactions(user['id'],database_path)
    pending={r['id']:r for r in records if r['borrow_status']=='รออนุมัติ' and r['review_stage']==FINAL_STAGE}
    st.subheader(f'คำขอรออนุมัติสุดท้าย {len(pending)} รายการ')
    if not pending:
        st.info('ไม่มีคำขอรออนุมัติสุดท้าย');return
    focus_loan_choice(pending,'approval_pending','approvals')
    selected=st.selectbox('คำขอยืม',list(pending),key='approval_pending',
        format_func=lambda k:f"{request_code(pending[k])} · {pending[k]['full_name']} · {pending[k]['equipment_name']}")
    row=pending[selected]
    with st.container(border=True):
        render_transaction(row,user['id'],database_path)
        st.write('วัตถุประสงค์: '+row['purpose'])
        group=[r for r in records if row['request_group'] and r['request_group']==row['request_group']]
        all_pending=len(group)>1 and all(r['borrow_status']=='รออนุมัติ' and r['review_stage']==FINAL_STAGE for r in group)
        whole=False
        if all_pending:
            st.dataframe([{'อุปกรณ์':r['equipment_name'],'จำนวน (ชิ้น)':r['amount'],
                'วันยืม':thai_date(r['borrow_date']),'กำหนดคืน':thai_date(r['due_date'])} for r in group],hide_index=True,width='stretch')
            whole=st.radio('ขอบเขตการพิจารณา',['เฉพาะรายการนี้','ทั้งใบคำขอ'],horizontal=True,key=f'executive_scope_{selected}')=='ทั้งใบคำขอ'
        document_ok=True
        if row.get('document_path'):
            with st.expander('เปิดตรวจ PDF ใบยืม',expanded=True):
                try:st.pdf(required_document(row['document_path']).read_bytes(),height=500,key=f'executive_pdf_{selected}')
                except (DomainError,OSError):
                    st.error('ไม่สามารถเปิดเอกสารได้ กรุณาส่งกลับให้เจ้าหน้าที่ตรวจเพิ่ม');document_ok=False
        else:st.caption('รายการเดิมก่อนบังคับแนบ PDF ไม่มีไฟล์ใบยืม')
        own=row['user_id']==user['id']
        if own:st.warning('ไม่สามารถพิจารณาคำขอของตนเองได้ ให้ผู้บริหารอีกคนพิจารณา')
        checked=st.checkbox('ตรวจข้อมูลและเอกสารประกอบครบแล้ว',key=f'approval_document_checked_{selected}')
        reason=st.text_area('เหตุผลหรือหมายเหตุ',max_chars=1000,key=f'executive_reason_{selected}',
            placeholder='ต้องระบุเมื่อไม่อนุมัติหรือส่งกลับตรวจเพิ่ม')
        approve,return_button,reject=st.columns(3)
        decide=decide_group if whole else decide_borrow
        target=row['request_group'] if whole else selected
        if approve.button('อนุมัติสุดท้ายทั้งใบคำขอ' if whole else 'อนุมัติสุดท้าย',type='primary',
            disabled=own or not checked or not document_ok,width='stretch'):
            action(decide,user['id'],target,True,database_path,reason=reason,success='อนุมัติแล้วและแจ้งผู้ยืมกับเจ้าหน้าที่แล้ว')
        if return_button.button('ส่งกลับตรวจเพิ่ม',disabled=own or not reason.strip(),width='stretch'):
            action(return_for_review,user['id'],selected,reason,database_path,whole_group=whole,success='ส่งกลับให้เจ้าหน้าที่ตรวจเพิ่ม พร้อมแจ้งเหตุผลแล้ว')
        if reject.button('ไม่อนุมัติ',disabled=own or not reason.strip(),width='stretch'):
            action(decide,user['id'],target,False,database_path,reason=reason,success='บันทึกไม่อนุมัติและแจ้งเหตุผลแก่ผู้ยืมแล้ว')
        st.caption('ตรวจเอกสารก่อนอนุมัติ · ไม่อนุมัติและส่งกลับต้องมีเหตุผล · ตรวจจำนวนพร้อมใช้อีกครั้งเมื่อบันทึก')


def render_decision_history(user,database_path):
    st.subheader('ประวัติการพิจารณา')
    rows=approval_history(user['id'],database_path)
    if not rows:
        st.info('ยังไม่มีประวัติการพิจารณา');return
    query=st.text_input('ค้นหาเลขคำขอ ผู้ยืม อุปกรณ์ หรือเหตุผล',key='executive_history_search')
    cols=st.columns(3)
    first=min(event_date(r['created_at']) for r in rows)
    start=cols[0].date_input('ตั้งแต่วันที่',value=first,key='executive_history_start')
    end=cols[1].date_input('ถึงวันที่',value=max(today(),first),key='executive_history_end')
    kind=cols[2].selectbox('ผลการพิจารณา',['ทั้งหมด',*ACTION_LABELS.values()],key='executive_history_action')
    if start>end:st.warning('วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่ม');return
    filtered=[r for r in rows if start<=event_date(r['created_at'])<=end
        and (kind=='ทั้งหมด' or ACTION_LABELS[r['action']]==kind)
        and (not query.strip() or query.strip().casefold() in ' '.join(str(r[k]) for k in
            ['transaction_id','request_group','borrower_name','equipment_name','actor_name','reason']).casefold())]
    st.caption(f'พบ {len(filtered)} เหตุการณ์ รวมรอบตรวจเพิ่มเติม และการพิจารณาของผู้บริหารทั้งสองตำแหน่ง')
    st.dataframe([{'เลขรายการ':r['transaction_id'],'ใบคำขอ':request_code({'id':r['transaction_id'],'request_group':r['request_group']}),
        'ผู้ยืม':r['borrower_name'],'อุปกรณ์':r['equipment_name'],'ผล':ACTION_LABELS[r['action']],
        'ผู้ดำเนินการ':r['actor_name'],'ตำแหน่ง':TITLES[r['actor_title']] if r['actor_title'] else 'เจ้าหน้าที่',
        'เวลา (ไทย)':local_timestamp(r['created_at']),'เหตุผล':r['reason'] or '—'} for r in filtered],hide_index=True,width='stretch',height=320)
    if filtered:
        with st.expander('ดูเหตุผลและรายละเอียดเหตุการณ์'):
            events={r['id']:r for r in filtered}
            selected=st.selectbox('เหตุการณ์',list(events),key='executive_history_event',
                format_func=lambda k:f"#{events[k]['transaction_id']} · {ACTION_LABELS[events[k]['action']]} · {local_timestamp(events[k]['created_at'])}")
            event=events[selected]
            st.write('ผู้ดำเนินการ: '+event['actor_name'])
            st.write('ผู้ยืม: '+event['borrower_name']+' · '+event['equipment_name'])
            st.write('เหตุผลหรือหมายเหตุ: '+(event['reason'] or 'ไม่ได้ระบุหมายเหตุ'))


def event_date(value):
    from datetime import datetime
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(TIMEZONE).date()


def local_timestamp(value):
    from datetime import datetime
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(TIMEZONE).strftime('%d/%m/%Y %H:%M')


def render_executive_overview(user,database_path):
    data=executive_overview(user['id'],database_path)
    st.subheader('ภาพรวมการใช้อุปกรณ์')
    st.caption('ข้อมูลปัจจุบันสำหรับติดตามงาน ดูได้อย่างเดียว งานที่ค้างเป็นจำนวนรายการ อุปกรณ์เป็นจำนวนชิ้น')
    cols=st.columns(4)
    for col,key,label in zip(cols,['pending','borrowed','overdue','awaiting_return'],
        ['รออนุมัติสุดท้าย (รายการ)','อยู่กับผู้ยืม (ชิ้น)','เกินกำหนด (รายการ)','รอตรวจรับคืน (รายการ)']):
        col.metric(label,data[key],border=True)
    st.metric('ไม่พร้อมใช้ รวมชำรุดและซ่อม (ชิ้น)',data['unavailable'],border=True)
    st.dataframe([{'หมวดหมู่':r['category'],'ทั้งหมด (ชิ้น)':r['total'],'พร้อมใช้ (ชิ้น)':r['available'],
        'ไม่พร้อมใช้ (ชิ้น)':r['unavailable']} for r in data['equipment']],hide_index=True,width='stretch')

