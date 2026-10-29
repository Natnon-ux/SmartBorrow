# หน้าที่: โค้ดส่ง OTP เดิม เก็บไว้โดยไม่มีการส่งในระบบปัจจุบัน
"""SMTP/SMS transports; credentials come from env/project secrets only."""
from email.message import EmailMessage
import base64
import json
import os
import re
import smtplib
import ssl
import tomllib
from uuid import UUID
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from common import DomainError,PROJECT_DIR,require_actor
from database import database_connection,DATABASE_PATH

FIELDS={'smtp_host':'','smtp_port':'587','smtp_security':'STARTTLS','smtp_user':'','smtp_from':'',
        'twilio_sid':'','twilio_from':'','registration_otp_mode':'email',
        'sms_enabled':'yes','sms_provider':'twilio','thaibulksms_sender':'','thaibulksms_credit':'standard',
        'thaibulksms_trial_only':'yes','thaibulksms_trial_phone':'',
        'email_provider':'smtp','tbs_email_template':'','tbs_email_from':'',
        'tbs_email_name':'SmartBorrow','tbs_email_subject':'SmartBorrow - รหัสยืนยัน OTP ของคุณ'}


def registration_channels(mode):
    # Legacy settings cannot bypass mandatory email verification.
    if mode not in {'off','email','sms','both'}:
        raise DomainError('การตั้งค่า OTP ไม่ถูกต้อง กรุณาติดต่อผู้ดูแล')
    return ['email','sms'] if mode in {'sms','both'} else ['email']


def delivery_settings(database_path=DATABASE_PATH):
    with database_connection(database_path) as con:
        rows={r['key']:r['value'] for r in con.execute("SELECT key,value FROM app_settings WHERE key LIKE 'otp_%'")}
    config={key:rows.get('otp_'+key,default) for key,default in FIELDS.items()}
    config['registration_otp_mode']='both' if len(registration_channels(config['registration_otp_mode']))==2 else 'email'
    return config


def secret(name):
    value=os.environ.get(name,'')
    if value:return value
    path=PROJECT_DIR/'.streamlit/secrets.toml'
    try:
        return str(tomllib.loads(path.read_text(encoding='utf-8')).get(name,'')) if path.is_file() else ''
    except (OSError,tomllib.TOMLDecodeError):
        return ''


def channel_ready(channel,database_path=DATABASE_PATH):
    import otp_policy
    if not otp_policy.OTP_ENABLED:return False
    config=delivery_settings(database_path)
    if channel=='email':
        if config['email_provider']=='thaibulksms':
            return bool(config['tbs_email_template'] and config['tbs_email_from']
                        and secret('SMARTBORROW_TBS_EMAIL_KEY') and secret('SMARTBORROW_TBS_EMAIL_SECRET'))
        return bool(config['smtp_host'] and config['smtp_from'] and config['smtp_user'] and secret('SMARTBORROW_SMTP_PASSWORD'))
    if channel=='sms':
        if config['sms_enabled']!='yes':return False
        if config['sms_provider']=='thaibulksms':
            return bool(config['thaibulksms_sender'] and secret('SMARTBORROW_THAIBULKSMS_KEY')
                        and secret('SMARTBORROW_THAIBULKSMS_SECRET')
                        and (config['thaibulksms_trial_only']=='no' or config['thaibulksms_trial_phone']))
        return bool(config['twilio_sid'] and config['twilio_from'] and secret('SMARTBORROW_TWILIO_TOKEN'))
    return False


def save_delivery_settings(actor_id,values,database_path=DATABASE_PATH):
    values={key:str(values.get(key,FIELDS[key])).strip() for key in FIELDS}
    if values['email_provider'] not in {'smtp','thaibulksms'}:raise DomainError('บริการอีเมลไม่ถูกต้อง')
    if values['tbs_email_template']:
        try:values['tbs_email_template']=str(UUID(values['tbs_email_template']))
        except ValueError:raise DomainError('Template UUID ต้องเป็น UUID เต็มจากเมนูเทมเพลตอีเมล') from None
    if values['tbs_email_from'] and not re.fullmatch(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,63}',values['tbs_email_from']):
        raise DomainError('อีเมลผู้ส่ง ThaiBulkSMS ไม่ถูกต้อง')
    if not values['tbs_email_name'] or not values['tbs_email_subject'] or len(values['tbs_email_subject'])>200:
        raise DomainError('กรอกชื่อผู้ส่งและหัวข้ออีเมลให้ครบ หัวข้อไม่เกิน 200 ตัวอักษร')
    if values['sms_enabled'] not in {'yes','no'}:raise DomainError('ตัวเลือกเปิดใช้ SMS ไม่ถูกต้อง')
    if values['sms_enabled']=='no':values['registration_otp_mode']='email'
    if values['sms_provider'] not in {'twilio','thaibulksms'} or values['thaibulksms_credit'] not in {'standard','corporate'} or values['thaibulksms_trial_only'] not in {'yes','no'}:
        raise DomainError('ตัวเลือกผู้ให้บริการ SMS ไม่ถูกต้อง')
    if values['thaibulksms_sender'] and not re.fullmatch(r'[A-Za-z0-9 ._-]{1,11}',values['thaibulksms_sender']):
        raise DomainError('ชื่อผู้ส่ง ThaiBulkSMS ต้องเป็นชื่อที่อนุมัติแล้ว ความยาวไม่เกิน 11 ตัวอักษร')
    if values['thaibulksms_trial_phone']:
        from otp_service import normalize_destination
        values['thaibulksms_trial_phone']=normalize_destination('sms',values['thaibulksms_trial_phone'])
    if values['smtp_security'] not in {'STARTTLS','SSL'} or values['registration_otp_mode'] not in {'off','email','sms','both'}:
        raise DomainError('ตัวเลือกการส่ง OTP ไม่ถูกต้อง')
    values['registration_otp_mode']='both' if len(registration_channels(values['registration_otp_mode']))==2 else 'email'
    if not values['smtp_port'].isdigit() or not 1<=int(values['smtp_port'])<=65535:
        raise DomainError('พอร์ต SMTP ต้องอยู่ระหว่าง 1–65535')
    if values['smtp_host'] and not re.fullmatch(r'[a-zA-Z0-9.-]{1,253}',values['smtp_host']):
        raise DomainError('กรุณาระบุชื่อเซิร์ฟเวอร์ SMTP โดยไม่มี URL หรือช่องว่าง')
    if any('\r' in value or '\n' in value for value in values.values()):
        raise DomainError('ค่าตั้งค่าต้องไม่มีการขึ้นบรรทัดใหม่')
    if values['twilio_sid'] and not re.fullmatch(r'AC[0-9a-fA-F]{32}',values['twilio_sid']):
        raise DomainError('Twilio Account SID ต้องขึ้นต้น AC และตามด้วย 32 ตัวอักษรฐานสิบหก')
    if values['smtp_from'] and not re.fullmatch(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,63}',values['smtp_from']):
        raise DomainError('กรอกอีเมลผู้ส่ง SMTP ให้ถูกต้อง')
    if values['twilio_from'] and not re.fullmatch(r'\+[1-9]\d{7,14}',values['twilio_from']):
        raise DomainError('เบอร์ผู้ส่ง Twilio ต้องเป็นรูปแบบ +รหัสประเทศและหมายเลข')
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE');require_actor(con,actor_id,{'admin'})
        for key,value in values.items():
            con.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('otp_'+key,value))
        # Save setup in stages. Unconfigured channels cannot send or grant proofs.


def send_code(channel,destination,code,purpose,database_path=DATABASE_PATH):
    from otp_policy import require_otp_enabled
    require_otp_enabled()
    config=delivery_settings(database_path)
    message=f'SmartBorrow OTP: {code}. Expires in 5 minutes. Do not share this code.'
    try:
        if not channel_ready(channel,database_path):raise DomainError('ยังไม่ได้ตั้งค่าบริการส่ง OTP ช่องทางนี้')
        if channel=='email' and config['email_provider']=='thaibulksms':
            from otp_service import normalize_destination
            destination=normalize_destination('email',destination)
            payload={'template_uuid':str(UUID(config['tbs_email_template'])),
                     'mail_from':{'email':config['tbs_email_from'],'name':config['tbs_email_name']},
                     'mail_to':{'email':destination},'subject':config['tbs_email_subject'],
                     'payload':{'OTP':str(code)}}
            request=Request('https://email-api.thaibulksms.com/email/v1/send_template',
                            data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),method='POST')
            credentials=secret('SMARTBORROW_TBS_EMAIL_KEY')+':'+secret('SMARTBORROW_TBS_EMAIL_SECRET')
            request.add_header('Authorization','Basic '+base64.b64encode(credentials.encode()).decode())
            request.add_header('Content-Type','application/json')
            with urlopen(request,timeout=10) as response:
                if response.status!=201:raise DomainError('ผู้ให้บริการไม่รับอีเมล OTP')
                result=json.loads(response.read(65536))
            if not result.get('message_id'):raise DomainError('ผู้ให้บริการไม่รับอีเมล OTP')
        elif channel=='email':
            mail=EmailMessage();mail['Subject']='SmartBorrow — รหัสยืนยัน OTP'
            mail['From']=config['smtp_from'];mail['To']=destination;mail.set_content(message)
            context=ssl.create_default_context()
            if config['smtp_security']=='SSL':
                client=smtplib.SMTP_SSL(config['smtp_host'],int(config['smtp_port']),timeout=10,context=context)
            else:
                client=smtplib.SMTP(config['smtp_host'],int(config['smtp_port']),timeout=10)
            with client:
                if config['smtp_security']=='STARTTLS':client.starttls(context=context)
                client.login(config['smtp_user'],secret('SMARTBORROW_SMTP_PASSWORD'))
                client.send_message(mail)
        elif channel=='sms' and config['sms_provider']=='thaibulksms':
            from otp_service import normalize_destination
            destination=normalize_destination('sms',destination)
            if config['thaibulksms_trial_only']=='yes' and destination!=config['thaibulksms_trial_phone']:
                raise DomainError('โหมดทดลองส่งได้เฉพาะเบอร์ที่ลงทะเบียน ThaiBulkSMS ไว้')
            body=urlencode({'msisdn':destination,'sender':config['thaibulksms_sender'],
                            'message':message,'force':config['thaibulksms_credit']}).encode()
            request=Request('https://api-v2.thaibulksms.com/sms',data=body,method='POST')
            credentials=secret('SMARTBORROW_THAIBULKSMS_KEY')+':'+secret('SMARTBORROW_THAIBULKSMS_SECRET')
            request.add_header('Authorization','Basic '+base64.b64encode(credentials.encode()).decode())
            request.add_header('Content-Type','application/x-www-form-urlencoded')
            with urlopen(request,timeout=10) as response:
                payload=json.loads(response.read(65536))
            accepted=payload.get('phone_number_list',[])
            number=str(accepted[0].get('number','')) if len(accepted)==1 else ''
            if re.fullmatch(r'66[689]\d{8}',number):number='+'+number
            if payload.get('bad_phone_number_list') or len(accepted)!=1 or not accepted[0].get('message_id') or normalize_destination('sms',number)!=destination:
                raise DomainError('ผู้ให้บริการไม่รับข้อความ OTP กรุณาตรวจเครดิต เบอร์ทดลอง และชื่อผู้ส่ง')
        else:
            sid=config['twilio_sid']
            if not re.fullmatch(r'AC[0-9a-fA-F]{32}',sid):raise DomainError('ค่า Twilio SID ไม่ถูกต้อง')
            body=urlencode({'To':destination,'From':config['twilio_from'],'Body':message}).encode()
            request=Request(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',data=body,method='POST')
            auth=base64.b64encode(f'{sid}:{secret("SMARTBORROW_TWILIO_TOKEN")}'.encode()).decode()
            request.add_header('Authorization','Basic '+auth)
            request.add_header('Content-Type','application/x-www-form-urlencoded')
            with urlopen(request,timeout=10) as response:response.read(1024)
    except DomainError:raise
    except Exception:
        # Never surface transport responses, destination details, or authentication headers.
        raise DomainError('ส่ง OTP ไม่สำเร็จ กรุณาลองใหม่ภายหลังหรือติดต่อผู้ดูแล') from None
