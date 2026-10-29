# หน้าที่: เลือกจำนวนตามสต็อก จัดตะกร้า และแนบใบยืม
"""ตะกร้าใบคำขอหลายรายการ พร้อมตรวจสรุปและแนบเอกสาร."""
from datetime import timedelta
import sqlite3
import streamlit as st
from common import DomainError, thai_date, today
from database import DATABASE_PATH
from services import catalog
from design import equipment_image
from borrow_requests import preview_cart, request_cart, save_document, request_code,validate_pdf_upload
from database import PROJECT_DIR

def loan_pdf_upload():
    return st.file_uploader('อัปโหลดใบยืมที่กรอกแล้ว (PDF)',type=['pdf'],key='cart_document',on_change=clear_draft,max_upload_size=10)


def clear_draft():
    st.session_state.pop('borrow_draft', None)


def stock_limit(row):
    return max(0,int(row['available_amount'])) if row and row['status']=='พร้อมใช้งาน' else 0

def add_item(equipment_id,database_path=DATABASE_PATH):
    cart = dict(st.session_state.get('borrow_cart', {}))
    row=next((r for r in catalog(database_path=database_path) if r['id']==equipment_id),None)
    amount=st.session_state.get('selected_amount',1)
    if type(amount) is not int or amount<1:
        st.session_state['borrow_cart_error']='กรุณาระบุจำนวนเป็นจำนวนเต็มมากกว่า 0'
        clear_draft()
        return
    total=cart.get(equipment_id,0)+amount
    if total>stock_limit(row):
        st.session_state['borrow_cart_error']='จำนวนเกินอุปกรณ์พร้อมใช้ กรุณาตรวจจำนวนอีกครั้ง'
        clear_draft()
        return
    st.session_state.pop('borrow_cart_error',None)
    cart[equipment_id] = total
    st.session_state['borrow_cart'] = cart
    st.session_state[f'cart_qty_{equipment_id}'] = cart[equipment_id]
    clear_draft()


def remove_item(equipment_id):
    cart = dict(st.session_state.get('borrow_cart', {}))
    cart.pop(equipment_id, None)
    st.session_state['borrow_cart'] = cart
    st.session_state.pop(f'cart_qty_{equipment_id}', None)
    clear_draft()


def update_quantity(equipment_id,database_path=DATABASE_PATH):
    cart = dict(st.session_state.get('borrow_cart', {}))
    row=next((r for r in catalog(database_path=database_path) if r['id']==equipment_id),None)
    limit=stock_limit(row)
    if not limit:
        remove_item(equipment_id)
        st.session_state['borrow_cart_error']='อุปกรณ์รายการนี้ไม่พร้อมใช้ จึงนำออกจากตะกร้าแล้ว'
        return
    amount=min(limit,max(1,int(st.session_state[f'cart_qty_{equipment_id}'] or 1)))
    st.session_state[f'cart_qty_{equipment_id}']=amount
    cart[equipment_id] = amount
    st.session_state['borrow_cart'] = cart
    clear_draft()

def step_cart_quantity(equipment_id, step, database_path=DATABASE_PATH):
    """ปุ่มเพิ่มลดตรวจสต็อกล่าสุดทุกครั้ง และไม่ลดต่ำกว่า 1 ชิ้น"""
    amount=st.session_state.get('borrow_cart',{}).get(equipment_id)
    if amount is None:
        return
    st.session_state[f'cart_qty_{equipment_id}']=amount+step
    update_quantity(equipment_id,database_path)

def sync_cart_stock(options):
    cart=dict(st.session_state.get('borrow_cart',{}))
    changed=False
    for eid,amount in list(cart.items()):
        limit=stock_limit(options.get(eid))
        if not limit:
            cart.pop(eid);st.session_state.pop(f'cart_qty_{eid}',None);changed=True
        else:
            quantity=min(limit,max(1,int(amount)))
            changed=changed or quantity!=amount
            cart[eid]=quantity
            st.session_state[f'cart_qty_{eid}']=quantity
    st.session_state['borrow_cart']=cart
    if changed:
        clear_draft()
        st.session_state['borrow_cart_error']='ปรับตะกร้าตามจำนวนพร้อมใช้ล่าสุดแล้ว กรุณาตรวจรายการอีกครั้ง'


def render_borrow(user, database_path=DATABASE_PATH):
    if st.session_state.pop('reset_borrow_form',False):
        for key in ['cart_purpose','cart_document','cart_document_url','selected_amount']:
            st.session_state.pop(key,None)
    st.title('ยืมอุปกรณ์')
    st.caption('เลือกอุปกรณ์ → จัดตะกร้า → กรอกรายละเอียด → ตรวจสรุปก่อนส่ง')
    from web_ui import render_borrow_steps
    stage=3 if st.session_state.get('borrow_draft') else (2 if st.session_state.get('borrow_cart') or st.session_state.get('cart_purpose') else 1)
    render_borrow_steps(stage)
    options = {r['id']:r for r in catalog(database_path=database_path)}
    sync_cart_stock(options)
    if st.session_state.get('borrow_cart_error'):st.warning(st.session_state.pop('borrow_cart_error'))
    if not options:
        st.info('ยังไม่มีอุปกรณ์ในระบบ')
        return
    if st.session_state.get('borrow_equipment_id') not in options:
        st.session_state['borrow_equipment_id']=next((r['id'] for r in options.values()
            if r['status']=='พร้อมใช้งาน' and r['available_amount']>0),next(iter(options)))
    left,right=st.columns([1.05,1.45],gap='large')
    with left:
        with st.container(border=True,key='borrow_selection'):
            st.subheader('1. เลือกอุปกรณ์')
            selected = st.selectbox('เลือกอุปกรณ์', list(options), key='borrow_equipment_id', on_change=clear_draft,
                format_func=lambda key:f"{options[key]['equipment_code']} · {options[key]['equipment_name']}")
            row=options[selected]
            ready=row['status']=='พร้อมใช้งาน' and row['available_amount']>0
            preview,details=st.columns([1,4],gap='small',wrap=False,vertical_alignment='center')
            preview.image(str(equipment_image(row)),width=105)
            with details:
                st.markdown(f"**{row['equipment_name']}**")
                st.caption(f"{row['category']} · {row['storage_location']}")
                st.badge(f"พร้อมใช้ {row['available_amount']} ชิ้น",icon=':material/inventory_2:',color='red')
            with st.expander('รายละเอียดอุปกรณ์',icon=':material/info:'):
                st.text(row['description'] or 'ยังไม่มีรายละเอียดเพิ่มเติม')
            with st.container(horizontal=True,wrap=False,vertical_alignment='bottom'):
                remaining=max(0,stock_limit(row)-st.session_state.get('borrow_cart',{}).get(selected,0))
                st.session_state['selected_amount']=min(remaining,max(1,int(st.session_state.get('selected_amount') or 1))) if remaining else 0
                st.number_input('จำนวนที่ยืม',min_value=1 if remaining else 0,max_value=remaining,step=1,value=None,
                                key='selected_amount',disabled=not remaining,on_change=clear_draft,width=130)
                st.button('เพิ่มลงตะกร้า',icon=':material/add_shopping_cart:',type='primary',width='stretch',
                    disabled=not remaining,on_click=add_item,args=(selected,database_path))
            if ready and not remaining:st.caption('เพิ่มอุปกรณ์พร้อมใช้ทั้งหมดลงตะกร้าแล้ว')
            if not ready:
                st.warning('อุปกรณ์รายการนี้ยังไม่พร้อมยืม')
            if row.get('has_reservation'):
                st.caption('มีการจองล่วงหน้า ระบบจะตรวจช่วงวันก่อนส่งคำขอ')
        cart=dict(st.session_state.get('borrow_cart',{}))
        with st.container(border=True,key='borrow_cart_panel'):
            st.subheader('2. ตะกร้าของคุณ')
            with st.container(horizontal=True,gap='small'):
                st.badge(f'{len(cart)} รายการ',icon=':material/shopping_cart:',color='red')
                st.caption(f"รวม {sum(cart.values())} ชิ้น")
            if not cart:
                st.caption('เพิ่มหลายรายการลงตะกร้า หรือยืมเฉพาะอุปกรณ์ที่เลือกได้เลย')
            for eid,amount in cart.items():
                item=options.get(eid)
                with st.container(horizontal=True,wrap=False,vertical_alignment='center',gap='small'):
                    with st.container(gap=None):
                        st.markdown(f"**{item['equipment_name'] if item else 'อุปกรณ์ปิดใช้งาน'}**")
                        if item:
                            st.caption(f"{item['equipment_code']} · เหลือ {item['available_amount']} ชิ้น")
                    if f'cart_qty_{eid}' not in st.session_state:
                        st.session_state[f'cart_qty_{eid}']=amount
                    with st.container(horizontal=True,wrap=False,gap=None,vertical_alignment='center',width=130,key=f'cart_stepper_{eid}'):
                        st.button('−',key=f'cart_minus_{eid}',help='ลดจำนวน',disabled=amount<=1,
                                  on_click=step_cart_quantity,args=(eid,-1,database_path))
                        st.markdown(f'<span class="sb-cart-quantity" aria-label="จำนวน {amount} ชิ้น">{amount}</span>',unsafe_allow_html=True)
                        st.button('+',key=f'cart_plus_{eid}',help='เพิ่มจำนวน',disabled=amount>=stock_limit(item),
                                  on_click=step_cart_quantity,args=(eid,1,database_path))
                    st.button('นำออก',key=f'cart_remove_{eid}',type='tertiary',on_click=remove_item,args=(eid,))
    with right,st.container(border=True,key='borrow_details'):
        st.subheader('3. รายละเอียดคำขอ')
        st.caption('ใช้วันยืมและกำหนดคืนเดียวกันกับทุกชิ้นในตะกร้า')
        first,last=st.columns(2,wrap=False)
        # ตรวจใหม่ทุกรอบ เผื่อเปิดหน้าค้างข้ามวันตามเวลาไทย
        current_day = today()
        if st.session_state.get('cart_start') and st.session_state['cart_start'] < current_day:
            st.session_state['cart_start'] = current_day
            clear_draft()
            st.info('วันที่เดิมผ่านมาแล้ว ระบบปรับวันยืมเป็นวันนี้ กรุณาตรวจวันที่อีกครั้ง')
        start=first.date_input('วันที่ต้องการยืม',value=current_day,min_value=current_day,key='cart_start',on_change=clear_draft)
        earliest_return = start or current_day
        if st.session_state.get('cart_end') and st.session_state['cart_end'] < earliest_return:
            st.session_state['cart_end'] = earliest_return
            clear_draft()
        end=last.date_input('กำหนดคืน',value=max(current_day+timedelta(days=3),earliest_return),min_value=earliest_return,key='cart_end',on_change=clear_draft)
        st.caption(f'วันนี้ {thai_date(current_day)} · เวลาไทย · เลือกวันย้อนหลังไม่ได้')
        purpose=st.text_area('วัตถุประสงค์',placeholder='เช่น ใช้ถ่ายภาพกิจกรรมโรงเรียน',key='cart_purpose',on_change=clear_draft)
        with st.container(border=True,key='borrow_required_document'):
            st.subheader('เอกสารใบยืม (บังคับ)')
            st.caption('1. โหลด Word → 2. กรอกข้อมูลและลายเซ็นผู้ยืม → 3. บันทึกเป็น PDF แล้วอัปโหลด')
            template=PROJECT_DIR/'assets/documents/SmartBorrow-borrowing-form.docx'
            st.download_button('ดาวน์โหลดแบบฟอร์มยืม (Word)', template.read_bytes(),
                file_name='SmartBorrow-ใบยืมพัสดุ.docx', mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                icon=':material/download:', key='blank_borrowing_form')
            url=''
            document=loan_pdf_upload()
            st.caption('PDF ไม่เกิน 10 MB ไม่ตั้งรหัสผ่าน • ใช้เอกสารเดียวสำหรับรายการทั้งหมดในตะกร้า • Admin จะตรวจเอกสารก่อนอนุมัติ')
        st.caption('ยืมฟรี · เลือกวันใช้งานวันนี้หรือล่วงหน้าได้ ส่งเอกสารครั้งเดียว แล้วรออนุมัติและรับอุปกรณ์')
        if st.button('ตรวจสรุปคำขอยืม',type='primary',width='stretch',icon=':material/arrow_forward:'):
            items=[{'equipment_id':eid,'amount':qty} for eid,qty in cart.items()] if cart else [{'equipment_id':selected,'amount':st.session_state['selected_amount']}]
            try:
                validate_pdf_upload(document)
                draft=preview_cart(user['id'],items,start,end,purpose,url,database_path)
                draft['document_name']=document.name if document else ''
                st.session_state['borrow_draft']=draft
            except (DomainError,sqlite3.Error) as error:
                clear_draft()
                st.error(str(error) if isinstance(error,DomainError) else 'ไม่สามารถตรวจข้อมูลได้ กรุณาลองอีกครั้ง')
    draft = st.session_state.get('borrow_draft')
    if draft:
        with st.container(border=True,key='borrow_review'):
            st.subheader('สรุปคำขอยืม')
            st.write(f"ผู้ยืม: {user['full_name']} · วันที่ยืม: {thai_date(draft['start'])} · กำหนดคืน: {thai_date(draft['end'])}")
            st.dataframe([{'อุปกรณ์':options.get(i['equipment_id'],{}).get('equipment_name','ปิดใช้งาน'),'จำนวน':i['amount']} for i in draft['items']], hide_index=True, width='stretch')
            st.write(f"วัตถุประสงค์: {draft['purpose']}")
            if draft['document_url']:
                st.link_button('เปิดลิงก์เอกสาร', draft['document_url'])
            if draft['document_name']:
                st.caption('เอกสารแนบ: '+draft['document_name'])
            st.caption('ยืมฟรี · กันสต็อกเมื่ออนุมัติ · อัตราค่าปรับแจ้งและบันทึกตอนส่งมอบอุปกรณ์')
            if st.button('ยืนยันส่งคำขอยืม', type='primary'):
                saved = ''
                try:
                    saved = save_document(document)
                    payload = {k:v for k,v in draft.items() if k!='document_name'}
                    result = request_cart(user['id'], **payload, document_path=saved, database_path=database_path)
                except (DomainError,sqlite3.Error,OSError) as error:
                    if saved:
                        from borrow_requests import document_file
                        document_file(saved).unlink(missing_ok=True)
                    st.error(str(error) if isinstance(error,DomainError) else 'ไม่สามารถบันทึกข้อมูลได้ กรุณาลองอีกครั้ง')
                else:
                    st.session_state['borrow_cart'] = {}
                    st.session_state['reset_borrow_form'] = True
                    clear_draft()
                    for key in list(st.session_state):
                        if key.startswith('cart_qty_'):
                            del st.session_state[key]
                    st.session_state['flash_message'] = 'ส่งใบคำขอ '+request_code(result)+' แล้ว กำลังรออนุมัติ'
                    from loan_workspace import open_loan_task
                    open_loan_task(result['transaction_ids'][0],'history','รออนุมัติ')
                    st.rerun()

