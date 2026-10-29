"""เตรียมบัญชีทดลองและรายการอุปกรณ์สำหรับสำเนาใหม่ ไม่แก้รายการที่มีอยู่."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database import initialize_database, database_connection
from auth import ensure_demo_users


def main():
    initialize_database()
    ensure_demo_users()
    rows = json.loads((ROOT / 'assets/equipment/catalog.json').read_text(encoding='utf-8'))
    added = 0
    with database_connection() as connection:
        for row in rows:
            if connection.execute('SELECT 1 FROM equipment WHERE equipment_code=?',
                                  (row['equipment_code'],)).fetchone():
                continue
            columns = list(row)
            connection.execute(
                'INSERT INTO equipment (' + ','.join(columns) + ') VALUES ('
                + ','.join('?' for _ in columns) + ')', [row[key] for key in columns])
            added += 1
    print(f'เตรียมข้อมูลเรียบร้อย เพิ่มอุปกรณ์ {added} รายการ โดยไม่แก้ข้อมูลเดิม')


if __name__ == '__main__':
    main()
