# 2026-02-08 浏览器调试对话

## 时间
2026-02-08 09:30-09:50 UTC

## 背景
用户要求解决浏览器自动化问题，OpenClaw的browser manager无法自动启动Chrome。

## 问题与解决

### 问题
`browser.start` 失败，报错 "Chrome extension relay is running, but no tab is connected"

### 原因
默认使用 `profile="chrome"` (relay模式)，需要用户手动点击浏览器扩展附加标签页。

### 解决方案
使用 `profile="openclaw"` 启动独立托管浏览器：
```
browser.start(
  profile="openclaw",
  target="node",
  node="cjwgx0ermi5b1pl"
)
```

### 结果
✅ 浏览器成功启动，CDP端口18800，可正常访问网页、获取快照。

## 用户重要指示

### 萝卜节点
- 用户说之前给过SSH凭证
- 记忆系统没有保存
- 用户不满意重复询问

### 记忆系统升级要求
> "除了文件的凭证记录，我和对话的所有信息都要记录，因为你是我的私人助手，除了我没有人可以联系你"

### 采取的行动
1. 创建 `credentials/` 目录
2. 创建 `credentials/nodes.md` - 节点凭证
3. 创建 `credentials/apis.md` - API凭证
4. 创建 `credentials/owner.md` - 主人信息
5. 创建 `skills/memory-system.md` - 记忆系统文档
6. 创建 `conversations/` 目录 - 对话记录

## 待完成
- [ ] 萝卜节点SSH凭证（等待用户提供）
- [ ] 皮特节点SSH凭证补全

---

*记录时间: 2026-02-08 09:50 UTC*
