#!/usr/bin/env python3
"""
任务监控告警系统
- 检查所有定时任务执行状态
- 失败时立即 Telegram 告警
- 生成每日汇总报告
"""

import os
import re
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path

# 配置
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_USER_ID = os.getenv('TG_USER_ID', '6221493343')

# 任务日志配置
TASKS = {
    "pvew5": {
        "name": "pvew5 回帖",
        "log_path": "/root/.openclaw/workspace/pvew5.log",
        "success_pattern": r"✅ 回复成功: (\d+)/(\d+)",
        "node": "皮特"
    },
    "xsijishe": {
        "name": "xsijishe 签到",
        "log_path": "/root/.openclaw/workspace/xsijishe.log",
        "success_pattern": r"(签到成功|已签到)",
        "node": "皮特"
    },
    "daily_report": {
        "name": "每日简报",
        "log_path": "/tmp/daily_report.log",
        "success_pattern": r"已发送至",
        "node": "本地"
    }
}


async def send_telegram(message: str, parse_mode: str = "Markdown"):
    """发送 Telegram 通知"""
    if not TG_BOT_TOKEN:
        print(f"[TG] {message}")
        return False
    
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_USER_ID,
        "text": message,
        "parse_mode": parse_mode
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                return resp.status == 200
    except Exception as e:
        print(f"发送失败: {e}")
        return False


def parse_log(log_path: str, success_pattern: str, hours: int = 24) -> dict:
    """解析日志文件"""
    result = {
        "exists": False,
        "last_run": None,
        "success": False,
        "details": "",
        "runs": []
    }
    
    if not os.path.exists(log_path):
        result["details"] = "日志文件不存在"
        return result
    
    result["exists"] = True
    cutoff = datetime.now() - timedelta(hours=hours)
    
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # 解析每次运行
        current_run = []
        runs = []
        
        for line in lines:
            # 尝试解析时间戳
            time_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if time_match:
                try:
                    log_time = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
                    if log_time > cutoff:
                        if '开始' in line or '====' in line:
                            if current_run:
                                runs.append(current_run)
                            current_run = [line]
                        else:
                            current_run.append(line)
                except:
                    pass
        
        if current_run:
            runs.append(current_run)
        
        result["runs"] = runs
        
        # 检查最后一次运行
        if runs:
            last_run = runs[-1]
            last_run_text = ''.join(last_run)
            
            # 获取最后运行时间
            time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_run[0])
            if time_match:
                result["last_run"] = time_match.group(1)
            
            # 检查成功
            success_match = re.search(success_pattern, last_run_text)
            if success_match:
                result["success"] = True
                result["details"] = success_match.group(0)
            else:
                # 检查错误
                if 'ERROR' in last_run_text or '失败' in last_run_text or 'error' in last_run_text.lower():
                    result["details"] = "执行出错"
                else:
                    result["details"] = "未找到成功标记"
    
    except Exception as e:
        result["details"] = f"解析错误: {e}"
    
    return result


async def check_all_tasks() -> dict:
    """检查所有任务状态"""
    results = {}
    
    for task_id, task_config in TASKS.items():
        result = parse_log(
            task_config["log_path"],
            task_config["success_pattern"]
        )
        result["name"] = task_config["name"]
        result["node"] = task_config["node"]
        results[task_id] = result
    
    return results


async def generate_report(results: dict) -> str:
    """生成汇总报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    report = f"📊 *任务监控报告*\n"
    report += f"🕐 {now}\n\n"
    
    success_count = 0
    fail_count = 0
    
    for task_id, result in results.items():
        if result["success"]:
            status = "✅"
            success_count += 1
        elif not result["exists"]:
            status = "⚪"
        else:
            status = "❌"
            fail_count += 1
        
        report += f"{status} *{result['name']}* ({result['node']})\n"
        if result["last_run"]:
            report += f"   最后运行: {result['last_run']}\n"
        if result["details"]:
            report += f"   {result['details']}\n"
        report += "\n"
    
    report += f"---\n"
    report += f"✅ 成功: {success_count} | ❌ 失败: {fail_count}"
    
    return report


async def alert_failures(results: dict):
    """失败任务告警"""
    failures = []
    
    for task_id, result in results.items():
        if result["exists"] and not result["success"]:
            failures.append(result)
    
    if failures:
        msg = "🚨 *任务失败告警*\n\n"
        for f in failures:
            msg += f"❌ {f['name']} ({f['node']})\n"
            msg += f"   {f['details']}\n\n"
        
        await send_telegram(msg)


async def main():
    """主函数"""
    import sys
    
    results = await check_all_tasks()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--report":
            # 生成并发送报告
            report = await generate_report(results)
            await send_telegram(report)
            print(report)
        elif sys.argv[1] == "--alert":
            # 只在失败时告警
            await alert_failures(results)
        elif sys.argv[1] == "--json":
            # 输出 JSON
            print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    else:
        # 默认：检查并输出
        report = await generate_report(results)
        print(report)


if __name__ == "__main__":
    asyncio.run(main())
