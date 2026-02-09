# OpenClaw 永久记忆系统配置建议

## 问题诊断

当前OpenClaw的记忆系统存在以下问题：

1. **`memory_search` 工具失效**
   - 原因：需要OpenAI embeddings API
   - 当前配置：仅有sydney-proxy（无embeddings支持）
   - 影响：无法语义搜索历史记忆

2. **压缩后记忆丢失**
   - 原因：压缩后的summary不完整
   - 影响：压缩后"失忆"，忘记之前的配置和决策

3. **缺少自动记忆回顾**
   - 原因：没有机制提示AI读取记忆文件
   - 影响：即使记忆文件存在，AI也不知道去读

## 解决方案

### 方案1：使用CORE-MEMORY.md作为永久参考 ⭐ 推荐

**已实现**：
- 创建 `/root/.openclaw/workspace/CORE-MEMORY.md`
- 包含所有关键信息：凭证、节点、任务、教训
- 压缩后必读此文件

**建议在 System Prompt 中添加**：
```
每次对话开始时（特别是压缩后），必须先读取：
1. /root/.openclaw/workspace/CORE-MEMORY.md（核心记忆）
2. /root/.openclaw/workspace/memory/最近2天.md（近期工作）
3. /root/.openclaw/workspace/CRITICAL-CONFIG-RULES.md（配置规则）

使用 grep 替代 memory_search 进行记忆搜索。
```

### 方案2：配置Embeddings API（彻底解决）

如果您有OpenAI API key或其他embeddings服务，可以配置：

```json
{
  "models": {
    "providers": {
      "openai": {
        "apiKey": "sk-...",
        "models": [...]
      }
    }
  }
}
```

这样 `memory_search` 工具就能正常工作。

### 方案3：定时记忆回顾任务

创建定时任务，每天自动：
1. 总结昨天的工作
2. 更新CORE-MEMORY.md
3. 标记重要决策

## 配置步骤

### 立即可用的改进（无需修改配置）

1. **压缩后自动读取CORE-MEMORY.md**
   - 在每次对话开始时读取此文件
   - 包含所有关键信息

2. **使用grep替代memory_search**
   ```bash
   grep -r "关键词" /root/.openclaw/workspace/memory/
   grep -r "关键词" /root/.openclaw/workspace/credentials/
   ```

3. **保持记忆文件更新**
   - 每日记忆：`memory/YYYY-MM-DD.md`
   - 核心记忆：`CORE-MEMORY.md`
   - 定期同步到GitHub

### 长期改进（需要配置）

1. **添加Embeddings Provider**
   - 选项1：OpenAI API
   - 选项2：本地embeddings服务
   - 选项3：使用sydney-proxy添加embeddings端点

2. **优化压缩策略**
   - 当前：`compaction.mode = "safeguard"`
   - 可能需要调整压缩阈值

3. **自动化记忆管理**
   - 定时任务自动总结
   - 重要事项自动标记
   - 定期记忆复习

## 测试验证

### 测试记忆系统

```bash
# 1. 读取核心记忆
cat /root/.openclaw/workspace/CORE-MEMORY.md

# 2. 搜索历史记忆
grep -r "pvew5" /root/.openclaw/workspace/memory/

# 3. 查看所有记忆文件
ls -lh /root/.openclaw/workspace/memory/
```

### 模拟压缩后场景

压缩后应该：
1. ✅ 立即读取 CORE-MEMORY.md
2. ✅ 读取最近的 memory/*.md
3. ✅ 使用 grep 搜索关键信息
4. ✅ 知道所有节点的SSH凭证
5. ✅ 知道定时任务配置
6. ✅ 记得配置修改的教训

## 文件结构

```
/root/.openclaw/workspace/
├── CORE-MEMORY.md              ⭐ 核心记忆（压缩后必读）
├── MEMORY.md                   📖 记忆系统说明
├── CRITICAL-CONFIG-RULES.md    ⚠️ 配置安全规则
├── credentials/                🔐 凭证目录
│   ├── nodes.md               # 三节点详细信息
│   ├── servers.md             # 服务器配置
│   └── SECURITY.md            # Fail2Ban等安全配置
├── memory/                     📅 每日记忆
│   ├── 2026-02-07.md
│   ├── 2026-02-08.md
│   └── 2026-02-09.md
└── scripts/                    🔧 工具脚本
```

## 建议的System Prompt修改

在Agent的System Prompt中添加：

```markdown
## 记忆系统

你拥有永久记忆系统，记忆存储在文件中：

### 核心记忆（每次必读）
- `/root/.openclaw/workspace/CORE-MEMORY.md` - 关键信息汇总

### 每日记忆
- `/root/.openclaw/workspace/memory/YYYY-MM-DD.md` - 每日工作记录

### 搜索记忆
由于 memory_search 工具不可用，使用 grep：
```bash
grep -r "关键词" /root/.openclaw/workspace/memory/
```

### 压缩后恢复步骤
1. 读取 CORE-MEMORY.md
2. 读取最近2天的记忆文件
3. 读取 credentials/nodes.md
4. 继续对话
```

---

*文档创建于: 2026-02-09*
*作者: OpenClaw小鸡*
