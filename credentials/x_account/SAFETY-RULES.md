# 🛡️ X账号操作安全规范 v2.0

> ⚠️ **最高优先级**：避免被检测为机器人，保护账号安全

---

## 🚨 教训记录

### 2026-02-09 临时限制事件
- **原因**：短时间内操作过多（发帖+连续关注多个账号）
- **触发条件**：5分钟内发帖2次+关注3人
- **结果**：账号被临时限制
- **教训**：新账号更容易被标记，需要更谨慎

---

## 🔒 核心安全规则

### 1️⃣ 随机延迟（最重要）

```python
import random
import asyncio

async def human_delay(min_sec=10, max_sec=30):
    """每次操作前必须调用"""
    delay = random.uniform(min_sec, max_sec)
    print(f'⏳ 等待 {delay:.1f} 秒...')
    await asyncio.sleep(delay)

# 不同场景的延迟
DELAY_CONFIG = {
    'before_action': (10, 30),      # 操作前
    'after_action': (20, 60),       # 操作后
    'between_pages': (5, 15),       # 页面切换
    'after_error': (60, 120),       # 出错后
    'session_start': (3, 8),        # 会话开始
}
```

### 2️⃣ 严格频率限制

| 操作类型 | 单次间隔 | 每日上限 | 建议 |
|---------|---------|---------|------|
| **发帖** | ≥ 30分钟 | ≤ 3条 | 1-2条最安全 |
| **带图发帖** | ≥ 1小时 | ≤ 2条 | 1条最安全 |
| **关注** | ≥ 2分钟 | ≤ 5人 | 2-3人最安全 |
| **点赞** | ≥ 30秒 | ≤ 20个 | 10个最安全 |
| **转发** | ≥ 5分钟 | ≤ 5条 | 2-3条最安全 |
| **评论** | ≥ 3分钟 | ≤ 10条 | 3-5条最安全 |

### 3️⃣ 人类行为模拟

```python
async def simulate_human_behavior(page):
    """模拟真人浏览行为"""
    
    # 1. 随机滚动页面
    scroll_times = random.randint(2, 5)
    for _ in range(scroll_times):
        scroll_amount = random.randint(200, 500)
        await page.evaluate(f'window.scrollBy(0, {scroll_amount})')
        await asyncio.sleep(random.uniform(1, 3))
    
    # 2. 随机鼠标移动
    x = random.randint(100, 800)
    y = random.randint(100, 600)
    await page.mouse.move(x, y, steps=random.randint(5, 15))
    
    # 3. 随机停留
    await asyncio.sleep(random.uniform(2, 8))
    
    # 4. 偶尔滚回顶部
    if random.random() < 0.3:
        await page.evaluate('window.scrollTo(0, 0)')
        await asyncio.sleep(random.uniform(1, 2))
```

### 4️⃣ 会话管理

```python
class XSession:
    def __init__(self):
        self.actions_count = 0
        self.session_start = time.time()
        self.MAX_ACTIONS_PER_SESSION = 3  # 单次会话最多3个操作
        self.MAX_SESSION_DURATION = 600   # 最长10分钟
    
    def can_continue(self):
        if self.actions_count >= self.MAX_ACTIONS_PER_SESSION:
            return False
        if time.time() - self.session_start > self.MAX_SESSION_DURATION:
            return False
        return True
    
    def record_action(self):
        self.actions_count += 1
```

### 5️⃣ 时间随机化

```python
def get_random_execution_time():
    """获取随机执行时间，避免固定模式"""
    
    # 基础时间偏移（-30到+30分钟）
    offset_minutes = random.randint(-30, 30)
    
    # 避开整点和半点
    minute = random.choice([7, 13, 23, 37, 43, 53])
    
    return offset_minutes, minute

# 不要在以下时间操作（容易被检测）
AVOID_TIMES = [
    (0, 0),   # 整点
    (30, 0),  # 半点
]
```

---

## ⛔ 绝对禁止

1. ❌ **连续操作** - 任何两个操作之间必须有随机延迟
2. ❌ **批量操作** - 禁止一次关注/点赞多个
3. ❌ **固定间隔** - 禁止使用固定的sleep时间
4. ❌ **重复内容** - 禁止发布相同或相似的帖子
5. ❌ **频繁登录** - 每天最多1-2次会话
6. ❌ **异常时间** - 避免凌晨2-6点操作
7. ❌ **跨账号操作** - 不要同IP操作多个账号
8. ❌ **无浏览直接操作** - 必须先模拟浏览行为

---

## ✅ 推荐操作流程

### 发帖流程
```python
async def safe_post(page, content, image_path=None):
    # 1. 会话开始延迟
    await human_delay(3, 8)
    
    # 2. 模拟浏览首页
    await page.goto('https://x.com/home')
    await simulate_human_behavior(page)
    
    # 3. 操作前延迟
    await human_delay(10, 30)
    
    # 4. 点击发帖区域
    await page.click('[data-testid="tweetTextarea_0"]')
    await human_delay(2, 5)
    
    # 5. 模拟人类打字（逐字输入）
    for char in content:
        await page.keyboard.type(char, delay=random.randint(50, 150))
        if random.random() < 0.1:  # 10%概率停顿
            await asyncio.sleep(random.uniform(0.5, 1.5))
    
    # 6. 如果有图片
    if image_path:
        await human_delay(3, 8)
        await page.set_input_files('input[type="file"]', image_path)
        await human_delay(5, 15)  # 等待图片上传
    
    # 7. 发布前延迟
    await human_delay(5, 15)
    
    # 8. 点击发布
    await page.click('[data-testid="tweetButton"]')
    
    # 9. 操作后延迟
    await human_delay(20, 60)
    
    # 10. 模拟继续浏览
    await simulate_human_behavior(page)
```

### 关注流程
```python
async def safe_follow(page, username):
    # 1. 先浏览首页
    await page.goto('https://x.com/home')
    await simulate_human_behavior(page)
    await human_delay(10, 30)
    
    # 2. 访问用户页面
    await page.goto(f'https://x.com/{username}')
    await simulate_human_behavior(page)
    await human_delay(10, 30)
    
    # 3. 点击关注
    await page.click('[data-testid$="-follow"]')
    
    # 4. 关注后延迟
    await human_delay(20, 60)
    
    # 5. 继续浏览该用户页面
    await simulate_human_behavior(page)
```

---

## 📊 操作配额管理

```python
class DailyQuota:
    def __init__(self):
        self.date = datetime.now().date()
        self.posts = 0
        self.follows = 0
        self.likes = 0
        self.retweets = 0
    
    def can_post(self):
        return self.posts < 2
    
    def can_follow(self):
        return self.follows < 3
    
    def can_like(self):
        return self.likes < 10
    
    def reset_if_new_day(self):
        if datetime.now().date() != self.date:
            self.__init__()
```

---

## 🆘 异常处理

```python
async def handle_restriction(page):
    """检测到限制时的处理"""
    
    body = await page.inner_text('body')
    
    if 'restricted' in body.lower():
        print('⚠️ 检测到账号限制！')
        # 1. 立即停止所有操作
        # 2. 记录事件
        # 3. 通知主人
        # 4. 等待24小时后再尝试
        return 'RESTRICTED'
    
    if 'suspended' in body.lower():
        print('❌ 账号被暂停！')
        return 'SUSPENDED'
    
    if 'verify' in body.lower() or 'captcha' in body.lower():
        print('🔐 需要验证！')
        return 'VERIFY_REQUIRED'
    
    return 'OK'
```

---

## 📅 推荐操作时间

| 时间段 | 风险等级 | 建议 |
|--------|---------|------|
| 08:00-10:00 | 🟢 低 | 推荐 |
| 12:00-14:00 | 🟢 低 | 推荐 |
| 18:00-21:00 | 🟢 低 | 推荐 |
| 22:00-24:00 | 🟡 中 | 可以 |
| 00:00-02:00 | 🟡 中 | 谨慎 |
| 02:00-06:00 | 🔴 高 | 避免 |

---

## 🔧 配置常量

```python
# X操作安全配置
X_SAFETY_CONFIG = {
    # 延迟配置（秒）
    'delay_before_action': (10, 30),
    'delay_after_action': (20, 60),
    'delay_between_pages': (5, 15),
    'delay_typing': (50, 150),  # 毫秒
    
    # 每日配额
    'max_posts_per_day': 2,
    'max_follows_per_day': 3,
    'max_likes_per_day': 10,
    'max_retweets_per_day': 3,
    
    # 会话配置
    'max_actions_per_session': 3,
    'max_session_duration': 600,  # 秒
    'min_session_interval': 3600,  # 两次会话间隔（秒）
    
    # 操作间隔（秒）
    'min_post_interval': 1800,    # 30分钟
    'min_follow_interval': 120,   # 2分钟
    'min_like_interval': 30,      # 30秒
}
```

---

## 🔧 API调用优化（避免400错误）

> 📋 **教训来源**：2026-02-09 分析@GGB9573时出现400 Invalid JSON错误
> 📌 **官方Issue**: [#1433](https://github.com/router-for-me/CLIProxyAPI/issues/1433) - 已确认的已知问题

### 问题原因（官方确认）
1. **请求体大小限制** - CLIProxyAPI内部有约280KB的限制
2. **请求体被截断** - 大请求在转发前被截断，导致JSON不完整
3. **上下文累积过长** - 长时间运行的脚本输出大量内容导致超限

### 相关官方Issues
- **#1433**: 大请求体(~290KB)被截断 → "Invalid JSON payload" (🟡 Open)
- **#1424**: Claude→Gemini转换时JSON Schema字段不兼容
- **#1189**: 大型工具定义导致400错误

### 官方修复状态
- v6.8.2: `400 invalid_request_error 立即返回不再重试` - 仅防止无限重试
- 根本问题**尚未修复**，需等待官方更新

### 改善措施

```python
# 1. 分段处理 - 不一次性获取整个页面
async def get_page_content_chunked(page, max_length=10000):
    """分段获取页面内容，避免一次性抓取过多"""
    content = await page.content()
    if len(content) > max_length:
        # 只取关键部分
        return content[:max_length] + "\n... [truncated]"
    return content

# 2. 精简DOM选择器 - 只获取需要的元素
SAFE_SELECTORS = {
    'tweets': '[data-testid="tweet"]',
    'user_info': '[data-testid="UserName"]',
    'follow_button': '[data-testid$="-follow"]',
    'like_button': '[data-testid="like"]',
}

# 3. 使用snapshot代替全量截取
async def safe_page_analysis(page):
    """安全的页面分析方式"""
    # 优先使用browser snapshot
    # 避免获取完整DOM树
    # 只提取必要信息
    pass

# 4. 定期重置上下文
class ContextManager:
    def __init__(self, max_operations=5):
        self.operation_count = 0
        self.max_operations = max_operations
    
    def should_reset(self):
        """超过阈值时建议重置上下文"""
        return self.operation_count >= self.max_operations
    
    def record(self):
        self.operation_count += 1

# 5. 错误恢复策略
ERROR_RECOVERY = {
    400: {
        'action': 'reset_context',
        'wait_seconds': 10,
        'retry': True,
    },
    429: {  # Rate limited
        'action': 'long_pause',
        'wait_seconds': 300,
        'retry': False,
    },
    500: {
        'action': 'retry_later',
        'wait_seconds': 60,
        'retry': True,
    },
}
```

### 最佳实践
1. ✅ **分批执行** - 长任务分成多个小任务
2. ✅ **精简输出** - 只获取需要的信息
3. ✅ **定期清理** - 避免上下文无限增长
4. ✅ **优雅降级** - 出错时自动简化请求
5. ✅ **监控大小** - 请求/响应超过阈值时预警

---

**版本**: v2.1
**创建时间**: 2026-02-09
**最后更新**: 2026-02-09 08:32 UTC
**原则**: 宁可慢，不可快；宁可少，不可多
