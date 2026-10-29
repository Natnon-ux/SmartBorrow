"""ทดสอบระบบในฐานข้อมูลชั่วคราว โดยไม่ใช้โฟลเดอร์สำรองภายนอกโครงการ."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests/support')]
scratch = ROOT / 'data/test_runtime'
scratch.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(scratch)
os.environ['TEMP'] = os.environ['TMP'] = str(scratch)

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
