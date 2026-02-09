# 🐦 X (Twitter) 账号信息

> ⚠️ 敏感信息，仅供小鸡内部使用

## 账号信息

| 项目 | 值 |
|------|-----|
| **显示名称** | Zelda Rosaleen |
| **用户名** | @zuzonren |
| **用户ID** | 2020743811916541952 |
| **关联邮箱** | myket109@gmail.com |
| **登录方式** | Google OAuth |
| **创建时间** | 2026-02-09 |
| **关注数** | 1 |
| **粉丝数** | 0 |
| **帖子数** | 0 |
| **账号状态** | ✅ 正常 |

## Cookie认证

**Cookie文件位置**: `credentials/x_account/cookies.json`

**关键Cookie**:
- `auth_token`: 主认证令牌
- `ct0`: CSRF令牌
- `twid`: 用户ID
- `kdt`: 设备令牌

**Cookie有效期**: 约1年（到2027年）

## 使用方法

### Python (Playwright)
```python
import json
from playwright.async_api import async_playwright

# 加载Cookie
with open('credentials/x_account/cookies.json') as f:
    cookies = json.load(f)

async with async_playwright() as p:
    browser = await p.chromium.launch()
    context = await browser.new_context()
    await context.add_cookies(cookies)
    page = await context.new_page()
    await page.goto('https://x.com/home')
```

### 刷新Cookie
如果登录失效，需要用户重新登录并导出Cookie。

## 自动化脚本

- **发帖**: `scripts/x_post.py` (待创建)
- **点赞**: `scripts/x_like.py` (待创建)
- **关注**: `scripts/x_follow.py` (待创建)

## 注意事项

1. ⚠️ **不要频繁操作**：避免触发X的反自动化机制
2. ⚠️ **保持Cookie安全**：不要泄露auth_token
3. ⚠️ **定期检查**：Cookie可能会过期

## 执行服务器

- **位置**: 萝卜节点 (152.53.171.21)
- **环境**: Python 3.10 + Playwright
- **浏览器**: Chromium (headless)

---

*创建时间: 2026-02-09*
*最后验证: 2026-02-09 06:20 UTC*
