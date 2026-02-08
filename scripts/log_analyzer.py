#!/usr/bin/env python3
"""
日志聚合分析
- 收集各任务日志
- 生成每日执行报告
- 自动识别异常模式
"""

import os
import re
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import List, Dict

# 日志源配置
LOG_SOURCES = {
    "local": {
        "path": "/root/.openclaw/workspace",
        "node": "小鸡Gateway",
        "logs": {
            "daily_report": "scripts/daily_report.py",  # 这个是脚本不是日志
        }
    },
    "皮特": {
        "path": "/root/.openclaw/workspace",
        "logs": {
            "pvew5": "pvew5.log",
            "xsijishe": "xsijishe.log"
        }
    }
}

# 异常模式
ERROR_PATTERNS = [
    (r'ERROR', '错误'),
    (r'Exception', '异常'),
    (r'Traceback', '堆栈追踪'),
    (r'失败', '失败'),
    (r'超时', '超时'),
    (r'timeout', '超时'),
    (r'refused', '连接拒绝'),
    (r'denied', '访问拒绝'),
    (r'EPIPE', '管道破裂'),
]

WARNING_PATTERNS = [
    (r'WARNING', '警告'),
    (r'发帖间隔', '发帖限制'),
    (r'重试', '重试'),
    (r'等待', '等待'),
]

SUCCESS_PATTERNS = [
    (r'✅', '成功'),
    (r'成功', '成功'),
    (r'完成', '完成'),
]


def parse_log_file(filepath: str, hours: int = 24) -> Dict:
    """解析单个日志文件"""
    result = {
        "filepath": filepath,
        "exists": False,
        "size": 0,
        "lines": 0,
        "recent_lines": 0,
        "errors": [],
        "warnings": [],
        "successes": [],
        "runs": [],
        "summary": ""
    }
    
    if not os.path.exists(filepath):
        result["summary"] = "文件不存在"
        return result
    
    result["exists"] = True
    result["size"] = os.path.getsize(filepath)
    
    cutoff = datetime.now() - timedelta(hours=hours)
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        result["lines"] = len(lines)
        
        recent_lines = []
        for line in lines:
            # 尝试解析时间戳
            time_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if time_match:
                try:
                    log_time = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
                    if log_time > cutoff:
                        recent_lines.append(line)
                except:
                    pass
        
        result["recent_lines"] = len(recent_lines)
        
        # 分析模式
        recent_text = ''.join(recent_lines)
        
        for pattern, desc in ERROR_PATTERNS:
            matches = re.findall(f'.*{pattern}.*', recent_text, re.IGNORECASE)
            if matches:
                result["errors"].extend([(desc, m.strip()[:100]) for m in matches[:5]])
        
        for pattern, desc in WARNING_PATTERNS:
            matches = re.findall(f'.*{pattern}.*', recent_text, re.IGNORECASE)
            if matches:
                result["warnings"].extend([(desc, m.strip()[:100]) for m in matches[:5]])
        
        for pattern, desc in SUCCESS_PATTERNS:
            matches = re.findall(f'.*{pattern}.*', recent_text)
            if matches:
                result["successes"].extend([(desc, m.strip()[:100]) for m in matches[:5]])
        
        # 统计运行次数
        run_starts = re.findall(r'===== 开始.*=====', recent_text)
        result["runs"] = len(run_starts)
        
        # 生成摘要
        if result["errors"]:
            result["summary"] = f"❌ {len(result['errors'])} 个错误"
        elif result["warnings"]:
            result["summary"] = f"⚠️ {len(result['warnings'])} 个警告"
        elif result["successes"]:
            result["summary"] = f"✅ {len(result['successes'])} 个成功"
        else:
            result["summary"] = f"📝 {result['recent_lines']} 行日志"
    
    except Exception as e:
        result["summary"] = f"解析错误: {e}"
    
    return result


def analyze_local_logs(hours: int = 24) -> Dict:
    """分析本地日志"""
    results = {}
    
    # 分析 scripts 目录下的日志
    scripts_dir = "/root/.openclaw/workspace/scripts"
    if os.path.exists(scripts_dir):
        for log_file in Path(scripts_dir).glob("*.log"):
            name = log_file.stem
            results[name] = parse_log_file(str(log_file), hours)
    
    # 分析 /tmp 下的临时日志
    for log_file in Path("/tmp").glob("*.log"):
        if "daily_report" in log_file.name or "openclaw" in log_file.name:
            name = log_file.stem
            results[name] = parse_log_file(str(log_file), hours)
    
    return results


def generate_daily_report(logs: Dict, node_name: str = "本地") -> str:
    """生成每日报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    report = f"📋 *日志分析报告 - {node_name}*\n"
    report += f"🕐 {now}\n\n"
    
    if not logs:
        report += "没有找到日志文件\n"
        return report
    
    total_errors = 0
    total_warnings = 0
    total_successes = 0
    
    for name, log in logs.items():
        if not log["exists"]:
            continue
        
        total_errors += len(log["errors"])
        total_warnings += len(log["warnings"])
        total_successes += len(log["successes"])
        
        # 状态图标
        if log["errors"]:
            icon = "❌"
        elif log["warnings"]:
            icon = "⚠️"
        elif log["successes"]:
            icon = "✅"
        else:
            icon = "📝"
        
        report += f"{icon} *{name}*\n"
        report += f"   {log['summary']}\n"
        
        if log["runs"]:
            report += f"   运行次数: {log['runs']}\n"
        
        # 显示最近的错误
        if log["errors"]:
            report += f"   错误示例: {log['errors'][0][1][:50]}...\n"
        
        report += "\n"
    
    report += "---\n"
    report += f"❌ 错误: {total_errors} | ⚠️ 警告: {total_warnings} | ✅ 成功: {total_successes}"
    
    return report


def main():
    """主函数"""
    hours = 24
    output_format = "text"
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--json":
            output_format = "json"
        elif sys.argv[1] == "--hours":
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        elif sys.argv[1] == "--help":
            print("日志聚合分析")
            print()
            print("用法:")
            print("  python3 log_analyzer.py              # 分析过去24小时日志")
            print("  python3 log_analyzer.py --json       # 输出 JSON")
            print("  python3 log_analyzer.py --hours 48   # 分析过去48小时")
            return
    
    logs = analyze_local_logs(hours)
    
    if output_format == "json":
        # 清理不可序列化的内容
        for name, log in logs.items():
            log["errors"] = [(e[0], e[1]) for e in log["errors"]]
            log["warnings"] = [(w[0], w[1]) for w in log["warnings"]]
            log["successes"] = [(s[0], s[1]) for s in log["successes"]]
        print(json.dumps(logs, ensure_ascii=False, indent=2))
    else:
        report = generate_daily_report(logs)
        print(report)


if __name__ == "__main__":
    main()
