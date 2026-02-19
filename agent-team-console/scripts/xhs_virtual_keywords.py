#!/usr/bin/env python3
"""
小红书虚拟产品类目高频词采集（公开页面）
- 通过关键词搜索页抓取可见文本
- 统计中文高频词并输出 markdown/json
"""

import argparse
import asyncio
import json
import os
import re
from collections import Counter
from datetime import datetime
from urllib.parse import quote

DEFAULT_KEYWORDS = [
    "虚拟产品",
    "数字产品",
    "PPT模板",
    "简历模板",
    "教程课程",
    "AI提示词",
    "素材包",
    "资料包",
]

STOPWORDS = {
    "小红书", "首页", "发现", "消息", "我的", "发布", "关注", "推荐", "评论", "点赞",
    "收藏", "转发", "更多", "登录", "注册", "搜索", "商品", "店铺", "内容", "用户", "视频",
    "图片", "作者", "发布于", "最新", "热门", "综合", "全部", "相关", "查看", "打开", "下载",
    "可以", "这个", "那个", "我们", "你们", "他们", "自己", "真的", "非常", "有点", "就是",
    "一个", "一些", "还有", "已经", "因为", "所以", "如果", "然后", "以及", "进行", "用于",
    "教程", "课程", "模板", "资料", "产品", "虚拟", "数字", "素材", "工具", "方法", "经验",
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS), help="逗号分隔关键词")
    p.add_argument("--scrolls", type=int, default=5, help="每个关键词滚动次数")
    p.add_argument("--max-top", type=int, default=80, help="输出高频词数量")
    p.add_argument("--out-md", default=os.path.join(os.getenv("TASK_OUTPUT_DIR", "."), "xhs_virtual_keywords.md"))
    p.add_argument("--out-json", default=os.path.join(os.getenv("TASK_OUTPUT_DIR", "."), "xhs_virtual_keywords.json"))
    p.add_argument("--headful", action="store_true", help="启用有界面浏览器")
    return p.parse_args()


def extract_words(text: str):
    # 先提取中文短语，再粗分词
    phrases = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    words = []
    for ph in phrases:
        if ph in STOPWORDS:
            continue
        if ph.startswith("http"):
            continue
        words.append(ph)
    return words


async def crawl_keywords(keywords, scrolls=5, headful=False):
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        raise RuntimeError(f"缺少 playwright 依赖: {e}")

    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headful, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1366, "height": 900})
        page = await context.new_page()

        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            url = f"https://www.xiaohongshu.com/search_result?keyword={quote(kw)}&source=web_explore_feed"
            print(f"[INFO] 抓取关键词: {kw}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)
                for _ in range(max(0, scrolls)):
                    await page.evaluate("window.scrollBy(0, 800)")
                    await asyncio.sleep(1.2)

                body = await page.inner_text("body")
                body = body[:300000]
                results.append({"keyword": kw, "url": url, "text": body})

                low = body.lower()
                if ("登录" in body and "查看更多" in body) or ("验证码" in body) or ("验证" in body and "安全" in body):
                    print(f"[WARN] 关键词[{kw}] 可能触发登录/验证限制，文本可能不完整")
            except Exception as e:
                print(f"[ERROR] 关键词[{kw}] 抓取失败: {e}")
                results.append({"keyword": kw, "url": url, "text": "", "error": str(e)})

        await browser.close()

    return results


def build_report(raw_items, max_top=80):
    counter = Counter()
    total_chars = 0

    for item in raw_items:
        txt = item.get("text", "") or ""
        total_chars += len(txt)
        for w in extract_words(txt):
            counter[w] += 1

    top = counter.most_common(max_top)
    return {
        "generatedAt": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "keywords": [x.get("keyword") for x in raw_items],
        "sourceCount": len(raw_items),
        "totalChars": total_chars,
        "topWords": [{"word": k, "count": v} for k, v in top],
    }


def write_outputs(report, raw_items, out_md, out_json):
    os.makedirs(os.path.dirname(os.path.abspath(out_md)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)

    payload = {"report": report, "sources": raw_items}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    lines = []
    lines.append(f"# 小红书虚拟产品高频词报告\n")
    lines.append(f"- 生成时间：{report['generatedAt']}")
    lines.append(f"- 关键词：{', '.join(report['keywords'])}")
    lines.append(f"- 采样源数量：{report['sourceCount']}")
    lines.append(f"- 抓取文本总长度：{report['totalChars']}\n")
    lines.append("## 高频词 TOP\n")
    if not report["topWords"]:
        lines.append("（未采集到可用词汇，可能被登录/风控拦截）\n")
    else:
        for i, item in enumerate(report["topWords"], 1):
            lines.append(f"{i}. {item['word']}（{item['count']}）")

    lines.append("\n## 采样来源\n")
    for s in raw_items:
        note = ""
        if s.get("error"):
            note = f"（失败: {s['error']}）"
        lines.append(f"- {s.get('keyword')}: {s.get('url')} {note}")

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    args = parse_args()
    keywords = [x.strip() for x in args.keywords.split(",") if x.strip()]
    if not keywords:
        keywords = DEFAULT_KEYWORDS

    raw_items = asyncio.run(crawl_keywords(keywords, scrolls=args.scrolls, headful=args.headful))
    report = build_report(raw_items, max_top=args.max_top)
    write_outputs(report, raw_items, args.out_md, args.out_json)

    print(f"[OK] 报告已生成: {args.out_md}")
    print(f"[OK] 原始结果已保存: {args.out_json}")


if __name__ == "__main__":
    main()
