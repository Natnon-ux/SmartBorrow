"""ตรวจหน้าจอ Streamlit และ flow ด้วยฐานข้อมูลแยกจากข้อมูลใช้งานจริง."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import test_features as fixtures
from services import transactions, handoff_borrow, request_return
from pathlib import Path
from seed_data import seed_sample_data
from navigation import allowed_pages
from services import catalog,maintenance_rows,save_equipment
from user_management import user_rows
from auth import authenticate_user

class UITests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.FeatureTests()
        self.fixture.setUp()
        self.path=self.fixture.path
        from test_pdf_fixtures import install_pdf_fixture,pdf_upload
        install_pdf_fixture(self,self.path)
        self.pdf_upload_patch=patch('borrowing.loan_pdf_upload',return_value=pdf_upload());self.pdf_upload_patch.start()
        self.addCleanup(self.pdf_upload_patch.stop)
        self.patch=patch('database.DATABASE_PATH',self.path)
        self.patch.start()
        self.app=AppTest.from_file(str(Path(__file__).resolve().parents[2] / 'app.py'),default_timeout=30).run()
    def tearDown(self):
        self.patch.stop()
        self.fixture.tearDown()
    def press(self,label):
        next(b for b in self.app.button if b.label==label).click().run()
        self.assertFalse(self.app.exception)
    def login(self,name='admin'):
        scan=self.app.query_params.get('equipment')
        self.app.query_params.clear()
        if scan:self.app.query_params['equipment']=scan
        if name=='admin':self.app.query_params['portal']='admin'
        self.app.run()
        self.app.text_input[0].set_value(name)
        self.app.text_input[1].set_value(name+'123')
        self.press('เข้าสู่ระบบ')
        self.accept_rules()
    def accept_rules(self):
        if any(b.key=='usage_rules_logout' for b in self.app.button):
            self.app.checkbox(key='usage_rules_acknowledged').check().run()
            self.press('ยอมรับและเข้าใช้งาน')
    def navigate(self,page):
        if page in {'history','fines'}:
            self.app.button(key='top_profile').click().run()
            self.app.session_state['profile_section']='ประวัติการยืม' if page=='history' else 'ค่าปรับ'
            self.app.run()
        elif page=='borrow':self.app.button(key='top_cart').click().run()
        elif page=='profile':self.app.button(key='top_profile').click().run()
        else:self.app.button(key='nav_'+page).click().run()
        self.assertFalse(self.app.exception)
    def test_borrow_approve_and_confirm_return_through_ui(self):
        self.fixture.create_equipment(2)
        self.login('student')
        self.navigate('borrow')
        self.app.text_area[0].set_value('กิจกรรมเรียน')
        self.press('ตรวจสรุปคำขอยืม')
        self.press('ยืนยันส่งคำขอยืม')
        tx=transactions(self.fixture.student['id'],self.path)[0]['id']
        self.press('ออกจากระบบ')
        self.login()
        self.navigate('approvals')
        self.assertTrue(next(b for b in self.app.button if b.label=='อนุมัติ').disabled)
        next(c for c in self.app.checkbox if c.label=='ตรวจข้อมูลและลายเซ็นผู้ยืมใน PDF แล้ว').set_value(True).run()
        self.press('อนุมัติ')
        handoff_borrow(self.fixture.admin['id'],tx,'ปกติ','assets/equipment/camera.png',self.path)
        request_return(self.fixture.student['id'],tx,'ปกติ','assets/equipment/camera.png','',self.path)
        self.navigate('return')
        next(c for c in self.app.checkbox if c.label=='ตรวจรับอุปกรณ์และตรวจสภาพจริงแล้ว').check().run()
        self.press('ยืนยันการคืน')
        self.assertEqual(transactions(self.fixture.student['id'],self.path)[0]['borrow_status'],'คืนแล้ว')
        self.navigate('history')
        self.assertTrue(self.app.dataframe)
    def test_completed_pages_render_without_errors(self):
        self.fixture.create_equipment()
        self.login()
        for page in allowed_pages('admin'):
            with self.subTest(page=page):
                self.navigate(page)
    def test_seeded_pages_for_all_roles_have_no_exceptions(self):
        seed_sample_data(self.path)
        for name,role in (('admin','admin'),('teacher','teacher'),('student','student')):
            self.login(name)
            for page in allowed_pages(role):
                with self.subTest(role=role,page=page):
                    self.navigate(page)
                    self.assertFalse(self.app.error)
            self.press('ออกจากระบบ')
    def test_qr_query_opens_equipment_after_login(self):
        self.fixture.create_equipment()
        self.app.query_params['equipment']='TEST001'
        self.login('student')
        self.assertEqual(self.app.title[0].value,'อุปกรณ์')
        self.assertEqual(self.app.text_input[0].value,'TEST001')
    def test_quick_menu_tracks_sidebar_and_respects_role(self):
        self.login('student')
        self.navigate('borrow')
        self.assertFalse(any(x.label=='ไปยังหน้า' for x in self.app.selectbox))
        keys=[b.key for b in self.app.button]
        self.assertEqual(keys.count('top_profile'),1)
        self.assertNotIn('top_my_loans',keys)
        self.assertNotIn('nav_borrow',keys)
        self.assertNotIn('nav_profile',keys)
        self.assertNotIn('nav_settings',keys)
        self.app.button(key='nav_calendar').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state['navigation_page'],'calendar')
        self.navigate('dashboard')
        self.assertEqual(self.app.session_state['navigation_page'],'dashboard')
    def input(self,label,value):
        next(x for x in self.app.text_input if x.label==label).set_value(value)
    def test_equipment_add_edit_and_confirm_deactivate_ui(self):
        self.login()
        self.navigate('equipment')
        for label,value in {'รหัสอุปกรณ์':'UI001','ชื่ออุปกรณ์':'กล้อง UI','สถานที่จัดเก็บ':'ห้องโสต'}.items():
            self.input(label,value)
        next(x for x in self.app.selectbox if x.label=='หมวดหมู่').select('กล้อง')
        self.press('บันทึกอุปกรณ์')
        eq=catalog(database_path=self.path)[0]['id']
        next(x for x in self.app.selectbox if x.label=='รายการที่ต้องการจัดการ').set_value(eq).run()
        self.input('ชื่ออุปกรณ์','กล้องชื่อใหม่')
        self.press('บันทึกอุปกรณ์')
        self.assertEqual(catalog(database_path=self.path)[0]['equipment_name'],'กล้องชื่อใหม่')
        next(c for c in self.app.checkbox if c.label=='ยืนยันปิดใช้งานอุปกรณ์รายการนี้').check().run()
        self.press('ปิดใช้งานอุปกรณ์')
        self.assertEqual(catalog(database_path=self.path),[])
    def test_user_create_and_reset_password_ui(self):
        self.login()
        self.navigate('users')
        for label,value in {'รหัสนักเรียน / บุคลากร':'683040111-0','Username':'uiuser','ชื่อ-นามสกุล':'คนทดสอบ','รหัสผ่านเริ่มต้น':'ui-password-123'}.items():
            self.input(label,value)
        self.press('บันทึกผู้ใช้งาน')
        uid=next(r['id'] for r in user_rows(self.fixture.admin['id'],self.path) if r['username']=='uiuser')
        next(x for x in self.app.selectbox if x.label=='เพิ่ม / แก้ไขบัญชี').set_value(uid).run()
        self.input('รหัสผ่านใหม่','ui-changed-123')
        next(c for c in self.app.checkbox if c.label=='ยืนยันรีเซ็ตรหัสผ่านของบัญชีนี้').check()
        self.press('รีเซ็ตรหัสผ่าน')
        self.assertIsNone(authenticate_user('uiuser','ui-password-123',self.path))
        self.assertIsNotNone(authenticate_user('uiuser','ui-changed-123',self.path))
    def test_maintenance_create_and_complete_ui(self):
        self.fixture.create_equipment(2)
        self.login()
        self.navigate('maintenance')
        self.input('อาการที่พบ','เลนส์เสีย')
        self.press('แจ้งซ่อม')
        self.assertEqual(len(maintenance_rows(self.fixture.admin['id'],self.path)),1)
        next(x for x in self.app.selectbox if x.label=='สถานะงานซ่อม').set_value('ซ่อมเสร็จ')
        self.press('อัปเดตงานซ่อม')
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'],2)

    def fill_registration(self,confirmation='register-password-123'):
        self.app.segmented_control[0].set_value('สมัครสมาชิก').run()
        self.assertFalse(next(b for b in self.app.button if b.label=='สมัครสมาชิก').disabled)
        self.assertFalse(any('OTP' in b.label for b in self.app.button))
        self.app.text_input(key='register_email').set_value('registered@example.com')
        for key,value in {'student_code':'683040112-0','classroom':'ม.4/1','full_name':'นักเรียน UI',
                          'username':'registeredui','password':'register-password-123','password_confirm':confirmation}.items():
            self.app.text_input(key='register_'+key).set_value(value)

    def test_signup_then_login_and_logout_through_ui(self):
        self.fill_registration()
        self.press('สมัครสมาชิก')
        self.assertEqual(self.app.segmented_control[0].value,'เข้าสู่ระบบ')
        self.assertTrue(self.app.success)
        self.assertEqual(self.app.text_input(key='login_username').value,'registeredui')
        self.assertNotIn('user',self.app.session_state)
        self.assertEqual(self.app.session_state['register_password'],'')
        self.app.text_input(key='login_password').set_value('register-password-123')
        self.press('เข้าสู่ระบบ')
        self.assertEqual(self.app.session_state['user']['role'],'student')
        self.assertFalse(any(button.key=='nav_users' for button in self.app.sidebar.button))
        self.press('ออกจากระบบ')
        self.assertNotIn('user',self.app.session_state)

    def test_signup_failure_stays_on_form_and_clears_passwords(self):
        self.fill_registration('mismatch')
        self.press('สมัครสมาชิก')
        self.assertEqual(self.app.segmented_control[0].value,'สมัครสมาชิก')
        self.assertIn('ไม่ตรงกัน',self.app.error[0].value)
        self.assertEqual(self.app.text_input(key='register_password').value,'')
        self.assertEqual(self.app.text_input(key='register_password_confirm').value,'')
        self.assertIsNone(authenticate_user('registeredui','register-password-123',self.path))

    def test_equipment_card_opens_borrow_form_with_selected_item(self):
        self.fixture.create_equipment(2)
        eq=catalog(database_path=self.path)[0]['id']
        self.login('student')
        self.navigate('equipment')
        self.app.button(key=f'equipment_borrow_{eq}').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.title[0].value,'ยืมอุปกรณ์')
        self.assertEqual(self.app.selectbox(key='borrow_equipment_id').value,eq)

    def test_explore_gallery_defaults_filters_and_sorting(self):
        camera=self.fixture.create_equipment(2)
        mic=save_equipment(self.fixture.admin['id'],{'equipment_code':'GALLERY002','equipment_name':'ไมค์กิจกรรม',
                           'category':'ไมโครโฟน','storage_location':'ห้องโสต','total_amount':3},database_path=self.path)
        self.login('student')
        self.assertEqual(self.app.pills(key='equipment_category').value,'ทุกหมวดหมู่')
        visible=lambda:[b.key for b in self.app.button if b.key and b.key.startswith('equipment_borrow_')]
        self.assertCountEqual(visible(),[f'equipment_borrow_{camera}',f'equipment_borrow_{mic}'])
        self.app.pills(key='equipment_category').set_value('ไมโครโฟน').run()
        self.assertEqual(visible(),[f'equipment_borrow_{mic}'])
        self.app.pills(key='equipment_category').set_value('ทุกหมวดหมู่').run()
        self.app.selectbox(key='equipment_order').set_value('พร้อมใช้มากที่สุด').run()
        self.assertEqual(visible(),[f'equipment_borrow_{mic}',f'equipment_borrow_{camera}'])
        self.app.text_input(key='equipment_search').set_value('ไม่พบอุปกรณ์นี้').run()
        self.assertEqual(visible(),[])
        self.app.text_input(key='equipment_search').set_value('กล้อง').run()
        self.app.button(key='nav_equipment').click().run()
        self.assertEqual(self.app.session_state['navigation_page'],'equipment')
        self.assertEqual(visible(),[f'equipment_borrow_{camera}'])
        self.assertFalse(self.app.exception)

    def test_multi_item_cart_document_and_bulk_approval_ui(self):
        first=self.fixture.create_equipment(2)
        second=save_equipment(self.fixture.admin['id'],{'equipment_code':'UI002','equipment_name':'ไมค์ UI',
                               'category':'ไมโครโฟน','storage_location':'ห้องโสต','total_amount':2},database_path=self.path)
        self.login('student')
        self.navigate('borrow')
        self.press('เพิ่มลงตะกร้า')
        self.app.selectbox(key='borrow_equipment_id').set_value(second).run()
        self.press('เพิ่มลงตะกร้า')
        self.app.button(key=f'cart_plus_{first}').click().run()
        self.app.text_area(key='cart_purpose').set_value('หลายอุปกรณ์')
        self.press('ตรวจสรุปคำขอยืม')
        self.assertEqual(len(self.app.session_state['borrow_draft']['items']),2)
        self.press('ยืนยันส่งคำขอยืม')
        rows=transactions(self.fixture.student['id'],self.path)
        self.assertEqual(len(rows),2)
        self.assertEqual(len({r['request_group'] for r in rows}),1)
        self.assertEqual(self.app.session_state['borrow_cart'],{})
        self.assertEqual(self.app.session_state['navigation_page'],'profile')
        self.assertEqual(self.app.session_state['profile_section'],'ประวัติการยืม')
        self.assertEqual(self.app.selectbox(key='history_detail').value,min(r['id'] for r in rows))
        self.assertTrue(any(h.value=='สถานะคำขอยืม' for h in self.app.title))
        self.assertTrue(all(r['document_path'].endswith('.pdf') for r in rows))
        self.assertEqual(len({r['document_path'] for r in rows}),1)
        self.press('ออกจากระบบ')
        self.login()
        self.navigate('approvals')
        self.assertTrue(next(b for b in self.app.button if b.label=='อนุมัติทั้งใบคำขอ').disabled)
        next(c for c in self.app.checkbox if c.label=='ตรวจข้อมูลและลายเซ็นผู้ยืมใน PDF แล้ว').check().run()
        self.press('อนุมัติทั้งใบคำขอ')
        self.assertTrue(all(r['borrow_status']=='อนุมัติแล้ว' for r in transactions(self.fixture.student['id'],self.path)))
        self.navigate('profile')
        self.app.session_state['profile_section']='ประวัติการยืม';self.app.run()
        self.assertTrue(self.app.dataframe)
        self.assertFalse(self.app.error)

    def test_cart_changes_remove_stale_confirmation(self):
        eq=self.fixture.create_equipment(3)
        self.login('student')
        self.navigate('borrow')
        self.press('เพิ่มลงตะกร้า')
        self.app.text_area(key='cart_purpose').set_value('ทดสอบ')
        self.press('ตรวจสรุปคำขอยืม')
        self.app.button(key=f'cart_plus_{eq}').click().run()
        self.assertNotIn('borrow_draft',self.app.session_state)
        self.press('ตรวจสรุปคำขอยืม')
        self.app.button(key=f'cart_remove_{eq}').click().run()
        self.assertNotIn('borrow_draft',self.app.session_state)
        self.assertEqual(self.app.session_state['borrow_cart'],{})
        self.press('เพิ่มลงตะกร้า')
        self.assertEqual(self.app.session_state['borrow_cart'][eq],1)

    def test_fine_settings_and_role_pages_ui(self):
        self.login()
        self.navigate('settings')
        next(n for n in self.app.number_input if n.label=='ค่าปรับต่อชิ้นต่อวัน (บาท)').set_value(12.5)
        self.press('บันทึกอัตราค่าปรับ')
        from settings import get_setting
        self.assertEqual(get_setting('fine_rate_cents','',self.path),'1250')
        self.navigate('fines')
        self.assertFalse(self.app.error)

    def test_calendar_month_navigation_and_today(self):
        from common import today
        from datetime import date
        self.login('student')
        self.navigate('calendar')
        first=today().replace(day=1)
        index=first.year*12+first.month
        year,zero_month=divmod(index,12)
        self.app.button(key='calendar_next').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state['calendar_month'],date(year,zero_month+1,1))
        self.app.button(key='calendar_prev').click().run()
        self.assertEqual(self.app.session_state['calendar_month'],first)
        self.app.button(key='calendar_today').click().run()
        self.assertEqual(self.app.session_state['calendar_day'],today())

    def test_profile_save_reads_new_values_once_and_keeps_photo(self):
        from profile_page import profile_data
        self.login('student')
        self.navigate('profile')
        before=profile_data(self.fixture.student['id'],self.path)
        self.app.text_input(key='profile_full_name').set_value('ชื่อใหม่ทดสอบ')
        self.app.text_input(key='profile_classroom').set_value('ม.5/2')
        self.press('บันทึกโปรไฟล์')
        after=profile_data(self.fixture.student['id'],self.path)
        self.assertEqual(after['full_name'],'ชื่อใหม่ทดสอบ')
        self.assertEqual(after['classroom'],'ม.5/2')
        self.assertEqual(after['profile_image'],before['profile_image'])
        self.assertEqual([t.value for t in self.app.title],['โปรไฟล์ของฉัน'])
        self.assertEqual(self.app.session_state['user']['full_name'],'ชื่อใหม่ทดสอบ')
        self.assertEqual(len(self.app.toast),1)
        self.assertIn('บันทึกโปรไฟล์แล้ว',self.app.toast[0].value)
        self.assertFalse(self.app.success)
        self.app.run()
        self.assertEqual([t.value for t in self.app.title],['โปรไฟล์ของฉัน'])
        self.assertFalse(self.app.success)

    def test_profile_invalid_save_keeps_existing_name_and_single_page(self):
        from profile_page import profile_data
        self.login('student')
        self.navigate('profile')
        before=profile_data(self.fixture.student['id'],self.path)
        self.app.text_input(key='profile_full_name').set_value('   ')
        self.press('บันทึกโปรไฟล์')
        self.assertTrue(self.app.error)
        self.assertEqual(profile_data(self.fixture.student['id'],self.path)['full_name'],before['full_name'])
        self.assertEqual([t.value for t in self.app.title],['โปรไฟล์ของฉัน'])

    def test_task_board_opens_exact_record_and_stage_for_role(self):
        seed_sample_data(self.path)
        self.login()
        all_rows=transactions(self.fixture.admin['id'],self.path)
        pickup=next(r for r in all_rows if r['borrow_status']=='อนุมัติแล้ว')
        self.app.button(key=f'task_pickup_{pickup["id"]}').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state['navigation_page'],'approvals')
        self.assertEqual(self.app.selectbox(key='approval_handoff').value,pickup['id'])
        self.assertEqual(self.app.session_state['approval_stage'],'รอรับอุปกรณ์')
        self.navigate('dashboard')
        returning=next(r for r in all_rows if r['borrow_status'] in {'กำลังยืม','เกินกำหนด'})
        if not any(b.key==f'task_return_{returning["id"]}' for b in self.app.button):
            returning=next(r for r in all_rows if any(b.key==f'task_return_{r["id"]}' for b in self.app.button))
        self.app.button(key=f'task_return_{returning["id"]}').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state['navigation_page'],'profile')
        self.assertEqual(self.app.selectbox(key='history_detail').value,returning['id'])
        self.press('ออกจากระบบ')
        self.login('student')
        self.navigate('dashboard')
        own=transactions(self.fixture.student['id'],self.path)
        request=next(r for r in own if r['borrow_status']=='รออนุมัติ')
        self.app.button(key=f'task_pickup_{request["id"]}').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state['navigation_page'],'profile')
        self.assertEqual(self.app.selectbox(key='history_detail').value,request['id'])
        self.assertFalse(any(b.key=='nav_approvals' for b in self.app.sidebar.button))
        self.assertFalse(self.app.exception)

    def test_gallery_list_preserves_filters_and_opens_correct_borrow_form(self):
        eq=self.fixture.create_equipment(2)
        self.login('student');self.navigate('equipment')
        self.app.text_input(key='equipment_search').set_value('TEST001').run()
        self.app.segmented_control(key='equipment_view').set_value('รายการ').run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.text_input(key='equipment_search').value,'TEST001')
        self.app.button(key=f'equipment_borrow_{eq}').click().run()
        self.assertEqual(self.app.session_state['navigation_page'],'borrow')
        self.assertEqual(self.app.selectbox(key='borrow_equipment_id').value,eq)
        self.assertEqual(transactions(self.fixture.student['id'],self.path),[])

    def test_command_palette_scopes_menus_and_routes_search_result(self):
        eq=self.fixture.create_equipment(2)
        self.login('student');self.press('ค้นหาเร็ว')
        keys=[b.key for b in self.app.button if b.key and b.key.startswith('command_page_')]
        self.assertIn('command_page_calendar',keys)
        self.assertNotIn('command_page_settings',keys);self.assertNotIn('command_page_approvals',keys)
        self.app.text_input(key='command_query').set_value('TEST001').run()
        self.app.button(key=f'command_equipment_{eq}').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state['navigation_page'],'equipment')
        self.assertEqual(self.app.text_input(key='equipment_search').value,'TEST001')
        self.assertEqual(self.app.pills(key='equipment_category').value,'ทุกหมวดหมู่')

    def test_detail_dialog_routes_to_selected_item_without_submitting(self):
        eq=self.fixture.create_equipment(2)
        self.login('student');self.navigate('equipment')
        self.app.button(key=f'equipment_details_{eq}').click().run()
        self.press('เลือกอุปกรณ์นี้')
        self.assertEqual(self.app.session_state['navigation_page'],'borrow')
        self.assertEqual(self.app.selectbox(key='borrow_equipment_id').value,eq)
        self.assertEqual(transactions(self.fixture.student['id'],self.path),[])
