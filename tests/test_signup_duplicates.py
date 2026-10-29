import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import test_features as fixtures
from registration import register_student,handle_registration
from common import DomainError
from database import database_connection
class SignupDuplicateTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.FeatureTests();self.f.setUp();self.addCleanup(self.f.tearDown)
    def register(self,username='NewUser123',email='new@example.com',code='690000001-1'):
        return register_student(code,username,'นักเรียนทดสอบ','ม.4/1','','password123','password123',self.f.path,email=email)
    def test_username_and_email_duplicate_ignore_case(self):
        self.register()
        for name,email,expected in [('newuser123','different@example.com','ชื่อผู้ใช้นี้ถูกใช้แล้ว'),('DifferentUser','NEW@EXAMPLE.COM','อีเมลนี้ถูกใช้แล้ว')]:
            with self.subTest(name=name),self.assertRaisesRegex(DomainError,expected):self.register(name,email,'690000002-2')
        with database_connection(self.f.path) as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM users').fetchone()[0],4)
    def test_duplicate_email_is_shown_in_signup_error(self):
        self.register()
        state={'register_student_code':'690000002-2','register_username':'OtherUser123','register_full_name':'ทดสอบ','register_classroom':'ม.4/1','register_phone':'','register_email':'NEW@example.com','register_password':'password123','register_password_confirm':'password123'}
        with patch('registration.st.session_state',state):handle_registration(self.f.path)
        self.assertIn('อีเมลนี้ถูกใช้แล้ว',state['registration_error'])
        self.assertEqual(state['register_password'],'')
        self.assertNotIn('auth_notice',state)
    def test_concurrent_same_email_only_one_account(self):
        def register(i):
            try:self.register('User'+str(i),'shared@example.com',f'69000000{i}-{i}');return True
            except DomainError as e:self.assertIn('อีเมลนี้ถูกใช้แล้ว',str(e));return False
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(register,[1,2])),1)
    def test_current_loopless_font_is_embedded_locally(self):
        from pathlib import Path
        from web_ui import apply_web_style
        calls=[]
        with patch('web_ui.st.html',side_effect=lambda value,**kwargs:calls.append(value)):apply_web_style()
        self.assertTrue(any(isinstance(v,str) and 'font-family:"SmartBorrow Thai"' in v and ';base64,' in v for v in calls))
        self.assertTrue(any(isinstance(v,Path) and v.name=='typography.css' for v in calls))
        from PIL import ImageFont
        self.assertEqual(ImageFont.truetype('assets/fonts/NotoSansThai.ttf',24).getname()[0],'Noto Sans Thai')
