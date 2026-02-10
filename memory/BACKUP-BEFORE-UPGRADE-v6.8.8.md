# 🔐 升级前记忆备份 - 2026-02-10 02:32 UTC

## 📋 升级信息
- **升级时间**: 2026-02-10 02:32:38 UTC
- **当前版本**: CLIProxyAPI v6.8.5
- **目标版本**: CLIProxyAPI v6.8.8
- **升级原因**: 用户要求升级到最新版本
- **风险评估**: 中等（#1433未修复，但有新功能和bug修复）

---

## 🗂️ 关键配置备份

### 1. OpenClaw配置
**路径**: `/root/.openclaw/openclaw.json`
**最后修改**: 2026-02-10T02:17:07.066Z

**关键设置**:
```json
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "sydney-proxy/gemini-claude-opus-4-6-thinking"
      },
      "compaction": {
        "mode": "safeguard"
      }
    }
  },
  "models": {
    "providers": {
      "sydney-proxy": {
        "baseUrl": "https://xiaoji.caopi.de/v1",
        "apiKey": "sk-openclaw-hk-link",
        "api": "openai-responses"
      }
    }
  },
  "gateway": {
    "port": 18789,
    "auth": {
      "token": "eff2afc5a93c9784072bcab7e655249d3bb09292850f1309"
    }
  }
}
```

### 2. 可用模型列表
- ✅ gemini-claude-opus-4-6-thinking (1M context) - **默认**
- ✅ gemini-claude-opus-4-5-thinking (200k context)
- ✅ gemini-claude-sonnet-4-5-thinking (200k context)
- ✅ gemini-claude-sonnet-4-5 (200k context)
- ✅ gemini-3-pro-preview (200k context)
- ✅ gpt-5.2-codex (subagent默认)

### 3. CLIProxyAPI配置（萝卜节点）
**路径**: `/root/cliproxyapi/`
**版本**: v6.8.5 (Commit: 3b34521)
**构建时间**: 2026-02-08T12:39:42Z
**服务器**: 152.53.171.21 (萝卜)

---

## 🤖 自动化任务配置

### Cron任务列表
| 任务ID | 名称 | 执行时间 | 节点 | 通知 |
|-------|------|---------|------|------|
| ba979e82... | X每日任务-美国晚上 | 04:00 UTC | 萝卜 | ✅ |
| 0cdb154f... | X每日任务-美国中午 | 20:00 UTC | 萝卜 | ✅ |
| 68082ed4... | xsijishe签到 | 00:00 Beijing | 皮特 | ✅ |
| 250e3e72... | pvew5回帖任务 | 01:00 Beijing | 皮特 | ✅ |
| 9fbda3f9... | 每日全球热点简报 | 09:00 Beijing | 本地 | ✅ |
| 6dceb8e2... | Daily Git Sync | 00:00 UTC | 本地 | ✅ |

### X自动化配置
**脚本位置**: 
- 萝卜节点: `/root/x_daily.py`
- Cookies: `/root/x_cookies.json`
- 安全规则: `/root/.openclaw/workspace/credentials/x_account/SAFETY-RULES.md` (v2.2)

**X账号**: @zuzonren (Zelda Rosaleen)
**状态**: 已恢复，可正常使用

---

## 📁 重要文件路径

### 配置文件
- `/root/.openclaw/openclaw.json` - OpenClaw主配置
- `/root/.openclaw/workspace/MEMORY.md` - 主记忆文件
- `/root/.openclaw/workspace/memory/2026-02-10.md` - 今日记忆
- `/root/.openclaw/workspace/CRITICAL-OUTPUT-CONTROL.md` - 输出控制规则
- `/root/.openclaw/workspace/CRITICAL-CONFIG-RULES.md` - 配置修改规则

### 脚本文件
- `/root/.openclaw/workspace/scripts/x_daily.py` - X自动化脚本（本地）
- `/root/x_daily.py` - X自动化脚本（萝卜节点）
- `/root/.openclaw/workspace/scripts/daily_report_wrapper.py` - 新闻简报包装器
- `/root/.openclaw/workspace/xsijishe_signin.py` - 论坛签到
- `/root/.openclaw/workspace/pvew5_login.py` - 回帖任务

### 凭证文件
- `/root/.openclaw/workspace/credentials/x_account/x_cookies.json` - X Cookies（本地）
- `/root/x_cookies.json` - X Cookies（萝卜节点）
- `/root/.openclaw/workspace/credentials/xsijishe/cookies.json` - 论坛cookies
- `/root/.openclaw/workspace/credentials/pvew5/cookies.json` - pvew5 cookies

---

## 🌐 节点信息

### 萝卜节点（主要）
- IP: 152.53.171.21
- 架构: ARM64
- 内存: 8GB
- 密码: H3Fwyq2fTJ7TjRn
- 用途: CLIProxyAPI、X自动化

### 皮特节点
- 位置: 香港
- 用途: xsijishe签到、pvew5任务

### 悉尼节点
- IP: 206.168.133.84
- 用途: 备用

---

## 🔑 关键决策记录

### 1. 输出大小控制（方案2）
**日期**: 2026-02-09
**原因**: 防止session累积过大触发280KB限制
**规则**: 
- read必须加limit
- 日志用grep+tail
- 单次输出≤2000字符

### 2. 模型选择
**当前**: gemini-claude-opus-4-6-thinking
**上下文**: 1M tokens
**切换时间**: 2026-02-10 02:22 UTC
**原因**: 5倍上下文提升，减少压缩需求

### 3. 不升级CLIProxyAPI决策（已撤回）
**原始决策**: 等待#1433修复
**撤回时间**: 2026-02-10 02:32 UTC
**新决策**: 立即升级到v6.8.8

---

## ⚠️ 已知问题

### #1433 - 280KB请求截断
- **状态**: Open（未修复）
- **影响**: 大请求会被截断导致400错误
- **规避**: 控制输出大小 + 使用1M上下文模型
- **预期**: 升级后仍存在

### 其他问题
- ✅ X账号限制已解除
- ✅ 所有cron任务配置正确
- ✅ Telegram通知正常

---

## 📊 当前Session状态

**Session Key**: agent:main:main
**Model**: gemini-claude-sonnet-4-5-thinking (即将切换回opus-4-6)
**Context Window**: 200k tokens (配置为1M)
**Total Tokens**: ~32k tokens
**Messages**: ~15条

---

## 🎯 升级检查清单

升级前验证：
- [ ] 备份当前CLIProxyAPI配置
- [ ] 记录当前运行状态
- [ ] 确认萝卜节点连接正常
- [ ] 备份cookies和凭证

升级步骤：
- [ ] 停止CLIProxyAPI服务
- [ ] 下载v6.8.8二进制文件
- [ ] 替换旧版本
- [ ] 重启服务
- [ ] 验证功能

升级后验证：
- [ ] 检查版本号
- [ ] 测试API调用
- [ ] 验证OpenClaw连接
- [ ] 测试cron任务
- [ ] 确认X自动化可用

回滚方案：
- [ ] 保留v6.8.5备份
- [ ] 如失败立即回滚

---

## 📝 v6.8.8 新特性

### v6.8.8 (2026-02-09 18:13)
- fix(amp): 修复SSE响应中的模型名称重写
- Responses API SSE事件的模型映射修复

### v6.8.7 (2026-02-09 12:03)
- feat(executor): 添加iFlow API请求支持
- fix(management): 改进管理界面资源同步

### v6.8.6 (2026-02-08 18:10)
- 无详细日志

---

## 💾 GitHub同步状态

**最后提交**: a95a740
**提交信息**: "记录2026-02-10: X任务状态、项目对比、版本决策、新增opus-4-6模型"
**提交时间**: 2026-02-10 02:20 UTC
**状态**: ✅ 已同步到远程

---

## 🔐 安全信息

### API密钥
- OpenClaw Gateway Token: eff2afc5a93c9784072bcab7e655249d3bb09292850f1309
- Sydney Proxy API Key: sk-openclaw-hk-link
- Brave Search API: BSAE-ShJ1YElUxKC_QmZKqvNaMoFc9I
- Webhook Token: sk_wh_fix_8d7a9c2b3e4f5a6b7c8d9e0f

### 账号信息
- Telegram Bot: 8596711036:AAG1SF19xwf0xUgp1fq8nOuhLMJ9xVGcnu8
- Gmail: zbobo9001@gmail.com
- X Account: @zuzonren

---

## 📌 恢复指南

如果升级后出现问题：

### 1. CLIProxyAPI回滚
```bash
cd /root/cliproxyapi
systemctl stop cliproxyapi
mv cli-proxy-api cli-proxy-api.v6.8.8.backup
mv cli-proxy-api.v6.8.5.backup cli-proxy-api
systemctl start cliproxyapi
```

### 2. OpenClaw配置恢复
```bash
cp /root/.openclaw/openclaw.json.backup /root/.openclaw/openclaw.json
openclaw gateway restart
```

### 3. 验证恢复
```bash
# 检查版本
/root/cliproxyapi/cli-proxy-api -version

# 测试连接
curl http://localhost:18789/status
```

---

## ✅ 备份完成确认

- ✅ 所有关键配置已记录
- ✅ 文件路径已备份
- ✅ 凭证信息已保存
- ✅ Cron任务已列出
- ✅ 节点信息已记录
- ✅ 回滚方案已准备
- ✅ GitHub已同步

**准备就绪，可以开始升级！** 🚀

---

*备份时间: 2026-02-10 02:32:38 UTC*
*备份文件: /root/.openclaw/workspace/memory/BACKUP-BEFORE-UPGRADE-v6.8.8.md*
