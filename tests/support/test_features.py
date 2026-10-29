"""ทดสอบฟีเจอร์เพิ่มทีละ STEP ในฐานข้อมูลชั่วคราว."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from auth import ensure_demo_users, authenticate_user
from database import PROJECT_DIR, initialize_database, database_connection
from analytics import dashboard_data
from services import catalog, save_equipment, deactivate_equipment
from common import DomainError
from common import today
from services import request_borrow, transactions
from services import decide_borrow
from services import handoff_borrow
from services import request_return, confirm_return
from services import reserve_equipment
from qr_codes import qr_png, label_pdf, equipment_url
from PIL import Image
from io import BytesIO
from history import filter_history, csv_bytes
from services import update_overdue, overdue_rows
from datetime import timedelta
from notifications import sync_notifications, notification_rows, mark_read
from services import create_maintenance,update_maintenance,maintenance_rows
from analytics import report_data
from analytics import insight_data
from user_management import save_user,reset_password,user_rows
from profile_page import profile_data,update_profile
from settings import stock_audit,backup_database,save_settings,get_setting
from seed_data import seed_sample_data
from database import get_integrity_report

class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="smartborrow_test_features_", dir=PROJECT_DIR / "data")
        self.path = Path(self.temp.name) / "features.db"
        initialize_database(self.path)
        ensure_demo_users(self.path)
        self.admin = authenticate_user("admin", "admin123", self.path)
        self.student = authenticate_user("student", "student123", self.path)
    def tearDown(self):
        assert Path(self.temp.name).resolve().is_relative_to((PROJECT_DIR / "data").resolve())
        self.temp.cleanup()
    def test_empty_dashboard_and_real_stock(self):
        self.assertEqual(dashboard_data(self.admin, self.path)["stock"]["total"], 0)
        with database_connection(self.path) as con:
            con.execute("INSERT INTO equipment(equipment_code,equipment_name,category,total_amount,available_amount,storage_location) "
                        "VALUES('TEST001','กล้องทดสอบ','กล้อง',5,5,'ห้องทดสอบ')")
        self.assertEqual(dashboard_data(self.admin, self.path)["stock"]["available"], 5)
    def test_catalog_search_and_status(self):
        with database_connection(self.path) as con:
            con.execute("INSERT INTO equipment(equipment_code,equipment_name,category,total_amount,available_amount,storage_location) "
                        "VALUES('CAM001','กล้อง Sony','กล้อง',0,0,'ห้องทดสอบ')")
        for phrase in ("sony", "CAM", "กล้อง"):
            self.assertEqual(len(catalog(phrase, "ทั้งหมด", self.path)), 1)
        self.assertEqual(catalog("", "ชำรุด", self.path), [])
        self.assertEqual(catalog("ไม่มี", "ทั้งหมด", self.path), [])
    def create_equipment(self, total=3):
        return save_equipment(self.admin["id"], {"equipment_code":"TEST001", "equipment_name":"กล้องทดสอบ",
                    "category":"กล้อง", "storage_location":"ห้องโสต", "total_amount":total}, database_path=self.path)
    def test_equipment_edit_permissions_and_deactivation_confirmation(self):
        eq_id = self.create_equipment(0)
        with self.assertRaises(DomainError):
            save_equipment(self.student["id"], {}, database_path=self.path)
        with self.assertRaises(DomainError):
            deactivate_equipment(self.admin["id"], eq_id, False, self.path)
        deactivate_equipment(self.admin["id"], eq_id, True, self.path)
        self.assertEqual(catalog(database_path=self.path), [])
        self.assertEqual(len(catalog(database_path=self.path, include_inactive=True)), 1)
    def test_borrow_validations_and_pending_stock(self):
        equipment = self.create_equipment(2)
        for amount in (0, 3):
            with self.assertRaises(DomainError):
                request_borrow(self.student['id'], equipment, amount, today(), today(), 'เรียน', self.path)
        request_borrow(self.student['id'], equipment, 1, today(), today(), 'เรียน', self.path)
        self.assertEqual(transactions(self.student['id'], self.path)[0]['borrow_status'], 'รออนุมัติ')
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'], 2)
    def pending(self, amount=1):
        return request_borrow(self.student['id'], self.create_equipment(2), amount, today(), today(), 'เรียน', self.path)
    def test_approval_is_atomic_and_role_protected(self):
        tx = self.pending()
        with self.assertRaises(DomainError):
            decide_borrow(self.student['id'], tx, True, self.path)
        decide_borrow(self.admin['id'], tx, True, self.path)
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'], 1)
        with self.assertRaises(DomainError):
            decide_borrow(self.admin['id'], tx, True, self.path)
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'], 1)
    def test_handoff_requires_photo_and_approval(self):
        tx = self.pending()
        with self.assertRaises(DomainError):
            handoff_borrow(self.admin['id'], tx, 'ปกติ', 'assets/equipment/camera.png', self.path)
        decide_borrow(self.admin['id'], tx, True, self.path)
        with self.assertRaises(DomainError):
            handoff_borrow(self.admin['id'], tx, 'ปกติ', None, self.path)
        handoff_borrow(self.admin['id'], tx, 'ปกติ', 'assets/equipment/camera.png', self.path)
        self.assertEqual(transactions(self.student['id'], self.path)[0]['borrow_status'], 'กำลังยืม')
    def live_loan(self):
        tx = self.pending()
        decide_borrow(self.admin['id'], tx, True, self.path)
        handoff_borrow(self.admin['id'], tx, 'ปกติ', 'assets/equipment/camera.png', self.path)
        return tx
    def test_normal_return_restores_once(self):
        tx = self.live_loan()
        request_return(self.student['id'], tx, 'ปกติ', 'assets/equipment/camera.png', '', self.path)
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'], 1)
        confirm_return(self.admin['id'], tx, self.path)
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'], 2)
        with self.assertRaises(DomainError):
            confirm_return(self.admin['id'], tx, self.path)
    def test_damaged_return_is_blocked_and_maintenance_created(self):
        tx = self.live_loan()
        request_return(self.student['id'], tx, 'ชำรุด', 'assets/equipment/camera.png', 'เลนส์แตก', self.path)
        confirm_return(self.admin['id'], tx, self.path)
        row = catalog(database_path=self.path)[0]
        self.assertEqual((row['available_amount'], row['unavailable_amount']), (1,1))
        with database_connection(self.path) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM maintenance').fetchone()[0],1)
    def test_reservation_overlap_and_shared_stock(self):
        eq = self.create_equipment(1)
        reserve_equipment(self.student['id'], eq, today(), today(), 'เรียน', self.path)
        with self.assertRaisesRegex(DomainError, 'อุปกรณ์นี้ถูกจอง'):
            reserve_equipment(self.admin['id'], eq, today(), today(), 'ประชุม', self.path)
        with self.assertRaises(DomainError):
            request_borrow(self.admin['id'], eq, 1, today(), today(), 'ประชุม', self.path)
        tx = request_borrow(self.student['id'], eq, 1, today(), today(), 'เรียน', self.path)
        decide_borrow(self.admin['id'], tx, True, self.path)
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'], 0)
    def test_qr_png_pdf_and_encoded_identifier(self):
        self.assertIn('equipment=CAM%2F001', equipment_url('CAM/001'))
        with Image.open(BytesIO(qr_png('CAM001'))) as picture:
            self.assertEqual(picture.format,'PNG')
            self.assertGreater(picture.width,200)
        self.assertTrue(label_pdf('CAM001').startswith(b'%PDF'))
    def test_history_search_filters_and_csv(self):
        self.pending()
        rows=transactions(self.student['id'],self.path)
        self.assertEqual(len(filter_history(rows,search='กล้อง',status='รออนุมัติ')),1)
        self.assertEqual(filter_history(rows,status='คืนแล้ว'),[])
        self.assertTrue(csv_bytes([{'ชื่อ':'=CMD()'}]).decode('utf-8-sig').splitlines()[1].startswith("'="))
    def test_overdue_update_is_idempotent_and_preserves_return_review(self):
        tx=self.live_loan()
        past=(today()-timedelta(days=1)).isoformat()
        with database_connection(self.path) as con:
            con.execute('UPDATE borrow_transactions SET borrow_date=?,due_date=? WHERE id=?',(past,past,tx))
        self.assertEqual(update_overdue(self.path),1)
        self.assertEqual(update_overdue(self.path),0)
        self.assertEqual(len(overdue_rows(self.student['id'],self.path)),1)
        request_return(self.student['id'],tx,'ปกติ','assets/equipment/camera.png','',self.path)
        update_overdue(self.path)
        self.assertEqual(transactions(self.student['id'],self.path)[0]['borrow_status'],'รอตรวจสอบการคืน')
    def test_notifications_are_private_and_deduplicated(self):
        tx=self.pending()
        decide_borrow(self.admin['id'],tx,True,self.path)
        sync_notifications(self.path)
        sync_notifications(self.path)
        rows=notification_rows(self.student['id'],self.path)
        self.assertEqual(len(rows),1)
        admin_rows=notification_rows(self.admin['id'],self.path)
        self.assertEqual(len(admin_rows),1)
        self.assertEqual(admin_rows[0]['reference_id'],tx)
        self.assertNotEqual(admin_rows[0]['id'],rows[0]['id'])
        with self.assertRaises(DomainError):
            mark_read(self.admin['id'],rows[0]['id'],self.path)
        mark_read(self.student['id'],rows[0]['id'],self.path)
        self.assertIsNotNone(notification_rows(self.student['id'],self.path)[0]['read_at'])
    def test_maintenance_restores_exact_amount_once(self):
        eq=self.create_equipment(3)
        job=create_maintenance(self.admin['id'],eq,2,'เสีย',sent_date=today(),database_path=self.path)
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'],1)
        update_maintenance(self.admin['id'],job,'ซ่อมเสร็จ','เปลี่ยนอะไหล่',500,today(),self.path)
        self.assertEqual(catalog(database_path=self.path)[0]['available_amount'],3)
        with self.assertRaises(DomainError):
            update_maintenance(self.admin['id'],job,'ซ่อมเสร็จ','',500,today(),self.path)
        self.assertEqual(maintenance_rows(self.admin['id'],self.path)[0]['repair_cost'],500)
    def test_reports_use_real_data_and_permissions(self):
        tx=self.pending()
        decide_borrow(self.admin['id'],tx,True,self.path)
        data=report_data(self.admin['id'],today(),today(),self.path)
        self.assertEqual(len(data['usage']),1)
        self.assertEqual(data['popular'][0]['จำนวนชิ้น'],1)
        with self.assertRaises(DomainError):
            report_data(self.student['id'],today(),today(),self.path)
    def test_insights_do_not_invent_percentages(self):
        self.assertIsNone(insight_data(self.admin['id'],self.path)['percent'])
        tx=self.pending()
        decide_borrow(self.admin['id'],tx,True,self.path)
        data=insight_data(self.admin['id'],self.path)
        self.assertEqual(data['current'],1)
        self.assertEqual(data['categories'][0]['หมวดหมู่'],'กล้อง')
    def test_user_management_hashes_password_and_protects_admin(self):
        values=dict(student_code='683040501-0',username='newstudent',full_name='นักเรียนใหม่',role='student')
        uid=save_user(self.admin['id'],values,password='newpass123',database_path=self.path)
        self.assertIsNotNone(authenticate_user('newstudent','newpass123',self.path))
        reset_password(self.admin['id'],uid,'changed123',True,self.path)
        self.assertIsNone(authenticate_user('newstudent','newpass123',self.path))
        self.assertIsNotNone(authenticate_user('newstudent','changed123',self.path))
        values=dict(self.admin,role='student',status='active')
        with self.assertRaises(DomainError):
            save_user(self.admin['id'],values,self.admin['id'],confirmed=True,database_path=self.path)
        with self.assertRaises(DomainError):
            user_rows(self.student['id'],self.path)
    def test_profile_statistics_and_edit_are_own_only(self):
        tx=self.live_loan()
        request_return(self.student['id'],tx,'ปกติ','assets/equipment/camera.png','',self.path)
        confirm_return(self.admin['id'],tx,self.path)
        data=profile_data(self.student['id'],self.path)
        self.assertEqual(data['stats'],dict(borrowed=1,on_time=1,late=0))
        self.assertEqual(profile_data(self.admin['id'],self.path)['stats']['borrowed'],0)
        update_profile(self.student['id'],'ชื่อใหม่','ม.4/2','01234',database_path=self.path)
        self.assertEqual(profile_data(self.student['id'],self.path)['role'],'student')
    def test_settings_backup_and_stock_integrity(self):
        self.live_loan()
        self.assertEqual(stock_audit(self.path),[])
        save_settings(self.admin['id'],'โรงเรียนทดสอบ','https://school.example',self.path)
        self.assertEqual(get_setting('base_url','',self.path),'https://school.example')
        self.assertTrue(backup_database(self.admin['id'],self.path).startswith(b'SQLite format 3'))
        with self.assertRaises(DomainError):
            backup_database(self.student['id'],self.path)
    def test_seed_is_complete_idempotent_and_integral(self):
        self.assertTrue(seed_sample_data(self.path))
        self.assertFalse(seed_sample_data(self.path))
        with database_connection(self.path) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM users').fetchone()[0],10)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM equipment').fetchone()[0],20)
        self.assertEqual(stock_audit(self.path),[])
        self.assertTrue(get_integrity_report(self.path)['ok'])
