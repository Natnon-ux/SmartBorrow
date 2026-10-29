# หน้าที่: การ์ดรายการที่กำลังยืมของเจ้าของบัญชี
"""รายการส่วนตัวพร้อมปุ่มดูรายละเอียดและแจ้งคืนตรงรายการ"""
from datetime import date
import streamlit as st
from common import today,thai_date
from database import DATABASE_PATH
from services import transactions
from design import equipment_image
from loan_workspace import open_loan_task

ACTIVE_STATUSES={'กำลังยืม','เกินกำหนด','รอตรวจสอบการคืน'}

def own_active_loans(user,database_path=DATABASE_PATH):
    # ครูและเจ้าหน้าที่อ่านธุรกรรมได้หลายคน แต่หน้านี้ต้องแสดงเฉพาะของตน
    return sorted((r for r in transactions(user['id'],database_path)
                   if r['user_id']==user['id'] and r['borrow_status'] in ACTIVE_STATUSES),
                  key=lambda r:(r['due_date'],r['id']))

def render_my_loans(user,database_path=DATABASE_PATH):
    st.title('รายการที่กำลังยืม')
    rows=own_active_loans(user,database_path)
    st.caption('อุปกรณ์ที่รับแล้วและยังไม่ตรวจรับคืน · ดูรายละเอียดหรือแจ้งคืนจากการ์ดได้ทันที')
    st.caption(f'{len(rows)} รายการ · รวม {sum(r["amount"] for r in rows)} ชิ้น')
    if not rows:
        st.info('ยังไม่มีอุปกรณ์ที่กำลังยืม คำขอที่รออนุมัติหรือรอรับดูได้ในประวัติการยืม')
        from navigation import navigate_to
        st.button('เลือกอุปกรณ์',key='my_loans_equipment',icon=':material/inventory_2:',on_click=navigate_to,args=('equipment',))
        return
    pages=list(range(1,(len(rows)+7)//8+1))
    if st.session_state.get('my_loans_page') not in pages:st.session_state['my_loans_page']=1
    page=st.selectbox('หน้ารายการ',pages,key='my_loans_page') if len(pages)>1 else 1
    for offset in range((page-1)*8,min(page*8,len(rows)),2):
        columns=st.columns(2,gap='medium')
        for column,row in zip(columns,rows[offset:offset+2]):
            waiting=row['borrow_status']=='รอตรวจสอบการคืน'
            days=(date.fromisoformat(row['due_date'])-today()).days
            tone='waiting' if waiting else ('late' if days<0 else 'active')
            with column,st.container(border=True,key=f'my_loan_card_{row["id"]}',gap='small'):
                st.badge('รอเจ้าหน้าที่ตรวจรับ' if waiting else ('เกินกำหนดคืน' if days<0 else 'กำลังยืม'),
                         color='orange' if waiting else ('red' if days<0 else 'green'))
                picture,copy=st.columns([1,3],vertical_alignment='center')
                picture.image(str(equipment_image(row)),width=90)
                with copy:
                    st.subheader(row['equipment_name'])
                    st.caption(f"#{row['id']} · {row['equipment_code']} · {row['amount']} ชิ้น")
                st.write('กำหนดคืน '+thai_date(row['due_date']))
                if waiting:
                    st.caption('ส่งคำขอคืนแล้ว กรุณานำอุปกรณ์ให้เจ้าหน้าที่ตรวจรับ')
                else:
                    st.caption(f'เกินกำหนด {abs(days)} วัน' if days<0 else ('ครบกำหนดวันนี้' if days==0 else f'เหลืออีก {days} วัน · คืนก่อนกำหนดได้'))
                with st.container(horizontal=True,gap='small'):
                    st.button('ดูรายละเอียด',key=f'my_loan_detail_{row["id"]}',icon=':material/info:',width='stretch',
                              on_click=open_loan_task,args=(row['id'],'history',row['borrow_status']))
                    st.button('รอตรวจรับ' if waiting else ('คืนก่อนกำหนด' if days>0 else 'แจ้งคืน'),
                              key=f'my_loan_return_{row["id"]}',icon=':material/assignment_return:',
                              type='primary',width='stretch',disabled=waiting,
                              on_click=open_loan_task,args=(row['id'],'return',row['borrow_status']))
