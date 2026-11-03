# 文件夹式构建：DLL/许可可检查，不请求管理员权限。
from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'packaging/entrypoint.py')], pathex=[str(root)],
    binaries=[], datas=[], hiddenimports=['app.jobs.native_query', 'app.jobs.search_query', 'pytsk3'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['pytest', 'tkinter', 'PySide6.QtWebEngineCore'],
    noarchive=False)
# QtGui 的通用 hook 会收集可选虚拟键盘插件；本程序不用该 GPL-only
# 模块，显式排除插件及其 DLL/翻译，避免不必要的许可与依赖扩张。
a.binaries = [item for item in a.binaries if 'virtualkeyboard' not in item[0].lower()]
a.datas = [item for item in a.datas if 'virtualkeyboard' not in item[0].lower()]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='CrossDiskManager', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False, uac_admin=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='CrossDiskManager')
