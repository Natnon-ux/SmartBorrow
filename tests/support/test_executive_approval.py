import unittest
from datetime import timedelta
from streamlit.testing.v1 import AppTest
import test_features
from common import today,DomainError
from database import database_connection,initialize_database
from auth import authenticate_user
from user_management import save_user
from services import request_borrow,decide_borrow,handoff_borrow,transactions,catalog
from borrow_requests import decide_group
from notifications import notification_rows

class ExecutiveApprovalTests(unittest.TestCase):
    def setUp(self):
        self.f=test_features.FeatureTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.eq=self.f.create_equipment(2)
        self.users={}
        for title in ('director','deputy'):
            uid=save_user(self.f.admin['id'],dict(student_code=title,username=title,full_name=title,role='staff',executive_title=title),password='testpass123',database_path=self.f.path)
            self.users[title]=authenticate_user(title,'testpass123',self.f.path)
        self.tx=self.request()
    def request(self):return request_borrow(self.f.student['id'],self.eq,1,today(),today()+timedelta(days=3),'ทดสอบ',self.f.path)
    def row(self):return next(r for r in transactions(self.f.admin['id'],self.f.path) if r['id']==self.tx)
    def test_either_executive_can_finalize_and_staff_cannot(self):
        for title in ('director','deputy'):
            with self.subTest(title=title):
                if title=='deputy':self.tx=self.request()
                with self.assertRaises(DomainError):decide_borrow(self.users[title]['id'],self.tx,True,self.f.path)
                decide_borrow(self.f.admin['id'],self.tx,True,self.f.path)
                self.assertEqual(self.row()['review_stage'],'รออนุมัติสุดท้าย')
                self.assertEqual(self.row()['borrow_status'],'รออนุมัติ')
                for executive in self.users.values():
                    self.assertTrue(any(n['event_key']==f'final-review:{self.tx}:{executive["id"]}' for n in notification_rows(executive['id'],self.f.path)))
                self.assertFalse(any(n['event_key']==f'borrow:{self.tx}:approved' for n in notification_rows(self.f.student['id'],self.f.path)))
                with self.assertRaises(DomainError):decide_borrow(self.f.admin['id'],self.tx,True,self.f.path)
                with self.assertRaises(DomainError):handoff_borrow(self.f.admin['id'],self.tx,'ปกติ','assets/equipment/camera.png',self.f.path)
                decide_borrow(self.users[title]['id'],self.tx,True,self.f.path)
                self.assertEqual(self.row()['borrow_status'],'อนุมัติแล้ว')
                self.assertEqual(self.row()['final_approved_by'],self.users[title]['id'])
                self.assertEqual(self.row()['document_reviewed_by'],self.f.admin['id'])
                self.assertTrue(any(n['event_key']==f'borrow:{self.tx}:approved' for n in notification_rows(self.f.student['id'],self.f.path)))
                with self.assertRaises(DomainError):decide_borrow(self.users['deputy']['id'],self.tx,True,self.f.path)
    def test_group_review_and_final_approval_atomic(self):
        from services import save_equipment
        eq2=save_equipment(self.f.admin['id'],dict(equipment_code='MICZ',equipment_name='ไมค์ทดสอบ',category='ไมโครโฟน',storage_location='ห้องโสต',total_amount=2),database_path=self.f.path)
        second=request_borrow(self.f.student['id'],eq2,1,today(),today()+timedelta(days=3),'ทดสอบ',self.f.path)
        with database_connection(self.f.path) as con:con.execute("UPDATE borrow_transactions SET request_group='testgroup'")
        decide_group(self.f.admin['id'],'testgroup',True,self.f.path)
        self.assertEqual(catalog(database_path=self.f.path)[0]['available_amount'],2)
        decide_group(self.users['deputy']['id'],'testgroup',True,self.f.path)
        self.assertTrue(all(r['borrow_status']=='อนุมัติแล้ว' for r in transactions(self.f.admin['id'],self.f.path)))
        self.assertEqual(sum(r['available_amount'] for r in catalog(database_path=self.f.path)),2)
    def test_rejection_and_inactive_executive(self):
        decide_borrow(self.f.admin['id'],self.tx,True,self.f.path)
        with database_connection(self.f.path) as con:con.execute("UPDATE users SET status='inactive' WHERE id=?",(self.users['director']['id'],))
        with self.assertRaises(DomainError):decide_borrow(self.users['director']['id'],self.tx,True,self.f.path)
        decide_borrow(self.users['deputy']['id'],self.tx,False,self.f.path)
        self.assertEqual(self.row()['borrow_status'],'ไม่อนุมัติ')
        self.assertEqual(catalog(database_path=self.f.path)[0]['available_amount'],2)
    def test_approval_screens_show_separate_queues(self):
        def screen(user,path):
            from approvals import render_approvals
            render_approvals(user,path)
        app=AppTest.from_function(screen,args=(self.f.admin,self.f.path),default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(b.label=='ผ่านการตรวจและส่งอนุมัติสุดท้าย' for b in app.button))
        decide_borrow(self.f.admin['id'],self.tx,True,self.f.path)
        app=AppTest.from_function(screen,args=(self.users['director'],self.f.path),default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(b.label=='อนุมัติสุดท้าย' for b in app.button))
    def test_missing_executive_configuration_and_no_student_assignment(self):
        with database_connection(self.f.path) as con:con.execute("UPDATE users SET executive_title=''")
        with self.assertRaises(DomainError):decide_borrow(self.f.admin['id'],self.tx,True,self.f.path)
        self.assertEqual(self.row()['review_stage'],'')
        with self.assertRaises(DomainError):
            save_user(self.f.admin['id'],dict(self.f.student,executive_title='director'),user_id=self.f.student['id'],confirmed=True,database_path=self.f.path)
    def test_schema_upgrade_is_idempotent(self):
        before=self.row()
        initialize_database(self.f.path);initialize_database(self.f.path)
        self.assertEqual(self.row(),before)
    def test_final_rechecks_stock_without_partial_approval(self):
        decide_borrow(self.f.admin['id'],self.tx,True,self.f.path)
        competing=request_borrow(self.f.student['id'],self.eq,2,today(),today()+timedelta(days=3),'อีกคำขอ',self.f.path)
        decide_borrow(self.f.admin['id'],competing,True,self.f.path)
        decide_borrow(self.users['director']['id'],competing,True,self.f.path)
        with self.assertRaises(DomainError):decide_borrow(self.users['deputy']['id'],self.tx,True,self.f.path)
        self.assertIsNone(self.row()['final_approved_by'])
        self.assertEqual(self.row()['review_stage'],'รออนุมัติสุดท้าย')
    def test_reviewer_cannot_finalize_after_becoming_executive(self):
        decide_borrow(self.f.admin['id'],self.tx,True,self.f.path)
        with database_connection(self.f.path) as con:
            con.execute("UPDATE users SET executive_title='director' WHERE id=?",(self.f.admin['id'],))
        with self.assertRaises(DomainError):decide_borrow(self.f.admin['id'],self.tx,True,self.f.path)
        self.assertIsNone(self.row()['final_approved_by'])
    def test_admin_can_configure_executive_title_in_ui(self):
        def screen(user,path):
            from user_management import render_users
            render_users(user,path)
        app=AppTest.from_function(screen,args=(self.f.admin,self.f.path),default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(w.label=='สิทธิ์อนุมัติสุดท้าย' for w in app.selectbox))
