import PyInstaller.__main__

PyInstaller.__main__.run([
    'app/divine_orchestrator.py',
    '--onedir',
    '--noconsole',
    '--name=holycompress',
    '--distpath=dist',
    '--workpath=build',
    '--clean',
])
