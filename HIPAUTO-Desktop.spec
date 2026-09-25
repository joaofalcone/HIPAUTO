# -*- mode: python ; coding: utf-8 -*-
# Gera sempre dist/HIPAUTO-Desktop (nome estável, sem número de versão).
a = Analysis(['hipauto_desktop.py'], pathex=[], binaries=[],
    datas=[('config.json', '.'), ('homologados-linux.json', '.'), ('perifericos-br.json', '.'),
           ('vendor', 'vendor')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['unittest', 'pydoc', 'http.server', 'xmlrpc'], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='HIPAUTO-Desktop',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None)
