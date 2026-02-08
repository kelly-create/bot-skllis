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
├── MEMORY.md          # 长期重要记忆（规则、教训、偏好）
├── CRITICAL-CONFIG-RULES.md  # 配置安全规则（最重要！）
├── memory/            # 每日记忆存档
│   ├── 2026-02-07.md
│   ├── 2026-02-08.md
│   └── ...
├── skills/            # 技能文档
│   ├── daily-report.md
│   ├── gmail-client.md
│   └── ...
└── scripts/           # 脚本文件
    ├── daily_report.py
    ├── context_backup.py
    └── ...
```

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

## 节点信息

| 节点 | 用途 | 状态 |
|------|------|------|
| **皮特** (cjwgx0ermi5b1pl) | 轻量测试、回帖任务 | x86_64 |
| **萝卜** (ARM-Node-4C6G) | 开发验证 | ARM64 |

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
