#!/bin/bash
# Build a standalone executable with PyInstaller
pip install pyinstaller
pyinstaller --onefile --add-data "user_settings.json:." main.py
