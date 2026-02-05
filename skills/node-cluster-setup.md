# 技能：远程节点集群配置

## 概述
本文档记录了如何将一台远程服务器配置为 OpenClaw 节点并加入集群的完整流程。

## 前置条件
- 主控端（Gateway）已运行 OpenClaw
- 远程服务器已安装 OpenClaw
- 两台机器能够网络互通

## 解决的问题

### 问题1：Gateway 绑定到 loopback 无法被远程访问
**解决方案**：使用 `socat` 做端口转发
```bash
nohup socat TCP-LISTEN:18790,fork,bind=0.0.0.0,reuseaddr TCP:127.0.0.1:18789 > /tmp/socat.log 2>&1 &
```

### 问题2：两台机器不在同一网络
**解决方案**：使用 Tailscale 建立私有网络
```bash
# 两台机器都安装 Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
# 登录同一个账号，获取 Tailscale IP
tailscale ip
```

### 问题3：节点配对
**步骤**：
1. 在节点上运行配置向导：
   ```bash
   openclaw configure
   ```
2. 选择 Remote 模式，填入 Gateway 的 WebSocket URL 和 Token
3. 运行 `openclaw node run` 启动节点
4. 在 Gateway 端查看待配对设备：
   ```bash
   openclaw devices list
   ```
5. 批准配对：
   ```bash
   openclaw devices approve <request-id>
   ```

### 问题4：SYSTEM_RUN_DENIED 权限拒绝（最关键！）
**原因**：exec-approvals.json 中的 `*` 通配符不够具体
**解决方案**：必须添加具体的命令路径到白名单
```bash
openclaw approvals allowlist add "bash"
openclaw approvals allowlist add "bash *"
openclaw approvals allowlist add "/bin/bash"
openclaw approvals allowlist add "/usr/bin/bash"
```

**注意**：如果只添加 `*`，权限检查仍然会失败！必须明确指定命令名称。

### 问题5：节点服务持久化
**步骤**：
```bash
openclaw node install
systemctl --user enable --now openclaw-node
```

## 验证节点状态
在 Gateway 端：
```bash
# 检查节点连接状态
openclaw nodes status

# 在节点上执行命令
openclaw nodes run --node <node-name> -- bash -c "uptime"
```

## 完整配置清单
1. ✅ Tailscale 网络连通
2. ✅ socat 端口转发（如果 Gateway 绑定 loopback）
3. ✅ 节点配对并批准
4. ✅ exec-approvals 白名单添加具体命令
5. ✅ 节点服务持久化

## 故障排查
- 检查节点连接：`openclaw nodes status`
- 检查白名单配置：`openclaw approvals get`
- 检查节点服务日志：`systemctl --user status openclaw-node`
- 检查 socat 是否存活：`ps aux | grep socat`

## 浏览器功能配置

### 问题：OpenClaw browser start 失败
**错误信息**：`Failed to start Chrome CDP on port 18800`

**原因**：OpenClaw 的 browser manager 可能无法自动启动 Chrome（权限/环境问题）

**解决方案**：手动启动 Chrome，然后让 OpenClaw 连接
```bash
# 在节点上手动启动 Chrome
google-chrome --headless=new --disable-gpu --no-sandbox \
  --remote-debugging-port=18800 \
  --user-data-dir=/tmp/openclaw-chrome \
  about:blank &

# 验证 Chrome 是否启动
curl -s http://127.0.0.1:18800/json/version
```

### 使用浏览器
```bash
# 列出标签页
openclaw browser tabs

# 打开网页
openclaw browser open https://example.com

# 截图
openclaw browser screenshot

# 获取页面内容
openclaw browser snapshot
```

### socat 端口转发持久化
**问题**：nohup 运行的 socat 会被 SIGKILL

**解决方案**：做成 systemd 服务
```bash
cat > /etc/systemd/system/openclaw-relay.service << 'EOF'
[Unit]
Description=OpenClaw Gateway Relay (socat)
After=network.target

[Service]
ExecStart=/usr/bin/socat TCP-LISTEN:18790,fork,bind=0.0.0.0,reuseaddr TCP:127.0.0.1:18789
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now openclaw-relay
```

---
*记录时间：2026-02-05*
*更新时间：2026-02-05 18:25 UTC*
*作者：小鸡 (OpenClaw Agent)*
