# หน้าที่: เปลี่ยนรูปโปรไฟล์ ซูมและครอปภาพ
"""Private, local avatar crop editor; only the confirmed square crop is saved."""
import base64
import binascii
from functools import partial
from hashlib import sha256
from io import BytesIO
import sqlite3
from PIL import Image, ImageOps, UnidentifiedImageError
import streamlit as st
from common import DomainError, PROJECT_DIR, require_actor, save_upload, validate_evidence
from database import DATABASE_PATH, database_connection

UI_DIR=PROJECT_DIR/'ui'
MAX_UPLOAD=5*1024*1024


def prepare_photo(content):
    if not content or len(content)>MAX_UPLOAD:
        raise DomainError('กรุณาเลือกรูปขนาดไม่เกิน 5 MB')
    try:
        with Image.open(BytesIO(content)) as original:
            if original.format not in {'PNG','JPEG','WEBP'} or original.width*original.height>20_000_000:
                raise DomainError('ใช้รูป PNG, JPEG หรือ WebP ขนาดไม่เกิน 20 ล้านพิกเซล')
            oriented=ImageOps.exif_transpose(original).convert('RGBA')
            oriented.thumbnail((1600,1600))
            image=Image.new('RGB',oriented.size,'white')
            image.paste(oriented,mask=oriented.getchannel('A'))
            buffer=BytesIO()
            image.save(buffer,format='PNG')
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as error:
        raise DomainError('อ่านรูปไม่ได้ กรุณาเลือกไฟล์ภาพที่ถูกต้อง') from error
    return {'image':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii'),
            'source_token':sha256(content).hexdigest()}


def decode_crop(value,expected_token):
    if not isinstance(value,dict) or value.get('source_token')!=expected_token:
        raise DomainError('รูปต้นฉบับเปลี่ยนแล้ว กรุณาจัดรูปใหม่')
    encoded=value.get('image')
    prefix='data:image/png;base64,'
    if not isinstance(encoded,str) or not encoded.startswith(prefix) or len(encoded)>MAX_UPLOAD*4//3+100:
        raise DomainError('ข้อมูลรูปไม่ถูกต้อง หรือรูปใหญ่เกินกำหนด')
    try:
        content=base64.b64decode(encoded[len(prefix):],validate=True)
        if len(content)>MAX_UPLOAD:
            raise DomainError('รูปต้องมีขนาดไม่เกิน 5 MB')
        with Image.open(BytesIO(content)) as image:
            if image.format!='PNG' or image.width!=image.height or not 128<=image.width<=1024:
                raise DomainError('กรุณาจัดรูปเป็นสี่เหลี่ยมก่อนบันทึก')
            image.verify()
    except (binascii.Error,UnidentifiedImageError,OSError,Image.DecompressionBombError) as error:
        raise DomainError('ข้อมูลรูปที่ครอปไม่ถูกต้อง') from error
    return content


def update_profile_photo(actor_id,image,database_path=DATABASE_PATH):
    validate_evidence(image)
    with database_connection(database_path) as con:
        require_actor(con,actor_id)
        con.execute('UPDATE users SET profile_image=? WHERE id=?',(image,actor_id))


def save_cropped_avatar(actor_id,source_token,database_path):
    saved=None
    st.session_state.pop('profile_crop_error',None)
    try:
        state=st.session_state.get('profile_photo_editor',{})
        result=state.get('save') if isinstance(state,dict) else None
        content=decode_crop(result,source_token)
        saved=save_upload(content,'profile')
        update_profile_photo(actor_id,saved,database_path)
    except (DomainError,sqlite3.Error,OSError) as error:
        # Only remove a new file created by this invocation, never the existing avatar.
        if saved:
            try:
                (PROJECT_DIR/saved).unlink(missing_ok=True)
            except OSError:
                pass
        st.session_state['profile_crop_error']=str(error) if isinstance(error,DomainError) else 'บันทึกรูปไม่ได้ กรุณาลองอีกครั้ง'
    else:
        st.session_state['profile_photo_saved']=True
        st.session_state['flash_message']='เปลี่ยนรูปโปรไฟล์แล้ว'


@st.dialog('จัดรูปโปรไฟล์',width='large')
def show_photo_editor(actor_id,database_path):
    if st.session_state.pop('profile_photo_saved',False):
        st.session_state.pop('profile_photo_upload',None)
        st.session_state.pop('profile_photo_camera',None)
        st.rerun(scope='app')
    st.caption('เลือกรูปหรือถ่ายจากกล้อง แล้วลากจัดตำแหน่งและซูมให้พอดีกับกรอบวงกลม')
    source=st.segmented_control('แหล่งรูปโปรไฟล์',['อัปโหลดรูป','ถ่ายจากกล้อง'],
                                default='อัปโหลดรูป',required=True,key='profile_photo_source')
    if source=='ถ่ายจากกล้อง':
        st.caption('อนุญาตให้เบราว์เซอร์ใช้กล้อง แล้วกดถ่ายรูป หากเปิดกล้องไม่ได้ให้เลือกอัปโหลดรูปแทน')
        upload=st.camera_input('ถ่ายรูปโปรไฟล์',key='profile_photo_camera')
    else:
        upload=st.file_uploader('เลือกรูปโปรไฟล์ใหม่',type=['png','jpg','jpeg','webp'],
                                key='profile_photo_upload',max_upload_size=5)
    if upload is None:
        st.info('รูปจะเปลี่ยนหลังจากกดบันทึกรูปเท่านั้น')
        return
    try:
        data=prepare_photo(upload.getvalue())
    except DomainError as error:
        st.error(str(error))
        return
    editor=st.components.v2.component('smartborrow_photo_editor',
        html=(UI_DIR/'photo_editor.html').read_text(encoding='utf-8'),
        css=(UI_DIR/'photo_editor.css').read_text(encoding='utf-8'),
        js=(UI_DIR/'photo_editor.js').read_text(encoding='utf-8'))
    editor(key='profile_photo_editor',data=data,
           on_save_change=partial(save_cropped_avatar,actor_id,data['source_token'],database_path))
    if st.session_state.get('profile_crop_error'):
        st.error(st.session_state['profile_crop_error'])
