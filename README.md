# Music Player with Vocal Separation

This project is a simple GUI music player that separates vocals from a track using Demucs and plays the result with a Tkinter interface.

## Installation

1. Create a Python environment.
2. Install the required packages:

```bash
pip install -r requirements.txt
```

## Usage

Run the application directly from the repository:

```bash
python main.py
```

## Packaging

To create a standalone executable you can use [PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller
pyinstaller --onefile --add-data "user_settings.json:." main.py
```

The generated binary will be in the `dist/` directory. The `--add-data` option ensures `user_settings.json` is bundled so user preferences are stored next to the executable.