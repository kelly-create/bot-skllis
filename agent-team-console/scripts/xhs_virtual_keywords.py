#!/usr/bin/env python3
"""
小红书虚拟产品类目高频词采集（公开页面）

重要说明：
- 小红书网页端常触发风控/验证页，可能导致“采样文本无效”。
- 本脚本会识别风控页面并剔除无效文本，避免输出“安全限制”等伪高频词。
- strict 模式下，若有效采样源过少会返回非0退出码，提醒结果不可信。
"""

import argparse
import asyncio
import json
import os
import re
import sys
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

RISK_TERMS = [
    "安全限制",
    "存在风险",
    "请切换可靠网络环境",
    "我要反馈",
    "返回首页",
    "验证码",
    "验证",
    "访问受限",
]

NOISE_MARKERS = [
    "沪ICP备",
    "营业执照",
    "公网安备",
    "增值电信业务经营许可证",
    "互联网药品信息服务资格证书",
    "违法不良信息举报",
    "互联网举报中心",
    "有害信息举报专区",
    "网络文化经营许可证",
    "个性化推荐算法",
    "网信算备",
    "行吟信息科技",
    "地址：",
    "电话：",
    "© 2014-2024",
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS), help="逗号分隔关键词")
    p.add_argument("--scrolls", type=int, default=5, help="每个关键词滚动次数")
    p.add_argument("--max-top", type=int, default=80, help="输出高频词数量")
    p.add_argument("--strict", action="store_true", help="严格模式：采样不足时返回非0")
    p.add_argument("--min-usable", type=int, default=3, help="strict 模式最低有效采样源")
    p.add_argument("--auto-related", type=int, default=0, help="每个关键词自动扩展相关搜索词数量（0=关闭）")
    p.add_argument("--max-keywords", type=int, default=30, help="自动扩展后的最大关键词总数")
    p.add_argument(
        "--cookie-file",
        default=os.path.join(os.getenv("TASK_INPUT_DIR", "."), "xhs_cookies.json"),
        help="登录态 Cookie 文件（默认读取任务附件目录 xhs_cookies.json）",
    )
    p.add_argument("--out-md", default=os.path.join(os.getenv("TASK_OUTPUT_DIR", "."), "xhs_virtual_keywords.md"))
    p.add_argument("--out-json", default=os.path.join(os.getenv("TASK_OUTPUT_DIR", "."), "xhs_virtual_keywords.json"))
    p.add_argument("--headful", action="store_true", help="启用有界面浏览器")
    return p.parse_args()


def is_risk_text(text: str) -> bool:
    if not text:
        return True
    hit = 0
    for t in RISK_TERMS:
        if t in text:
            hit += 1
    # 命中多个风控词，判定为无效页
    return hit >= 2


def sanitize_text(text: str) -> str:
    lines = []
    seen = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if len(line) < 2:
            continue
        if line in seen:
            continue
        if any(m in line for m in NOISE_MARKERS):
            continue
        # 常见导航词过滤
        if line in {"创作中心", "业务合作", "发现", "发布", "通知", "我", "更多", "全部", "图文", "视频", "用户", "筛选", "综合", "最新", "榜单", "活动", "相关搜索"}:
            continue
        seen.add(line)
        lines.append(line)
    return "\n".join(lines)


def extract_words(text: str):
    phrases = re.findall(r"[\u4e00-\u9fff]{2,10}", text)
    words = []
    for ph in phrases:
        if ph in STOPWORDS:
            continue
        if ph.startswith("http"):
            continue
        if any(rt in ph for rt in RISK_TERMS):
            continue
        if any(nm in ph for nm in NOISE_MARKERS):
            continue
        words.append(ph)
    return words


def normalize_cookie(c: dict):
    name = c.get("name")
    value = c.get("value")
    domain = c.get("domain")
    path = c.get("path", "/")
    if not (name and value and domain):
        return None

    out = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "httpOnly": bool(c.get("httpOnly", False)),
        "secure": bool(c.get("secure", False)),
    }

    # 浏览器导出常见字段：expirationDate / sameSite
    if not c.get("session", False):
        exp = c.get("expirationDate")
        if exp is not None:
            try:
                out["expires"] = int(float(exp))
            except Exception:
                pass

    ss = str(c.get("sameSite", "")).lower()
    if ss in ("lax",):
        out["sameSite"] = "Lax"
    elif ss in ("strict",):
        out["sameSite"] = "Strict"
    elif ss in ("none", "no_restriction"):
        out["sameSite"] = "None"

    return out


def load_cookie_file(path: str):
    if not path:
        return []
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        # 兼容部分格式：{"cookies": [...]} 或 playwright storage state
        if isinstance(raw.get("cookies"), list):
            raw = raw.get("cookies")
        else:
            raw = []

    cookies = []
    if isinstance(raw, list):
        for c in raw:
            if not isinstance(c, dict):
                continue
            nc = normalize_cookie(c)
            if nc:
                cookies.append(nc)
    return cookies


def extract_related_keywords(text: str, max_n: int = 3):
    if max_n <= 0:
        return []
    lines = [x.strip() for x in (text or "").splitlines() if x.strip()]
    out = []
    for i, line in enumerate(lines):
        if "相关搜索" not in line:
            continue
        for cand in lines[i + 1 : i + 40]:
            if len(out) >= max_n:
                break
            # 过滤明显噪声
            if len(cand) < 2 or len(cand) > 16:
                continue
            if any(ch.isdigit() for ch in cand):
                continue
            if cand in STOPWORDS:
                continue
            if any(nm in cand for nm in NOISE_MARKERS):
                continue
            if cand in {"活动", "全部", "图文", "视频", "用户", "筛选", "综合", "最新", "榜单"}:
                continue
            # 只保留中英文常见词
            if not re.match(r"^[\u4e00-\u9fffA-Za-z]{2,16}$", cand):
                continue
            if cand not in out:
                out.append(cand)
        if out:
            break
    return out[:max_n]


async def crawl_keywords(keywords, scrolls=5, headful=False, cookie_file=None, auto_related=0, max_keywords=30):
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        raise RuntimeError(f"缺少 playwright 依赖: {e}")

    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headful, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1366, "height": 900})

        loaded_cookie_count = 0
        if cookie_file:
            try:
                cookies = load_cookie_file(cookie_file)
                if cookies:
                    await context.add_cookies(cookies)
                    loaded_cookie_count = len(cookies)
                    print(f"[INFO] 已加载登录态 Cookie: {loaded_cookie_count} 条")
                else:
                    print(f"[WARN] 未加载到有效 Cookie（文件不存在或为空）: {cookie_file}")
            except Exception as e:
                print(f"[WARN] Cookie 文件解析失败，按未登录模式继续: {e}")

        page = await context.new_page()

        queue = [x.strip() for x in keywords if x.strip()]
        seen = set()

        while queue and len(seen) < max(1, max_keywords):
            kw = queue.pop(0).strip()
            if not kw or kw in seen:
                continue
            seen.add(kw)

            url = f"https://www.xiaohongshu.com/search_result?keyword={quote(kw)}&source=web_explore_feed"
            print(f"[INFO] 抓取关键词: {kw}")
            item = {"keyword": kw, "url": url, "text": "", "blocked": False, "error": None, "related": []}
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)

                for _ in range(max(0, scrolls)):
                    try:
                        await page.evaluate("window.scrollBy(0, 800)")
                        await asyncio.sleep(1.2)
                    except Exception:
                        await asyncio.sleep(1.5)

                body = await page.inner_text("body")
                body = (body or "")[:300000]
                item["text_raw"] = body
                if is_risk_text(body):
                    item["blocked"] = True
                    print(f"[WARN] 关键词[{kw}] 命中风控/验证页面，已标记为无效采样")

                item["text"] = sanitize_text(body)

                if auto_related > 0 and not item["blocked"]:
                    rel = extract_related_keywords(body, max_n=auto_related)
                    item["related"] = rel
                    for r in rel:
                        if r not in seen and r not in queue and len(seen) + len(queue) < max_keywords:
                            queue.append(r)
                    if rel:
                        print(f"[INFO] 关键词[{kw}] 自动扩展相关词: {', '.join(rel)}")
            except Exception as e:
                item["error"] = str(e)
                print(f"[ERROR] 关键词[{kw}] 抓取失败: {e}")

            results.append(item)

        await browser.close()

    return results


def build_report(raw_items, max_top=80):
    counter = Counter()
    total_chars = 0
    usable_sources = 0
    blocked_sources = 0

    for item in raw_items:
        txt = item.get("text", "") or ""
        blocked = bool(item.get("blocked"))
        err = item.get("error")

        if blocked:
            blocked_sources += 1
            continue
        if err:
            continue
        if len(txt) < 80:
            # 文本过短也视为不可靠
            continue

        usable_sources += 1
        total_chars += len(txt)
        for w in extract_words(txt):
            counter[w] += 1

    top = counter.most_common(max_top)
    return {
        "generatedAt": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "keywords": [x.get("keyword") for x in raw_items],
        "sourceCount": len(raw_items),
        "usableSourceCount": usable_sources,
        "blockedSourceCount": blocked_sources,
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
    lines.append("# 小红书虚拟产品高频词报告\n")
    lines.append(f"- 生成时间：{report['generatedAt']}")
    lines.append(f"- 关键词：{', '.join(report['keywords'])}")
    lines.append(f"- 采样源数量：{report['sourceCount']}")
    lines.append(f"- 有效采样源：{report['usableSourceCount']}")
    lines.append(f"- 风控/拦截源：{report['blockedSourceCount']}")
    lines.append(f"- 有效文本总长度：{report['totalChars']}\n")

    if report["usableSourceCount"] == 0:
        lines.append("## 结果有效性\n")
        lines.append("⚠️ 本次采样基本被风控拦截，结果不具参考价值。建议使用登录态 Cookie 或降低频率后重试。\n")

    lines.append("## 高频词 TOP\n")
    if not report["topWords"]:
        lines.append("（未采集到可用词汇）\n")
    else:
        for i, item in enumerate(report["topWords"], 1):
            lines.append(f"{i}. {item['word']}（{item['count']}）")

    lines.append("\n## 采样来源\n")
    for s in raw_items:
        notes = []
        if s.get("blocked"):
            notes.append("风控/验证页")
        if s.get("error"):
            notes.append(f"失败: {s['error']}")
        note = f"（{'；'.join(notes)}）" if notes else ""
        lines.append(f"- {s.get('keyword')}: {s.get('url')} {note}")

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    args = parse_args()
    keywords = [x.strip() for x in args.keywords.split(",") if x.strip()]
    if not keywords:
        keywords = DEFAULT_KEYWORDS

    raw_items = asyncio.run(
        crawl_keywords(
            keywords,
            scrolls=args.scrolls,
            headful=args.headful,
            cookie_file=args.cookie_file,
            auto_related=args.auto_related,
            max_keywords=args.max_keywords,
        )
    )
    report = build_report(raw_items, max_top=args.max_top)
    write_outputs(report, raw_items, args.out_md, args.out_json)

    print(f"[OK] 报告已生成: {args.out_md}")
    print(f"[OK] 原始结果已保存: {args.out_json}")

    if args.strict and report["usableSourceCount"] < max(1, args.min_usable):
        print(
            f"[ERROR] 有效采样源不足（{report['usableSourceCount']} < {args.min_usable}），结果不可信，按 strict 模式返回失败",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
