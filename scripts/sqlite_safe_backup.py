"""Validated SQLite backup/restore; never open a missing source for writing."""
import argparse
from contextlib import closing
import sqlite3
from pathlib import Path

REQUIRED = {'settings', 'users', 'q_invites'}

def source(path):
    path=Path(path).resolve()
    if not path.is_file(): raise ValueError(f'Missing source: {path}')
    conn=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('SQLite integrity_check failed')
        names={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED <= names: raise ValueError('Required tables are missing')
        return conn
    except BaseException:
        conn.close(); raise

def copy(source_path, target_path, *, new):
    source_path, target_path=Path(source_path).resolve(),Path(target_path).resolve()
    if source_path==target_path: raise ValueError('Source and target must differ')
    src=source(source_path)
    try:
        if new:
            with target_path.open('xb'): pass
        elif not target_path.is_file(): raise ValueError('Target database is missing')
        with sqlite3.connect(target_path) as dst: src.backup(dst)
    finally: src.close()
    with closing(source(target_path)): pass

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('operation',choices=['backup','restore']);parser.add_argument('source');parser.add_argument('target');parser.add_argument('--safety')
    args=parser.parse_args()
    if args.operation=='backup': copy(args.source,args.target,new=True)
    else:
        if not args.safety: parser.error('restore requires --safety')
        paths=[Path(x).resolve() for x in (args.source,args.target,args.safety)]
        if len(set(paths))!=3: parser.error('source, target and safety must differ')
        # Validate source before taking any action, then preserve current target independently.
        with closing(source(args.source)): pass
        copy(args.target,args.safety,new=True)
        copy(args.source,args.target,new=False)

if __name__=='__main__': main()
