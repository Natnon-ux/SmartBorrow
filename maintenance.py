# หน้าที่: จัดการอุปกรณ์ชำรุดและงานซ่อม
"""STEP 18: งานซ่อมและจำนวนอุปกรณ์ที่ไม่พร้อมใช้."""
import streamlit as st
from common import MANAGER_ROLES, action, today, thai_date, image_path, save_upload, DomainError
from database import DATABASE_PATH
from services import catalog,maintenance_rows,create_maintenance,update_maintenance

def render_maintenance(user,database_path=DATABASE_PATH):
    st.title('ซ่อมบำรุง')
    if user['role'] not in MANAGER_ROLES:
        st.error('คุณไม่มีสิทธิ์เข้าหน้านี้')
        return
    new_tab,work_tab=st.tabs(['แจ้งซ่อม','รายการงานซ่อม'])
    with new_tab:
        equipment={r['id']:r for r in catalog(database_path=database_path)}
        if not equipment:
            st.info('ไม่มีอุปกรณ์ในระบบ')
        else:
            with st.form('maintenance_create'):
                selected=st.selectbox('อุปกรณ์ที่แจ้งซ่อม',list(equipment),format_func=lambda key:f"{equipment[key]['equipment_code']} · {equipment[key]['equipment_name']}")
                amount=st.number_input('จำนวนที่ส่งซ่อม',min_value=1,step=1,value=1)
                blocked=st.checkbox('ใช้จำนวนที่ถูกกันว่าไม่พร้อมใช้อยู่แล้ว')
                st.caption('เลือกเมื่อ Admin ตั้งอุปกรณ์เป็นชำรุดไว้แล้ว; รายการจากการคืนชำรุดมีงานซ่อมอัตโนมัติ')
                issue=st.text_input('อาการที่พบ')
                detail=st.text_area('รายละเอียดการซ่อม')
                photo=st.file_uploader('รูปอาการ (ไม่เกิน 5 MB)',type=['png','jpg','jpeg','webp'],max_upload_size=5)
                cost=st.number_input('ค่าใช้จ่าย (บาท)',min_value=0.0,step=100.0)
                sent=st.date_input('วันที่ส่งซ่อม',today(),max_value=today())
                submit=st.form_submit_button('แจ้งซ่อม',type='primary')
            if submit:
                try:
                    image=save_upload(photo,'maintenance')
                except DomainError as error:
                    st.error(str(error))
                else:
                    action(create_maintenance,user['id'],selected,amount,issue,detail,image,cost,sent,blocked,database_path,success='บันทึกงานซ่อมและกันจำนวนแล้ว')
    with work_tab:
        rows=maintenance_rows(user['id'],database_path)
        if not rows:
            st.info('ยังไม่มีงานซ่อม')
            return
        st.dataframe([{'เลขที่':r['id'],'อุปกรณ์':r['equipment_name'],'จำนวน':r['amount'],'อาการ':r['issue'],
                       'สถานะ':r['status'],'ค่าใช้จ่าย':r['repair_cost'],'ส่งซ่อม':thai_date(r['sent_date']),
                       'เสร็จ':thai_date(r['repaired_date'])} for r in rows],hide_index=True,width='stretch')
        options={r['id']:r for r in rows}
        selected=st.selectbox('ดู / อัปเดตงานซ่อม',list(options))
        row=options[selected]
        st.write(row['issue'])
        if row['image']:
            st.image(str(image_path(row['image'])),width=360)
        if row['status'] in {'ซ่อมเสร็จ','ไม่สามารถซ่อมได้'}:
            st.info('งานซ่อมสิ้นสุดแล้ว')
            st.write(row['repair_detail'])
        else:
            with st.form(f'maintenance_update_{selected}'):
                states=['รอตรวจสอบ','กำลังซ่อม','ซ่อมเสร็จ','ไม่สามารถซ่อมได้']
                state=st.selectbox('สถานะงานซ่อม',states,index=states.index(row['status']))
                detail=st.text_area('ผลการซ่อม',value=row['repair_detail'])
                cost=st.number_input('ค่าซ่อมรวม (บาท)',min_value=0.0,value=float(row['repair_cost']))
                completed=st.date_input('วันที่งานสิ้นสุด',today(),max_value=today())
                if st.form_submit_button('อัปเดตงานซ่อม',type='primary'):
                    action(update_maintenance,user['id'],selected,state,detail,cost,completed,database_path,success='อัปเดตงานซ่อมแล้ว')
