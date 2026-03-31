# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=['/Users/x/.openclaw/workspace/cc-feishu-plugin'],
    binaries=[],
    datas=[],
    hiddenimports=[
    "src.config",
    "src.feishu.client",
    "src.feishu.message_handler",
    "src.security.auth",
    "src.security.validator",
    "src.claude.integration",
    "src.claude.session_manager",
    "src.format.reply_formatter",
    "src.install.api",
    "src.install.qr",
    "src.install.flow",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='cc-feishu-bridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    console=True,
)
