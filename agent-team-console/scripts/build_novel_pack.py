#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--in-json", required=True)
    p.add_argument("--out-md", required=True)
    p.add_argument("--out-json", required=True)
    return p.parse_args()


def main():
    args = parse_args()
    data = json.load(open(args.in_json, "r", encoding="utf-8"))
    top = (data.get("report") or {}).get("topWords") or []
    top = top[:40]
    words = [x.get("word", "") for x in top if x.get("word")]
    if not words:
        words = ["小说推文", "言情", "悬疑"]

    title_templates = [
        "看完上头：{a}+{b}，结局反转太狠了",
        "熬夜都要看完！{a}这本太会拿捏情绪",
        "书荒急救：{a}/{b}/{c}这3本建议收藏",
        "同题材封神：{a}党闭眼入，后劲太大",
        "一口气刷完：{a}×{b}，高能不断",
    ]

    opening_templates = [
        "这本我原本只想看10分钟，结果直接通宵。",
        "如果你最近书荒，这条一定先收藏。",
        "今天这本的情绪拉扯，真的后劲太大。",
        "别被书名骗了，正文比想象狠太多。",
        "同题材里很少见到这么稳的节奏。",
    ]

    lines = []
    lines.append("# 小说类目爆款文包（自动生成）")
    lines.append(f"生成时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("")
    lines.append("## 高频关键词（TOP40）")
    for i, item in enumerate(top, 1):
        lines.append(f"{i}. {item.get('word', '')}（{item.get('count', 0)}）")

    lines.append("")
    lines.append("## 爆款标题模板（可直接改词使用）")
    for i, tpl in enumerate(title_templates, 1):
        a = words[(i - 1) % len(words)]
        b = words[i % len(words)]
        c = words[(i + 1) % len(words)]
        lines.append(f"{i}. " + tpl.format(a=a, b=b, c=c))

    lines.append("")
    lines.append("## 爆款开头文案模板")
    for i, t in enumerate(opening_templates, 1):
        lines.append(f"{i}. {t}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out_md)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out_json)), exist_ok=True)

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    payload = {
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "topWords": top,
        "titleTemplates": title_templates,
        "openingTemplates": opening_templates,
    }
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[OK] 爆款文包已生成: {args.out_md}")
    print(f"[OK] 文包JSON已生成: {args.out_json}")


if __name__ == "__main__":
    main()
