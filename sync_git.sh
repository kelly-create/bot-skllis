#!/bin/bash
cd /root/.openclaw/workspace
git pull origin main --rebase || true
git add .
git commit -m "Daily sync: $(date -u)" || exit 0
git push origin main
