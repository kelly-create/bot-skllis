# 🔐 节点凭证信息

> ⚠️ 敏感信息，仅供小鸡内部使用

## 🌍 三节点架构总览

```
萝卜（美国）→ 主力API代理 + 开发测试
  ├─ 域名：xiaoji.caopi.de
  ├─ HTTPS + SSL
  └─ 主模型API服务

皮特（香港）→ 生产任务 + 验证节点
  ├─ 定时任务执行
  ├─ 脚本验证测试
  └─ OpenClaw节点

悉尼（澳洲）→ 备用API代理 + 亚太端点
  ├─ 备用模型API（当萝卜故障）
  ├─ 低延迟亚太访问
  └─ 轻量级监控任务
```

---

## 萝卜节点 (Radish) - 美国 🇺🇸

**定位**：🎯 主力API代理服务器 + 开发测试节点

| 项目 | 值 |
|------|-----|
| 显示名 | 萝卜 (Radish) |
| Node ID | e1a1d0a5d5c5e8cea616022a6ef0b17f94952f7f1e1fa9bc96c2a402f8361491 |
| 地理位置 | 🇺🇸 美国 |
| 平台 | Linux ARM64 |
| 系统 | Ubuntu 22.04 ARM64 |
| SSH地址 | 152.53.171.21 |
| SSH用户 | root |
| SSH密码 | H3Fwyq2fTJ7TjRn |
| 内存 | 8GB ✅ |
| Tailscale IP | 待补充 |
| 状态 | ✅ 在线 |
| 工作目录 | /root/bot-skllis/ |
| 脚本目录 | /root/bot-skllis/scripts/ |
| 浏览器 | Chromium (/usr/bin/chromium-browser) |

### 🎯 主要职责
1. **主力API代理服务**
   - 域名：xiaoji.caopi.de
   - HTTPS + SSL (Let's Encrypt)
   - CLI Proxy API v6.8.5
   - 端口：8317 (内部) / 443 (HTTPS)
   
2. **OpenClaw开发节点**
   - 新功能测试
   - 脚本开发验证

3. **Nginx反向代理**
   - HTTP自动跳转HTTPS
   - WebSocket支持

---

## 皮特节点 (Pete) - 香港 🇭🇰

**定位**：⚙️ 生产任务执行器 + 验证节点

| 项目 | 值 |
|------|-----|
| 显示名 | cjwgx0ermi5b1pl (Pete) |
| Node ID | dbb7776b0d63741e9ab0e91a55f44c5a1d26bc1934e06bde860302091aec5390 |
| 地理位置 | 🇭🇰 香港 |
| 平台 | Linux x86_64 |
| SSH地址 | 83.229.126.21 (公网) |
| SSH用户 | root |
| SSH密码 | 4-@8FVkY@P |
| Tailscale IP | 100.72.108.80 |
| 状态 | ✅ 在线 |
| 工作目录 | /root/.openclaw/workspace/ |
| 脚本目录 | /root/bot-skllis/scripts/ |

### 🎯 主要职责
1. **定时任务执行**
   - pvew5 回帖任务（每日 09:00 北京时间）
   - xsijishe 签到任务（每日 08:00 北京时间）
   
2. **OpenClaw验证节点**
   - 配置验证测试
   - 脚本运行验证
   
3. **中国大陆就近访问**
   - 地理位置优势
   - 低延迟连接

### 环境变量 (.env)
```
XSIJISHE_USERNAME=月笙
XSIJISHE_PASSWORD=kl5348988.
PVEW5_USERNAME=吊大小日本
PVEW5_PASSWORD=k5348988
TG_BOT_TOKEN=8235816943:AAGrtXB2p2d6mAyaggXcGXhBCZv0CcmxDNE
TG_USER_ID=6221493343
```

---

## 悉尼节点 (Sydney) - 澳大利亚 🇦🇺

**定位**：🔄 备用API代理 + 亚太区域端点

| 项目 | 值 |
|------|-----|
| 显示名 | 悉尼 (Sydney) |
| 主机名 | SYDKnightVPS |
| 地理位置 | 🇦🇺 澳大利亚（悉尼） |
| 平台 | Linux x86_64 |
| 系统 | Debian 11 (bullseye) |
| 内核 | 5.10.0-36-amd64 |
| SSH地址 | 206.168.133.84 |
| SSH用户 | root |
| SSH密码 | k5348988. |
| 内存 | 964MB (可用 571MB) ⚠️ |
| 磁盘 | 8.3GB (已用 56%) |
| 运行时长 | 66天+ |
| 状态 | ✅ 在线 |

### 🎯 主要职责
1. **备用API代理服务**
   - CLI Proxy API 运行中
   - 端口：8317
   - API端点：`http://206.168.133.84:8317/v1`
   - 当萝卜故障时自动切换
   
2. **亚太区域低延迟访问**
   - 为澳洲、东南亚用户提供低延迟
   - 地理位置独特优势
   
3. **轻量级监控**
   - 健康检查
   - 状态监控
   
4. **管理面板**
   - 管理密钥：`k5348988`
   - 远程管理：https://remote.router-for.me/
   - 服务器地址：`http://206.168.133.84:8317`

### ⚠️ 限制说明
- 内存仅964MB，**无法运行OpenClaw节点**（会OOM）
- 适合运行轻量级服务（API代理、监控脚本）
- 不建议部署大型应用

### 🔄 故障切换配置
当萝卜服务器故障时，可手动切换到悉尼：
```bash
# 切换Gateway配置到悉尼
openclaw gateway config.patch --raw '{
  "models": {
    "providers": {
      "sydney-proxy": {
        "baseUrl": "http://206.168.133.84:8317/v1"
      }
    }
  }
}'
```

---

## 📊 服务器对比

| 特性 | 萝卜 🇺🇸 | 皮特 🇭🇰 | 悉尼 🇦🇺 |
|------|---------|---------|---------|
| **角色** | 主力API代理 | 生产任务执行 | 备用API代理 |
| **内存** | 8GB ✅ | 充足 ✅ | 964MB ⚠️ |
| **架构** | ARM64 | x86_64 | x86_64 |
| **域名** | ✅ xiaoji.caopi.de | ❌ | ❌ |
| **HTTPS** | ✅ Let's Encrypt | ❌ | ❌ |
| **OpenClaw** | ✅ 节点 | ✅ 节点 | ❌ 不支持 |
| **CLI Proxy** | ✅ v6.8.5 | ❌ | ✅ 运行中 |
| **定时任务** | ❌ | ✅ 主力 | 可选 |
| **地理优势** | 美国 | 中国就近 | 亚太低延迟 |

---

## 🔧 运维策略

### 监控检查
- **萝卜**：每小时检查HTTPS域名可用性
- **皮特**：每日检查定时任务执行情况
- **悉尼**：定期检查API服务状态

### 备份策略
- **配置文件**：三节点定期同步到GitHub
- **认证文件**：敏感信息仅本地存储
- **脚本**：统一版本控制

### 故障应对
1. **萝卜故障** → 切换到悉尼API代理
2. **皮特故障** → 定时任务迁移到萝卜
3. **悉尼故障** → 影响较小，仅失去备用能力

---

*最后更新: 2026-02-08*
