# หน้าที่: รายงานสำหรับผู้มีสิทธิ์จัดการ
"""STEP 19: รายงานการใช้งานและค่าใช้จ่ายจากข้อมูลจริง."""
from datetime import date
import streamlit as st
import plotly.express as px
from common import MANAGER_ROLES,today,thai_date
from database import DATABASE_PATH
from analytics import report_data
from history import history_table,csv_bytes
from design import RED,style_chart

def chart_table(rows,x,y,title):
    with st.container(border=True):
        st.subheader(title)
        if not rows:
            st.info('ยังไม่มีข้อมูลในช่วงวันที่เลือก')
            return
        fig=px.bar(rows,x=x,y=y,color_discrete_sequence=[RED])
        fig.update_traces(marker_cornerradius=7)
        st.plotly_chart(style_chart(fig,300),width='stretch',config={'displayModeBar':False})
        st.dataframe(rows,hide_index=True,width='stretch')

def render_reports(user,database_path=DATABASE_PATH):
    st.title('รายงาน')
    if user['role'] not in MANAGER_ROLES:
        st.error('คุณไม่มีสิทธิ์เข้าหน้านี้')
        return
    left,right=st.columns(2)
    start=left.date_input('รายงานตั้งแต่วันที่',date(today().year,1,1))
    end=right.date_input('ถึงวันที่',today())
    if end<start:
        st.error('วันที่สิ้นสุดต้องไม่ก่อนวันเริ่ม')
        return
    data=report_data(user['id'],start,end,database_path)
    columns=st.columns(3)
    columns[0].metric('การยืมในช่วงวันที่',len(data['usage']))
    columns[1].metric('รายการเกินกำหนดในช่วงวันที่',len(data['overdue']))
    columns[2].metric('ค่าซ่อมในช่วงวันที่',f"{data['cost']:,.2f} บาท")
    usage_tab,repair_tab=st.tabs(['การใช้งาน','เกินกำหนดและซ่อมบำรุง'])
    with usage_tab:
        st.caption('นับรายการที่อนุมัติแล้ว ส่งมอบแล้ว หรือคืนแล้ว ตามวันที่ยืม')
        chart_table(data['monthly'],'เดือน','จำนวนครั้ง','การยืมรายเดือน')
        chart_table(data['popular'],'อุปกรณ์','จำนวนชิ้น','อุปกรณ์ที่ถูกยืมมากที่สุด')
        chart_table(data['people'],'ผู้ยืม','จำนวนครั้ง','ผู้ใช้ที่ยืมมากที่สุด')
        if data['usage']:
            st.download_button('ดาวน์โหลดรายการยืม CSV',csv_bytes(history_table(data['usage'])),file_name='smartborrow-report.csv',mime='text/csv')
    with repair_tab:
        st.subheader('รายการเกินกำหนด')
        if data['overdue']:
            st.dataframe(history_table(data['overdue']),hide_index=True,width='stretch')
        else:
            st.info('ไม่มีรายการเกินกำหนดในช่วงวันที่เลือก')
        st.subheader('อุปกรณ์ที่ไม่พร้อมใช้ ณ ปัจจุบัน')
        if data['broken']:
            st.dataframe([{'รหัส':r['equipment_code'],'อุปกรณ์':r['equipment_name'],'จำนวนไม่พร้อมใช้':r['unavailable_amount']} for r in data['broken']],hide_index=True,width='stretch')
        else:
            st.info('ไม่มีอุปกรณ์ที่ถูกกันว่าไม่พร้อมใช้')
        if data['repairs']:
            rows=[{'อุปกรณ์':r['equipment_name'],'อาการ':r['issue'],'ค่าใช้จ่าย':r['repair_cost'],'สถานะ':r['status'],'ส่งซ่อม':thai_date(r['sent_date'])} for r in data['repairs']]
            chart_table(rows,'อุปกรณ์','ค่าใช้จ่าย','ค่าซ่อมตามงานซ่อม')
        else:
            st.info('ไม่มีงานซ่อมในช่วงวันที่เลือก')
