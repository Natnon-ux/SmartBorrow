"""STEP 24: ข้อมูลจำลองสำหรับ prototype เพิ่มครั้งเดียวบนชุดอุปกรณ์ที่ว่าง."""
from datetime import timedelta
from auth import ensure_demo_users,hash_password
from common import today,DomainError,USAGE_STATUSES
from database import DATABASE_PATH,initialize_database,database_connection
from services import refresh_stock,update_overdue
from notifications import sync_notifications
from equipment_content import demo_description

SAMPLE_EQUIPMENT=[
 ('CAM001','Sony A7 IV','กล้อง','camera',3),('CAM002','Sony A7 III','กล้อง','camera',2),
 ('CAM003','Canon EOS R','กล้อง','camera',2),('PJ001','Epson Projector','โปรเจกเตอร์','projector',2),
 ('PJ002','BenQ Projector','โปรเจกเตอร์','projector',2),('MIC001','Wireless Microphone','ไมโครโฟน','microphone',4),
 ('MIC002','USB Microphone','ไมโครโฟน','microphone',3),('SPK001','Speaker','ลำโพง','speaker',4),
 ('NB001','Notebook Lenovo','คอมพิวเตอร์','notebook',5),('NB002','Notebook Acer','คอมพิวเตอร์','notebook',4),
 ('TAB001','iPad','แท็บเล็ต','placeholder',3),('TRI001','Tripod','อุปกรณ์เสริม','placeholder',5),
 ('CAP001','Capture Card','อุปกรณ์เสริม','placeholder',3),('HDMI001','HDMI Cable','สายสัญญาณ','placeholder',8),
 ('EXT001','Extension Cord','อุปกรณ์ไฟฟ้า','placeholder',6),('CAM004','DSLR Camera','กล้อง','camera',2),
 ('CAM005','Video Camera','กล้อง','camera',2),('SPK002','Portable Speaker','ลำโพง','speaker',2),
 ('MIC003','Lavalier Microphone','ไมโครโฟน','microphone',3),('ADP001','USB-C Adapter','อุปกรณ์เสริม','placeholder',0),
]

def seed_sample_data(database_path=DATABASE_PATH):
    initialize_database(database_path)
    ensure_demo_users(database_path)
    with database_connection(database_path) as con:
        con.execute('BEGIN IMMEDIATE')
        if con.execute("SELECT 1 FROM app_settings WHERE key='sample_seed_v1'").fetchone():
            return False
        if any(con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('equipment','borrow_transactions','reservations','maintenance')):
            raise DomainError('เพิ่มข้อมูลตัวอย่างได้เมื่อชุดอุปกรณ์และรายการใช้งานยังว่าง เพื่อเก็บข้อมูลเดิมของคุณ')
        accounts=[('staff','เจ้าหน้าที่โสตทัศนศึกษา','staff','โสตทัศนศึกษา','staff1234'),
                  ('teacher02','ครูพิมพ์ชนก ใจดี','teacher','วิทยาศาสตร์','teacher123')]
        accounts += [(f'student{i:02}',name,'student',f'ม.{4+i%2}/1','student123') for i,name in
                     zip(range(2,7),('กิตติพงษ์ รักเรียน','พิมพ์ใจ แสงทอง','ธนภัทร ดีพร้อม','ศิริพร ตั้งใจ','ณัฐนนท์ สายสื่อ'))]
        for username,name,role,classroom,password in accounts:
            if not con.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():
                con.execute('INSERT INTO users(student_code,username,password,full_name,role,classroom) VALUES(?,?,?,?,?,?)',
                            ('DEMO-'+username.upper(),username,hash_password(password),name,role,classroom))
        users={r['username']:r['id'] for r in con.execute('SELECT id,username FROM users')}
        equipment=[]
        for code,name,category,kind,total in SAMPLE_EQUIPMENT:
            eid=con.execute('INSERT INTO equipment(equipment_code,equipment_name,category,description,total_amount,available_amount,image,storage_location) VALUES(?,?,?,?,?,?,?,?)',
                            (code,name,category,demo_description(kind,name),total,total,f'assets/equipment/{kind}.png','ห้องโสตทัศนศึกษา')).lastrowid
            equipment.append(eid)
        student_ids=[users['student'],*[users[f'student{i:02}'] for i in range(2,7)]]
        def add_loan(user_id,index,days_ago,state,return_delay=None,condition='ปกติ',due_offset=3):
            start=today()-timedelta(days=days_ago)
            due=start+timedelta(days=due_offset)
            returned=(start+timedelta(days=return_delay)).isoformat() if return_delay is not None else None
            photo=f'assets/equipment/{SAMPLE_EQUIPMENT[index][3]}.png'
            before=state in {'กำลังยืม','เกินกำหนด','รอตรวจสอบการคืน','คืนแล้ว'}
            after=state in {'รอตรวจสอบการคืน','คืนแล้ว'}
            approved=state in USAGE_STATUSES or state=='ไม่อนุมัติ'
            return con.execute('INSERT INTO borrow_transactions(user_id,equipment_id,amount,borrow_date,due_date,return_date,purpose,borrow_status,condition_before,condition_after,before_image,after_image,approved_by,approved_at,created_at,return_note,return_requested_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (user_id,equipment[index],1,start.isoformat(),due.isoformat(),returned,'ตัวอย่าง: กิจกรรมการเรียนและสื่อโรงเรียน',state,
                 'ปกติ' if before else None,condition if after else None,photo if before else None,photo if after else None,
                 users['admin'] if approved else None,start.isoformat()+'T01:00:00Z' if approved else None,
                 start.isoformat()+'T00:00:00Z','ข้อมูลจำลอง' if after else '',today().isoformat()+'T00:00:00Z' if after else None)).lastrowid
        for i in range(30):
            add_loan(student_ids[i%6],i%19,5+i*3,'คืนแล้ว',return_delay=4 if i%5==0 else 2)
        add_loan(users['student'],0,0,'กำลังยืม')
        add_loan(users['student'],1,5,'เกินกำหนด')
        add_loan(student_ids[1],2,2,'กำลังยืม',due_offset=2)
        add_loan(student_ids[2],3,1,'รอตรวจสอบการคืน')
        add_loan(student_ids[3],4,-1,'อนุมัติแล้ว')
        add_loan(users['student'],5,0,'รออนุมัติ')
        add_loan(student_ids[4],6,1,'ไม่อนุมัติ')
        damaged=add_loan(student_ids[5],9,6,'คืนแล้ว',return_delay=2,condition='ชำรุด')
        for offset,cost in ((60,650),(30,900)):
            sent=(today()-timedelta(days=offset)).isoformat()
            completed=(today()-timedelta(days=offset-3)).isoformat()
            con.execute("INSERT INTO maintenance(equipment_id,issue,repair_detail,repair_cost,status,created_at,completed_at,amount,stock_locked,sent_date,repaired_date,image) VALUES(?,?,?,?,'ซ่อมเสร็จ',?,?,1,0,?,?,?)",
                        (equipment[3],'ภาพโปรเจกเตอร์ไม่ชัด','ทำความสะอาดและปรับระบบภาพ',cost,sent+'T00:00:00Z',completed+'T00:00:00Z',sent,completed,'assets/equipment/projector.png'))
        con.execute("INSERT INTO maintenance(equipment_id,issue,repair_detail,repair_cost,amount,stock_locked,source_transaction_id,image,sent_date) VALUES(?,?,?,0,1,1,?,?,?)",
                    (equipment[9],'แป้นพิมพ์ชำรุดจากการคืน','รอตรวจอุปกรณ์',damaged,'assets/equipment/notebook.png',today().isoformat()))
        con.execute("INSERT INTO maintenance(equipment_id,issue,repair_detail,repair_cost,status,amount,stock_locked,image,sent_date) VALUES(?,?,?,1200,'กำลังซ่อม',1,1,?,?)",
                    (equipment[3],'หลอดภาพไม่ติด','รอเปลี่ยนอะไหล่','assets/equipment/projector.png',today().isoformat()))
        for eid in (equipment[9],equipment[3]):
            con.execute("UPDATE equipment SET available_amount=available_amount-1,unavailable_amount=1,status='ซ่อมบำรุง' WHERE id=?",(eid,))
        for eid in equipment:
            refresh_stock(con,eid)
        future=(today()+timedelta(days=5)).isoformat()
        finish=(today()+timedelta(days=7)).isoformat()
        con.execute("INSERT INTO reservations(user_id,equipment_id,start_date,end_date,purpose,status) VALUES(?,?,?,?,?,'ยืนยันแล้ว')",
                    (users['student'],equipment[11],future,finish,'ตัวอย่าง: ถ่ายทำกิจกรรมโรงเรียน'))
        con.execute("INSERT INTO app_settings(key,value) VALUES('sample_seed_v1',?)",(today().isoformat(),))
    update_overdue(database_path)
    sync_notifications(database_path)
    return True

if __name__=='__main__':
    print('เพิ่มข้อมูลตัวอย่างแล้ว' if seed_sample_data() else 'มีข้อมูลตัวอย่างแล้ว ไม่มีการเพิ่มซ้ำ')
