# หน้าที่: ตรวจรูปแบบรหัสนักเรียนและครู
"""Canonical student-number formatting: nine digits, a dash, then one digit."""
import re
from common import DomainError


def format_student_code(value):
    value=str(value).strip()
    if not re.fullmatch(r'6[0-9]{8}-[0-9]',value):
        raise DomainError('รหัสประจำตัวต้องเป็นรูปแบบ 6xxxxxxxx-x เช่น 683040123-4 (เลข 9 หลักก่อนขีด และ 1 หลักหลังขีด)')
    return value
