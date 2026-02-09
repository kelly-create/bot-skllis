#!/usr/bin/env python3
"""
每日新闻简报包装器 - 带监控和通知
确保任务执行成功或失败都会通知主人
"""

import subprocess
import sys
import json
import requests
from datetime import datetime

# Telegram配置
TG_BOT_TOKEN = "8596711036:AAG1SF19xwf0xUgp1fq8nOuhLMJ9xVGcnu8"
TG_USER_ID = "6221493343"

def send_telegram_message(message):
    """发送Telegram消息"""
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TG_USER_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=data, timeout=10)
        return response.ok
    except Exception as e:
        print(f"发送Telegram消息失败: {e}")
        return False

def main():
    script_path = "/root/.openclaw/workspace/scripts/daily_report.py"
    start_time = datetime.now()
    
    print(f"🚀 开始执行每日新闻简报任务")
    print(f"⏰ 执行时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 执行主脚本
        result = subprocess.run(
            ["python3", script_path],
            capture_output=True,
            text=True,
            timeout=600  # 10分钟超时
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if result.returncode == 0:
            # 成功
            message = f"""✅ **每日新闻简报执行成功**

📅 日期: {start_time.strftime('%Y-%m-%d')}
⏰ 执行时间: {start_time.strftime('%H:%M:%S')}
⏱ 耗时: {duration:.1f}秒

📧 邮件已发送到: k925138635@gmail.com

输出摘要:
```
{result.stdout[-500:] if len(result.stdout) > 500 else result.stdout}
```
"""
            print("✅ 任务执行成功")
            print(result.stdout)
        else:
            # 失败
            message = f"""❌ **每日新闻简报执行失败**

📅 日期: {start_time.strftime('%Y-%m-%d')}
⏰ 执行时间: {start_time.strftime('%H:%M:%S')}
⏱ 耗时: {duration:.1f}秒
🔴 错误码: {result.returncode}

错误信息:
```
{result.stderr[-800:] if len(result.stderr) > 800 else result.stderr}
```
"""
            print(f"❌ 任务执行失败，错误码: {result.returncode}")
            print(result.stderr)
        
        # 发送Telegram通知
        send_telegram_message(message)
        sys.exit(result.returncode)
        
    except subprocess.TimeoutExpired:
        # 超时
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        message = f"""⚠️ **每日新闻简报执行超时**

📅 日期: {start_time.strftime('%Y-%m-%d')}
⏰ 执行时间: {start_time.strftime('%H:%M:%S')}
⏱ 运行时间: {duration:.1f}秒（超过600秒限制）

脚本被强制终止
"""
        print("⚠️ 任务执行超时")
        send_telegram_message(message)
        sys.exit(124)
        
    except Exception as e:
        # 其他异常
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        message = f"""💥 **每日新闻简报执行异常**

📅 日期: {start_time.strftime('%Y-%m-%d')}
⏰ 执行时间: {start_time.strftime('%H:%M:%S')}
⏱ 耗时: {duration:.1f}秒

异常信息:
```
{str(e)}
```
"""
        print(f"💥 任务执行异常: {e}")
        send_telegram_message(message)
        sys.exit(1)

if __name__ == "__main__":
    main()
