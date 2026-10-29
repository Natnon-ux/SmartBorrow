# หน้าที่: เชื่อม SQLite และปรับโครงสร้างโดยรักษาข้อมูลเดิม
"""SQLite: 5 ตารางหลัก 2 ตารางสนับสนุน และ migration ที่เก็บข้อมูลเดิม.

วันที่ใช้ YYYY-MM-DD; timestamp ใช้ UTC การยืมและสต็อกจัดการใน services.py
"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


PROJECT_DIR = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_DIR / "smartborrow.db"
SCHEMA_VERSION = 14
TABLE_DESCRIPTIONS = {
    "users": "ผู้ใช้งานและสิทธิ์ในระบบ",
    "equipment": "อุปกรณ์ จำนวนคงเหลือ และที่จัดเก็บ",
    "borrow_transactions": "รายการยืม การอนุมัติ และการคืน",
    "reservations": "การจองอุปกรณ์ล่วงหน้า",
    "maintenance": "ประวัติอาการเสียและค่าใช้จ่ายซ่อม",
    "approval_events": "ประวัติการตรวจเอกสารและการตัดสินใจอนุมัติ",
}
REQUIRED_COLUMNS = {
    "users": ("id", "student_code", "username", "password", "full_name", "role",
              "classroom", "phone", "created_at", "status", "profile_image", "email", "email_verified_at", "phone_verified_at", "auth_version"),
    "equipment": ("id", "equipment_code", "equipment_name", "category", "description",
                  "total_amount", "available_amount", "image", "storage_location",
                  "status", "created_at", "unavailable_amount"),
    "borrow_transactions": ("id", "user_id", "equipment_id", "amount", "borrow_date",
                            "due_date", "return_date", "purpose", "borrow_status",
                            "condition_before", "condition_after", "before_image",
                            "after_image", "approved_by", "approved_at", "created_at", "return_note", "return_requested_at", "reservation_id",
                            "request_group", "document_url", "document_path", "fine_rate_cents", "fine_days", "fine_amount_cents",
                            "fine_status", "fine_note", "fine_resolved_by", "fine_resolved_at", "payment_slip", "payment_review", "payment_submitted_at", "payment_review_note"),
    "reservations": ("id", "user_id", "equipment_id", "reservation_date", "start_date",
                     "end_date", "purpose", "status", "document_path", "reviewed_by", "reviewed_at"),
    "maintenance": ("id", "equipment_id", "issue", "repair_detail", "repair_cost",
                    "status", "created_at", "completed_at", "amount", "stock_locked", "source_transaction_id", "image", "sent_date", "repaired_date"),
    "notifications": ("id","user_id","event_key","message","created_at","read_at","reference_id","target_page"),
    "otp_challenges": ("id","purpose","channel","destination","user_id","auth_version","binding","code_hash","created_at","expires_at","attempts","status","proof_hash","proof_expires_at","delivery_state"),
    "app_settings": ("key","value"),
}


def date_constraint(column: str, nullable: bool = False) -> str:
    """สร้าง SQL ตรวจวันที่จริง รวมถึงวันเกินเดือนและปีอธิกสุรทิน.

    ชื่อคอลัมน์ที่ส่งเข้าฟังก์ชันนี้เป็นค่าคงที่ใน schema เท่านั้น
    """
    condition = (
        f"length({column}) = 10 AND date({column}, '+0 days') IS NOT NULL "
        f"AND date({column}, '+0 days') = {column}"
    )
    if nullable:
        condition = f"{column} IS NULL OR ({condition})"
    return f"CHECK ({condition})"


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_code TEXT NOT NULL UNIQUE CHECK (length(trim(student_code)) > 0),
        username TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (length(trim(username)) > 0),
        password TEXT NOT NULL CHECK (length(password) > 0),
        full_name TEXT NOT NULL CHECK (length(trim(full_name)) > 0),
        role TEXT NOT NULL DEFAULT 'student'
            CHECK (role IN ('student', 'teacher', 'staff', 'admin')),
        classroom TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipment_code TEXT NOT NULL COLLATE NOCASE UNIQUE
            CHECK (length(trim(equipment_code)) > 0),
        equipment_name TEXT NOT NULL CHECK (length(trim(equipment_name)) > 0),
        category TEXT NOT NULL CHECK (length(trim(category)) > 0),
        description TEXT NOT NULL DEFAULT '',
        total_amount INTEGER NOT NULL
            CHECK (typeof(total_amount) = 'integer' AND total_amount >= 0),
        available_amount INTEGER NOT NULL
            CHECK (typeof(available_amount) = 'integer'
                   AND available_amount >= 0 AND available_amount <= total_amount),
        image TEXT NOT NULL DEFAULT 'assets/equipment/placeholder.png',
        storage_location TEXT NOT NULL CHECK (length(trim(storage_location)) > 0),
        status TEXT NOT NULL DEFAULT 'พร้อมใช้งาน'
            CHECK (status IN ('พร้อมใช้งาน', 'ถูกยืม', 'จอง', 'ชำรุด', 'ซ่อมบำรุง', 'ปิดใช้งาน')),
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS borrow_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE RESTRICT,
        amount INTEGER NOT NULL CHECK (typeof(amount) = 'integer' AND amount > 0),
        borrow_date TEXT NOT NULL {date_constraint('borrow_date')},
        due_date TEXT NOT NULL {date_constraint('due_date')},
        return_date TEXT {date_constraint('return_date', nullable=True)},
        purpose TEXT NOT NULL CHECK (length(trim(purpose)) > 0),
        borrow_status TEXT NOT NULL DEFAULT 'รออนุมัติ'
            CHECK (borrow_status IN ('รออนุมัติ', 'อนุมัติแล้ว', 'ไม่อนุมัติ',
                'กำลังยืม', 'รอตรวจสอบการคืน', 'คืนแล้ว', 'เกินกำหนด', 'ยกเลิก')),
        condition_before TEXT
            CHECK (condition_before IS NULL OR condition_before IN ('ปกติ', 'มีรอยเล็กน้อย', 'มีตำหนิ')),
        condition_after TEXT
            CHECK (condition_after IS NULL OR condition_after IN ('ปกติ', 'ชำรุด', 'สูญหาย')),
        before_image TEXT,
        after_image TEXT,
        approved_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
        approved_at TEXT,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        CHECK (due_date >= borrow_date),
        CHECK (return_date IS NULL OR return_date >= borrow_date)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE RESTRICT,
        reservation_date TEXT NOT NULL DEFAULT (date('now', '+7 hours'))
            {date_constraint('reservation_date')},
        start_date TEXT NOT NULL {date_constraint('start_date')},
        end_date TEXT NOT NULL {date_constraint('end_date')},
        purpose TEXT NOT NULL CHECK (length(trim(purpose)) > 0),
        status TEXT NOT NULL DEFAULT 'รออนุมัติ'
            CHECK (status IN ('รออนุมัติ', 'ยืนยันแล้ว', 'ไม่อนุมัติ', 'ยกเลิก', 'สิ้นสุดแล้ว')),
        CHECK (end_date >= start_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS maintenance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE RESTRICT,
        issue TEXT NOT NULL CHECK (length(trim(issue)) > 0),
        repair_detail TEXT NOT NULL DEFAULT '',
        repair_cost REAL NOT NULL DEFAULT 0
            CHECK (typeof(repair_cost) IN ('integer', 'real') AND repair_cost >= 0),
        status TEXT NOT NULL DEFAULT 'รอตรวจสอบ'
            CHECK (status IN ('รอตรวจสอบ', 'กำลังซ่อม', 'ซ่อมเสร็จ', 'ไม่สามารถซ่อมได้')),
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        completed_at TEXT,
        CHECK (completed_at IS NULL OR completed_at >= created_at)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_borrow_user ON borrow_transactions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_borrow_equipment ON borrow_transactions(equipment_id)",
    "CREATE INDEX IF NOT EXISTS idx_borrow_status_due ON borrow_transactions(borrow_status, due_date)",
    "CREATE INDEX IF NOT EXISTS idx_borrow_approver ON borrow_transactions(approved_by)",
    "CREATE INDEX IF NOT EXISTS idx_equipment_category_status ON equipment(category, status)",
    "CREATE INDEX IF NOT EXISTS idx_reservation_user ON reservations(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_reservation_period ON reservations(equipment_id, start_date, end_date)",
    "CREATE INDEX IF NOT EXISTS idx_maintenance_equipment ON maintenance(equipment_id)",
)


def get_connection(database_path: str | Path = DATABASE_PATH) -> sqlite3.Connection:
    """เปิด connection ใหม่ พร้อมเปิด Foreign Keys ทุกครั้งและอ่านแถวด้วยชื่อคอลัมน์."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


@contextmanager
def database_connection(database_path: str | Path = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    """Commit เมื่อสำเร็จ, rollback เมื่อมีข้อผิดพลาด และปิด connection เสมอ."""
    connection = get_connection(database_path)
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: str | Path = DATABASE_PATH) -> Path:
    """สร้างทั้งห้าตารางอย่างปลอดภัย เรียกซ้ำได้โดยไม่ลบข้อมูลเดิม."""
    with database_connection(database_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise sqlite3.DatabaseError("ฐานข้อมูลเป็นเวอร์ชันใหม่กว่าโค้ด กรุณาใช้โค้ดเวอร์ชันที่ตรงกัน")
        connection.execute("BEGIN IMMEDIATE")
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        equipment_columns = {row["name"] for row in connection.execute("PRAGMA table_info(equipment)")}
        if "unavailable_amount" not in equipment_columns:
            connection.execute("ALTER TABLE equipment ADD COLUMN unavailable_amount INTEGER NOT NULL DEFAULT 0 "
                               "CHECK(typeof(unavailable_amount)='integer' AND unavailable_amount>=0 "
                               "AND available_amount+unavailable_amount<=total_amount)")
        additions = {
            "users": {"profile_image": "TEXT NOT NULL DEFAULT 'assets/profile.png'",
                      "email": "TEXT NOT NULL DEFAULT ''", "email_verified_at": "TEXT", "phone_verified_at": "TEXT",
                      "auth_version": "INTEGER NOT NULL DEFAULT 0 CHECK(auth_version>=0)",
                      "executive_title": "TEXT NOT NULL DEFAULT '' CHECK(executive_title IN ('','director','deputy'))"},
            "borrow_transactions": {"review_stage": "TEXT NOT NULL DEFAULT ''",
                                    "decision_note": "TEXT NOT NULL DEFAULT ''",
                                    "document_reviewed_by": "INTEGER REFERENCES users(id)", "document_reviewed_at": "TEXT",
                                    "final_approved_by": "INTEGER REFERENCES users(id)", "final_approved_at": "TEXT",
                                    "return_note": "TEXT NOT NULL DEFAULT ''", "return_requested_at": "TEXT",
                                    "reservation_id": "INTEGER REFERENCES reservations(id)",
                                    "request_group": "TEXT NOT NULL DEFAULT ''", "document_url": "TEXT NOT NULL DEFAULT ''",
                                    "document_path": "TEXT NOT NULL DEFAULT ''",
                                    "fine_rate_cents": "INTEGER NOT NULL DEFAULT 0 CHECK(typeof(fine_rate_cents)='integer' AND fine_rate_cents>=0)",
                                    "fine_days": "INTEGER NOT NULL DEFAULT 0 CHECK(typeof(fine_days)='integer' AND fine_days>=0)",
                                    "fine_amount_cents": "INTEGER NOT NULL DEFAULT 0 CHECK(typeof(fine_amount_cents)='integer' AND fine_amount_cents>=0)",
                                    "fine_status": "TEXT NOT NULL DEFAULT 'ไม่มีค่าปรับ' CHECK(fine_status IN ('ไม่มีค่าปรับ','ค้างชำระ','ชำระแล้ว','ยกเว้น'))",
                                    "fine_note": "TEXT NOT NULL DEFAULT ''", "fine_resolved_by": "INTEGER REFERENCES users(id)",
                                    "fine_resolved_at": "TEXT",
                                    "payment_slip": "TEXT NOT NULL DEFAULT ''",
                                    "payment_review": "TEXT NOT NULL DEFAULT '' CHECK(payment_review IN ('','รอตรวจสอบ','ยืนยันแล้ว','ไม่ผ่าน'))",
                                    "payment_submitted_at": "TEXT",
                                    "payment_review_note": "TEXT NOT NULL DEFAULT ''"},
            "reservations": {"document_path":"TEXT NOT NULL DEFAULT ''","reviewed_by":"INTEGER REFERENCES users(id)","reviewed_at":"TEXT"},
            "maintenance": {"amount": "INTEGER NOT NULL DEFAULT 1 CHECK(typeof(amount)='integer' AND amount>0)",
                            "stock_locked": "INTEGER NOT NULL DEFAULT 0 CHECK(stock_locked IN (0,1))",
                            "source_transaction_id": "INTEGER REFERENCES borrow_transactions(id)", "image": "TEXT",
                            "sent_date": "TEXT " + date_constraint('sent_date',nullable=True),
                            "repaired_date": "TEXT " + date_constraint('repaired_date',nullable=True)},
        }
        for table, columns in additions.items():
            existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            for name, declaration in columns.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_maintenance_source ON maintenance(source_transaction_id) WHERE source_transaction_id IS NOT NULL")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_borrow_group ON borrow_transactions(request_group)")
        connection.execute('''CREATE TABLE IF NOT EXISTS approval_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL REFERENCES borrow_transactions(id),
            actor_id INTEGER NOT NULL REFERENCES users(id),
            actor_name TEXT NOT NULL, actor_title TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('reviewed','approved','rejected','returned')),
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL)''')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_approval_event_loan ON approval_events(transaction_id,id)')
        if version < 14:
            # เติมประวัติเดิมเท่าที่มีหลักฐาน ห้ามสร้างชื่อ เวลา หรือเหตุผลขึ้นเอง
            for field,stamp,event in [('document_reviewed_by','document_reviewed_at','reviewed'),('approved_by','approved_at','approved')]:
                for old in connection.execute(f'''SELECT b.id,b.borrow_status,b.{stamp} stamp,u.id actor,u.full_name,u.executive_title
                    FROM borrow_transactions b JOIN users u ON u.id=b.{field} WHERE b.{stamp} IS NOT NULL''').fetchall():
                    kind='rejected' if event=='approved' and old['borrow_status']=='ไม่อนุมัติ' else event
                    connection.execute('INSERT INTO approval_events(transaction_id,actor_id,actor_name,actor_title,action,reason,created_at) VALUES(?,?,?,?,?,?,?)',
                        (old['id'],old['actor'],old['full_name'],old['executive_title'],kind,'ข้อมูลเดิมก่อนเพิ่มประวัติการพิจารณา',old['stamp']))
        connection.execute("CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                           "user_id INTEGER NOT NULL REFERENCES users(id),event_key TEXT NOT NULL UNIQUE,message TEXT NOT NULL,"
                           "created_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')),read_at TEXT)")
        connection.execute('CREATE INDEX IF NOT EXISTS idx_notification_user ON notifications(user_id,read_at)')
        notification_columns={r['name'] for r in connection.execute('PRAGMA table_info(notifications)')}
        if 'reference_id' not in notification_columns:
            connection.execute('ALTER TABLE notifications ADD COLUMN reference_id INTEGER')
        if 'target_page' not in notification_columns:
            connection.execute("ALTER TABLE notifications ADD COLUMN target_page TEXT NOT NULL DEFAULT ''")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_email ON users(email COLLATE NOCASE) WHERE email!=''")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_verified_phone ON users(phone) WHERE phone_verified_at IS NOT NULL AND phone!=''")
        connection.execute('''CREATE TABLE IF NOT EXISTS otp_challenges (
            id TEXT PRIMARY KEY, purpose TEXT NOT NULL, channel TEXT NOT NULL CHECK(channel IN ('email','sms')),
            destination TEXT NOT NULL, user_id INTEGER REFERENCES users(id), auth_version INTEGER,
            binding TEXT NOT NULL, code_hash TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
            proof_hash TEXT, proof_expires_at INTEGER, delivery_state TEXT NOT NULL DEFAULT 'queued')''')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_otp_destination ON otp_challenges(channel,destination,created_at)')
        connection.execute('CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        for table, expected_columns in REQUIRED_COLUMNS.items():
            existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            if not set(expected_columns).issubset(existing):
                raise sqlite3.DatabaseError(f"โครงสร้างตาราง {table} ไม่ตรงกับเวอร์ชันนี้")
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return Path(database_path).resolve()


def get_database_overview(database_path: str | Path = DATABASE_PATH) -> list[dict]:
    """อ่านจำนวนข้อมูลจริงในแต่ละตาราง โดยไม่มีการสร้างข้อมูลตัวอย่าง."""
    with database_connection(database_path) as connection:
        return [
            {"ตาราง": table, "หน้าที่": description,
             "จำนวนข้อมูล": connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]}
            for table, description in TABLE_DESCRIPTIONS.items()
        ]


def get_integrity_report(database_path: str | Path = DATABASE_PATH) -> dict:
    """ตรวจความสมบูรณ์ของ SQLite และตรวจ Foreign Keys."""
    with database_connection(database_path) as connection:
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        foreign_key_errors = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
        return {
            "ok": integrity == ["ok"] and not foreign_key_errors,
            "integrity": integrity,
            "foreign_key_errors": foreign_key_errors,
            "schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
        }


if __name__ == "__main__":
    path = initialize_database()
    report = get_integrity_report()
    print(f"Database: {path}")
    print(f"Tables: {len(get_database_overview())}")
    print(f"Integrity: {'PASS' if report['ok'] else 'FAIL'}")
    if not report["ok"]:
        raise SystemExit(1)
