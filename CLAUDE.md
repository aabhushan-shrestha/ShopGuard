# ShopGuard

AI-powered shoplifting detection MVP for Nepali retail stores.

## Stack
- Python, OpenCV, YOLOv8 (ultralytics), python-telegram-bot
- Camera: iPhone via iVCam (index 0)
- Alerts: Telegram message + beep sound + video clip save

## Rules
- Keep all code simple, flat scripts, no classes
- Always end with: git add . && git commit -m "..." && git push
- MVP only, no overengineering

## Files
- capture.py — main detection script
- config.yaml — zone coordinates and thresholds
- .env — Telegram bot token and chat ID
