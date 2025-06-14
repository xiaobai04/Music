from cx_Freeze import setup, Executable
import os

# 设置环境变量（对 matplotlib、tkinter 等库有用）
os.environ['TCL_LIBRARY'] = r'C:\Python310\tcl\tcl8.6'
os.environ['TK_LIBRARY'] = r'C:\Python310\tcl\tk8.6'

build_exe_options = {
    "packages": [
        "os", "sys", "tkinter", "json", "threading", "wave",
        "pyaudio", "numpy", "librosa", "mutagen"
    ],
    "includes": ["audio", "lyrics", "ui", "utils"],
    "include_files": [
        "user_settings.json",
        "requirements.txt",
        "README.md"
    ]
}


setup(
    name="MusicPlayer",
    version="1.0",
    description="一个可以做到让本地flac，MP3文件人声大小可调的软件",
    options={"build_exe": build_exe_options},
    executables=[Executable("main.py", base="Win32GUI", target_name="MusicPlayer.exe")]
)
