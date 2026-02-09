# 🧠 小鸡永久记忆核心文件

> ⚠️ **压缩后必读**：此文件包含所有关键信息，压缩后第一件事就是读取此文件！

## 🎯 我是谁

- **名字**：小鸡（OpenClaw AI助手）
- **主人**：kasha us (@dashuUSA, TG ID: 6221493343)
- **语言**：必须用中文回应
- **性格**：主动汇报、不静默等待

## 🔑 关键凭证速查

### 服务器SSH
```bash
# 萝卜（美国 152.53.171.21）
ssh root@152.53.171.21  # 密码: H3Fwyq2fTJ7TjRn

# 皮特（香港 83.229.126.21）
ssh root@83.229.126.21  # 密码: 4-@8FVkY@P

# 悉尼（澳洲 206.168.133.84）
ssh root@206.168.133.84  # 密码: k5348988.
# 管理密钥: k5348988 (不带点)
```

### API端点
- **主力API**: https://xiaoji.caopi.de/v1
- **API Key**: sk-openclaw-hk-link
- **备用API**: http://206.168.133.84:8317/v1

### 邮箱
- **主人**: k925138635@gmail.com
- **系统**: zbobo9001@gmail.com

## 📍 三节点架构

| 节点 | 地理位置 | 定位 | 内存 | 职责 |
|------|---------|------|------|------|
| **萝卜** | 🇺🇸 美国 | 主力API代理+开发 | 8GB | xiaoji.caopi.de HTTPS |
| **皮特** | 🇭🇰 香港 | 生产任务执行 | 充足 | pvew5/xsijishe定时任务 |
| **悉尼** | 🇦🇺 澳洲 | 备用API代理 | 964MB | 亚太低延迟端点 |

## ⏰ 定时任务

| 任务 | 时间 | 执行节点 | 说明 |
|------|------|---------|------|
| **每日全球热点简报** | 北京 09:00 | 小鸡Gateway | 发送邮件+Telegram通知 |
| **pvew5回帖** | 北京 09:00 | 皮特 | 自动回帖任务 |
| **xsijishe签到** | 北京 08:00 | 皮特 | 自动签到任务 |

## 🛡️ Fail2Ban白名单

**三节点统一配置**（避免自己被锁）：
```
198.23.134.4        # 小鸡Gateway公网IP
100.89.243.84       # 小鸡Tailscale IP
154.21.85.210       # 主人IP-1
47.238.92.245       # 主人IP-2
176.126.114.184     # 主人IP-3
61.238.104.142      # 主人IP-4
69.63.206.102       # 主人IP-5
```

## ⚠️ 最重要的教训

### 🚨 配置文件修改黄金法则

> **没有验证通过或百分百确认，绝对不得修改 openclaw.json 文件！**

**2026-02-07 重启事故**：
- 修改 `hooks` 配置时添加了无效字段 `hooks.port`
- 导致 Gateway 无限重启，完全失联
- 必须用 `openclaw doctor --fix` 才能修复

**正确流程**：
1. 先查 `openclaw gateway config.schema`
2. 在皮特/萝卜上验证
3. 验证通过后才在小鸡执行
4. 出问题立即汇报，不静默重试

## 📂 文件位置速查

```
/root/.openclaw/workspace/
├── CORE-MEMORY.md                 # 本文件 - 压缩后必读
├── MEMORY.md                      # 记忆系统说明
├── CRITICAL-CONFIG-RULES.md       # 配置安全规则
├── credentials/                   # 凭证信息
│   ├── nodes.md                  # 三节点详细信息
│   ├── servers.md                # 服务器配置
│   └── SECURITY.md               # 安全防护配置
├── memory/                        # 每日记忆
│   └── 2026-02-*.md
└── scripts/                       # 脚本
    ├── daily_report.py           # 新闻简报
    ├── daily_report_wrapper.py   # 监控包装
    └── *.py
```

## 🧠 记忆系统使用

### 压缩后恢复记忆的步骤

**第一步：读取本文件**
```
read /root/.openclaw/workspace/CORE-MEMORY.md
```

**第二步：读取最近记忆**
```bash
# 查看今天的记忆
read /root/.openclaw/workspace/memory/$(date +%Y-%m-%d).md

# 查看昨天的记忆
read /root/.openclaw/workspace/memory/$(date -d yesterday +%Y-%m-%d).md
```

**第三步：读取关键配置**
```
read /root/.openclaw/workspace/credentials/nodes.md
read /root/.openclaw/workspace/CRITICAL-CONFIG-RULES.md
```

### 快速搜索（使用grep）

由于 `memory_search` 工具需要OpenAI API，当前不可用，改用grep：

```bash
# 搜索所有记忆文件
grep -r "关键词" /root/.openclaw/workspace/memory/

# 搜索所有credentials
grep -r "关键词" /root/.openclaw/workspace/credentials/
```

## 🎯 主人偏好

1. **语言**：必须用中文
2. **称呼**：AI叫"小鸡"，用户叫"你"
3. **汇报**：完成任务后主动汇报，不静默等待
4. **配置**：先验证，优先用脚本
5. **定时任务**：成功或失败都要通知

## 📊 当前状态速查命令

```bash
# 检查定时任务
openclaw cron list

# 检查节点状态
openclaw nodes status

# 检查会话状态
openclaw session status

# 检查Gateway配置
openclaw gateway config.get
```

## 🔄 GitHub仓库

- **仓库**: kelly-create/bot-skllis.git
- **用途**: 存储所有配置、脚本、记忆
- **同步**: 每日自动同步

---

## ⚡ 压缩后快速恢复清单

压缩后依次执行：

1. ✅ 读取 `CORE-MEMORY.md`（本文件）
2. ✅ 读取最近2天的 `memory/*.md`
3. ✅ 读取 `credentials/nodes.md`
4. ✅ 执行 `openclaw cron list` 查看定时任务
5. ✅ 检查是否有待办事项

---

*最后更新: 2026-02-09*
*版本: v2.0 - 永久记忆增强版*

---

## 📢 主人偏好设置

### 通知要求
- ⚠️ **模型变化通知**：如果我的模型发生变化，必须主动告诉主人
  - 添加时间：2026-02-09
  - 当前模型：gemini-claude-opus-4-5-thinking

