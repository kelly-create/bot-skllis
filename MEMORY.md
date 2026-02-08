# 🧠 小鸡记忆系统

## 快速回忆指南

当上下文被压缩后，我可以通过以下方式快速回忆：

### 1. 搜索记忆
```
memory_search "关键词"
```

### 2. 读取特定日期
```
memory_get path="memory/2026-02-08.md"
```

### 3. 查看所有记忆文件
```
ls memory/
```

### 4. 查看技能文档
```
ls skills/
```

## 记忆结构

```
/root/.openclaw/workspace/
├── MEMORY.md              # 长期规则（必读）
├── CRITICAL-CONFIG-RULES.md  # 配置安全规则（必读）
├── credentials/           # 🔐 凭证信息（必读）
│   ├── nodes.md          # 节点SSH/Tailscale信息
│   ├── apis.md           # API密钥汇总
│   └── owner.md          # 主人信息和偏好
├── memory/               # 每日记忆存档
│   └── YYYY-MM-DD.md
├── skills/               # 技能文档
│   └── *.md
└── scripts/              # 可执行脚本
    └── *.py
```

## ⚠️ 上下文压缩后必读

1. `credentials/owner.md` - 知道主人是谁
2. `credentials/nodes.md` - 节点SSH信息
3. `credentials/apis.md` - API凭证
4. `CRITICAL-CONFIG-RULES.md` - 配置安全
5. 最近的 `memory/*.md` - 近期工作

## 自动备份

脚本 `scripts/context_backup.py` 可以：
- 生成结构化的每日摘要
- 自动推送到 GitHub

使用方法：
```bash
python3 scripts/context_backup.py '{"summary": "今日摘要..."}'
```

## 重要规则提醒

**每次压缩后必读：**
1. `CRITICAL-CONFIG-RULES.md` - 配置安全规则
2. `MEMORY.md` - 用户偏好和教训
3. 最近的 `memory/*.md` - 近期工作内容

## 用户偏好

- **称呼**：AI 叫"小鸡"，用户叫"你"
- **语言**：必须用中文回应
- **完成任务后**：主动汇报，不静默等待
- **配置修改**：先验证，优先用脚本

## 教训记录

### ⚠️ 【最重要】配置文件修改规则

**详见：`CRITICAL-CONFIG-RULES.md`**

> **黄金法则**：没有验证通过或百分百确认，**绝对不得修改 openclaw.json 文件**！

- 修改 openclaw.json 极易导致 Gateway 断连/无限重启
- 必须先查 Schema 确认字段存在
- 用独立脚本能解决的问题，不要改配置
- 必须改配置时，先在**皮特**或**萝卜**上验证
- 出现问题立即汇报，不静默重试

### 2026-02-07 重启事故
- **原因**: 配置 hooks 时添加了无效字段 `hooks.port`
- **后果**: Gateway 无限重启，小鸡完全失联
- **修复**: `openclaw doctor --fix`
- **教训**: 配置验证失败 = 服务崩溃

## 节点分工

```
萝卜(开发) → 皮特(验证) → 小鸡(最终核对)
```

| 节点 | 定位 | 架构 | 说明 |
|------|------|------|------|
| **萝卜** | 🔧 开发 | ARM64 | 新功能/脚本开发 |
| **皮特** | ✅ 验证 | x86_64 | 测试验证、生产任务 |
| **小鸡** | 🎯 核对 | Gateway | 最终审核确认 |

## 定时任务

| 任务 | 时间 | 说明 |
|------|------|------|
| 每日全球热点简报 | 北京时间 09:00 | 发送到 k925138635@gmail.com |
| pvew5 回帖 | 北京时间 09:00 | 皮特节点执行 |
| xsijishe 签到 | 北京时间 08:00 | 皮特节点执行 |

## 凭证位置（已脱敏）

- Gmail: `scripts/gmail_client.py` (zbobo9001@gmail.com)
- 和风天气 API: `scripts/qweather.py`
- 皮特 .env: `/root/.openclaw/workspace/.env`
