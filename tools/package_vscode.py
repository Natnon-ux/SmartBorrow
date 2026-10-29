"""หน้าที่: รวมไฟล์ระบบสำหรับ VS Code พร้อมสำเนา SQLite ที่ตรวจสอบแล้ว."""
from pathlib import Path
from contextlib import closing
import hashlib
import json
import sqlite3
import tempfile
import zipfile
import ast
import shutil

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'output'/'SmartBorrow.zip'
LEGACY_DEST=ROOT/'output'/'SmartBorrow-VSCode-20261013.zip'
ROOT_FILES=('README.md','FILES.md','requirements.txt','SmartBorrow.code-workspace','.gitignore')
DIRECTORIES=('assets','ui','sql','.vscode','data/uploads')

def runtime_sources():
    """เลือกเฉพาะโมดูลที่ระบบนำเข้าใช้งานจริง รวมการนำเข้าภายในฟังก์ชัน."""
    modules={p.stem:p for p in ROOT.glob('*.py')}
    pending=['start','app','check_sqlite']
    selected=set()
    while pending:
        name=pending.pop()
        if name in selected or name not in modules:continue
        selected.add(name)
        tree=ast.parse(modules[name].read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):pending.extend(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:pending.append(node.module.split('.')[0])
    return [modules[name] for name in sorted(selected)]

def main():
    DEST.parent.mkdir(exist_ok=True)
    files=runtime_sources()+[ROOT/name for name in ROOT_FILES]+[ROOT/'tools/package_vscode.py']
    for directory in DIRECTORIES:
        files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.log'} and not p.is_symlink())
    with tempfile.TemporaryDirectory(prefix='smartborrow-package-') as temp:
        snapshot=Path(temp)/'smartborrow.db'
        with closing(sqlite3.connect(ROOT.as_uri()+'/smartborrow.db?mode=ro',uri=True)) as source,closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
        with closing(sqlite3.connect(snapshot)) as con:
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not con.execute('PRAGMA foreign_key_check').fetchall()
            counts={table:con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('users','equipment','borrow_transactions','reservations','maintenance')}
            references=[]
            for table in ('users','equipment','borrow_transactions','reservations','maintenance'):
                columns=[r[1] for r in con.execute(f'PRAGMA table_info({table})') if r[1].endswith('_image') or r[1] in {'image','document_path','payment_slip'}]
                for column in columns:
                    references.extend(r[0] for r in con.execute(f'SELECT "{column}" FROM {table}') if r[0] and str(r[0]).startswith(('assets/','data/uploads/')))
        entries={p.relative_to(ROOT).as_posix():p for p in files}
        assert all(value in entries for value in references),'A referenced upload or asset is missing'
        entries['smartborrow.db']=snapshot
        manifest={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sorted(entries.items())}
        with zipfile.ZipFile(DEST,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for name,path in sorted(entries.items()):archive.write(path,'SmartBorrow/'+name)
            archive.writestr('SmartBorrow/MANIFEST.json',json.dumps({'files':manifest,'sqlite_counts':counts,'secrets_included':False},ensure_ascii=False,indent=2))
        with zipfile.ZipFile(DEST) as archive:
            assert archive.testzip() is None
            assert 'SmartBorrow/.vscode/launch.json' in archive.namelist()
            assert 'SmartBorrow/start.py' in archive.namelist()
            assert 'SmartBorrow/.streamlit/secrets.toml' not in archive.namelist()
            assert not any(Path(name).name.startswith(('test_','figma-')) for name in archive.namelist())
            for name in archive.namelist():
                if name.endswith('.py'):compile(archive.read(name),name,'exec')
        report={'archive':str(DEST),'size_bytes':DEST.stat().st_size,'file_count':len(manifest)+1,'sha256':hashlib.sha256(DEST.read_bytes()).hexdigest(),'sqlite_counts':counts,'integrity':'ok','referenced_assets_complete':True,'source_syntax':'ok','zip_crc':'ok','secrets_included':False}
        (DEST.parent/'SmartBorrow-package-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        shutil.copy2(DEST,LEGACY_DEST)
        print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
