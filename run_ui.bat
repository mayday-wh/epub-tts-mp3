@echo off
set UV_CACHE_DIR=%~dp0.uv-cache
set UV_PYTHON_INSTALL_DIR=%~dp0.uv-python
cd /d "%~dp0"
uv run --managed-python epub_tts_ui.py
