# 🎯 输出大小控制规则

> ⚠️ **目的**: 防止session上下文累积过大导致400错误和模型降级

**决策日期**: 2026-02-09  
**触发事件**: session累积139条消息，触发280KB限制，自动从Opus降级到Sonnet

---

## 📏 强制规则

### 1️⃣ 读取文件
```bash
# ❌ 错误 - 不限制大小
read /path/to/large/file.md

# ✅ 正确 - 限制行数
read /path/to/large/file.md --limit 50
read /path/to/large/file.md --offset 1 --limit 30
```

**上限**: 
- 配置文件: ≤100行
- 日志文件: ≤50行
- 记忆文件: ≤100行
- 代码文件: ≤200行

### 2️⃣ 查看日志
```bash
# ❌ 错误 - 读完整日志
cat /var/log/nginx/access.log

# ✅ 正确 - 用grep过滤
tail -100 /var/log/nginx/access.log | grep "关键词" | head -30
grep "error" /var/log/app.log | tail -20
```

### 3️⃣ 查看配置
```bash
# ❌ 错误 - 输出完整配置
openclaw gateway config.get

# ✅ 正确 - 提取关键字段
openclaw gateway config.get | jq '.agents.defaults.compaction'
openclaw gateway config.get | jq '.models.providers'
```

### 4️⃣ 搜索内容
```bash
# ❌ 错误 - 返回所有结果
grep -r "关键词" /path/

# ✅ 正确 - 限制结果数
grep -r "关键词" /path/ | head -20
grep -r "关键词" /path/ 2>/dev/null | head -30
```

### 5️⃣ GitHub/Web内容
```bash
# ❌ 错误 - 获取完整页面
web_fetch url --maxChars 20000

# ✅ 正确 - 限制字符数
web_fetch url --maxChars 5000
web_fetch url --maxChars 3000
```

---

## 🚨 特殊场景例外

**允许大输出的情况**（需要明确必要性）：
1. 用户明确要求查看完整内容
2. 调试关键错误，需要完整堆栈
3. 首次部署/配置时的完整检查

**处理方式**: 
- 先询问用户是否需要完整输出
- 说明会增加上下文压力
- 建议分批查看

---

## 📊 监控指标

**安全阈值**:
- 单次输出: ≤2000字符
- 单个工具调用返回: ≤5000字符
- Session总token: ≤150k (200k上限的75%)

**预警信号**:
- ✅ 当前: 95k tokens (47%) - 安全
- ⚠️ 警告: 150k tokens (75%) - 需要注意
- 🔴 危险: 180k tokens (90%) - 立即压缩

---

## ✅ 执行承诺

从现在开始，小鸡会：
1. ✅ 所有 `read` 命令都加 `limit` 参数
2. ✅ 日志查看优先用 `grep` + `tail`
3. ✅ 配置查看用 `jq` 提取关键部分
4. ✅ Web内容限制在5000字符以内
5. ✅ 每次大输出前问自己：真的需要这么多吗？

---

**最后更新**: 2026-02-09  
**版本**: v1.0  
**状态**: ✅ 激活中
