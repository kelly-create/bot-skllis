# 🧠 永久记忆系统完整指南

> 整合自 PERMANENT-MEMORY-GUIDE.md 和 PERMANENT-MEMORY-SYSTEM.md

---

## 📋 系统架构

OpenClaw的永久记忆基于**文件系统**，包含两个层次：

### 1️⃣ 核心记忆（压缩后必读）
**CORE-MEMORY.md** - 包含所有关键信息的汇总文件
- 位置：`/root/.openclaw/workspace/CORE-MEMORY.md`
- 用途：压缩后第一时间读取，快速恢复记忆
- 内容：凭证、节点、任务、教训、文件位置

### 2️⃣ 详细记忆（按需查阅）
- **每日记忆**：`memory/YYYY-MM-DD.md`
- **凭证信息**：`credentials/*.md`
- **技能文档**：`skills/*.md`
- **配置规则**：`CRITICAL-CONFIG-RULES.md`

---

## 🔄 压缩后恢复记忆流程

### 标准流程（5步法）

```bash
# 1. 读取核心记忆（最重要）
read /root/.openclaw/workspace/CORE-MEMORY.md

# 2. 读取今天的记忆
read /root/.openclaw/workspace/memory/$(date +%Y-%m-%d).md

# 3. 读取昨天的记忆
read /root/.openclaw/workspace/memory/$(date -d yesterday +%Y-%m-%d).md

# 4. 读取节点详细信息
read /root/.openclaw/workspace/credentials/nodes.md

# 5. 搜索特定关键词（如需要）
exec: grep -r "关键词" /root/.openclaw/workspace/memory/
```

### 快速恢复清单

**压缩后立即执行**：
- [ ] 读取 CORE-MEMORY.md
- [ ] 读取最近2天的 memory/*.md
- [ ] 检查定时任务状态：`cron list`
- [ ] 确认没有遗漏的待办事项

---

## 🎯 CORE-MEMORY.md 内容结构

```
CORE-MEMORY.md
├── 我是谁（身份和主人信息）
├── 关键凭证速查（SSH、API、邮箱）
├── 三节点架构（萝卜、皮特、悉尼）
├── 定时任务列表
├── Fail2Ban白名单
├── 最重要的教训（配置修改黄金法则）
├── 文件位置速查
└── 压缩后恢复步骤
```

---

## 🔍 搜索记忆的方法

### 方法1：grep文本搜索（推荐）

```bash
# 搜索所有记忆文件
grep -r "关键词" /root/.openclaw/workspace/memory/

# 搜索凭证信息
grep -r "关键词" /root/.openclaw/workspace/credentials/

# 搜索特定日期
grep "关键词" /root/.openclaw/workspace/memory/2026-02-09.md

# 忽略大小写
grep -ri "关键词" /root/.openclaw/workspace/
```

### 方法2：Embeddings语义搜索（备用）

**当前状态**：embeddings服务已部署在萝卜节点（测试阶段）

- 模型：paraphrase-multilingual-MiniLM-L12-v2
- 端口：8318（localhost）
- 中文支持：优秀

**未来可能启用**：通过memory_search工具进行语义搜索

---

## 📝 记忆文件维护

### 每日记忆文件

**命名规范**：`memory/YYYY-MM-DD.md`

**内容包含**：
- 完成的任务
- 创建/修改的文件
- 关键决策和原因
- 遇到的问题和解决方案
- 重要配置变更
- 待办事项

### CORE-MEMORY.md 更新时机

**何时更新**：
- ✅ 新增服务器/节点
- ✅ 更改关键凭证
- ✅ 新增定时任务
- ✅ 发生重要事故/教训
- ✅ 文件结构变化

**更新后必须**：
```bash
cd /root/.openclaw/workspace
git add CORE-MEMORY.md
git commit -m "🧠 更新核心记忆: [变更说明]"
git push
```

---

## ⚠️ 重要原则

### 黄金法则

1. **压缩后必读CORE-MEMORY.md**
   - 这是最重要的恢复手段
   - 包含所有关键信息汇总

2. **不依赖自动化记忆搜索**
   - `memory_search` 工具需要额外配置
   - grep搜索更可靠、简单

3. **每日更新记忆文件**
   - 重要工作当天记录
   - 不要依赖长期记忆

4. **定期同步到GitHub**
   - 所有记忆文件定期推送
   - 防止本地丢失

---

## 📊 记忆系统对比

| 方案 | 可靠性 | 速度 | 配置复杂度 | 推荐 |
|------|-------|------|-----------|------|
| **CORE-MEMORY.md** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ **主要方案** |
| **grep搜索** | ⭐⭐⭐⭐☆ | ⭐⭐⭐⭐☆ | ⭐⭐⭐⭐⭐ | ✅ 辅助搜索 |
| **memory_search** | ⭐⭐⭐☆☆ | ⭐⭐⭐☆☆ | ⭐⭐☆☆☆ | ⚠️ 备用（未集成） |

---

## 🎯 最佳实践

### 压缩前准备

1. **更新今日记忆**
2. **标记重要信息到CORE-MEMORY.md**
3. **同步到GitHub**

### 压缩后恢复

1. **立即读取CORE-MEMORY.md**
2. **检查最近2-3天的记忆**
3. **确认定时任务状态**
4. **如有疑问，用grep搜索**

---

## 📚 相关文档

- **核心记忆**：`CORE-MEMORY.md`
- **根目录记忆说明**：`MEMORY.md`
- **配置安全规则**：`CRITICAL-CONFIG-RULES.md`
- **Embeddings部署文档**：`docs/EMBEDDINGS-DEPLOYMENT.md`

---

**版本**: v3.0  
**最后更新**: 2026-02-09  
**维护者**: OpenClaw小鸡
