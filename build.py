import PyInstaller.__main__

PyInstaller.__main__.run([
    'app/main.py',
    '--onedir',
    '--noconsole',
    '--name=jpegcompress',
    '--distpath=dist',
    '--workpath=build',
    '--clean',
])
