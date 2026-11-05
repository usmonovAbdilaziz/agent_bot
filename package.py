"""Tarqatiladigan ZIP: faqat manba, yo'riqnoma va testlar; maxfiy fayllarsiz."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import argparse

ROOT=Path(__file__).resolve().parent
FILES=['designs.py','config.py','invitation_store.py','web_common.py','legacy_bot.py','legacy_webapp.py','API_CONTRACT.md','PRODUCT.md','DESIGN.md','main.py','db.py','run.py','launch.py','webapp.py','package.py','requirements.txt','requirements-dev.txt','package.json','package-lock.json','vite.config.js',
       '.env.example','.gitignore','README.md','TEST_REPORT.md','ROLLBACK.md','CHANGELOG.md','DEVICE_CHECKLIST.md','scripts/sqlite_safe_backup.py','pytest.ini','start.command','start.bat',
       'start_windows.ps1','setup_config.py','WINDOWS_README.txt']


def build(windows=False):
    files=[ROOT/name for name in FILES]
    files += [p for folder in ('tests','postman','web','web_minimal','react_src') for p in (ROOT/folder).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.js','.jsx','.yaml','.json','.html','.css','.cjs','.md','.sql')]
    target=ROOT.parent/('agent_bot_windows.zip' if windows else 'agent_bot_minimal.zip')
    with ZipFile(target,'w',ZIP_DEFLATED) as z:
        for path in sorted(files):
            name=Path('agent_bot')/path.relative_to(ROOT)
            if path.suffix in ('.bat','.ps1'):
                z.writestr(str(name),path.read_text(encoding='utf-8').replace('\r\n','\n').replace('\n','\r\n').encode('utf-8'))
            else:
                z.write(path,name)
    with ZipFile(target) as z:
        assert z.testzip() is None
        assert all(Path(name).name!='.env' and '.venv' not in Path(name).parts for name in z.namelist())
    print(f'ZIP: {target}\nFayllar: {len(files)}\nSHA256: {hashlib.sha256(target.read_bytes()).hexdigest()}')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--windows',action='store_true')
    build(parser.parse_args().windows)
