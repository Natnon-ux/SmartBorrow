"""ทดสอบหน้าจอครบวงจรด้วย PDF และรูปจำลองในฐานข้อมูลชั่วคราว"""
import unittest
from unittest.mock import patch
from io import BytesIO
from PIL import Image
from test_ui import UITests
from user_management import save_user
from services import transactions,catalog,confirm_return,request_return
from notifications import notification_rows
from common import DomainError,today

class ExecutiveEndToEndTests(unittest.TestCase):
    setUp=UITests.setUp
    tearDown=UITests.tearDown
    press=UITests.press
    login=UITests.login
    accept_rules=UITests.accept_rules
    navigate=UITests.navigate

    def setup_flow(self):
        self.eq=self.fixture.create_equipment(2)
        for title in ('director','deputy'):
            save_user(self.fixture.admin['id'],dict(student_code='EXEC-'+title,username=title,full_name=title,role='staff',executive_title=title),password=title+'123',database_path=self.path)
        image=BytesIO();Image.new('RGB',(200,150),'#45a184').save(image,format='PNG')
        for target in ('approvals.evidence_input','returns.evidence_input'):
            p=patch(target,return_value=image.getvalue());p.start();self.addCleanup(p.stop)
    def row(self,tx):return next(r for r in transactions(self.fixture.student['id'],self.path) if r['id']==tx)
    def stock(self):return next(r for r in catalog(database_path=self.path) if r['id']==self.eq)['available_amount']
    def run_flow(self,executive):
        self.setup_flow()
        self.login('student');self.navigate('borrow')
        self.app.text_area(key='cart_purpose').set_value('ทดสอบยืมและคืนผ่านสองขั้นอนุมัติ')
        self.press('ตรวจสรุปคำขอยืม');self.press('ยืนยันส่งคำขอยืม')
        tx=transactions(self.fixture.student['id'],self.path)[0]['id']
        self.assertEqual(self.app.session_state['navigation_page'],'profile')
        self.assertTrue(self.row(tx)['document_path'].endswith('.pdf'))
        self.assertEqual(self.stock(),2)
        self.press('ออกจากระบบ');self.login();self.navigate('approvals')
        label='ผ่านการตรวจและส่งอนุมัติสุดท้าย'
        self.assertTrue(next(b for b in self.app.button if b.label==label).disabled)
        self.app.checkbox(key=f'approval_document_checked_{tx}').check().run()
        self.press(label)
        self.assertEqual(self.row(tx)['review_stage'],'รออนุมัติสุดท้าย')
        self.assertEqual(self.stock(),2)
        self.assertFalse(any(s.key=='approval_handoff' for s in self.app.selectbox))
        with self.assertRaises(DomainError):request_return(self.fixture.student['id'],tx,'ปกติ','assets/equipment/camera.png','',self.path)
        self.assertFalse(any(n['event_key']==f'borrow:{tx}:approved' for n in notification_rows(self.fixture.student['id'],self.path)))
        self.press('ออกจากระบบ');self.login(executive);self.navigate('approvals')
        self.assertTrue(next(b for b in self.app.button if b.label=='อนุมัติสุดท้าย').disabled)
        self.app.checkbox(key=f'approval_document_checked_{tx}').check().run()
        self.press('อนุมัติสุดท้าย')
        self.assertEqual(self.row(tx)['borrow_status'],'อนุมัติแล้ว')
        self.assertIsNotNone(self.row(tx)['final_approved_by'])
        self.assertEqual(self.stock(),1)
        self.assertEqual(len([n for n in notification_rows(self.fixture.student['id'],self.path) if n['event_key']==f'borrow:{tx}:approved']),1)
        self.press('ออกจากระบบ');self.login();self.navigate('approvals')
        self.app.session_state['approval_stage']='รอรับอุปกรณ์';self.app.run()
        self.press('ยืนยันผู้ยืมรับอุปกรณ์แล้ว')
        self.assertEqual(self.row(tx)['borrow_status'],'กำลังยืม')
        self.assertTrue(self.row(tx)['before_image'])
        self.press('ออกจากระบบ');self.login('student');self.navigate('profile')
        self.app.session_state['profile_section']='กำลังยืม';self.app.run()
        self.app.button(key=f'my_loan_return_{tx}').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state['navigation_page'],'return')
        self.assertEqual(self.app.selectbox(key='return_loan').value,tx)
        self.press('ส่งคำขอคืนก่อนกำหนด')
        self.assertEqual(self.row(tx)['borrow_status'],'รอตรวจสอบการคืน')
        self.assertTrue(self.row(tx)['after_image'])
        self.assertEqual(self.stock(),1)
        self.press('ออกจากระบบ');self.login();self.navigate('return')
        self.app.session_state['return_stage']='รายการรอตรวจรับ';self.app.run()
        button=next(b for b in self.app.button if b.label=='ยืนยันการคืน')
        self.assertTrue(button.disabled)
        next(c for c in self.app.checkbox if c.label=='ตรวจรับอุปกรณ์และตรวจสภาพจริงแล้ว').check().run()
        self.press('ยืนยันการคืน')
        self.assertEqual(self.row(tx)['borrow_status'],'คืนแล้ว')
        self.assertEqual(self.row(tx)['return_date'],today().isoformat())
        self.assertEqual(self.row(tx)['fine_amount_cents'],0)
        self.assertEqual(self.stock(),2)
        with self.assertRaises(DomainError):confirm_return(self.fixture.admin['id'],tx,self.path)
        self.assertEqual(self.stock(),2)
        self.press('ออกจากระบบ');self.login('student');self.navigate('profile')
        self.app.session_state['profile_section']='กำลังยืม';self.app.run()
        self.assertFalse(any(str(b.key).startswith('my_loan_return_') for b in self.app.button))
        self.assertFalse(self.app.exception)
    def test_director_request_to_return_ui(self):self.run_flow('director')
    def test_deputy_request_to_return_ui(self):self.run_flow('deputy')
