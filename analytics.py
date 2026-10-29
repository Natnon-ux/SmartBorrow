# หน้าที่: สรุปข้อมูลสำหรับหน้าจัดการและรายงาน
"""ข้อมูล Dashboard และกราฟจาก SQLite โดยไม่สร้างตัวเลขจำลอง."""
from common import HELD_STATUSES, OUT_STATUSES, USAGE_STATUSES, query_rows, today
from database import DATABASE_PATH
from database import database_connection
from common import MANAGER_ROLES,require_actor
from services import transactions,maintenance_rows,validate_period
from collections import Counter
from datetime import date,timedelta
from common import thai_month

def dashboard_data(user: dict, database_path=DATABASE_PATH) -> dict:
    stock = query_rows("SELECT COALESCE(SUM(total_amount),0) total, COALESCE(SUM(available_amount),0) available, "
                       "COALESCE(SUM(unavailable_amount),0) broken "
                       "FROM equipment WHERE status!='ปิดใช้งาน'", database_path=database_path)[0]
    rows = query_rows("SELECT b.*,e.equipment_name,u.full_name FROM borrow_transactions b "
                      "JOIN equipment e ON e.id=b.equipment_id JOIN users u ON u.id=b.user_id ORDER BY b.created_at DESC,b.id DESC",
                      database_path=database_path)
    visible = rows if user["role"] in {"admin", "staff", "teacher"} else [r for r in rows if r["user_id"] == user["id"]]
    stock["borrowed"] = sum(r["amount"] for r in rows if r["borrow_status"] in HELD_STATUSES)
    stock["overdue"] = sum(r["borrow_status"] in OUT_STATUSES and r["due_date"] < today().isoformat() for r in visible)
    usage = [r for r in visible if r["borrow_status"] in USAGE_STATUSES]
    monthly, popular = {}, {}
    for row in usage:
        month = row["borrow_date"][:7]
        monthly[month] = monthly.get(month, 0) + 1
        name = row["equipment_name"]
        popular[name] = popular.get(name, 0) + row["amount"]
    due = [r for r in visible if r["borrow_status"] in OUT_STATUSES]
    due.sort(key=lambda r: r["due_date"])
    return {"stock": stock, "recent": visible[:10], "due": due[:10],
            "monthly": [{"เดือน": thai_month(m), "จำนวนครั้ง": n} for m, n in sorted(monthly.items())],
            "popular": [{"อุปกรณ์": name, "จำนวนที่ยืม": n} for name, n in sorted(popular.items(), key=lambda item: -item[1])[:5]]}

def report_data(actor_id,start,end,database_path=DATABASE_PATH):
    start,end=validate_period(start,end,future=False)
    with database_connection(database_path) as con:
        require_actor(con,actor_id,MANAGER_ROLES)
    loans=[r for r in transactions(actor_id,database_path) if start<=r['borrow_date']<=end]
    usage=[r for r in loans if r['borrow_status'] in USAGE_STATUSES]
    monthly=Counter(r['borrow_date'][:7] for r in usage)
    equipment,people,categories=Counter(),Counter(),Counter()
    for r in usage:
        equipment[f"{r['equipment_code']} · {r['equipment_name']}"]+=r['amount']
        people[r['full_name']+' · '+r['username']]+=1
        categories[r['category']]+=r['amount']
    repairs=[r for r in maintenance_rows(actor_id,database_path) if start<=(r['sent_date'] or r['created_at'][:10])<=end]
    broken=query_rows('SELECT * FROM equipment WHERE unavailable_amount>0',database_path=database_path)
    return dict(usage=usage,monthly=[{'เดือน':thai_month(m),'จำนวนครั้ง':n} for m,n in sorted(monthly.items())],
                popular=[{'อุปกรณ์':m,'จำนวนชิ้น':n} for m,n in equipment.most_common(10)],
                people=[{'ผู้ยืม':m,'จำนวนครั้ง':n} for m,n in people.most_common(10)],categories=categories,
                overdue=[r for r in loans if r['borrow_status'] in OUT_STATUSES and r['due_date']<today().isoformat()],
                repairs=repairs,cost=sum(r['repair_cost'] for r in repairs),broken=broken)

def insight_data(actor_id,database_path=DATABASE_PATH):
    first=today().replace(day=1)
    previous_end=first-timedelta(days=1)
    previous_start=previous_end.replace(day=1)
    current=report_data(actor_id,first,today(),database_path)
    previous=report_data(actor_id,previous_start,previous_end,database_path)
    all_data=report_data(actor_id,date(1900,1,1),today(),database_path)
    current_count,previous_count=len(current['usage']),len(previous['usage'])
    percent=(current_count-previous_count)/previous_count*100 if previous_count else None
    repeated=Counter(f"{r['equipment_code']} · {r['equipment_name']}" for r in all_data['repairs'])
    return dict(current=current_count,previous=previous_count,percent=percent,
                categories=[{'หมวดหมู่':name,'จำนวนชิ้น':n} for name,n in all_data['categories'].most_common()],
                repeated=[{'อุปกรณ์':name,'จำนวนงานซ่อม':n} for name,n in repeated.most_common() if n>=2])
