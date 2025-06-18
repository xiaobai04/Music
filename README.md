# 人声分离音乐播放器

本项目提供一个简单的图形界面音乐播放器，能够在播放前使用 Demucs 模型将音频中的人声与伴奏分离，并通过 Tkinter 界面进行播放与控制。

## 新特性

- 支持选择任意麦克风输入设备，可调节音量并在需要时启用/关闭混音，实现简单的卡拉OK 效果。
- 支持选择输出声卡或耳机设备，自动匹配采样率，减少启动错误并降低延迟。
- 优化音频延迟，提升实时演唱体验。
- 在 Windows 平台上自动优先选择 WASAPI 音频接口，以获得更低的输入延迟。
- 播放时可实时切换麦克风或输出设备，兼容 Windows 和 macOS。
- 默认窗口尺寸更大，文件列表和歌词框会随窗口大小自动调整，搜索框可按 **Enter** 键触发搜索。
- 可分别调节人声和伴奏音量，调节值会保存在配置文件中。
## 安装

1. 建议在虚拟环境中安装依赖。
2. 执行下列命令安装所需库：

```bash
pip install -r requirements.txt
```

### 额外依赖

本项目需要系统中安装 [FFmpeg](https://ffmpeg.org/)。大多数 Linux 发行版可直接
通过软件包管理器安装，Windows 用户可从官方网站下载并将可执行文件加入 `PATH` 环
境变量。

如果打算使用 **GPU** 进行人声分离，请确保安装的 PyTorch 版本已编译并启用了 CUDA。
可访问 [PyTorch 官网](https://pytorch.org/) 根据个人显卡与 CUDA 版本选择合适的安
装命令。若未安装带 CUDA 的 PyTorch，在界面中选择 `cuda` 将会出现 `torch not compiled
with cuda enabled` 错误。此时请改用 `cpu` 运行或重新安装带 CUDA 的 PyTorch。

若导出音频时收到 `AttributeError: 'NoneType' object has no attribute 'write'`，通常是因为 `torchaudio` 缺少编码器支持。本仓库已在 `requirements.txt` 中包含 `soundfile`，或者可使用官方提供的完整 `torchaudio` 轮子解决该问题。

## 使用

在仓库根目录直接运行：

```bash
python main.py
```

程序会在当前目录生成 `user_settings.json` 保存播放模式以及最近打开的音乐文件夹等设置。重新启动时会自动加载该文件夹。

## 打包

若需要生成独立的可执行文件，可使用 [PyInstaller](https://pyinstaller.org/)：

```bash
pip install pyinstaller
pyinstaller --onefile --add-data "user_settings.json:." main.py
```

生成的文件位于 `dist/` 目录。`--add-data` 选项可确保 `user_settings.json` 与可执行文件位于同一目录，便于保存用户偏好。


