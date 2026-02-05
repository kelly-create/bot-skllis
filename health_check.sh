#!/bin/bash
# OpenClaw 健康检查脚本

# 检查 Gateway
if ! pgrep -f "openclaw-gateway" > /dev/null; then
    echo "[$(date)] Gateway down, restarting..."
    systemctl --user restart openclaw-gateway
fi

# 检查 socat relay
if ! pgrep -f "socat.*18790" > /dev/null; then
    echo "[$(date)] socat relay down, restarting..."
    systemctl restart openclaw-relay
fi

echo "[$(date)] Health check OK"
