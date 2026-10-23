# PyInstaller spec — one folder (fast start) that Inno Setup packs into ChequePrinterSetup.exe
# Build:  pyinstaller --noconfirm ChequePrinter.spec
block_cipher = None

EXCLUDE = ['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick', 'PySide6.Qt3DCore',
           'PySide6.Qt3DRender', 'PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.QtQuick3D', 'PySide6.QtMultimedia',
           'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtBluetooth', 'PySide6.QtNfc',
           'PySide6.QtPositioning', 'PySide6.QtLocation', 'PySide6.QtSensors', 'PySide6.QtSerialPort',
           'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtWebSockets', 'PySide6.QtWebChannel', 'PySide6.QtPdf',
           'PySide6.QtPdfWidgets', 'PySide6.QtSpatialAudio', 'PySide6.QtTextToSpeech', 'tkinter']

a = Analysis(['run.py'], pathex=[], binaries=[], datas=[('assets', 'assets')], hiddenimports=[],
             hookspath=[], runtime_hooks=[], excludes=EXCLUDE, cipher=block_cipher, noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ChequePrinter', debug=False, strip=False, upx=False,
          console=False, icon='assets/icon.ico', version=None)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name='ChequePrinter')
