# หน้าที่: แสดงอุปกรณ์และแบบฟอร์มจัดการอุปกรณ์
"""STEP 7: รายการอุปกรณ์แบบ Card ค้นหาและกรองข้อมูลจริง."""
import streamlit as st
from common import action, save_upload, DomainError
from database import DATABASE_PATH
from services import catalog, save_equipment, deactivate_equipment
from design import equipment_image
from navigation import start_borrow,navigate_to,close_overlays,open_overlay
from web_ui import equipment_card_html

def render_editor(user, database_path):
    with st.expander("เพิ่ม / แก้ไข / ปิดใช้งานอุปกรณ์"):
        records = catalog(database_path=database_path, include_inactive=True)
        options = {row["id"]: row for row in records}
        selected = st.selectbox("รายการที่ต้องการจัดการ", [None, *options], key='equipment_editor_id',
                                format_func=lambda key: "เพิ่มอุปกรณ์ใหม่" if key is None else f"{options[key]['equipment_code']} · {options[key]['equipment_name']}")
        row = options.get(selected, {})
        if row.get('unavailable_amount'):
            st.info(f"จำนวนไม่พร้อมใช้ {row['unavailable_amount']} ชิ้น จะกลับเข้าสต็อกเมื่อบันทึกงานซ่อมเสร็จในเมนูซ่อมบำรุง")
        with st.form(f"equipment_edit_{selected}"):
            code = st.text_input("รหัสอุปกรณ์", value=row.get("equipment_code", ""))
            name = st.text_input("ชื่ออุปกรณ์", value=row.get("equipment_name", ""))
            # รวมหมวดมาตรฐานกับข้อมูลเดิม เพื่อให้แก้ไขรายการเก่าได้โดยไม่เปลี่ยนหมวด
            categories = list(dict.fromkeys([
                "กล้อง", "เลนส์", "คอมพิวเตอร์", "แท็บเล็ต", "โปรเจกเตอร์",
                "ไมโครโฟน", "ลำโพง", "สายสัญญาณ", "อุปกรณ์ไฟฟ้า", "อุปกรณ์เสริม",
                *sorted({item["category"].strip() for item in records if item.get("category", "").strip()}),
            ]))
            current_category = row.get("category", "").strip()
            category = st.selectbox("หมวดหมู่", categories,
                                    index=categories.index(current_category) if current_category in categories else None,
                                    placeholder="เลือกหมวดหมู่อุปกรณ์")
            description = st.text_area("รายละเอียด", value=row.get("description", ""),height=180,
                                       help='ระบุการใช้งาน จุดเด่น อุปกรณ์ที่ส่งมอบ และข้อควรระวัง ข้อมูลจะแสดงบนเว็บโดยตรง')
            total = st.number_input("จำนวนทั้งหมด", min_value=0, step=1, value=row.get("total_amount", 1))
            location = st.text_input("สถานที่จัดเก็บ", value=row.get("storage_location", ""))
            states = ["พร้อมใช้งาน", "ชำรุด", "ซ่อมบำรุง"]
            status = st.selectbox("สภาพอุปกรณ์", states, index=states.index(row["status"]) if row.get("status") in states else 0)
            uploaded = st.file_uploader("รูปอุปกรณ์ (ไม่เกิน 5 MB)", type=["png", "jpg", "jpeg", "webp"], max_upload_size=5)
            submitted = st.form_submit_button("บันทึกอุปกรณ์", type="primary")
        if submitted:
            try:
                image = save_upload(uploaded)
            except DomainError as error:
                st.error(str(error))
            else:
                action(save_equipment, user["id"], {"equipment_code": code, "equipment_name": name, "category": category or "",
                       "description": description, "total_amount": total, "storage_location": location, "status": status,
                       "image": image}, selected, database_path, success="บันทึกอุปกรณ์แล้ว")
        if selected:
            st.caption("การปิดใช้งานจะเก็บประวัติเดิมไว้")
            confirmed = st.checkbox("ยืนยันปิดใช้งานอุปกรณ์รายการนี้", key=f"close_eq_{selected}")
            if st.button("ปิดใช้งานอุปกรณ์", disabled=not confirmed):
                action(deactivate_equipment, user["id"], selected, confirmed, database_path, success="ปิดใช้งานอุปกรณ์แล้ว")

def reset_catalog_page():
    st.session_state['equipment_page']=1


def change_catalog_page(delta,page_count):
    """เลื่อนหน้าได้ภายในจำนวนหน้าที่มี และปิดรายละเอียดรายการจากหน้าก่อน."""
    st.session_state['equipment_page']=max(1,min(page_count,st.session_state.get('equipment_page',1)+delta))
    close_overlays()


@st.dialog('รายละเอียดอุปกรณ์',width='large',on_dismiss=close_overlays)
def show_equipment_details(equipment_id,user,database_path):
    row=next((r for r in catalog(database_path=database_path) if r['id']==equipment_id),None)
    if row is None:
        st.info('อุปกรณ์รายการนี้ไม่พร้อมแสดง กรุณาค้นหาใหม่')
        return
    left,right=st.columns(2)
    left.image(str(equipment_image(row)),width='stretch')
    with right:
        st.subheader(row['equipment_name'])
        st.caption(f"{row['equipment_code']} · {row['category']}")
        st.text(row['description'] or 'ยังไม่มีรายละเอียดเพิ่มเติม')
        st.write(f"สถานะ: {row['status']}")
        st.write(f"พร้อมใช้ {row['available_amount']} จาก {row['total_amount']} ชิ้น")
        st.caption(f"จัดเก็บ: {row['storage_location']}")
        if row.get('has_reservation'):
            st.info('มีการจองล่วงหน้า ระบบจะตรวจช่วงวันอีกครั้งก่อนส่งคำขอยืม')
    if st.button('เลือกอุปกรณ์นี้',key='detail_start_borrow',type='primary',icon=':material/add_shopping_cart:',
                 disabled=not (row['available_amount']>0 and row['status']=='พร้อมใช้งาน'),width='stretch'):
        start_borrow(row['id']);st.rerun(scope='app')


def render_catalog(user,database_path):
    with st.container(key='catalog_section'):
        _render_catalog(user,database_path)


def _render_catalog(user,database_path):
    all_rows=catalog(database_path=database_path)
    categories=['ทุกหมวดหมู่',*sorted({row['category'] for row in all_rows})]
    if st.session_state.get('equipment_category') not in categories:
        st.session_state['equipment_category']=categories[0]
    with st.container(key='catalog_tools',horizontal=True,vertical_alignment='bottom',gap='small'):
        search=st.text_input('ค้นหาชื่อ รหัส หรือหมวดหมู่',key='equipment_search',
                            placeholder='ค้นหาอุปกรณ์สำหรับไอเดียของคุณ…',icon=':material/search:',
                            label_visibility='collapsed',on_change=reset_catalog_page,width='stretch',
                            help='กด / เพื่อไปช่องค้นหา เมื่อไม่ได้พิมพ์ในฟอร์มอื่น')
        with st.popover('ตัวกรอง',icon=':material/tune:'):
            status=st.selectbox('สถานะ',['ทั้งหมด','พร้อมใช้งาน','ถูกยืม','ชำรุด','ซ่อมบำรุง'],
                                key='equipment_status',on_change=reset_catalog_page)
            st.caption('เลือกหมวดหมู่จากแถบด้านล่าง และเปิดรายละเอียดเพื่อตรวจสถานที่จัดเก็บ')
        order=st.selectbox('เรียงตาม',['แนะนำ','ชื่อ ก–ฮ','พร้อมใช้มากที่สุด'],key='equipment_order',
                           label_visibility='collapsed',width=190,on_change=reset_catalog_page)
    with st.container(key='catalog_categories'):
        category=st.pills('หมวดหมู่อุปกรณ์',categories,key='equipment_category',required=True,
                          label_visibility='collapsed',on_change=reset_catalog_page)
    with st.container(key='catalog_view_switch',horizontal=True,horizontal_alignment='right'):
        view=st.segmented_control('มุมมองอุปกรณ์',['การ์ด','รายการ'],default='การ์ด',required=True,key='equipment_view',
                                  label_visibility='collapsed')
    rows=catalog(search,status,database_path)
    if category!='ทุกหมวดหมู่':
        rows=[row for row in rows if row['category']==category]
    if order=='แนะนำ':
        rows.sort(key=lambda row:(not (row['status']=='พร้อมใช้งาน' and row['available_amount']>0),row['equipment_name'].casefold()))
    elif order=='พร้อมใช้มากที่สุด':
        rows.sort(key=lambda row:(-row['available_amount'],row['equipment_name'].casefold()))
    else:
        rows.sort(key=lambda row:row['equipment_name'].casefold())
    if not rows:
        st.info('ไม่พบอุปกรณ์ที่ตรงกับการค้นหา ลองเปลี่ยนคำค้นหาหรือตัวกรอง')
        return
    page_size=8
    page_count=(len(rows)+page_size-1)//page_size
    if not 1<=st.session_state.get('equipment_page',1)<=page_count:
        st.session_state['equipment_page']=1
    summary_text=f'พบ {len(rows)} รายการ · เลือกอุปกรณ์ แล้วส่งคำขอพร้อมกันได้ในตะกร้า'
    if page_count>1:
        summary,pager=st.columns([3,2],vertical_alignment='center')
        summary.caption(summary_text)
        with pager.container(horizontal=True,horizontal_alignment='right',vertical_alignment='center',gap='small'):
            current=st.session_state.get('equipment_page',1)
            st.button('ก่อนหน้า',key='catalog_previous',icon=':material/chevron_left:',disabled=current<=1,
                      on_click=change_catalog_page,args=(-1,page_count),width='content')
            page=st.number_input('หน้า',min_value=1,max_value=page_count,step=1,key='equipment_page',
                                help=f'ทั้งหมด {page_count} หน้า',label_visibility='collapsed',width=85)
            st.caption(f'/ {page_count}',width='content')
            st.button('ถัดไป',key='catalog_next',icon=':material/chevron_right:',disabled=current>=page_count,
                      on_click=change_catalog_page,args=(1,page_count),width='content')
    else:
        st.caption(summary_text)
        page=1
    visible=rows[(page-1)*page_size:page*page_size]
    if view=='รายการ':
        with st.container(key='gallery_list'):
            for row in visible:
                with st.container(key=f'gallery_row_{row["id"]}',border=True):
                    image,info=st.columns([1,3],vertical_alignment='center')
                    image.image(str(equipment_image(row)),width='stretch')
                    with info:
                        st.subheader(row['equipment_name'])
                        st.caption(row['equipment_code']+' · '+row['category']+' · '+row['storage_location'])
                        st.badge(f"พร้อมใช้ {row['available_amount']} / {row['total_amount']} ชิ้น" if row['status']=='พร้อมใช้งาน' else row['status'],
                                 color='green' if row['status']=='พร้อมใช้งาน' and row['available_amount']>0 else 'orange')
                        _catalog_actions(row,user,database_path)
        return
    with st.container(key='gallery_grid'):
        for offset in range(0,len(visible),4):
            for column,row in zip(st.columns(4,gap='medium'),visible[offset:offset+4]):
                with column,st.container(key=f'gallery_card_{row["id"]}',gap='small'):
                    st.html(equipment_card_html(row))
                    _catalog_actions(row,user,database_path)


def _catalog_actions(row,user,database_path):
    ready=row['available_amount']>0 and row['status']=='พร้อมใช้งาน'
    details,borrow=st.columns(2,wrap=False)
    details.button('รายละเอียด',key=f'equipment_details_{row["id"]}',type='tertiary',width='stretch',
                   on_click=open_overlay,args=('equipment_detail_id',row['id']))
    if st.session_state.get('equipment_detail_id')==row['id']:
        show_equipment_details(row['id'],user,database_path)
    borrow.button('ยืมอุปกรณ์',key=f'equipment_borrow_{row["id"]}',icon=':material/add:',type='primary',
                  width='stretch',disabled=not ready,on_click=start_borrow,args=(row['id'],))


def render_equipment(user,database_path=DATABASE_PATH):
    st.html('<section class="sb-catalog-hero" aria-label="สำรวจอุปกรณ์">'
            '<h2>ไอเดียพร้อม อุปกรณ์ก็พร้อม</h2>'
            '<p>เลือกอุปกรณ์สำหรับการเรียนและกิจกรรมของคุณ</p></section>')
    st.title('อุปกรณ์')
    if user['role']=='admin':
        gallery,manage=st.tabs(['ค้นหาและยืม','จัดการอุปกรณ์'])
        with gallery:
            render_catalog(user,database_path)
        with manage:
            render_editor(user,database_path)
    else:
        render_catalog(user,database_path)
