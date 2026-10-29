# หน้าที่: กราฟและการวิเคราะห์ข้อมูล
"""STEP 20: วิเคราะห์ข้อมูลด้วยกฎและสถิติ Python."""
import streamlit as st
from common import MANAGER_ROLES
from database import DATABASE_PATH
from analytics import insight_data
from reports import chart_table

def render_insights(user,database_path=DATABASE_PATH):
    st.title('วิเคราะห์ข้อมูลอัจฉริยะ')
    if user['role'] not in MANAGER_ROLES:
        st.error('คุณไม่มีสิทธิ์เข้าหน้านี้')
        return
    data=insight_data(user['id'],database_path)
    st.caption('คำนวณจากข้อมูลจริงในระบบ; เดือนนี้ถึงปัจจุบันเทียบกับเดือนก่อนทั้งเดือน')
    left,right=st.columns(2)
    left.metric('การยืมเดือนนี้',data['current'])
    right.metric('การยืมเดือนก่อน',data['previous'])
    if data['percent'] is None:
        st.info('เดือนก่อนยังไม่มีรายการยืม จึงยังคำนวณเปอร์เซ็นต์การเปลี่ยนแปลงไม่ได้')
    elif data['percent']>0:
        st.success(f"เดือนนี้มีการยืมเพิ่มขึ้น {data['percent']:.1f}% จากเดือนก่อน")
    elif data['percent']<0:
        st.info(f"เดือนนี้มีการยืมลดลง {abs(data['percent']):.1f}% จากเดือนก่อน")
    else:
        st.info('จำนวนการยืมเดือนนี้เท่ากับเดือนก่อน')
    if data['categories']:
        top=data['categories'][0]
        st.success(f"{top['หมวดหมู่']} เป็นหมวดหมู่ที่ถูกยืมมากที่สุด รวม {top['จำนวนชิ้น']} ชิ้น")
        chart_table(data['categories'],'หมวดหมู่','จำนวนชิ้น','การใช้งานแยกหมวดหมู่')
    else:
        st.info('ยังไม่มีข้อมูลการยืมเพื่อวิเคราะห์หมวดหมู่')
    st.subheader('อุปกรณ์ที่ควรตรวจสอบ')
    if not data['repeated']:
        st.info('ยังไม่พบอุปกรณ์ที่มีงานซ่อมตั้งแต่ 2 ครั้งขึ้นไป')
    for row in data['repeated']:
        st.warning(f"ควรตรวจสอบ {row['อุปกรณ์']} เนื่องจากมีประวัติงานซ่อม {row['จำนวนงานซ่อม']} ครั้ง")
