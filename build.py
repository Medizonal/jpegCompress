import PyInstaller.__main__

PyInstaller.__main__.run([
    'app/main.py',
    '--onedir',
    '--noconsole',
    '--name=holycompress',
    '--distpath=dist',
    '--workpath=build',
    '--clean',
])
