# 人声分离音乐播放器

本项目提供一个简单的图形界面音乐播放器，能够在播放前使用 Demucs 模型将音频中的人声与伴奏分离，并通过 Tkinter 界面进行播放与控制。

## 安装

1. 建议在虚拟环境中安装依赖。
2. 执行下列命令安装所需库：

```bash
pip install -r requirements.txt
```

## 使用

在仓库根目录直接运行：

```bash
python main.py
```

程序会在当前目录生成 `user_settings.json` 保存播放模式等用户设置。

## 打包

若需要生成独立的可执行文件，可使用 [PyInstaller](https://pyinstaller.org/)：

```bash
pip install pyinstaller
pyinstaller --onefile --add-data "user_settings.json:." main.py
```

生成的文件位于 `dist/` 目录。`--add-data` 选项可确保 `user_settings.json` 与可执行文件位于同一目录，便于保存用户偏好。


