# หน้าที่: ตั้งค่าหน่วยงาน ค่าปรับ ช่องทางชำระ และสำรองฐานข้อมูล
"""STEP 23: ตั้งค่า URL, ตรวจสต็อก และสำรอง SQLite ด้วย Native UI."""
import sqlite3
import streamlit as st
from common import require_actor,HELD_STATUSES,action
from database import DATABASE_PATH,database_connection,get_database_overview,get_integrity_report
from qr_codes import DEFAULT_BASE_URL,validate_base_url
from fines import save_fine_rate,configured_rate

def get_setting(key,default='',database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        row=con.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone()
    return row['value'] if row else default

def save_settings(actor_id,school_name,base_url,database_path=DATABASE_PATH):
    base_url=validate_base_url(base_url)
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        require_actor(con,actor_id,{'admin'})
        for key,value in [('school_name',str(school_name).strip()[:200]),('base_url',base_url)]:
            con.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))

def stock_audit(database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        marks=','.join('?' for _ in HELD_STATUSES)
        rows=con.execute(f'SELECT e.*,COALESCE((SELECT SUM(b.amount) FROM borrow_transactions b WHERE b.equipment_id=e.id AND b.borrow_status IN ({marks})),0) held FROM equipment e',HELD_STATUSES)
        return [dict(r) for r in rows if r['available_amount']+r['unavailable_amount']+r['held']!=r['total_amount']]

def backup_database(actor_id,database_path=DATABASE_PATH):
    with database_connection(database_path) as source:
        require_actor(source,actor_id,{'admin'})
        target=sqlite3.connect(':memory:')
        try:
            source.backup(target)
            return target.serialize()
        finally:
            target.close()

def render_settings(user,database_path=DATABASE_PATH):
    st.title('ตั้งค่า')
    if user['role']!='admin':
        st.error('เฉพาะ Admin สามารถตั้งค่าระบบได้')
        return
    st.caption('จัดการข้อมูลหน่วยงาน อัตราค่าปรับ และความพร้อมของระบบ')
    general,fine_tab,health=st.tabs(['ทั่วไป','ค่าปรับ','ฐานข้อมูล'])
    with general:
        with st.form('system_settings'):
            school=st.text_input('ชื่อโรงเรียน / หน่วยงาน',get_setting('school_name','โรงเรียน',database_path))
            if st.form_submit_button('บันทึกการตั้งค่า',type='primary'):
                action(save_settings,user['id'],school,get_setting('base_url',DEFAULT_BASE_URL,database_path),database_path,success='บันทึกการตั้งค่าแล้ว')
    with fine_tab:
        from fine_payments import render_payment_settings
        render_payment_settings(user,database_path)
        st.subheader('ค่าปรับคืนเกินกำหนด')
        with database_connection(database_path) as con:
            rate=configured_rate(con)/100
        with st.form('fine_settings'):
            amount=st.number_input('ค่าปรับต่อชิ้นต่อวัน (บาท)',min_value=0.0,max_value=1000000.0,value=rate,step=1.0,format='%.2f')
            st.caption('0 = ยังไม่คิดค่าปรับ อัตราใหม่ใช้กับรายการที่ส่งมอบหลังบันทึกเท่านั้น คิดจนถึงวันที่ตรวจรับจริง')
            if st.form_submit_button('บันทึกอัตราค่าปรับ',type='primary'):
                action(save_fine_rate,user['id'],amount,database_path,success='บันทึกอัตราค่าปรับแล้ว')
    with health:
        st.subheader('ความพร้อมของข้อมูล')
        report=get_integrity_report(database_path)
        errors=stock_audit(database_path)
        if report['ok'] and not errors:
            st.success('ฐานข้อมูล ความสัมพันธ์ และจำนวนสต็อกผ่านการตรวจสอบ')
        else:
            st.error('พบข้อมูลที่ต้องตรวจสอบ กรุณาติดต่อผู้ดูแลระบบ')
            if errors:
                st.dataframe([{'รหัส':r['equipment_code'],'ทั้งหมด':r['total_amount'],'พร้อมใช้':r['available_amount'],'กันไว้':r['held'],'ไม่พร้อมใช้':r['unavailable_amount']} for r in errors],hide_index=True)
        st.dataframe(get_database_overview(database_path),hide_index=True,width='stretch')
        st.caption(f"เวอร์ชันโครงสร้างข้อมูล: {report['schema_version']}")
        with st.expander('สำรองข้อมูล'):
            st.caption('ไฟล์ฐานข้อมูลรวมบัญชีและแฮชรหัสผ่าน ส่วนรูปอัปโหลดเก็บใน data/uploads ให้สำรองโฟลเดอร์นี้ด้วย')
            if st.button('เตรียมไฟล์สำรองฐานข้อมูล'):
                st.download_button('ดาวน์โหลด SQLite',backup_database(user['id'],database_path),file_name='smartborrow-backup.db',mime='application/octet-stream')


def render_otp_settings(actor_id,database_path=DATABASE_PATH):
    import otp_policy
    if not otp_policy.OTP_ENABLED:
        otp_policy.render_staff_recovery()
        return
    from otp_delivery import delivery_settings,channel_ready,save_delivery_settings
    config=delivery_settings(database_path)
    st.subheader('ช่องทางยืนยันบัญชี')
    st.caption('ยืนยันบัญชีและกู้คืนรหัสผ่านด้วย OTP ทางอีเมล')
    a,b=st.columns(2)
    for column,channel,label in [(a,'email','อีเมล'),(b,'sms','SMS')]:
        with column:
            st.badge(label+' · '+('ตั้งค่าครบแล้ว' if channel_ready(channel,database_path) else 'ยังไม่เชื่อมบริการ'),
                     color='green' if channel_ready(channel,database_path) else 'orange')
    with st.form('otp_delivery_settings'):
        email_providers={'thaibulksms':'ThaiBulkSMS Email API','smtp':'SMTP / Gmail / Resend'}
        email_provider=st.selectbox('บริการส่งอีเมล OTP',list(email_providers),index=list(email_providers).index(config['email_provider']),format_func=email_providers.get)
        with st.expander('ThaiBulkSMS Email API',expanded=config['email_provider']=='thaibulksms'):
            template=st.text_input('Email Template UUID',config['tbs_email_template'],placeholder='UUID เต็มจาก SmartBorrow - Email OTP')
            tbs_from=st.text_input('อีเมลผู้ส่ง ThaiBulkSMS',config['tbs_email_from'])
            tbs_name=st.text_input('ชื่อผู้ส่งอีเมล',config['tbs_email_name'])
            tbs_subject=st.text_input('หัวข้ออีเมล OTP',config['tbs_email_subject'])
            st.caption('ใช้ Email API Key / Secret ใน SMARTBORROW_TBS_EMAIL_KEY และ SMARTBORROW_TBS_EMAIL_SECRET ระบบแทน {{OTP}} ด้วยรหัสจริง ไม่ส่งแคมเปญเป็นกลุ่ม')
        st.markdown('**อีเมล · SMTP**')
        a,b=st.columns([3,1])
        host=a.text_input('SMTP Host',config['smtp_host'],placeholder='smtp.example.com')
        port=b.number_input('SMTP Port',min_value=1,max_value=65535,value=int(config['smtp_port']))
        security=st.selectbox('การเข้ารหัส SMTP',['STARTTLS','SSL'],index=['STARTTLS','SSL'].index(config['smtp_security']))
        username=st.text_input('SMTP Username',config['smtp_user'])
        from_email=st.text_input('อีเมลผู้ส่ง',config['smtp_from'])
        st.caption('รหัสผ่าน SMTP อ่านจาก SMARTBORROW_SMTP_PASSWORD บนเซิร์ฟเวอร์')
        sms_enabled=st.checkbox('เปิดใช้ OTP ทาง SMS เพิ่มเติม',value=config['sms_enabled']=='yes')
        with st.expander('SMS · ตัวเลือกเพิ่มเติม',expanded=config['sms_enabled']=='yes'):
            st.markdown('**SMS · ผู้ให้บริการ (ตัวเลือกเพิ่มเติม)**')
            providers={'thaibulksms':'ThaiBulkSMS','twilio':'Twilio'}
            provider=st.selectbox('บริการส่ง SMS',list(providers),index=list(providers).index(config['sms_provider']),format_func=providers.get)
            st.markdown('**ThaiBulkSMS · ตั้งค่าทดลอง**')
            st.caption('เครดิตฟรีทดลอง 20 เครดิตตามเงื่อนไขผู้ให้บริการ ส่งได้เฉพาะเบอร์ที่ลงทะเบียน ไม่ใช่การส่งฟรีไม่จำกัด')
            sender=st.text_input('ชื่อผู้ส่ง ThaiBulkSMS',config['thaibulksms_sender'],placeholder='ชื่อผู้ส่งที่มีอยู่ในบัญชี ThaiBulkSMS')
            credit=st.selectbox('ประเภทเครดิต ThaiBulkSMS',['standard','corporate'],index=['standard','corporate'].index(config['thaibulksms_credit']))
            trial=st.checkbox('จำกัดส่งเฉพาะเบอร์ทดลอง',value=config['thaibulksms_trial_only']=='yes')
            trial_phone=st.text_input('เบอร์ที่ลงทะเบียน ThaiBulkSMS',config['thaibulksms_trial_phone'],placeholder='08xxxxxxxx')
            st.caption('API Key / Secret อ่านจาก SMARTBORROW_THAIBULKSMS_KEY และ SMARTBORROW_THAIBULKSMS_SECRET ใน secrets.toml ใช้คีย์ SMS API ไม่ใช่คีย์ OTP Ready to use')
            st.markdown('**Twilio · สำหรับเลือกใช้ภายหลัง**')
            sid=st.text_input('Twilio Account SID',config['twilio_sid'])
            from_phone=st.text_input('เบอร์ผู้ส่ง Twilio',config['twilio_from'],placeholder='+12345678900')
            st.caption('Auth Token อ่านจาก SMARTBORROW_TWILIO_TOKEN บนเซิร์ฟเวอร์')
        labels={'email':'ยืนยันอีเมล (บังคับ)','both':'ยืนยันอีเมลและเบอร์มือถือ'} if config['sms_enabled']=='yes' else {'email':'ยืนยันอีเมล (บังคับ)'}
        mode=st.selectbox('การยืนยันตอนสมัครสมาชิก',list(labels),index=list(labels).index(config['registration_otp_mode']),format_func=labels.get)
        st.caption('สมัครใหม่ต้องกรอกและยืนยันอีเมลเสมอ บันทึกการตั้งค่าล่วงหน้าได้ แต่ผู้สมัครต้องรอจนบริการส่งพร้อม บัญชีเดิมยืนยันช่องทางกู้คืนได้ในโปรไฟล์')
        if st.form_submit_button('บันทึกการตั้งค่า OTP',type='primary'):
            values={'email_provider':email_provider,'tbs_email_template':template,'tbs_email_from':tbs_from,'tbs_email_name':tbs_name,'tbs_email_subject':tbs_subject,
                    'smtp_host':host,'smtp_port':str(port),'smtp_security':security,'smtp_user':username,'smtp_from':from_email,
                    'twilio_sid':sid,'twilio_from':from_phone,'registration_otp_mode':mode,
                    'sms_enabled':'yes' if sms_enabled else 'no','sms_provider':provider,'thaibulksms_sender':sender,'thaibulksms_credit':credit,
                    'thaibulksms_trial_only':'yes' if trial else 'no','thaibulksms_trial_phone':trial_phone}
            action(save_delivery_settings,actor_id,values,database_path,success='บันทึกการตั้งค่า OTP แล้ว')
    if not channel_ready('email',database_path):
        st.warning('ยังส่งอีเมล OTP ไม่ได้: ตั้งค่าผู้ให้บริการที่เลือกให้ครบ รวมคีย์หรือรหัสผ่านใน secrets.toml การสมัครใหม่จะรอการยืนยัน OTP')
    with st.expander('เชื่อมบริการบนเซิร์ฟเวอร์'):
        st.write('คัดลอก .streamlit/secrets.example.toml เป็น .streamlit/secrets.toml แล้วใส่ค่าจากผู้ให้บริการ หรือกำหนด environment variables ชื่อเดียวกัน จากนั้นรีสตาร์ตเว็บ')
        st.caption('หน้านี้ไม่แสดงหรือบันทึกรหัสผ่านและ Auth Token ลง SQLite และจะไม่ส่ง OTP ทดสอบอัตโนมัติ')
        st.write('OTP มีอายุ 5 นาที ใช้ครั้งเดียว ลองผิดได้ 5 ครั้ง ขอใหม่ได้หลัง 60 วินาที และไม่เกิน 5 ครั้งต่อชั่วโมงต่อช่องทางติดต่อ')
        st.link_button('สมัครทดลอง ThaiBulkSMS','https://account.thaibulksms.com/register/')
        st.link_button('คู่มือ SMS API ThaiBulkSMS','https://developer.thaibulksms.com/')
        st.caption('ชื่อผู้ส่งต้องตรงกับบัญชีผู้ให้บริการ โหมดทดลองจำกัดเบอร์แต่ไม่ได้สร้างเครดิตให้ ตรวจเครดิตในบัญชี ThaiBulkSMS ก่อนส่ง อีเมล OTP ยังต้องตั้งค่า SMTP แยกต่างหาก')
