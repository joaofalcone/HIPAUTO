# -*- mode: python ; coding: utf-8 -*-
a = Analysis(['hipauto_desktop_v22.py'], pathex=[], binaries=[],
    datas=[('config.json', '.'), ('homologados-linux.json', '.'),
           ('serial_probe.py', '.'), ('vendor', 'vendor'),
           ('VERSION.md', '.'), ('RELEASES.md', '.')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='HIPAUTO-Desktop',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None)
