"""ผู้บริหารเห็นเฉพาะงานอนุมัติ ไม่มีเมนูหน้าบ้านหรือส่วนส่งมอบ."""
import unittest
import test_executive_approval as fixtures
from streamlit.testing.v1 import AppTest
from services import decide_borrow
from navigation import allowed_pages


class ExecutivePortalTests(unittest.TestCase):
    def test_executive_restricted_to_approval_and_stale_page_redirected(self):
        fixture=fixtures.ExecutiveApprovalTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        decide_borrow(fixture.f.admin['id'],fixture.tx,True,fixture.f.path)
        for title in ('director','deputy'):
            with self.subTest(title=title):
                user=fixture.users[title]
                self.assertEqual(allowed_pages(user['role'],title),['approvals'])
                def screen(path):
                    from app import main
                    main(path)
                app=AppTest.from_function(screen,args=(fixture.f.path,),default_timeout=30)
                app.session_state['user']=user
                app.session_state['navigation_page']='equipment'
                app.run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['navigation_page'],'approvals')
                keys={b.key for b in app.button}
                self.assertIn('nav_approvals',keys)
                self.assertFalse(keys & {'nav_equipment','nav_return','nav_users','nav_settings','top_cart','top_profile','top_command'})
                self.assertFalse(any(s.key=='approval_handoff' for s in app.selectbox))
                self.assertFalse(any(b.label=='ยืนยันผู้ยืมรับอุปกรณ์แล้ว' for b in app.button))
                self.assertFalse(any(c.key=='usage_rules_acknowledged' for c in app.checkbox))
                self.assertTrue(any(b.label=='อนุมัติสุดท้าย' for b in app.button))
