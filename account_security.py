# หน้าที่: ข้อมูลติดต่อและช่วยเหลือบัญชีเมื่อไม่ใช้ OTP
"""Native forms for verification; codes and transport secrets are never displayed."""
import sqlite3
import streamlit as st
from common import DomainError
from database import database_connection
from otp_delivery import channel_ready
from otp_service import (normalize_destination,mask_destination,request_otp,verify_otp,
                         request_recovery,request_contact_change,change_contact,
                         request_password_change,reset_with_proof)

CHANNELS={'อีเมล':'email','SMS':'sms'}


def _perform(prefix,operation,*args,**kwargs):
    st.session_state.pop(prefix+'_error',None)
    try:
        return operation(*args,**kwargs)
    except DomainError as error:
        st.session_state[prefix+'_error']=str(error)
    except (sqlite3.Error,OSError):
        st.session_state[prefix+'_error']='ไม่สามารถดำเนินการได้ กรุณาตรวจสอบข้อมูลแล้วลองใหม่'
    return None


def _verify(prefix,challenge,path):
    code=st.session_state.get(prefix+'_code','')
    st.session_state[prefix+'_code']=''
    proof=_perform(prefix,verify_otp,challenge,code,path)
    if proof:st.session_state[prefix+'_proof']=proof


def verification_block(prefix,challenge,path,label='รหัส OTP 6 หลัก'):
    if st.session_state.get(prefix+'_proof'):
        st.success('ยืนยัน OTP แล้ว • ใช้ดำเนินการได้ภายใน 10 นาที')
    else:
        with st.form(prefix+'_verify'):
            st.text_input(label,key=prefix+'_code',max_chars=6,autocomplete='one-time-code')
            st.form_submit_button('ยืนยัน OTP',on_click=_verify,args=(prefix,challenge,path))
    if st.session_state.get(prefix+'_error'):st.error(st.session_state[prefix+'_error'])


def _request_registration(prefix,channel,destination_key,path):
    challenge=_perform(prefix,request_otp,'register',channel,st.session_state.get(destination_key,''),database_path=path)
    if challenge:
        st.session_state[prefix+'_challenge']=challenge
        st.session_state.pop(prefix+'_proof',None)


def registration_verification(channel,destination_key,path):
    prefix='signup_otp_'+channel
    destination=st.session_state.get(destination_key,'').strip()
    if st.session_state.get(prefix+'_destination')!=destination:
        for suffix in ('challenge','proof','error'):st.session_state.pop(prefix+'_'+suffix,None)
        st.session_state[prefix+'_destination']=destination
    ready=channel_ready(channel,path)
    st.button('ส่ง OTP ทาง '+('อีเมล' if channel=='email' else 'SMS'),key=prefix+'_send',
              type='primary',width='stretch',disabled=not ready or not destination,on_click=_request_registration,args=(prefix,channel,destination_key,path))
    if not ready:st.caption('ผู้ดูแลยังไม่ได้เชื่อมบริการส่ง OTP ช่องทางนี้')
    challenge=st.session_state.get(prefix+'_challenge')
    if challenge:
        st.caption('รหัสมีอายุ 5 นาที ขอใหม่ได้หลัง 60 วินาที')
        verification_block(prefix,challenge,path)
    elif st.session_state.get(prefix+'_error'):st.error(st.session_state[prefix+'_error'])


def _start_recovery(path):
    channel=CHANNELS[st.session_state['recover_channel']]
    challenge=_perform('recover',request_recovery,st.session_state.get('recover_username',''),channel,
                       st.session_state.get('recover_destination',''),path)
    if challenge:
        st.session_state['recover_challenge']=challenge
        st.session_state.pop('recover_proof',None)


def _reset_password(prefix,path):
    password=st.session_state.get(prefix+'_password','');confirm=st.session_state.get(prefix+'_confirm','')
    st.session_state[prefix+'_password']='';st.session_state[prefix+'_confirm']=''
    # Operation returns None on success; inspect the error slot instead.
    _perform(prefix,reset_with_proof,st.session_state.get(prefix+'_proof',''),password,confirm,path)
    if prefix+'_error' not in st.session_state:
        from auth import logout_user
        logout_user('เปลี่ยนรหัสผ่านสำเร็จ กรุณาเข้าสู่ระบบใหม่ ทุกเซสชันเดิมถูกยกเลิกแล้ว')


def _new_password_form(prefix,path):
    with st.form(prefix+'_new_password'):
        st.text_input('รหัสผ่านใหม่',type='password',key=prefix+'_password')
        st.text_input('ยืนยันรหัสผ่านใหม่',type='password',key=prefix+'_confirm')
        st.form_submit_button('บันทึกรหัสผ่านใหม่',type='primary',on_click=_reset_password,args=(prefix,path))
    if st.session_state.get(prefix+'_error'):st.error(st.session_state[prefix+'_error'])


def render_recovery(database_path):
    import otp_policy
    if not otp_policy.OTP_ENABLED:
        otp_policy.render_staff_recovery(show_contacts=True)
        return
    st.caption('ใช้ชื่อผู้ใช้และอีเมลหรือเบอร์ที่ยืนยันไว้ในโปรไฟล์')
    channel_label=st.selectbox('รับรหัสกู้คืนทาง',list(CHANNELS),key='recover_channel')
    channel=CHANNELS[channel_label]
    with st.form('recover_request'):
        st.text_input('ชื่อผู้ใช้ของบัญชี',key='recover_username')
        st.text_input('อีเมลที่ยืนยันไว้' if channel=='email' else 'เบอร์ที่ยืนยันไว้',key='recover_destination')
        st.form_submit_button('ขอ OTP กู้คืนบัญชี',disabled=not channel_ready(channel,database_path),
                              on_click=_start_recovery,args=(database_path,))
    if not channel_ready(channel,database_path):st.info('ยังไม่ได้เปิดบริการส่ง OTP กรุณาติดต่อผู้ดูแลเพื่อกู้คืนบัญชี')
    if st.session_state.get('recover_error'):st.error(st.session_state['recover_error'])
    if st.session_state.get('recover_challenge'):
        st.info('หากข้อมูลตรงกับบัญชีที่ยืนยันไว้ ระบบจะส่ง OTP ให้ รหัสมีอายุ 5 นาที ขอใหม่ได้หลัง 60 วินาที')
        verification_block('recover',st.session_state['recover_challenge'],database_path)
        if st.session_state.get('recover_proof'):_new_password_form('recover',database_path)


def _start_contact(actor_id,path):
    password=st.session_state.get('contact_password','');st.session_state['contact_password']=''
    channel=CHANNELS[st.session_state['contact_channel']]
    details=_perform('contact',request_contact_change,actor_id,channel,st.session_state.get('contact_destination',''),password,path)
    if details:
        st.session_state['contact_request']=details
        for key in ('contact_new_proof','contact_old_proof'):st.session_state.pop(key,None)


def _save_contact(actor_id,path):
    details=st.session_state.get('contact_request',{})
    _perform('contact',change_contact,actor_id,details.get('channel'),details.get('destination',''),
             st.session_state.get('contact_new_proof',''),st.session_state.get('contact_old_proof'),path)
    if 'contact_error' not in st.session_state:
        from auth import logout_user
        logout_user('ยืนยันช่องทางติดต่อแล้ว กรุณาเข้าสู่ระบบใหม่เพื่อใช้งานต่อ')


def _start_password(actor_id,path):
    password=st.session_state.get('password_change_current','');st.session_state['password_change_current']=''
    channel=st.session_state['password_change_channel']
    challenge=_perform('password_change',request_password_change,actor_id,password,channel,path)
    if challenge:
        st.session_state['password_change_challenge']=challenge
        st.session_state.pop('password_change_proof',None)


def render_account_security(actor_id,database_path):
    import otp_policy
    if not otp_policy.OTP_ENABLED:
        otp_policy.render_staff_recovery()
        return
    with database_connection(database_path) as con:
        user=dict(con.execute('SELECT * FROM users WHERE id=?',(actor_id,)).fetchone())
    # Never let an unfinished operation belonging to another login survive logout/login.
    identity=(actor_id,user['auth_version'])
    if st.session_state.get('security_identity')!=identity:
        for key in list(st.session_state):
            if key.startswith(('contact_','password_change_')):st.session_state.pop(key,None)
        st.session_state['security_identity']=identity
    for channel,field in [('email','email'),('sms','phone')]:
        confirmed=bool(user[field+'_verified_at'])
        st.write(('อีเมล' if channel=='email' else 'เบอร์โทร')+' · '+
                 (mask_destination(channel,user[field]) if confirmed else 'ยังไม่ได้ยืนยัน')+
                 (' ✓' if confirmed else ''))
    st.caption('ช่องทางที่ยืนยันแล้วใช้กู้คืนบัญชีได้ การเปลี่ยนข้อมูลต้องใช้ OTP จากช่องทางเดิมและช่องทางใหม่')
    st.subheader('ยืนยันหรือเปลี่ยนช่องทางติดต่อ')
    selected=st.selectbox('ช่องทางติดต่อ',list(CHANNELS),key='contact_channel')
    channel=CHANNELS[selected]
    with st.form('contact_request_form'):
        st.text_input('อีเมลใหม่' if channel=='email' else 'เบอร์มือถือใหม่',key='contact_destination')
        st.text_input('รหัสผ่านปัจจุบัน',type='password',key='contact_password')
        st.form_submit_button('ขอ OTP ยืนยันช่องทาง',disabled=not channel_ready(channel,database_path),
                              on_click=_start_contact,args=(actor_id,database_path))
    if not channel_ready(channel,database_path):st.info('ผู้ดูแลยังไม่ได้เชื่อมบริการส่ง '+selected)
    if st.session_state.get('contact_error'):st.error(st.session_state['contact_error'])
    details=st.session_state.get('contact_request')
    if details:
        if details['authorization']:
            st.caption('ยืนยันช่องทางเดิม: '+details['old_masked'])
            verification_block('contact_old',details['authorization'],database_path,'OTP จากช่องทางเดิม')
        st.caption('ยืนยันช่องทางใหม่: '+mask_destination(details['channel'],details['destination']))
        verification_block('contact_new',details['challenge'],database_path,'OTP จากช่องทางใหม่')
        verified=bool(st.session_state.get('contact_new_proof')) and (not details['authorization'] or bool(st.session_state.get('contact_old_proof')))
        st.button('บันทึกช่องทางที่ยืนยันแล้ว',disabled=not verified,on_click=_save_contact,args=(actor_id,database_path))
    st.subheader('เปลี่ยนรหัสผ่าน')
    channels=[c for c,f in [('email','email'),('sms','phone')] if user[f+'_verified_at']]
    if not channels:
        st.caption('ยืนยันอีเมลหรือเบอร์โทรด้านบนก่อนเปลี่ยนรหัสผ่านด้วย OTP')
        return
    channel=st.selectbox('รับ OTP เปลี่ยนรหัสผ่านทาง',channels,format_func=lambda c:'อีเมล' if c=='email' else 'SMS',key='password_change_channel')
    with st.form('password_change_request'):
        st.text_input('รหัสผ่านปัจจุบันเพื่อเปลี่ยนรหัส',type='password',key='password_change_current')
        st.form_submit_button('ขอ OTP เปลี่ยนรหัสผ่าน',disabled=not channel_ready(channel,database_path),on_click=_start_password,args=(actor_id,database_path))
    if st.session_state.get('password_change_error'):st.error(st.session_state['password_change_error'])
    if st.session_state.get('password_change_challenge'):
        verification_block('password_change',st.session_state['password_change_challenge'],database_path)
        if st.session_state.get('password_change_proof'):_new_password_form('password_change',database_path)
