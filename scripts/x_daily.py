#!/usr/bin/env python3
"""
X每日内容发布脚本
- 参考 @GGB9573 风格
- 发布/转发吸引人的内容
- 避免政治倾向
- 遵守安全规范
"""

import asyncio
import random
import json
from datetime import datetime
from playwright.async_api import async_playwright

# ========== 配置 ==========
COOKIES_FILE = '/root/.openclaw/workspace/credentials/x_account/cookies.json'

# 安全配置
DELAY_BEFORE = (10, 30)
DELAY_AFTER = (20, 60)
MAX_ACTIONS = 2  # 单次最多2个操作

# 内容主题（非政治，吸引人）
CONTENT_THEMES = [
    'photography',      # 摄影
    'art',              # 艺术
    'technology',       # 科技
    'nature',           # 自然
    'travel',           # 旅行
    'food',             # 美食
    'music',            # 音乐
    'movies',           # 电影
    'gaming',           # 游戏
    'cute animals',     # 可爱动物
]

# 中文内容模板（非政治）
POST_TEMPLATES = [
    "今天的心情：{emoji}",
    "分享一下最近的发现 ✨",
    "生活需要一点仪式感 🎭",
    "周末愉快 🌟",
    "早安，新的一天开始了 ☀️",
    "晚安，好梦 🌙",
    "记录生活的美好瞬间 📷",
    "音乐是最好的陪伴 🎵",
    "美食治愈一切 🍜",
    "今日份的小确幸 💫",
]

EMOJIS = ['😊', '🌸', '✨', '🎉', '💪', '🌈', '🎭', '🌟', '💫', '🔥']

# ========== 安全函数 ==========
async def human_delay(min_sec=10, max_sec=30):
    """人类延迟"""
    delay = random.uniform(min_sec, max_sec)
    print(f'⏳ 等待 {delay:.1f}s...')
    await asyncio.sleep(delay)

async def simulate_human(page):
    """模拟人类行为"""
    # 随机滚动
    for _ in range(random.randint(2, 4)):
        await page.evaluate(f'window.scrollBy(0, {random.randint(100, 400)})')
        await asyncio.sleep(random.uniform(1, 3))
    
    # 随机鼠标移动
    await page.mouse.move(
        random.randint(100, 800),
        random.randint(100, 600),
        steps=random.randint(5, 10)
    )
    await asyncio.sleep(random.uniform(1, 3))

# ========== 主要功能 ==========
async def get_trending_content(page):
    """获取热门内容用于转发"""
    print('🔍 查找可转发的内容...')
    
    # 访问首页
    await page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=60000)
    await asyncio.sleep(5)
    
    # 关闭弹窗
    try:
        await page.click('button:has-text("Refuse")', timeout=3000)
        await asyncio.sleep(1)
    except:
        pass
    
    await simulate_human(page)
    
    # 查找可转发的帖子（非政治）
    articles = page.locator('article')
    count = await articles.count()
    
    retweet_candidates = []
    
    for i in range(min(count, 10)):
        try:
            text = await articles.nth(i).inner_text()
            text_lower = text.lower()
            
            # 排除政治内容
            political_keywords = [
                'trump', 'biden', 'politics', 'election', 'government',
                'democrat', 'republican', 'vote', 'congress', 'senate',
                '政治', '选举', '政府', '民主党', '共和党',
            ]
            
            is_political = any(kw in text_lower for kw in political_keywords)
            
            if not is_political and len(text) > 50:
                # 检查是否有图片/视频（更吸引人）
                has_media = await articles.nth(i).locator('img, video').count() > 0
                if has_media:
                    retweet_candidates.append({
                        'index': i,
                        'preview': text[:100],
                        'has_media': True
                    })
        except:
            pass
    
    return retweet_candidates

async def retweet_post(page, article_index):
    """转发帖子"""
    print(f'🔄 转发第 {article_index} 条帖子...')
    
    await human_delay(*DELAY_BEFORE)
    
    articles = page.locator('article')
    article = articles.nth(article_index)
    
    # 点击转发按钮
    retweet_btn = article.locator('[data-testid="retweet"]')
    await retweet_btn.click()
    await asyncio.sleep(2)
    
    # 点击"Repost"
    await page.click('[data-testid="retweetConfirm"]')
    
    await human_delay(*DELAY_AFTER)
    print('✅ 转发成功')

async def like_post(page, article_index):
    """点赞帖子"""
    print(f'❤️ 点赞第 {article_index} 条帖子...')
    
    await human_delay(*DELAY_BEFORE)
    
    articles = page.locator('article')
    article = articles.nth(article_index)
    
    like_btn = article.locator('[data-testid="like"]')
    await like_btn.click()
    
    await human_delay(10, 20)
    print('✅ 点赞成功')

async def post_content(page, content):
    """发布帖子"""
    print(f'📝 发布帖子: {content}')
    
    await page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=60000)
    await asyncio.sleep(5)
    
    await simulate_human(page)
    await human_delay(*DELAY_BEFORE)
    
    # 点击发帖区域
    textarea = page.locator('[data-testid="tweetTextarea_0"]')
    await textarea.click()
    await asyncio.sleep(1)
    
    # 逐字输入
    for char in content:
        await page.keyboard.type(char, delay=random.randint(50, 150))
        if random.random() < 0.1:
            await asyncio.sleep(random.uniform(0.3, 0.8))
    
    await human_delay(5, 15)
    
    # 发布
    await page.click('[data-testid="tweetButtonInline"]')
    
    await human_delay(*DELAY_AFTER)
    await simulate_human(page)
    
    print('✅ 发布成功')

async def main():
    print(f'🚀 X每日任务开始 - {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    
    # 加载Cookie
    with open(COOKIES_FILE) as f:
        cookies = json.load(f)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 900})
        await context.add_cookies(cookies)
        page = await context.new_page()
        
        actions_done = 0
        
        try:
            # 随机选择操作类型
            action_type = random.choice(['post', 'retweet', 'like'])
            
            if action_type == 'post':
                # 发布原创内容
                template = random.choice(POST_TEMPLATES)
                emoji = random.choice(EMOJIS)
                content = template.format(emoji=emoji)
                await post_content(page, content)
                actions_done += 1
                
            elif action_type == 'retweet':
                # 转发内容
                candidates = await get_trending_content(page)
                if candidates:
                    candidate = random.choice(candidates[:3])
                    await retweet_post(page, candidate['index'])
                    actions_done += 1
                    
            elif action_type == 'like':
                # 点赞
                await page.goto('https://x.com/home', wait_until='domcontentloaded')
                await asyncio.sleep(5)
                await simulate_human(page)
                
                # 随机点赞1-2条
                for i in range(random.randint(1, 2)):
                    if actions_done >= MAX_ACTIONS:
                        break
                    await like_post(page, random.randint(0, 5))
                    actions_done += 1
            
            print(f'\\n📊 完成 {actions_done} 个操作')
            
        except Exception as e:
            print(f'❌ 错误: {e}')
        
        await browser.close()
    
    print(f'✅ 任务完成 - {datetime.now().strftime("%H:%M")}')

if __name__ == '__main__':
    asyncio.run(main())
