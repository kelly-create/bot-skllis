#!/usr/bin/env python3
"""
小说类目关键词多Agent流水线（采集 -> 清洗 -> 复核 -> 文包）

Agent角色：
- Collector Agent: 抓取关键词与文本
- Cleaner Agent: 去噪并生成纯化词表
- Reviewer Agent: 质量复核，决定是否进入下一轮
- Packager Agent: 生成爆款文包并打包
- Lead Agent: 统筹轮次、最终决策
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

NOISE_PATTERNS = [
    "素材", "素材库", "礼拿", "自取", "留痕", "爆款开头", "开头素材", "怎么变现", "变现",
    "账号", "入行", "指南", "教程", "可商用", "底图", "高清", "无水印", "兼职", "网名",
    "博主", "涨粉", "运营", "搬运", "大家都在搜", "小时前", "天前", "分钟前",
]

DOMAIN_TERMS = [
    "小说", "推文", "网文", "言情", "悬疑", "书荒", "完结", "番茄", "爽文", "推理", "剧情", "题材",
]


def ts():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def log(role: str, msg: str):
    print(f"[{role}] {msg}", flush=True)


def run_stream(cmd: str, cwd: str):
    log("Lead Agent", f"执行命令: {cmd}")
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=cwd,
        executable="/bin/bash",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in iter(proc.stdout.readline, ""):
        if line:
            print(line.rstrip(), flush=True)
    return proc.wait()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--keywords", required=True)
    p.add_argument("--cookie-file", required=True)
    p.add_argument("--output-dir", default=os.getenv("TASK_OUTPUT_DIR", "."))
    p.add_argument("--workdir", default="/opt/agent-team-console")
    p.add_argument("--max-rounds", type=int, default=3)
    p.add_argument("--min-usable", type=int, default=8)
    p.add_argument("--min-domain-ratio", type=float, default=0.75)
    p.add_argument("--max-noise-ratio", type=float, default=0.35)
    p.add_argument("--pack-format", choices=["zip", "7z"], default="zip", help="压缩格式：zip 或 7z")
    return p.parse_args()


def load_json(path):
    return json.load(open(path, "r", encoding="utf-8"))


def word_noise(word: str):
    return any(p in word for p in NOISE_PATTERNS)


def word_domain(word: str):
    return any(p in word for p in DOMAIN_TERMS)


def compute_noise_ratio(top_words, n=20):
    if not top_words:
        return 1.0
    top = top_words[:n]
    noisy = sum(1 for x in top if word_noise(x.get("word", "")))
    return noisy / max(1, len(top))


def refine_top_words(top_words):
    refined = []
    seen = set()
    for x in top_words:
        w = (x.get("word") or "").strip()
        c = int(x.get("count") or 0)
        if not w or c <= 0:
            continue
        if word_noise(w):
            continue
        if not word_domain(w):
            continue
        if w in seen:
            continue
        seen.add(w)
        refined.append({"word": w, "count": c})
    return refined


def write_pure_report(raw_report: dict, pure_top_words, out_md: str, out_json: str):
    report = dict(raw_report)
    report["topWords"] = pure_top_words

    payload = {"report": report, "sources": []}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    lines = []
    lines.append("# 小说类目高频词报告（纯化版）\n")
    lines.append(f"- 生成时间：{ts()}")
    lines.append(f"- 采样源数量：{report.get('sourceCount')}")
    lines.append(f"- 有效采样源：{report.get('usableSourceCount')}")
    lines.append(f"- 领域命中率(top20)：{report.get('domainTop20HitRatio')}\n")
    lines.append("## 高频词 TOP\n")
    if not pure_top_words:
        lines.append("（纯化后无可用词，请放宽过滤或扩大采样）")
    else:
        for i, x in enumerate(pure_top_words[:80], 1):
            lines.append(f"{i}. {x['word']}（{x['count']}）")

    os.makedirs(os.path.dirname(os.path.abspath(out_md)), exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def pack_outputs(output_dir: str, files: list[str], pack_format: str):
    if pack_format == "7z":
        seven_zip = shutil.which("7z")
        if seven_zip:
            out_path = os.path.join(output_dir, "小说类目_爆款文包_纯化版.7z")
            cmd = [seven_zip, "a", "-t7z", out_path] + [os.path.join(output_dir, f) for f in files]
            rc = subprocess.call(cmd)
            if rc == 0:
                return out_path
            log("Packager Agent", "7z 打包失败，回退到 zip")
        else:
            log("Packager Agent", "系统未安装 7z，回退到 zip")

    out_path = os.path.join(output_dir, "小说类目_爆款文包_纯化版.zip")
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            full = os.path.join(output_dir, f)
            if os.path.exists(full):
                zf.write(full, arcname=f)
    return out_path


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    if not os.path.exists(args.cookie_file):
        log("Lead Agent", f"未找到 Cookie 文件: {args.cookie_file}")
        sys.exit(2)

    rounds = [
        {"scrolls": 4, "auto_related": 1, "max_keywords": 16},
        {"scrolls": 5, "auto_related": 1, "max_keywords": 20},
        {"scrolls": 6, "auto_related": 0, "max_keywords": 12},
    ]
    rounds = rounds[: max(1, args.max_rounds)]

    audit = {
        "startedAt": ts(),
        "rounds": [],
        "decision": None,
    }

    selected_json = None
    selected_report = None

    for idx, cfg in enumerate(rounds, 1):
        log("Lead Agent", f"开始第 {idx} 轮：{cfg}")

        out_md = os.path.join(args.output_dir, f"xhs_round{idx}.md")
        out_json = os.path.join(args.output_dir, f"xhs_round{idx}.json")

        cmd = (
            "python3 scripts/xhs_virtual_keywords.py "
            f"--keywords '{args.keywords}' "
            f"--cookie-file '{args.cookie_file}' "
            f"--scrolls {cfg['scrolls']} --auto-related {cfg['auto_related']} --max-keywords {cfg['max_keywords']} "
            "--domain novel --strict "
            f"--min-usable {args.min_usable} --min-domain-ratio {args.min_domain_ratio} "
            f"--out-md '{out_md}' --out-json '{out_json}'"
        )

        rc = run_stream(cmd, cwd=args.workdir)
        if not os.path.exists(out_json):
            audit["rounds"].append({"round": idx, "rc": rc, "error": "missing output json"})
            continue

        data = load_json(out_json)
        report = data.get("report", {})
        top_words = report.get("topWords", [])

        usable = int(report.get("usableSourceCount") or 0)
        domain_ratio = float(report.get("domainTop20HitRatio") or 0.0)
        noise_ratio = compute_noise_ratio(top_words, n=20)

        round_stat = {
            "round": idx,
            "rc": rc,
            "usable": usable,
            "domainRatio": domain_ratio,
            "noiseRatioTop20": round(noise_ratio, 4),
            "outputJson": out_json,
        }
        audit["rounds"].append(round_stat)

        log("Reviewer Agent", f"第{idx}轮复核: usable={usable}, domainRatio={domain_ratio}, noiseRatio={noise_ratio:.3f}")

        pass_ok = (
            usable >= args.min_usable
            and domain_ratio >= args.min_domain_ratio
            and noise_ratio <= args.max_noise_ratio
        )
        if pass_ok:
            selected_json = out_json
            selected_report = report
            audit["decision"] = {"round": idx, "result": "pass"}
            log("Reviewer Agent", f"第{idx}轮通过复核，进入文包生成")
            break

        # 保存当前最优候选（至少有数据）
        if selected_report is None and usable > 0:
            selected_json = out_json
            selected_report = report

    audit_path = os.path.join(args.output_dir, "小说类目_多Agent复核_审计.json")
    if selected_report is None:
        audit["decision"] = {"result": "fail", "reason": "all rounds unusable"}
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
        log("Lead Agent", "所有轮次均未通过，且无可用候选数据")
        sys.exit(2)

    # Cleaner Agent: 输出纯化版词表（中文文件名）
    final_md = os.path.join(args.output_dir, "小说类目_高频词_纯化版.md")
    final_json = os.path.join(args.output_dir, "小说类目_高频词_纯化版.json")

    pure_top = refine_top_words(selected_report.get("topWords", []))
    write_pure_report(selected_report, pure_top, final_md, final_json)
    log("Cleaner Agent", f"纯化词表已生成：{final_md}")

    # Packager Agent: 生成文包（中文文件名）
    hot_md = os.path.join(args.output_dir, "小说类目_爆款文包_纯化版.md")
    hot_json = os.path.join(args.output_dir, "小说类目_爆款文包_纯化版.json")

    cmd_pack = (
        "python3 scripts/build_novel_pack.py "
        f"--in-json '{final_json}' --out-md '{hot_md}' --out-json '{hot_json}'"
    )
    rc_pack = run_stream(cmd_pack, cwd=args.workdir)
    if rc_pack != 0:
        log("Packager Agent", "文包生成失败")
        sys.exit(3)

    pack_path = pack_outputs(
        args.output_dir,
        ["小说类目_高频词_纯化版.md", "小说类目_高频词_纯化版.json", "小说类目_爆款文包_纯化版.md", "小说类目_爆款文包_纯化版.json"],
        args.pack_format,
    )

    audit["finishedAt"] = ts()
    audit["outputs"] = {
        "keywordsMd": final_md,
        "keywordsJson": final_json,
        "hotpackMd": hot_md,
        "hotpackJson": hot_json,
        "pack": pack_path,
    }
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    log("Lead Agent", f"多Agent流水线完成，压缩包：{pack_path}")


if __name__ == "__main__":
    main()
