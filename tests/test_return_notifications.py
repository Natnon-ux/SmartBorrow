"""ทดสอบแจ้งคืนและผลตรวจรับในฐานข้อมูลแยก พร้อมป้องกันแจ้งซ้ำ."""
import unittest
from datetime import timedelta
from unittest.mock import patch
import test_executive_return_edges as fixture
from common import DomainError,today
from services import request_return,confirm_return
from notifications import notification_rows,notify_return_requested,notify_return_confirmed
from database import database_connection


class ReturnNotificationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ExecutiveReturnEdges()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.tx=self.f.borrow()
        self.path=self.f.f.path
        self.admin=self.f.f.admin['id']
        self.student=self.f.f.student['id']

    def test_return_request_reaches_staff_and_opens_inspection(self):
        request_return(self.student,self.tx,'ปกติ','assets/equipment/camera.png','คืนก่อนกำหนด',self.path)
        notices=[r for r in notification_rows(self.admin,self.path) if r['event_key'].startswith('return-requested:')]
        self.assertEqual(len(notices),1)
        self.assertEqual((notices[0]['reference_id'],notices[0]['target_page']),(self.tx,'return'))
        with database_connection(self.path) as con:notify_return_requested(con,self.tx)
        self.assertEqual(len([r for r in notification_rows(self.admin,self.path) if r['event_key'].startswith('return-requested:')]),1)
        self.assertFalse(any(r['event_key'].startswith('return-requested:') for r in notification_rows(self.f.executive,self.path)))
        with self.assertRaises(DomainError):request_return(self.student,self.tx,'ปกติ','assets/equipment/camera.png','',self.path)

    def test_confirmation_notifies_borrower_once_and_routes_fine(self):
        day=today()+timedelta(days=5)
        with patch('services.today',return_value=day),patch('fines.today',return_value=day):
            request_return(self.student,self.tx,'ปกติ','assets/equipment/camera.png','คืนช้า',self.path)
            confirm_return(self.admin,self.tx,self.path)
        notices=[r for r in notification_rows(self.student,self.path) if r['event_key'].startswith('return-confirmed:')]
        self.assertEqual(len(notices),1)
        self.assertEqual(notices[0]['target_page'],'fines')
        self.assertIn('20.00',notices[0]['message'])
        with database_connection(self.path) as con:notify_return_confirmed(con,self.tx)
        self.assertEqual(len([r for r in notification_rows(self.student,self.path) if r['event_key'].startswith('return-confirmed:')]),1)
        with self.assertRaises(DomainError):confirm_return(self.admin,self.tx,self.path)

    def test_on_time_return_routes_to_history_without_fine(self):
        request_return(self.student,self.tx,'ปกติ','assets/equipment/camera.png','คืนก่อนกำหนด',self.path)
        confirm_return(self.admin,self.tx,self.path)
        notice=next(r for r in notification_rows(self.student,self.path) if r['event_key'].startswith('return-confirmed:'))
        self.assertEqual(notice['target_page'],'history')
        self.assertNotIn('ค่าปรับ',notice['message'])

    def test_open_return_notification_focuses_exact_inspection(self):
        from streamlit.testing.v1 import AppTest
        request_return(self.student,self.tx,'ปกติ','assets/equipment/camera.png','คืนก่อนกำหนด',self.path)
        notice=next(r for r in notification_rows(self.admin,self.path) if r['event_key'].startswith('return-requested:'))
        def screen(user,path):
            import streamlit as st
            from notifications import render_notifications
            st.session_state['user']=user
            render_notifications(user,path)
        app=AppTest.from_function(screen,args=(self.f.f.admin,self.path)).run()
        self.assertFalse(app.exception)
        app.button(key=f'notification_open_{notice["id"]}').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['navigation_page'],'return')
        self.assertEqual(app.session_state['return_stage'],'รายการรอตรวจรับ')
        self.assertEqual(app.session_state['loan_task_id'],self.tx)

    def test_evidence_upload_limit_matches_backend(self):
        from streamlit.testing.v1 import AppTest
        def screen():
            from common import evidence_input
            evidence_input('รูปหลักฐาน','test_limit')
        app=AppTest.from_function(screen).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.get('file_uploader')[0].proto.max_upload_size_mb,5)
