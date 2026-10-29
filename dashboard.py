# หน้าที่: หน้าภาพรวมการยืมและสถิติที่แอดมินเท่านั้นดูได้
"""STEP 6: Dashboard และกราฟ Plotly."""
import pandas as pd
import plotly.express as px
import streamlit as st
from analytics import dashboard_data
from common import thai_date,today
from database import DATABASE_PATH
from design import RED, BURGUNDY, CHART_COLORS, style_chart
from navigation import navigate_to
from equipment import render_catalog
from services import catalog
from web_ui import render_hero_visual,dashboard_visual_html

def transaction_table(rows):
    if not rows:
        st.info("ยังไม่มีรายการ")
        return
    st.dataframe([{ "ผู้ยืม": r["full_name"], "อุปกรณ์": r["equipment_name"], "จำนวน": r["amount"],
                    "วันที่ยืม": thai_date(r["borrow_date"]), "กำหนดคืน": thai_date(r["due_date"]),
                    "สถานะ": r["borrow_status"]} for r in rows], hide_index=True, width="stretch")

def render_dashboard(user, database_path=DATABASE_PATH):
    with st.container(key='dashboard_intro'):
        left,right=st.columns([1.65,1],gap='large',vertical_alignment='center')
        with left,st.container(key='dashboard_intro_copy',gap='small'):
            st.html('<div class="sb-intro-eyebrow"><span></span> SMARTBORROW · CREATE SOMETHING GREAT</div>')
            st.title('ศูนย์ยืม–คืนอุปกรณ์')
            st.caption(f"สวัสดี {user['full_name']} · เลือกอุปกรณ์ ติดตามคำขอ และจัดการการคืนได้ที่นี่")
            with st.container(key='dashboard_intro_actions',horizontal=True,gap='small'):
                st.button('ค้นหาอุปกรณ์',key='intro_equipment',icon=':material/search:',on_click=navigate_to,args=('equipment',))
                st.button('วางแผนด้วยปฏิทิน',key='intro_calendar',icon=':material/calendar_month:',type='tertiary',on_click=navigate_to,args=('calendar',))
        with right:
            st.html(dashboard_visual_html(catalog(database_path=database_path)))
    work,explore=st.tabs(['งานยืม–คืน','สำรวจอุปกรณ์'])
    with work:
        from loan_workspace import render_task_board
        render_task_board(user,database_path)
    with explore:
        render_explore(user,database_path)


def render_explore(user,database_path):
    equipment = catalog(database_path=database_path)
    available = sum(r['available_amount'] for r in equipment if r['status']=='พร้อมใช้งาน')
    with st.container(key='home_hero'):
        left,right=st.columns([1.08,1],gap='large',vertical_alignment='center')
        with left,st.container(key='home_copy',gap='small'):
            st.html('<div class="sb-kicker">SCHOOL CREATIVE TOOLKIT</div>')
            st.title('ทุกไอเดีย เริ่มได้ที่นี่')
            st.html('<p class="sb-hero-accent">อุปกรณ์พร้อม ความคิดสร้างสรรค์ก็พร้อม</p>'
                    '<p class="sb-hero-description">กล้อง เครื่องเสียง และอุปกรณ์สำหรับกิจกรรมโรงเรียน<br>'
                    'เลือกสิ่งที่ต้องใช้ แล้วเริ่มสร้างสรรค์งานของคุณ</p>')
            with st.container(key='home_actions',horizontal=True,gap='small'):
                st.button('เริ่มยืมอุปกรณ์',icon=':material/arrow_forward:',type='primary',on_click=navigate_to,args=('borrow',))
                st.button('ดูอุปกรณ์',icon=':material/inventory_2:',on_click=navigate_to,args=('equipment',))
                st.button('ดูปฏิทิน',icon=':material/calendar_month:',type='tertiary',on_click=navigate_to,args=('calendar',))
            st.html(f'<div class="sb-hero-stats"><div><strong>{len(equipment)}</strong>รายการอุปกรณ์</div>'
                    f'<div><strong>{available}</strong>ชิ้นพร้อมใช้</div><div><strong>ยืมฟรี</strong>สำหรับกิจกรรมโรงเรียน</div></div>')
        with right:
            render_hero_visual()
    render_catalog(user,database_path)


def render_statistics(user,database_path):
    from common import require_actor
    from database import database_connection
    with database_connection(database_path) as con:
        require_actor(con,user['id'],{'admin'})
    data = dashboard_data(user, database_path)
    stock = data["stock"]
    st.subheader('ภาพรวม')
    st.caption(f"สวัสดี {user['full_name']} · {thai_date(today())}")
    metrics = (("อุปกรณ์ทั้งหมด", "total", "inventory_2"), ("พร้อมใช้งาน", "available", "check_circle"),
               ("ยืม / อนุมัติ", "borrowed", "swap_horiz"), ("เกินกำหนดคืน", "overdue", "schedule"),
               ("ชำรุด / ซ่อม", "broken", "build"))
    with st.container(key='dashboard_stats_metrics',horizontal=True,gap='small'):
        for label,key,icon in metrics:
            with st.container(key='dashboard_metric_'+key,width='stretch'):
                st.metric(label, stock[key], border=True, icon=f':material/{icon}:',width='stretch')
    left, right = st.columns([3, 2])
    with left, st.container(border=True):
        st.subheader("การยืมรายเดือน")
        if data["monthly"]:
            figure = px.bar(pd.DataFrame(data["monthly"]), x="เดือน", y="จำนวนครั้ง", color_discrete_sequence=[RED])
            figure.update_traces(marker_cornerradius=6)
            figure.update_traces(texttemplate='%{y}',textposition='outside',cliponaxis=False)
            figure.update_layout(xaxis_title=None, yaxis_title='จำนวนครั้ง', bargap=0.5)
            st.plotly_chart(style_chart(figure), width="stretch", config={'displayModeBar': False})
        else:
            st.info("กราฟจะแสดงเมื่อมีรายการอนุมัติหรือยืมอุปกรณ์")
    with right, st.container(border=True):
        st.subheader("สัดส่วนสถานะอุปกรณ์")
        quantities = {"พร้อมใช้": stock["available"], "ถูกยืม / อนุมัติ": stock["borrowed"], "ชำรุด / ซ่อม": stock["broken"]}
        if any(quantities.values()):
            figure = px.pie(names=list(quantities), values=list(quantities.values()), hole=0.72,
                            color_discrete_sequence=CHART_COLORS)
            figure.update_traces(textinfo='none', sort=False)
            figure.update_layout(legend=dict(orientation='h', y=-0.1, x=0.5, xanchor='center'),
                                 annotations=[dict(text=str(stock['total']), x=0.5, y=0.5, showarrow=False,
                                                   font=dict(size=32, color=BURGUNDY))])
            st.plotly_chart(style_chart(figure), width="stretch", config={'displayModeBar': False})
        else:
            st.info("ยังไม่มีอุปกรณ์ในฐานข้อมูล")
    activity, popular = st.columns([3, 2])
    with activity, st.container(border=True):
        st.subheader('ติดตามรายการยืม')
        recent_tab, due_tab = st.tabs(["รายการล่าสุด", "กำหนดคืน"])
        with recent_tab:
            transaction_table(data["recent"])
        with due_tab:
            transaction_table(data["due"])
    with popular, st.container(border=True):
        st.subheader("อุปกรณ์ยอดนิยม")
        st.caption('5 อันดับจากจำนวนชิ้นที่ถูกยืม')
        if data["popular"]:
            maximum = max(row['จำนวนที่ยืม'] for row in data['popular'])
            for index, row in enumerate(data['popular'], 1):
                st.caption(f"{index}. {row['อุปกรณ์']} · {row['จำนวนที่ยืม']} ชิ้น")
                st.progress(row['จำนวนที่ยืม'] / maximum)
        else:
            st.info("ยังไม่มีข้อมูลการใช้งาน")
