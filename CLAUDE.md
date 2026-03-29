# ShopGuard

AI-powered shoplifting detection MVP for Nepali retail stores.

## Stack
- Python, OpenCV, YOLOv8 (ultralytics), python-telegram-bot
- Camera: iPhone via iVCam (index 0)
- Alerts: Telegram message + beep sound + video clip save

## Rules
- MVP only, no overengineering
- Use proper logging (no print statements)
- Type hints throughout

## Structure
- shopguard/ — main package (config, log, camera, detector, display, main)
- config.yaml — default configuration
- capture.py — legacy standalone script (Phase 0)
- .env — Telegram bot token and chat ID

## Running
- `python -m shopguard` or `python shopguard/main.py`
- `python -m shopguard --config path/to/config.yaml`
