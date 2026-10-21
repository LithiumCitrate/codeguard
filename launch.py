"""Entry point for the portable Windows app and source distribution."""
import os
from pathlib import Path
import sys

if getattr(sys, 'frozen', False):
    root = Path(sys.executable).resolve().parent
else:
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / 'src'))

from codeguard.web import serve

if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    try:
        serve(str(root / '.codeguard'), port=0, open_browser='--no-browser' not in sys.argv)
    except Exception as exc:
        print('CodeGuard 启动失败：%s' % exc)
        print('请确认 .codeguard/index.bin 和 corpus 文件夹与程序在同一目录。')
        if '--no-browser' not in sys.argv:
            input('按 Enter 退出…')
        raise SystemExit(2)
