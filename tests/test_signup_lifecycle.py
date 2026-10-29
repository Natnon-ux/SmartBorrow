"""สมัครบัญชีใหม่ผ่านฟอร์ม แล้วทดสอบยืมจนคืนผ่านผู้อนุมัติทั้งสองแบบ.

ใช้ fixture ในชุดตรวจระบบที่ data/audit_current.py คัดลอกไปพื้นที่ชั่วคราว
PDF และรูปทดสอบเป็นข้อมูลจำลอง ไม่ใช่เอกสารลงนามจริง
"""
import test_executive_end_to_end as lifecycle
from auth import authenticate_user
from database import database_connection
from notifications import notification_rows


class SignupLifecycleTests(lifecycle.ExecutiveEndToEndTests):
    def setup_flow(self):
        # เปิดหน้าสมัครจริงและส่งผ่าน callback เดียวกับหน้าเว็บ
        self.app.session_state['auth_view'] = 'สมัครสมาชิก'
        self.app.run()
        values = {
            'student_code': '690000001-1',
            'username': 'flowstudent',
            'full_name': 'นักเรียน ทดสอบวงจร',
            'classroom': 'ม.4/1',
            'phone': '',
            'email': 'flowstudent@example.com',
            'password': 'flowstudent123',
            'password_confirm': 'flowstudent123',
        }
        for name, value in values.items():
            self.app.text_input(key='register_' + name).set_value(value)
        self.press('สมัครสมาชิก')
        self.assertFalse(self.app.error)
        self.assertEqual(self.app.session_state['auth_view'], 'เข้าสู่ระบบ')
        fresh = authenticate_user('FLOWSTUDENT', 'flowstudent123', self.path)
        self.assertIsNotNone(fresh)
        self.assertEqual(fresh['role'], 'student')
        self.assertNotEqual(fresh['id'], self.fixture.student['id'])
        self.fixture.student = fresh
        with database_connection(self.path) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM users WHERE lower(username)=?', ('flowstudent',)).fetchone()[0], 1)
        # รหัสผิดต้องอยู่หน้าล็อกอิน และไม่เปิดเมนูผู้ใช้
        self.app.text_input(key='login_username').set_value('flowstudent')
        self.app.text_input(key='login_password').set_value('wrong-password')
        self.press('เข้าสู่ระบบ')
        self.assertTrue(self.app.error)
        self.assertFalse(any(b.key == 'top_cart' for b in self.app.button))
        super().setup_flow()

    def login(self, name='admin'):
        return super().login('flowstudent' if name == 'student' else name)

    def run_flow(self, executive):
        super().run_flow(executive)
        # ปลายทางการแจ้งผลคืนต้องไปประวัติ และสร้างครั้งเดียว
        with database_connection(self.path) as con:
            row = con.execute('SELECT id,borrow_status FROM borrow_transactions WHERE user_id=? ORDER BY id DESC LIMIT 1', (self.fixture.student['id'],)).fetchone()
        self.assertEqual(row['borrow_status'], 'คืนแล้ว')
        notices = [n for n in notification_rows(self.fixture.student['id'], self.path)
                   if n['event_key'] == f'return-confirmed:{row["id"]}']
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]['target_page'], 'history')
