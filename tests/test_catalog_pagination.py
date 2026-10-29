"""ตรวจปุ่มแบ่งหน้า ขอบเขตหน้า และการเปลี่ยนตัวกรอง."""
import unittest
import test_features
from database import database_connection
from streamlit.testing.v1 import AppTest


class CatalogPaginationTests(unittest.TestCase):
    def test_next_previous_and_filter_reset(self):
        f=test_features.FeatureTests();f.setUp();self.addCleanup(f.tearDown)
        with database_connection(f.path) as con:
            for i in range(18):
                con.execute("INSERT INTO equipment(equipment_code,equipment_name,category,total_amount,available_amount,storage_location) VALUES(?,?,?,1,1,'ห้องทดสอบ')",
                            (f'PG{i:02d}',f'Pagination {i:02d}','กล้อง' if i<17 else 'เลนส์'))
        def screen(user,path):
            from equipment import render_catalog
            render_catalog(user,path)
        app=AppTest.from_function(screen,args=(f.student,f.path),default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(app.button(key='catalog_previous').disabled)
        first={b.key for b in app.button if str(b.key).startswith('equipment_borrow_')}
        self.assertEqual(len(first),8)
        app.button(key='catalog_next').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['equipment_page'],2)
        second={b.key for b in app.button if str(b.key).startswith('equipment_borrow_')}
        self.assertFalse(first & second)
        app.button(key='catalog_next').click().run()
        self.assertEqual(app.session_state['equipment_page'],3)
        self.assertTrue(app.button(key='catalog_next').disabled)
        self.assertEqual(sum(str(b.key).startswith('equipment_borrow_') for b in app.button),2)
        app.button(key='catalog_previous').click().run()
        self.assertEqual(app.session_state['equipment_page'],2)
        app.text_input(key='equipment_search').set_value('Pagination 17').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['equipment_page'],1)
        self.assertFalse(any(b.key=='catalog_next' for b in app.button))
