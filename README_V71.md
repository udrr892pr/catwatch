# CatWatch v7.1 — Source Priority Engine

This update widens app coverage while keeping Telegram strict and quiet.

Files to upload/replace:
- app.py
- requirements.txt
- .streamlit/config.toml

Main changes:
- Adds JMA Japan earthquake feed coverage.
- Adds EMSC earthquake cross-check feed coverage.
- Adds regional source-priority scoring.
- Adds insurance relevance scoring.
- Adds separate Executive Alerts and Recent Global Events queues.
- Adds Sources tab showing the current source hierarchy.

Telegram is not changed by this package. Keep the fixed alert_checker.py already uploaded.
