"""ตรวจสิทธิ์ผู้บริหาร วงจรส่งกลับ ประวัติ และสต็อกในฐานข้อมูลทดสอบเท่านั้น."""
import unittest
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from streamlit.testing.v1 import AppTest
import test_executive_approval as fixture
from common import DomainError,today
from database import database_connection,initialize_database
from executive_approval import return_for_review,approval_history,executive_overview
from services import (decide_borrow,transactions,catalog,request_borrow,handoff_borrow,
    request_return,confirm_return,cancel_borrow,save_equipment)
from borrow_requests import decide_group
from notifications import notification_rows


class ExecutiveWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.ExecutiveApprovalTests();self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.f=self.base.f;self.path=self.f.path;self.tx=self.base.tx
        self.director=self.base.users['director'];self.deputy=self.base.users['deputy']
    def row(self,tx=None):
        return next(r for r in transactions(self.f.admin['id'],self.path) if r['id']==(tx or self.tx))
    def review(self):decide_borrow(self.f.admin['id'],self.tx,True,self.path)
    def test_return_review_reapproval_and_early_return(self):
        self.review()
        return_for_review(self.director['id'],self.tx,'ตรวจจำนวนในเอกสารอีกครั้ง',self.path)
        self.assertEqual(self.row()['review_stage'],'ส่งกลับตรวจเพิ่ม')
        self.assertEqual(self.row()['borrow_status'],'รออนุมัติ')
        self.assertIsNone(self.row()['document_reviewed_by'])
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'],2)
        for uid in (self.f.admin['id'],self.f.student['id']):
            self.assertTrue(any('ตรวจจำนวนในเอกสาร' in n['message'] for n in notification_rows(uid,self.path)))
        with self.assertRaises(DomainError):decide_borrow(self.deputy['id'],self.tx,True,self.path)
        self.review()
        self.assertEqual(sum(n['event_key'].startswith(f'final-review:{self.tx}:') for n in notification_rows(self.deputy['id'],self.path)),2)
        decide_borrow(self.deputy['id'],self.tx,True,self.path,reason='ให้ใช้ในกิจกรรมตามกำหนด')
        events=approval_history(self.director['id'],self.path)
        self.assertEqual([r['action'] for r in events],['approved','reviewed','returned','reviewed'])
        self.assertEqual(events[0]['actor_name'],'deputy')
        self.assertEqual(events[0]['reason'],'ให้ใช้ในกิจกรรมตามกำหนด')
        self.assertTrue(any('รอนัดส่งมอบ' in n['message'] for n in notification_rows(self.f.admin['id'],self.path)))
        handoff_borrow(self.f.admin['id'],self.tx,'ปกติ','assets/equipment/camera.png',self.path)
        request_return(self.f.student['id'],self.tx,'ปกติ','assets/equipment/camera.png','คืนก่อนกำหนด',self.path)
        confirm_return(self.f.admin['id'],self.tx,self.path)
        self.assertEqual(self.row()['borrow_status'],'คืนแล้ว')
        self.assertEqual(self.row()['fine_amount_cents'],0)
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'],2)
    def test_rejection_requires_reason_and_notifies_borrower(self):
        self.review()
        with self.assertRaises(DomainError):decide_borrow(self.director['id'],self.tx,False,self.path)
        self.assertEqual(len(approval_history(self.director['id'],self.path)),1)
        decide_borrow(self.director['id'],self.tx,False,self.path,reason='ไม่ตรงวัตถุประสงค์การใช้')
        self.assertEqual(self.row()['borrow_status'],'ไม่อนุมัติ')
        self.assertIn('ไม่ตรงวัตถุประสงค์',notification_rows(self.f.student['id'],self.path)[0]['message'])
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'],2)
    def test_group_return_is_atomic_and_cannot_repeat(self):
        eq=save_equipment(self.f.admin['id'],dict(equipment_code='MIC-REV',equipment_name='ไมค์ทดสอบ',category='ไมโครโฟน',storage_location='ห้องทดสอบ',total_amount=1),database_path=self.path)
        second=request_borrow(self.f.student['id'],eq,1,today(),today()+timedelta(days=3),'ทดสอบทั้งใบ',self.path)
        with database_connection(self.path) as con:con.execute("UPDATE borrow_transactions SET request_group='reviewgroup'")
        decide_group(self.f.admin['id'],'reviewgroup',True,self.path)
        return_for_review(self.director['id'],self.tx,'ตรวจให้ครบทั้งใบ',self.path,whole_group=True)
        self.assertTrue(all(r['review_stage']=='ส่งกลับตรวจเพิ่ม' for r in transactions(self.f.admin['id'],self.path)))
        with self.assertRaises(DomainError):return_for_review(self.deputy['id'],second,'ส่งซ้ำ',self.path,whole_group=True)
        decide_group(self.f.admin['id'],'reviewgroup',True,self.path)
        decide_borrow(self.director['id'],second,True,self.path)
        before=len(approval_history(self.director['id'],self.path))
        with self.assertRaises(DomainError):return_for_review(self.director['id'],self.tx,'ห้ามครึ่งใบ',self.path,whole_group=True)
        self.assertEqual(self.row()['review_stage'],'รออนุมัติสุดท้าย')
        self.assertEqual(len(approval_history(self.director['id'],self.path)),before)
    def test_self_decision_all_outcomes_blocked(self):
        with database_connection(self.path) as con:con.execute('UPDATE borrow_transactions SET user_id=? WHERE id=?',(self.director['id'],self.tx))
        self.review()
        for approved in (True,False):
            with self.assertRaises(DomainError):decide_borrow(self.director['id'],self.tx,approved,self.path,reason='คำขอของตัวเอง')
        with self.assertRaises(DomainError):return_for_review(self.director['id'],self.tx,'ของตัวเอง',self.path)
        decide_borrow(self.deputy['id'],self.tx,True,self.path)
    def test_competing_executives_commit_only_once(self):
        self.review()
        def run(uid):
            try:decide_borrow(uid,self.tx,True,self.path);return True
            except DomainError:return False
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,[self.director['id'],self.deputy['id']]))
        self.assertEqual(sum(results),1)
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'],1)
        self.assertEqual(sum(r['action']=='approved' for r in approval_history(self.director['id'],self.path)),1)
    def test_executive_operational_writes_blocked_even_with_admin_role(self):
        with database_connection(self.path) as con:con.execute("UPDATE users SET role='admin' WHERE id=?",(self.director['id'],))
        self.review();decide_borrow(self.director['id'],self.tx,True,self.path)
        for fn,args in [(handoff_borrow,(self.tx,'ปกติ','assets/equipment/camera.png')), (cancel_borrow,(self.tx,)), (save_equipment,({},))]:
            with self.subTest(fn=fn.__name__),self.assertRaises(DomainError):fn(self.director['id'],*args,database_path=self.path)
        with self.assertRaises(DomainError):executive_overview(self.f.student['id'],self.path)
        with self.assertRaises(DomainError):approval_history(self.f.admin['id'],self.path)
    def test_overview_counts_and_schema_idempotent(self):
        self.review();self.assertEqual(executive_overview(self.director['id'],self.path)['pending'],1)
        decide_borrow(self.director['id'],self.tx,True,self.path)
        handoff_borrow(self.f.admin['id'],self.tx,'ปกติ','assets/equipment/camera.png',self.path)
        data=executive_overview(self.deputy['id'],self.path)
        self.assertEqual((data['borrowed'],data['pending'],data['overdue']),(1,0,0))
        before=approval_history(self.director['id'],self.path)
        initialize_database(self.path);initialize_database(self.path)
        self.assertEqual(before,approval_history(self.director['id'],self.path))
        with database_connection(self.path) as con:self.assertEqual(con.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_legacy_migration_preserves_actual_decisions(self):
        self.review();decide_borrow(self.deputy['id'],self.tx,True,self.path)
        with database_connection(self.path) as con:
            con.execute('DROP TABLE approval_events');con.execute('PRAGMA user_version=13')
        initialize_database(self.path)
        rows=approval_history(self.director['id'],self.path)
        self.assertEqual({r['action'] for r in rows},{'reviewed','approved'})
        self.assertEqual(next(r['actor_id'] for r in rows if r['action']=='approved'),self.deputy['id'])
        initialize_database(self.path)
        self.assertEqual(len(approval_history(self.director['id'],self.path)),2)
    def test_history_uses_thai_date_across_utc_midnight(self):
        from executive_workspace import event_date
        self.assertEqual(event_date('2026-10-28T23:30:00Z').isoformat(),'2026-10-29')
    def test_three_views_and_return_button_ui(self):
        self.review()
        def screen(user,path):
            from executive_workspace import render_executive_workspace
            render_executive_workspace(user,path)
        app=AppTest.from_function(screen,args=(self.director,self.path),default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(next(b for b in app.button if b.label=='อนุมัติสุดท้าย').disabled)
        app.text_area(key=f'executive_reason_{self.tx}').set_value('ขอให้ตรวจลายเซ็นอีกครั้ง').run()
        next(b for b in app.button if b.label=='ส่งกลับตรวจเพิ่ม').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.row()['review_stage'],'ส่งกลับตรวจเพิ่ม')
        for section in ('ประวัติการพิจารณา','ภาพรวม','คำขอรออนุมัติ'):
            app.session_state['executive_section']=section;app.run()
            self.assertFalse(app.exception)
            self.assertFalse(any('ยืนยันผู้ยืมรับ' in b.label for b in app.button))
    def test_inactive_revoked_and_blank_return_reasons(self):
        self.review()
        for reason in ('','   ','x'*1001):
            with self.assertRaises(DomainError):return_for_review(self.director['id'],self.tx,reason,self.path)
        with database_connection(self.path) as con:con.execute("UPDATE users SET executive_title='' WHERE id=?",(self.director['id'],))
        with self.assertRaises(DomainError):return_for_review(self.director['id'],self.tx,'ถูกถอดสิทธิ์',self.path)
        with database_connection(self.path) as con:con.execute("UPDATE users SET status='inactive' WHERE id=?",(self.deputy['id'],))
        with self.assertRaises(DomainError):executive_overview(self.deputy['id'],self.path)
