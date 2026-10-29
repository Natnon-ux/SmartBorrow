import unittest
from datetime import timedelta
from unittest.mock import patch
import test_features
from common import DomainError,today
from user_management import save_user
from borrow_requests import request_cart
from services import decide_borrow,handoff_borrow,request_return,confirm_return,catalog,transactions,maintenance_rows
from fines import save_fine_rate
from test_pdf_fixtures import install_pdf_fixture

class ExecutiveReturnEdges(unittest.TestCase):
    def setUp(self):
        self.f=test_features.FeatureTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.eq=self.f.create_equipment(2)
        self.pdf=install_pdf_fixture(self,self.f.path)
        self.executive=save_user(self.f.admin['id'],dict(student_code='EXEC-TEST',username='director',full_name='ผอ ทดสอบ',role='staff',executive_title='director'),password='test12345',database_path=self.f.path)
        save_fine_rate(self.f.admin['id'],10,self.f.path)
    def borrow(self,amount=1):
        result=request_cart(self.f.student['id'],[dict(equipment_id=self.eq,amount=amount)],today(),today()+timedelta(days=3),'ทดสอบ',document_path=self.pdf,database_path=self.f.path)
        tx=result['transaction_ids'][0]
        decide_borrow(self.f.admin['id'],tx,True,self.f.path)
        decide_borrow(self.executive,tx,True,self.f.path)
        handoff_borrow(self.f.admin['id'],tx,'ปกติ','assets/equipment/camera.png',self.f.path)
        return tx
    def test_late_return_uses_handoff_rate_and_rejects_repeat(self):
        tx=self.borrow(2)
        save_fine_rate(self.f.admin['id'],50,self.f.path)
        day=today()+timedelta(days=5)
        with patch('services.today',return_value=day),patch('fines.today',return_value=day):
            request_return(self.f.student['id'],tx,'ปกติ','assets/equipment/camera.png','คืนช้า',self.f.path)
            with self.assertRaises(DomainError):request_return(self.f.student['id'],tx,'ปกติ','assets/equipment/camera.png','',self.f.path)
            with self.assertRaises(DomainError):confirm_return(self.f.student['id'],tx,self.f.path)
            confirm_return(self.f.admin['id'],tx,self.f.path)
        row=next(r for r in transactions(self.f.student['id'],self.f.path) if r['id']==tx)
        self.assertEqual((row['fine_days'],row['fine_amount_cents'],row['fine_status']),(2,4000,'ค้างชำระ'))
        self.assertEqual(catalog(database_path=self.f.path)[0]['available_amount'],2)
        with self.assertRaises(DomainError):confirm_return(self.f.admin['id'],tx,self.f.path)
    def test_damaged_and_lost_items_do_not_return_to_available_stock(self):
        for condition in ['ชำรุด','สูญหาย']:
            tx=self.borrow()
            request_return(self.f.student['id'],tx,condition,'assets/equipment/camera.png','รายละเอียดความเสียหาย',self.f.path)
            confirm_return(self.f.admin['id'],tx,self.f.path)
        row=catalog(database_path=self.f.path)[0]
        self.assertEqual((row['available_amount'],row['unavailable_amount']),(0,2))
        self.assertEqual(len(maintenance_rows(self.f.admin['id'],self.f.path)),2)
    def test_missing_document_and_borrower_approval_are_blocked(self):
        with self.assertRaises(DomainError):request_cart(self.f.student['id'],[dict(equipment_id=self.eq,amount=1)],today(),today()+timedelta(days=3),'ทดสอบ',database_path=self.f.path)
        self.assertEqual(transactions(self.f.student['id'],self.f.path),[])
        tx=self.borrow()
        with self.assertRaises(DomainError):decide_borrow(self.f.student['id'],tx,True,self.f.path)
