# 🐣 小鸡 OpenClaw 工作空间

> OpenClaw智能助手的配置、记忆和技能库

## 📋 项目简介

这是小鸡（OpenClaw AI助手）的工作空间，包含：
- 🧠 **永久记忆系统** - 防止上下文压缩后失忆
- 🔧 **自动化脚本** - 每日新闻、邮件、监控等
- 📚 **技能文档** - 各项能力的使用说明
- 🔐 **凭证管理** - 服务器和API密钥

## 📁 目录结构

```
bot-skllis/
├── 📁 credentials/     # 凭证和安全配置
│   ├── nodes.md        # 服务器节点信息
│   ├── apis.md         # API密钥
│   ├── SECURITY.md     # 安全配置手册
│   └── ...
│
├── 📁 docs/            # 文档
│   ├── PERMANENT-MEMORY.md  # 永久记忆使用指南
│   ├── EMBEDDINGS-DEPLOYMENT.md
│   └── ...
│
├── 📁 memory/          # 每日记忆存档
│   └── YYYY-MM-DD.md   # 按日期存储
│
├── 📁 scripts/         # 自动化脚本
│   ├── daily_report.py         # 每日新闻简报
│   ├── gmail_client.py         # 邮件发送
│   ├── multi_search.py         # 多源搜索
│   └── ...
│
├── 📁 skills/          # 技能文档
│   ├── daily-report.md         # 每日简报技能
│   ├── gmail-client.md         # 邮件技能
│   └── ...
│
├── 📄 CORE-MEMORY.md   # ⭐ 核心记忆（压缩后必读）
├── 📄 IDENTITY.md      # 身份定义
├── 📄 USER.md          # 主人信息
└── 📄 CRITICAL-CONFIG-RULES.md  # 配置安全规则
```

## 🚀 核心功能

### 永久记忆系统
- **CORE-MEMORY.md** - 压缩后第一时间读取，恢复所有关键信息
- **memory/*.md** - 每日详细记忆存档
- **grep搜索** - 快速查找历史信息

### 自动化任务
| 任务 | 时间（北京） | 说明 |
|------|-------------|------|
| 每日新闻简报 | 09:00 | 全球热点 + 天气预报 |
| pvew5回复 | 09:00 | 帖子自动回复 |
| xsijishe签到 | 08:00 | 网站自动签到 |

### 三节点架构
| 节点 | 位置 | 角色 |
|------|------|------|
| 萝卜 🥕 | 美国 | 主力API代理 + Embeddings |
| 皮特 🇭🇰 | 香港 | 生产任务执行 |
| 悉尼 🇦🇺 | 澳洲 | 备用API代理 |

## 🔐 安全

- ✅ Fail2Ban防护（三节点）
- ✅ Nginx安全规则
- ✅ IP白名单
- ✅ HTTPS域名

## 📝 使用说明

### 压缩后恢复记忆
```bash
# 1. 读取核心记忆
read /root/.openclaw/workspace/CORE-MEMORY.md

# 2. 读取最近记忆
read /root/.openclaw/workspace/memory/$(date +%Y-%m-%d).md

# 3. 搜索特定信息
grep -r "关键词" /root/.openclaw/workspace/memory/
```

### 运行脚本
```bash
# 每日简报
python3 scripts/daily_report.py

# 发送邮件
python3 scripts/gmail_client.py
```

## 📊 维护

- **记忆更新**：每日任务完成后更新memory/*.md
- **核心记忆**：重要变更后更新CORE-MEMORY.md
- **Git同步**：所有变更推送到GitHub

## 🔗 相关链接

- **OpenClaw**: [openclaw.dev](https://openclaw.dev)
- **API代理**: https://xiaoji.caopi.de/v1

---

**维护者**: 小鸡 (OpenClaw AI)  
**主人**: kasha us (@dashuUSA)  
**最后更新**: 2026-02-09
