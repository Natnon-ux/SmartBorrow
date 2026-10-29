# หน้าที่: ตรวจการเชื่อมต่อและอ่านข้อมูลจากฐานข้อมูล
"""ตรวจฐานข้อมูลเดิมหรือรันคำสั่งอ่านข้อมูลจาก Terminal ของ VS Code."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from database import DATABASE_PATH, REQUIRED_COLUMNS, SCHEMA_VERSION


def check_connection(connection, database_path):
    tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing=sorted(set(REQUIRED_COLUMNS)-tables)
    counts={name:connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in REQUIRED_COLUMNS if name in tables}
    integrity=[row[0] for row in connection.execute('PRAGMA integrity_check')]
    foreign_keys=[list(row) for row in connection.execute('PRAGMA foreign_key_check')]
    version=connection.execute('PRAGMA user_version').fetchone()[0]
    return dict(connected=True,database=str(database_path),sqlite_version=sqlite3.sqlite_version,
                schema_version=version,tables=counts,missing_tables=missing,
                integrity=integrity,foreign_key_errors=foreign_keys,
                ok=not missing and integrity==['ok'] and not foreign_keys and version==SCHEMA_VERSION)


def main():
    parser=argparse.ArgumentParser(description='ตรวจ SQLite ของ SmartBorrow หรือรัน SQL แบบอ่านข้อมูล')
    parser.add_argument('--database',type=Path,default=DATABASE_PATH)
    parser.add_argument('--query',help='คำสั่ง SQL หนึ่งคำสั่งสำหรับอ่านข้อมูล')
    args=parser.parse_args()
    path=args.database.resolve()
    if not path.is_file():
        parser.exit(1,f'ไม่พบฐานข้อมูล: {path}\n')
    try:
        # mode=ro ไม่สร้างฐานข้อมูลใหม่ และป้องกันแก้ไขข้อมูลจริงจากเครื่องมือตรวจนี้
        connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)
        try:
            connection.row_factory=sqlite3.Row
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA query_only=ON')
            if args.query:
                cursor=connection.execute(args.query)
                if cursor.description is None:
                    parser.exit(1,'กรุณาใช้คำสั่ง SQL ที่แสดงผลข้อมูล\n')
                result=[dict(row) for row in cursor.fetchall()]
            else:
                result=check_connection(connection,path)
        finally:
            connection.close()
    except sqlite3.Error as error:
        parser.exit(1,f'ไม่สามารถอ่านฐานข้อมูล: {error}\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if args.query or result['ok'] else 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
