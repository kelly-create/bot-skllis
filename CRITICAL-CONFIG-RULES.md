# ⚠️ 关键安全规则：配置文件修改

## 🚨 严重警告

**修改 `openclaw.json` 配置文件极其危险！**

一旦配置错误，会导致：
- ❌ Gateway 无限重启循环
- ❌ 小鸡完全断连，无法响应
- ❌ 用户无法与 AI 通信
- ❌ 需要人工干预才能修复

## 📋 强制规则

### 🔴 绝对禁止

1. **未经验证，禁止直接修改 `openclaw.json`**
2. **不确定的配置字段，绝对不要添加**
3. **不要在主 Gateway 上测试配置更改**

### 🟢 正确做法

1. **查看 Schema**：修改前必须运行 `gateway config.schema` 确认字段存在
2. **使用验证服务器**：
   - **皮特** (cjwgx0ermi5b1pl, x86_64) - 轻量测试
   - **萝卜** (ARM-Node-4C6G, ARM64) - 开发验证
3. **独立脚本优先**：能用脚本实现的功能，不要改配置
4. **备份配置**：修改前先备份 `cp openclaw.json openclaw.json.bak`
5. **小步修改**：一次只改一个字段

## 🔧 验证流程

```
┌─────────────────────────────────────────────────────────┐
│  1. 检查 Schema                                         │
│     gateway config.schema | grep "要添加的字段"          │
│                                                         │
│  2. 在皮特或萝卜上测试（如果可能）                         │
│     nodes run --node 皮特 -- openclaw doctor             │
│                                                         │
│  3. 备份配置                                             │
│     cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak │
│                                                         │
│  4. 应用配置                                             │
│     gateway config.patch                                │
│                                                         │
│  5. 验证服务状态                                         │
│     systemctl --user status openclaw-gateway            │
│                                                         │
│  6. 如果失败，立即恢复                                   │
│     cp ~/.openclaw/openclaw.json.bak ~/.openclaw/openclaw.json │
│     openclaw doctor --fix                               │
└─────────────────────────────────────────────────────────┘
```

## 📌 事故案例

### 2026-02-07 重启事故

**原因**：添加 Gmail 配置时，写入了不存在的字段 `hooks.port`

**后果**：
- Gateway 启动失败，错误码 1
- systemd 自动重启，陷入循环
- 重启计数器从 426 增加到 428（20分钟内）
- 小鸡完全失联

**修复**：
```bash
openclaw doctor --fix
```

**教训**：
- 配置验证失败 = 服务崩溃
- 不存在的字段 = 致命错误
- 必须先查 Schema 再修改

## ✅ 安全替代方案

| 需求 | 危险做法 | 安全做法 |
|------|----------|----------|
| 添加 Gmail | 修改 hooks 配置 | 使用独立 Python 脚本 |
| 添加搜索 API | 修改 tools.web 配置 | 使用独立 Python 脚本 |
| 添加天气 API | 修改配置 | 使用独立 Python 脚本 |
| 测试新功能 | 主 Gateway 测试 | 在皮特/萝卜上测试 |

## 🎯 总结

> **黄金法则**：
> 
> 如果不是 100% 确定，**不要碰 openclaw.json**！
> 
> 用脚本能解决的问题，就不要改配置。
> 
> 必须改配置时，先在皮特或萝卜上验证。

---

*创建时间：2026-02-07*
*原因：重启事故教训*
*重要程度：⚠️⚠️⚠️ 最高*
