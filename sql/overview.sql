-- sqlite
-- SmartBorrow: ใช้ SQLite: Use Database เลือก smartborrow.db ก่อนรัน
-- เลือกคำสั่งที่ต้องการ แล้วคลิกขวา SQLite: Run Selected Query

-- จำนวนข้อมูลในตารางหลักและตารางสนับสนุน
SELECT 'users' AS table_name, COUNT(*) AS row_count FROM users
UNION ALL SELECT 'equipment', COUNT(*) FROM equipment
UNION ALL SELECT 'borrow_transactions', COUNT(*) FROM borrow_transactions
UNION ALL SELECT 'reservations', COUNT(*) FROM reservations
UNION ALL SELECT 'maintenance', COUNT(*) FROM maintenance
UNION ALL SELECT 'notifications', COUNT(*) FROM notifications
UNION ALL SELECT 'app_settings', COUNT(*) FROM app_settings;

-- อุปกรณ์และสต็อกปัจจุบัน
SELECT equipment_code, equipment_name, category,
       total_amount, available_amount, unavailable_amount, status
FROM equipment
ORDER BY equipment_name;

-- ตัวอย่าง JOIN ผู้ยืม + อุปกรณ์ + ประวัติยืม
SELECT b.id, u.full_name, e.equipment_code, e.equipment_name,
       b.amount, b.borrow_date, b.due_date, b.borrow_status
FROM borrow_transactions AS b
JOIN users AS u ON u.id = b.user_id
JOIN equipment AS e ON e.id = b.equipment_id
ORDER BY b.id DESC
LIMIT 20;

-- บัญชีผู้ใช้ ไม่แสดงแฮชรหัสผ่าน
SELECT id, student_code, username, full_name, role, classroom, status
FROM users
ORDER BY id;

-- ตรวจความสมบูรณ์และความสัมพันธ์ (foreign_key_check ต้องไม่มีแถว)
PRAGMA integrity_check;
PRAGMA foreign_key_check;

-- ใบคำขอหลายรายการ (กลุ่มว่างคือรายการยืมเดิม)
SELECT request_group, COUNT(*) AS equipment_count, SUM(amount) AS total_pieces,
       MIN(borrow_date) AS borrow_date, MAX(due_date) AS due_date
FROM borrow_transactions
WHERE request_group <> ''
GROUP BY request_group
ORDER BY MAX(id) DESC;

-- ค่าปรับค้างชำระ เก็บเป็นสตางค์ / 100 เพื่อแสดงบาท
SELECT b.id, u.full_name, e.equipment_name, b.fine_days,
       b.fine_rate_cents / 100.0 AS daily_rate_baht,
       b.fine_amount_cents / 100.0 AS fine_baht, b.fine_status
FROM borrow_transactions b
JOIN users u ON u.id = b.user_id
JOIN equipment e ON e.id = b.equipment_id
WHERE b.fine_status = 'ค้างชำระ'
ORDER BY b.id DESC;
