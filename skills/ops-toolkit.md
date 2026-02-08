# 运维技能集

## 概述
一套自动化运维工具，用于监控任务状态、保护配置安全、探测网站状态、分析日志和管理代理。

## 工具列表

### 1. 任务监控告警 (task_monitor.py)
监控所有定时任务执行状态，失败时立即告警。

```bash
# 查看所有任务状态
python3 scripts/task_monitor.py

# 生成报告并发送 Telegram
python3 scripts/task_monitor.py --report

# 只在失败时告警
python3 scripts/task_monitor.py --alert

# 输出 JSON
python3 scripts/task_monitor.py --json
```

**监控的任务：**
- pvew5 回帖（皮特节点）
- xsijishe 签到（皮特节点）
- 每日简报（本地）

---

### 2. 配置安全检查器 (config_guard.py)
修改配置前自动验证，防止配置错误导致服务崩溃。

```bash
# 备份当前配置
python3 scripts/config_guard.py backup

# 恢复最新备份
python3 scripts/config_guard.py restore

# 检查当前配置
python3 scripts/config_guard.py check

# 安全应用新配置（自动备份+验证+回滚）
python3 scripts/config_guard.py apply /path/to/new_config.json

# 列出所有备份
python3 scripts/config_guard.py list
```

**安全机制：**
- 自动验证 JSON 格式
- 检查已知危险字段
- 修改前自动备份
- 失败时自动回滚
- 运行 doctor 检查

---

### 3. 网站状态探测 (site_probe.py)
检测目标网站可访问性和限制情况。

```bash
# 检测所有站点
python3 scripts/site_probe.py

# 输出 JSON
python3 scripts/site_probe.py --json

# 检测单个站点
python3 scripts/site_probe.py --site pvew5

# 获取建议等待时间
python3 scripts/site_probe.py --suggest pvew5
```

**检测内容：**
- 网站是否可访问
- 响应时间
- 是否被封禁 (403/关键词检测)
- 自适应建议等待时间

---

### 4. 日志聚合分析 (log_analyzer.py)
收集各任务日志，识别异常模式。

```bash
# 分析过去24小时日志
python3 scripts/log_analyzer.py

# 输出 JSON
python3 scripts/log_analyzer.py --json

# 分析过去48小时
python3 scripts/log_analyzer.py --hours 48
```

**分析内容：**
- 错误统计
- 警告统计
- 成功统计
- 运行次数
- 异常模式识别

---

### 5. 代理/IP 轮换 (proxy_rotator.py)
管理代理池，遇到限制时自动切换。

```bash
# 查看状态
python3 scripts/proxy_rotator.py status

# 列出所有代理
python3 scripts/proxy_rotator.py list

# 添加代理
python3 scripts/proxy_rotator.py add http://127.0.0.1:7890
python3 scripts/proxy_rotator.py add socks5://user:pass@host:port

# 移除代理
python3 scripts/proxy_rotator.py remove http://127.0.0.1:7890

# 轮换代理
python3 scripts/proxy_rotator.py rotate

# 检测所有代理可用性
python3 scripts/proxy_rotator.py check

# 获取当前代理
python3 scripts/proxy_rotator.py current
```

**功能：**
- 代理池管理
- 自动轮换
- 可用性检测
- 失败标记和恢复

---

## 建议的定时任务

```
# 每天早上检查任务状态
0 9 * * * python3 /root/.openclaw/workspace/scripts/task_monitor.py --report

# 每天备份配置
0 0 * * * python3 /root/.openclaw/workspace/scripts/config_guard.py backup

# 每6小时探测网站状态
0 */6 * * * python3 /root/.openclaw/workspace/scripts/site_probe.py --json > /tmp/site_status.json
```

---

## 配置文件位置

- 代理配置: `~/.openclaw/workspace/config/proxies.json`
- 配置备份: `~/.openclaw/config_backups/`
- 网站状态缓存: `/tmp/site_status_cache.json`

---

*创建时间：2026-02-08*
*作者：小鸡 (OpenClaw Agent)*
