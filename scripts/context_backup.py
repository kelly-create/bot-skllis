#!/usr/bin/env python3
"""
自动上下文备份脚本
- 生成当日对话摘要
- 保存到 memory/ 目录
- 推送到 GitHub
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timezone, timedelta

WORKSPACE = "/root/.openclaw/workspace"
MEMORY_DIR = f"{WORKSPACE}/memory"

def get_today_date():
    """获取北京时间日期"""
    beijing_tz = timezone(timedelta(hours=8))
    return datetime.now(beijing_tz).strftime("%Y-%m-%d")

def create_memory_template(date: str, content: dict) -> str:
    """生成记忆模板"""
    template = f"""# {date} 记忆存档

## 📋 今日摘要
{content.get('summary', '无')}

## ✅ 完成的任务
{content.get('completed_tasks', '无')}

## 🔧 创建/修改的文件
{content.get('files_changed', '无')}

## 📝 关键决策和原因
{content.get('decisions', '无')}

## ⚠️ 遇到的问题和解决方案
{content.get('issues', '无')}

## 🔑 重要配置/凭证（已脱敏）
{content.get('configs', '无')}

## 📌 待办事项
{content.get('todos', '无')}

## 💡 经验教训
{content.get('lessons', '无')}

---
*自动生成于 {datetime.now().isoformat()}*
"""
    return template

def save_memory(date: str, content: dict):
    """保存记忆到文件"""
    os.makedirs(MEMORY_DIR, exist_ok=True)
    
    filepath = f"{MEMORY_DIR}/{date}.md"
    
    # 如果文件已存在，追加内容
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            existing = f.read()
        
        # 追加新内容
        new_content = f"\n\n---\n## 📝 追加记录 ({datetime.now().strftime('%H:%M')})\n\n"
        new_content += content.get('append', '')
        
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(new_content)
    else:
        # 创建新文件
        template = create_memory_template(date, content)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(template)
    
    return filepath

def git_push(message: str):
    """推送到 GitHub"""
    try:
        os.chdir(WORKSPACE)
        subprocess.run(['git', 'add', '-A'], check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', message], check=True, capture_output=True)
        subprocess.run(['git', 'push'], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    """主函数"""
    date = get_today_date()
    
    # 从命令行参数或标准输入读取内容
    if len(sys.argv) > 1:
        # JSON 格式的内容
        try:
            content = json.loads(sys.argv[1])
        except json.JSONDecodeError:
            # 简单文本作为摘要
            content = {"summary": sys.argv[1]}
    else:
        # 交互模式
        print("请输入今日摘要（输入 END 结束）：")
        lines = []
        while True:
            line = input()
            if line.strip() == 'END':
                break
            lines.append(line)
        content = {"summary": "\n".join(lines)}
    
    # 保存记忆
    filepath = save_memory(date, content)
    print(f"✅ 记忆已保存: {filepath}")
    
    # 推送到 GitHub
    if git_push(f"📝 自动备份 {date} 上下文"):
        print("✅ 已推送到 GitHub")
    else:
        print("⚠️ GitHub 推送失败（可能无更改）")

if __name__ == "__main__":
    main()
