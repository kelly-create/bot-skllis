# 技能：Gmail 邮件客户端

## 概述
通过 IMAP/SMTP 协议访问 Gmail，支持读取、发送、搜索邮件等功能。
**独立脚本，不修改 Gateway 配置，避免重启问题。**

## 配置信息

- **邮箱账号**: zbobo9001@gmail.com
- **认证方式**: 应用专用密码（16位）
- **协议**: IMAP (读取) + SMTP (发送)
- **服务器**: imap.gmail.com / smtp.gmail.com

## 功能列表

| 功能 | 命令 | 说明 |
|------|------|------|
| **查看收件箱** | `inbox [count] [--unread]` | 获取最新邮件 |
| **读取邮件** | `read <email_id>` | 读取完整邮件内容 |
| **搜索邮件** | `search <query> [count]` | 按主题/发件人搜索 |
| **发送邮件** | `send <to> <subject> <body>` | 发送邮件 |
| **未读数量** | `unread` | 查看未读邮件数 |
| **文件夹列表** | `folders` | 列出所有文件夹 |
| **标记已读** | `mark-read <email_id>` | 标记为已读 |
| **标记未读** | `mark-unread <email_id>` | 标记为未读 |

## 使用方法

### 基本命令

```bash
# 查看收件箱（最新5封）
python3 /root/.openclaw/workspace/scripts/gmail_client.py inbox 5

# 只看未读邮件
python3 /root/.openclaw/workspace/scripts/gmail_client.py inbox 10 --unread

# 查看未读邮件数量
python3 /root/.openclaw/workspace/scripts/gmail_client.py unread

# 读取指定邮件
python3 /root/.openclaw/workspace/scripts/gmail_client.py read 61

# 搜索邮件
python3 /root/.openclaw/workspace/scripts/gmail_client.py search "Google" 10

# 发送邮件
python3 /root/.openclaw/workspace/scripts/gmail_client.py send "收件人@example.com" "主题" "正文内容"

# 标记已读
python3 /root/.openclaw/workspace/scripts/gmail_client.py mark-read 61

# 列出文件夹
python3 /root/.openclaw/workspace/scripts/gmail_client.py folders
```

### 在 OpenClaw 中调用

```python
# 小鸡可以这样调用
result = exec(
    command="python3 /root/.openclaw/workspace/scripts/gmail_client.py inbox 5"
)
```

## 输出格式

### 收件箱 (inbox)

```json
{
  "emails": [
    {
      "id": "61",
      "subject": "您的家人群组有一位新成员",
      "from": "Google <families-noreply@google.com>",
      "to": "zbobo9001@gmail.com",
      "date": "Sat, 07 Feb 2026 04:48:14 -0800",
      "preview": "已接受家人群组邀请...",
      "body_length": 355
    }
  ],
  "unread_only": false
}
```

### 读取邮件 (read)

```json
{
  "id": "61",
  "subject": "测试邮件",
  "from": "sender@example.com",
  "to": "zbobo9001@gmail.com",
  "date": "Sat, 07 Feb 2026 04:48:14 -0800",
  "body": "完整邮件正文内容..."
}
```

### 发送邮件 (send)

```json
{
  "success": true,
  "message": "邮件已发送至 xxx@example.com",
  "subject": "主题",
  "timestamp": "2026-02-07T13:24:47.598036"
}
```

### 未读数量 (unread)

```json
{
  "unread_count": 49
}
```

## 测试结果

| 测试项 | 结果 | 备注 |
|--------|------|------|
| **IMAP 连接** | ✅ 成功 | 使用 SSL 端口 993 |
| **SMTP 连接** | ✅ 成功 | 使用 TLS 端口 587 |
| **读取收件箱** | ✅ 成功 | 49 封未读邮件 |
| **发送邮件** | ✅ 成功 | 已发送测试邮件 |
| **中文支持** | ✅ 成功 | 正确解码中文标题和正文 |

## 安全说明

1. **应用专用密码**：不是账号主密码，可以随时在 Google 账号中撤销
2. **脚本存储**：密码保存在脚本中，请勿公开分享
3. **权限限制**：应用专用密码只能访问邮件，无法更改账号设置

## 与 Pub/Sub 方案对比

| 特性 | 本方案 (IMAP/SMTP) | Pub/Sub 方案 |
|------|-------------------|--------------|
| **配置复杂度** | ⭐ 简单 | ⭐⭐⭐⭐⭐ 复杂 |
| **实时推送** | ❌ 需轮询 | ✅ 实时 |
| **外部依赖** | ❌ 无 | gcloud, gog, Tailscale |
| **Gateway 影响** | ❌ 无 | 可能导致重启 |
| **可靠性** | ⭐⭐⭐⭐ 高 | ⭐⭐⭐ 中等 |
| **成本** | 免费 | GCP 可能收费 |

## 未来扩展

- [ ] 添加定时检查新邮件（cron job）
- [ ] 支持附件上传/下载
- [ ] 邮件分类和过滤
- [ ] 自动回复规则
- [ ] 集成到 OpenClaw 消息通知

---

*创建时间：2026-02-07*
*作者：小鸡 (OpenClaw Agent)*
*教训：不修改 Gateway 配置，避免重启循环问题*
