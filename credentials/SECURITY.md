# 🛡️ 安全配置文档

> 三节点安全防护配置说明

## 📊 防护概览

| 服务器 | Fail2Ban | SSH防护 | Web防护 | Git扫描防护 | 状态 |
|--------|----------|---------|---------|-------------|------|
| **萝卜** 🇺🇸 | ✅ 已启用 | ✅ 已启用 | ✅ 已启用 | ✅ 已启用 | 🟢 运行中 |
| **皮特** 🇭🇰 | ✅ 已启用 | ✅ 已启用 | N/A | N/A | 🟢 运行中 |
| **悉尼** 🇦🇺 | ✅ 已启用 | ✅ 已启用 | N/A | N/A | 🟢 运行中 |

---

## 🇺🇸 萝卜节点 (152.53.171.21)

### Fail2Ban 配置
- **版本**: 1.0.2
- **状态**: Active (运行中)
- **配置文件**: `/etc/fail2ban/jail.local`

### 保护规则

#### 1. SSH 防护
```ini
[sshd]
enabled = true
maxretry = 5
bantime = 3600    # 1小时
findtime = 600    # 10分钟窗口
```

#### 2. Nginx HTTP 认证防护
```ini
[nginx-http-auth]
enabled = true
logpath = /var/log/nginx/error.log
```

#### 3. Git 扫描器防护 🔴 重点
```ini
[nginx-git-scanner]
enabled = true
maxretry = 1       # 一次即封
bantime = 86400    # 24小时
filter = nginx-git-scanner
```
**过滤规则**: 检测对 `.git` 目录的任何访问尝试

#### 4. Nginx 安全配置
位置: `/etc/nginx/sites-available/xiaoji.caopi.de.conf`

```nginx
# 禁止访问 .git 目录
location ~ /\.git {
    deny all;
    return 404;
}

# 禁止访问隐藏文件
location ~ /\. {
    deny all;
    return 404;
}

# 禁止访问敏感文件
location ~* \.(env|sql|config|bak|backup|swp|old)$ {
    deny all;
    return 404;
}
```

### 当前保护监狱
```bash
# 查看状态
fail2ban-client status

输出:
|- Number of jail: 3
`- Jail list: nginx-git-scanner, nginx-http-auth, sshd
```

### 日志位置
- **Fail2Ban**: `/var/log/fail2ban.log`
- **Nginx访问**: `/var/log/nginx/access.log`
- **Nginx错误**: `/var/log/nginx/error.log`

---

## 🇭🇰 皮特节点 (83.229.126.21)

### Fail2Ban 配置
- **版本**: 0.11.2
- **状态**: Active (运行中)
- **配置文件**: `/etc/fail2ban/jail.local`

### 保护规则

#### SSH 防护（加强版）
```ini
[sshd]
enabled = true
maxretry = 3       # 更严格：3次失败即封
bantime = 3600
findtime = 600
```

### 当前保护监狱
```bash
# 查看状态
fail2ban-client status

输出:
|- Number of jail: 1
`- Jail list: sshd
```

**说明**: 皮特节点不对外提供Web服务，仅需SSH防护

---

## 🇦🇺 悉尼节点 (206.168.133.84)

### Fail2Ban 配置
- **版本**: 0.11.2
- **状态**: Active (运行中)
- **配置文件**: `/etc/fail2ban/jail.local`

### 保护规则

#### SSH 防护（加强版）
```ini
[sshd]
enabled = true
maxretry = 3       # 更严格：3次失败即封
bantime = 3600
findtime = 600
```

### CLI Proxy API 日志
- **主日志**: `/root/cliproxyapi/logs/main.log`
- **错误日志**: `/root/cliproxyapi/logs/error-*.log`

**说明**: 悉尼运行CLI Proxy API服务，日志文件动态生成，未配置Web扫描防护

---

## 🔧 常用管理命令

### 查看状态
```bash
# 查看Fail2Ban状态
systemctl status fail2ban

# 查看所有监狱
fail2ban-client status

# 查看特定监狱状态
fail2ban-client status sshd
fail2ban-client status nginx-git-scanner
```

### 查看封禁IP
```bash
# 查看SSH监狱的封禁列表
fail2ban-client status sshd

# 查看Git扫描器封禁列表（萝卜）
fail2ban-client status nginx-git-scanner
```

### 手动封禁/解封
```bash
# 封禁IP
fail2ban-client set sshd banip 1.2.3.4

# 解封IP
fail2ban-client set sshd unbanip 1.2.3.4
```

### 重载配置
```bash
# 重启服务
systemctl restart fail2ban

# 重载监狱
fail2ban-client reload
```

---

## 📈 威胁情报

### 近期检测到的扫描

| 时间 | IP | 攻击类型 | 目标 | 处理 |
|------|----|---------|----|------|
| 2026-02-09 05:07 | 185.196.8.135 | Git配置泄露扫描 | `/.git/config` | ✅ 返回404 |
| 2026-02-09 04:24 | 84.254.106.197 | 支付系统扫描 | `/js/twint_ch.js` | ✅ 返回404 |
| 2026-02-09 01:18 | 74.0.42.209 | 代理探测 | CONNECT | ✅ 返回404 |

**结论**: 所有扫描请求均被有效拦截，未发现成功入侵

---

## ⚠️ 安全最佳实践

### 1. 定期检查
```bash
# 每周检查封禁日志
tail -100 /var/log/fail2ban.log

# 每周检查Nginx错误日志
tail -100 /var/log/nginx/error.log
```

### 2. 白名单管理
编辑 `/etc/fail2ban/jail.local`:
```ini
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1 YOUR_TRUSTED_IP
```

### 3. 邮件告警（可选）
```ini
[DEFAULT]
destemail = your-email@example.com
sendername = Fail2Ban
action = %(action_mwl)s
```

### 4. 日志轮转
确保日志不占满磁盘:
```bash
# 检查日志大小
du -sh /var/log/nginx/
du -sh /var/log/fail2ban.log
```

---

## 🔒 防护层次

```
第1层: Nginx配置级别
  ├─ 禁止 .git 目录访问
  ├─ 禁止隐藏文件访问
  └─ 禁止敏感文件扩展名

第2层: Fail2Ban监控
  ├─ Git扫描器检测（1次即封，24小时）
  ├─ SSH暴力破解防护（3-5次失败，1小时）
  └─ Nginx异常请求检测

第3层: 系统防火墙
  └─ iptables/nftables（由Fail2Ban动态管理）
```

---

## 📝 部署记录

| 时间 | 操作 | 执行者 |
|------|------|--------|
| 2026-02-09 01:28 | 安全配置审计 | 主人 |
| 2026-02-09 01:36 | 萝卜节点安装Fail2Ban | 小鸡 |
| 2026-02-09 01:37 | 皮特节点安装Fail2Ban | 小鸡 |
| 2026-02-09 01:30 | 悉尼节点安装Fail2Ban | 小鸡 |
| 2026-02-09 01:36 | 萝卜Nginx安全加固 | 小鸡 |
| 2026-02-09 01:36 | Git扫描器防护部署 | 小鸡 |

---

*最后更新: 2026-02-09 01:40 UTC*
*维护者: OpenClaw 小鸡*
