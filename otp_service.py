# หน้าที่: โค้ด OTP เดิมที่ยังถูกนำเข้า แต่ไม่ทำงานเมื่อ OTP ปิด
"""Expiring, rate-limited OTPs and single-use proofs bound to the intended operation."""
import hashlib
import hmac
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from common import DomainError,require_actor,utc_now
from database import database_connection,DATABASE_PATH
from otp_delivery import channel_ready,send_code,secret

_PEPPER=secret('SMARTBORROW_OTP_PEPPER') or secrets.token_hex(32)
_WORKERS=ThreadPoolExecutor(max_workers=4,thread_name_prefix='smartborrow-otp')
INVALID='รหัสไม่ถูกต้อง หมดอายุ หรือถูกใช้แล้ว กรุณาขอรหัสใหม่'


def normalize_destination(channel,value):
    value=str(value).strip()
    if channel=='email':
        value=value.lower()
        if len(value)>254 or not re.fullmatch(r'[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,63}',value):
            raise DomainError('กรุณากรอกอีเมลให้ถูกต้อง')
    elif channel=='sms':
        value=re.sub(r'[\s()-]','',value)
        if re.fullmatch(r'0[689]\d{8}',value):value='+66'+value[1:]
        if not re.fullmatch(r'\+[1-9]\d{7,14}',value):raise DomainError('กรอกเบอร์มือถือไทย หรือเบอร์แบบ +รหัสประเทศ')
    else:raise DomainError('ช่องทาง OTP ไม่ถูกต้อง')
    return value


def mask_destination(channel,value):
    if channel=='email':
        local,domain=value.split('@',1);return local[:1]+'***@'+domain
    return value[:3]+'******'+value[-3:]


def binding_for(user_id,version,purpose,destination):
    return hashlib.sha256(f'{user_id}:{version}:{purpose}:{destination}'.encode()).hexdigest()


def _deliver(challenge,channel,destination,code,purpose,path,noop=False,sender=None):
    state='noop' if noop else 'sent'
    try:
        if not noop:(sender or send_code)(channel,destination,code,purpose,path)
    except Exception:state='failed'
    with database_connection(path) as con:
        con.execute("UPDATE otp_challenges SET delivery_state=?,status=CASE WHEN ?='failed' THEN 'failed' ELSE status END WHERE id=?",(state,state,challenge))


def request_otp(purpose,channel,destination,*,user_id=None,auth_version=None,binding='',database_path=DATABASE_PATH,sender=None,noop=False,now=None):
    from otp_policy import require_otp_enabled
    require_otp_enabled()
    destination=normalize_destination(channel,destination)
    if purpose not in {'register','recover','change_email','change_phone','authorize_change','change_password'}:
        raise DomainError('การยืนยันนี้ไม่ถูกต้อง')
    if sender is None and not channel_ready(channel,database_path):raise DomainError('ยังไม่ได้ตั้งค่าบริการส่ง OTP ช่องทางนี้')
    now=int(time.time()) if now is None else int(now)
    challenge=secrets.token_urlsafe(24);code=f'{secrets.randbelow(1_000_000):06}'
    digest=hmac.new(_PEPPER.encode(),f'{challenge}:{code}'.encode(),hashlib.sha256).hexdigest()
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        recent=con.execute('SELECT MAX(created_at) latest,COUNT(*) total FROM otp_challenges WHERE channel=? AND destination=? AND created_at>?',(channel,destination,now-3600)).fetchone()
        if recent['latest'] is not None and now-recent['latest']<60:raise DomainError('กรุณารอ 60 วินาทีก่อนขอ OTP ใหม่')
        if recent['total']>=5:raise DomainError('ขอ OTP บ่อยเกินไป กรุณาลองใหม่ในอีกหนึ่งชั่วโมง')
        if con.execute('SELECT COUNT(*) FROM otp_challenges WHERE created_at>?',(now-3600,)).fetchone()[0]>=100:
            raise DomainError('ระบบส่ง OTP ถึงขีดจำกัดชั่วคราว กรุณาลองใหม่ภายหลัง')
        con.execute("UPDATE otp_challenges SET status='superseded' WHERE purpose=? AND channel=? AND destination=? AND binding=? AND status IN ('pending','verified')",(purpose,channel,destination,binding))
        con.execute('INSERT INTO otp_challenges(id,purpose,channel,destination,user_id,auth_version,binding,code_hash,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (challenge,purpose,channel,destination,user_id,auth_version,binding,digest,now,now+300))
    args=(challenge,channel,destination,code,purpose,database_path,noop,sender)
    if sender is not None:_deliver(*args)
    else:_WORKERS.submit(_deliver,*args)
    return challenge


def verify_otp(challenge,code,database_path=DATABASE_PATH,now=None):
    from otp_policy import require_otp_enabled
    require_otp_enabled()
    now=int(time.time()) if now is None else int(now)
    error=None;proof=None
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT * FROM otp_challenges WHERE id=?',(str(challenge),)).fetchone()
        if row is None or row['status']!='pending' or row['expires_at']<=now or row['attempts']>=5 or row['delivery_state']!='sent':
            error=INVALID
        else:
            digest=hmac.new(_PEPPER.encode(),f'{challenge}:{str(code).strip()}'.encode(),hashlib.sha256).hexdigest()
            if not re.fullmatch(r'\d{6}',str(code).strip()) or not hmac.compare_digest(digest,row['code_hash']):
                con.execute("UPDATE otp_challenges SET attempts=attempts+1,status=CASE WHEN attempts+1>=5 THEN 'failed' ELSE status END WHERE id=?",(challenge,))
                error=INVALID
            else:
                token=secrets.token_urlsafe(32)
                con.execute("UPDATE otp_challenges SET status='verified',proof_hash=?,proof_expires_at=? WHERE id=?",(hashlib.sha256(token.encode()).hexdigest(),now+600,challenge))
                proof=challenge+'.'+token
    if error:raise DomainError(error)
    return proof


def consume_proof(con,proof,purpose,channel,destination,user_id,binding,now=None):
    from otp_policy import require_otp_enabled
    require_otp_enabled()
    now=int(time.time()) if now is None else int(now)
    if not isinstance(proof,str) or len(proof)>200 or '.' not in proof:raise DomainError(INVALID)
    challenge,token=proof.split('.',1)
    row=con.execute('SELECT * FROM otp_challenges WHERE id=?',(challenge,)).fetchone()
    if (row is None or row['status']!='verified' or not row['proof_expires_at'] or row['proof_expires_at']<=now
        or (row['purpose'],row['channel'],row['destination'],row['user_id'],row['binding'])!=(purpose,channel,destination,user_id,binding)
        or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),row['proof_hash'] or '')):
        raise DomainError(INVALID)
    if user_id is not None:
        actor=con.execute("SELECT auth_version,status FROM users WHERE id=?",(user_id,)).fetchone()
        if actor is None or actor['status']!='active' or actor['auth_version']!=row['auth_version']:raise DomainError(INVALID)
    con.execute("UPDATE otp_challenges SET status='used',proof_hash=NULL WHERE id=?",(challenge,))


def request_recovery(username,channel,destination,database_path=DATABASE_PATH,sender=None,now=None):
    destination=normalize_destination(channel,destination)
    field,verified=('email','email_verified_at') if channel=='email' else ('phone','phone_verified_at')
    with database_connection(database_path) as con:
        row=con.execute(f'SELECT * FROM users WHERE username=? AND {field}=? AND {verified} IS NOT NULL AND status=\'active\'',(str(username).strip(),destination)).fetchone()
    uid=row['id'] if row else None;version=row['auth_version'] if row else None
    binding=binding_for(uid,version,'recover',destination)
    return request_otp('recover',channel,destination,user_id=uid,auth_version=version,binding=binding,
                       database_path=database_path,sender=sender,noop=row is None,now=now)


def reset_with_proof(proof,password,confirm,database_path=DATABASE_PATH,now=None):
    from user_management import validate_password
    from auth import hash_password
    validate_password(password)
    if not password.strip() or password!=confirm:raise DomainError('รหัสผ่านทั้งสองช่องต้องตรงกันและไม่เป็นช่องว่าง')
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        challenge=str(proof).split('.',1)[0]
        row=con.execute('SELECT * FROM otp_challenges WHERE id=?',(challenge,)).fetchone()
        if row is None or row['user_id'] is None or row['purpose'] not in {'recover','change_password'}:raise DomainError(INVALID)
        user=con.execute('SELECT * FROM users WHERE id=?',(row['user_id'],)).fetchone()
        field,verified=('email','email_verified_at') if row['channel']=='email' else ('phone','phone_verified_at')
        if user is None or not user[verified] or user[field]!=row['destination']:raise DomainError(INVALID)
        consume_proof(con,proof,row['purpose'],row['channel'],row['destination'],row['user_id'],row['binding'],now)
        con.execute('UPDATE users SET password=?,auth_version=auth_version+1 WHERE id=?',(hash_password(password),user['id']))
        con.execute("UPDATE otp_challenges SET status='superseded',proof_hash=NULL WHERE user_id=? AND status IN ('pending','verified')",(user['id'],))
        con.execute("INSERT INTO notifications(user_id,event_key,message) VALUES(?,?,?)",(user['id'],'security:password:'+secrets.token_hex(16),'รหัสผ่านบัญชีของคุณถูกเปลี่ยนแล้ว หากไม่ได้ดำเนินการเอง กรุณาติดต่อผู้ดูแล'))


def request_password_change(actor_id,current_password,channel,database_path=DATABASE_PATH,sender=None):
    from auth import verify_password
    with database_connection(database_path) as con:
        require_actor(con,actor_id);row=con.execute('SELECT * FROM users WHERE id=?',(actor_id,)).fetchone()
    if not verify_password(current_password,row['password']):raise DomainError('รหัสผ่านปัจจุบันไม่ถูกต้อง')
    field,verified=('email','email_verified_at') if channel=='email' else ('phone','phone_verified_at')
    if not row[verified]:raise DomainError('ยืนยันช่องทางนี้ในโปรไฟล์ก่อนเปลี่ยนรหัสผ่าน')
    binding=binding_for(actor_id,row['auth_version'],'change_password',row[field])
    return request_otp('change_password',channel,row[field],user_id=actor_id,auth_version=row['auth_version'],binding=binding,database_path=database_path,sender=sender)


def request_contact_change(actor_id,channel,destination,current_password,database_path=DATABASE_PATH,sender=None):
    from auth import verify_password
    destination=normalize_destination(channel,destination)
    with database_connection(database_path) as con:
        require_actor(con,actor_id);row=con.execute('SELECT * FROM users WHERE id=?',(actor_id,)).fetchone()
    if not verify_password(current_password,row['password']):raise DomainError('รหัสผ่านปัจจุบันไม่ถูกต้อง')
    purpose='change_email' if channel=='email' else 'change_phone'
    binding=binding_for(actor_id,row['auth_version'],purpose,destination)
    old=None
    if row['email_verified_at']:old=('email',row['email'])
    elif row['phone_verified_at']:old=('sms',row['phone'])
    if old and old==(channel,destination):raise DomainError('ช่องทางนี้ยืนยันไว้แล้ว')
    authorization=None
    if old:
        authorization=request_otp('authorize_change',*old,user_id=actor_id,auth_version=row['auth_version'],binding=binding,database_path=database_path,sender=sender)
    challenge=request_otp(purpose,channel,destination,user_id=actor_id,auth_version=row['auth_version'],binding=binding,database_path=database_path,sender=sender)
    return {'challenge':challenge,'authorization':authorization,'old_channel':old[0] if old else None,
            'old_masked':mask_destination(*old) if old else None,'destination':destination,'channel':channel}


def change_contact(actor_id,channel,destination,proof,authorization=None,database_path=DATABASE_PATH,now=None):
    destination=normalize_destination(channel,destination)
    field,verified=('email','email_verified_at') if channel=='email' else ('phone','phone_verified_at')
    purpose='change_email' if channel=='email' else 'change_phone'
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE');require_actor(con,actor_id)
        row=con.execute('SELECT * FROM users WHERE id=?',(actor_id,)).fetchone()
        binding=binding_for(actor_id,row['auth_version'],purpose,destination)
        old=('email',row['email']) if row['email_verified_at'] else (('sms',row['phone']) if row['phone_verified_at'] else None)
        if old:consume_proof(con,authorization,'authorize_change',*old,actor_id,binding,now)
        consume_proof(con,proof,purpose,channel,destination,actor_id,binding,now)
        if con.execute(f'SELECT 1 FROM users WHERE {field}=? AND {verified} IS NOT NULL AND id!=?',(destination,actor_id)).fetchone():
            raise DomainError('ช่องทางนี้ถูกยืนยันกับบัญชีอื่นแล้ว')
        con.execute(f'UPDATE users SET {field}=?,{verified}=?,auth_version=auth_version+1 WHERE id=?',(destination,utc_now(),actor_id))
        con.execute("UPDATE otp_challenges SET status='superseded',proof_hash=NULL WHERE user_id=? AND status IN ('pending','verified')",(actor_id,))
        con.execute('INSERT INTO notifications(user_id,event_key,message) VALUES(?,?,?)',(actor_id,'security:contact:'+secrets.token_hex(16),'ช่องทางติดต่อสำหรับกู้คืนบัญชีของคุณถูกเปลี่ยนแล้ว'))
