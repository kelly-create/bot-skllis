# 🧠 小鸡记忆系统 - 技能文档

## 记忆系统架构

```
/root/.openclaw/workspace/
├── MEMORY.md              # 长期规则（必读）
├── CRITICAL-CONFIG-RULES.md  # 配置安全规则（必读）
├── credentials/           # 🔐 凭证信息（必读）
│   ├── nodes.md          # 节点SSH信息
│   ├── apis.md           # API密钥
│   └── owner.md          # 主人信息
├── memory/               # 📅 每日记录
│   └── YYYY-MM-DD.md
├── conversations/        # 💬 重要对话记录
│   └── YYYY-MM-DD-topic.md
└── skills/               # 📚 技能文档
```

## 启动时必读文件

每次上下文压缩后，立即读取：

```bash
# 1. 核心规则
read MEMORY.md
read CRITICAL-CONFIG-RULES.md

# 2. 凭证信息
read credentials/owner.md
read credentials/nodes.md
read credentials/apis.md

# 3. 最近记忆
read memory/$(date +%Y-%m-%d).md
```

## 记录规则

### 必须记录的信息

1. **凭证类** → `credentials/*.md`
   - SSH账号密码
   - API密钥
   - 任何敏感信息

2. **每日摘要** → `memory/YYYY-MM-DD.md`
   - 完成的任务
   - 创建/修改的文件
   - 遇到的问题
   - 重要决策

3. **重要对话** → `conversations/YYYY-MM-DD-topic.md`
   - 讨论过的需求
   - 用户的明确指示
   - 达成的共识

### 记录时机

- ✅ 收到新凭证时立即保存
- ✅ 完成重要任务后记录
- ✅ 每天结束时总结
- ✅ 上下文即将压缩前

## 搜索方法

### 方法1: grep搜索（推荐）
```bash
grep -r "关键词" /root/.openclaw/workspace/credentials/
grep -r "关键词" /root/.openclaw/workspace/memory/
```

### 方法2: memory_search（API可用时）
```
memory_search "关键词"
```

### 方法3: 直接读取
```
read credentials/nodes.md
```

## 核心原则

1. **不要重复问** - 用户说过的信息必须记录
2. **主动记录** - 不等用户要求
3. **即时保存** - 收到就存，不要拖延
4. **结构清晰** - 便于查找

---

*小鸡是主人的私人助手，所有对话都值得记录*
