#!/usr/bin/env python3
"""
网站状态探测 (requests 版本)
- 检测网站是否可访问
- 检测发帖间隔限制
- 自适应调整等待时间
"""

import json
import sys
import time
import requests
from datetime import datetime
from typing import Dict, Optional

# 禁用 SSL 警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 默认检测配置
DEFAULT_SITES = {
    "pvew5": {
        "url": "https://pvew5.pver549cn.com",
        "name": "pvew5 论坛",
        "timeout": 30,
        "keywords": ["登录", "论坛"],
        "block_keywords": ["403", "banned", "forbidden"]
    },
    "xsijishe": {
        "url": "https://xsijishe.com",
        "name": "xsijishe 论坛",
        "timeout": 30,
        "keywords": [],
        "block_keywords": ["403", "banned"]
    }
}

# 状态缓存
STATUS_CACHE: Dict[str, dict] = {}
CACHE_FILE = "/tmp/site_status_cache.json"


def check_site(site_id: str, config: dict) -> dict:
    """检测单个网站状态"""
    result = {
        "site_id": site_id,
        "name": config["name"],
        "url": config["url"],
        "status": "unknown",
        "response_time": None,
        "status_code": None,
        "accessible": False,
        "blocked": False,
        "message": "",
        "checked_at": datetime.now().isoformat()
    }
    
    try:
        start_time = time.time()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        resp = requests.get(
            config["url"],
            timeout=config.get("timeout", 30),
            headers=headers,
            verify=False
        )
        
        result["response_time"] = round((time.time() - start_time) * 1000)
        result["status_code"] = resp.status_code
        
        if resp.status_code == 200:
            text_lower = resp.text.lower()
            
            # 检查是否被封禁
            for kw in config.get("block_keywords", []):
                if kw.lower() in text_lower:
                    result["status"] = "blocked"
                    result["blocked"] = True
                    result["message"] = f"检测到封禁关键词: {kw}"
                    return result
            
            # 检查正常关键词
            keywords = config.get("keywords", [])
            if keywords:
                found = any(kw.lower() in text_lower for kw in keywords)
                if found:
                    result["status"] = "ok"
                    result["accessible"] = True
                    result["message"] = "网站正常"
                else:
                    result["status"] = "warning"
                    result["accessible"] = True
                    result["message"] = "页面内容可能异常"
            else:
                result["status"] = "ok"
                result["accessible"] = True
                result["message"] = "网站可访问"
        
        elif resp.status_code == 403:
            result["status"] = "blocked"
            result["blocked"] = True
            result["message"] = "403 禁止访问"
        
        elif resp.status_code == 503:
            result["status"] = "maintenance"
            result["message"] = "网站维护中"
        
        else:
            result["status"] = "error"
            result["message"] = f"HTTP {resp.status_code}"
    
    except requests.Timeout:
        result["status"] = "timeout"
        result["message"] = f"连接超时 ({config.get('timeout', 30)}s)"
    
    except requests.RequestException as e:
        result["status"] = "error"
        result["message"] = f"连接错误: {type(e).__name__}"
    
    except Exception as e:
        result["status"] = "error"
        result["message"] = f"未知错误: {e}"
    
    return result


def check_all_sites(sites: dict = None) -> dict:
    """检测所有网站"""
    if sites is None:
        sites = DEFAULT_SITES
    
    results = {}
    
    for site_id, config in sites.items():
        result = check_site(site_id, config)
        results[site_id] = result
        STATUS_CACHE[site_id] = result
    
    # 保存缓存
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    except:
        pass
    
    return results


def get_cached_status(site_id: str) -> Optional[dict]:
    """获取缓存的状态"""
    if site_id in STATUS_CACHE:
        return STATUS_CACHE[site_id]
    
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
            return cache.get(site_id)
    except:
        return None


def suggest_wait_time(site_id: str) -> int:
    """根据网站状态建议等待时间"""
    status = get_cached_status(site_id)
    
    if not status:
        return 120  # 默认
    
    if status["blocked"]:
        return 600  # 被封禁，等待更长
    
    if status["status"] == "ok":
        response_time = status.get("response_time", 1000)
        if response_time < 500:
            return 90  # 响应快，可以短一点
        elif response_time < 2000:
            return 120  # 正常
        else:
            return 180  # 响应慢，等待更长
    
    if status["status"] == "timeout":
        return 300  # 超时，网站可能有问题
    
    return 120  # 默认


def format_report(results: dict) -> str:
    """格式化报告"""
    lines = ["📡 网站状态探测\n"]
    
    for site_id, result in results.items():
        if result["status"] == "ok":
            icon = "✅"
        elif result["status"] == "warning":
            icon = "⚠️"
        elif result["status"] == "blocked":
            icon = "🚫"
        elif result["status"] == "timeout":
            icon = "⏱️"
        else:
            icon = "❌"
        
        lines.append(f"{icon} {result['name']}")
        lines.append(f"   {result['url']}")
        
        if result["response_time"]:
            lines.append(f"   响应: {result['response_time']}ms")
        
        if result["status_code"]:
            lines.append(f"   状态码: {result['status_code']}")
        
        lines.append(f"   {result['message']}")
        lines.append("")
    
    return "\n".join(lines)


def main():
    """主函数"""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--json":
            results = check_all_sites()
            print(json.dumps(results, ensure_ascii=False, indent=2))
        
        elif sys.argv[1] == "--suggest":
            site_id = sys.argv[2] if len(sys.argv) > 2 else "pvew5"
            wait_time = suggest_wait_time(site_id)
            print(f"建议等待时间: {wait_time}秒")
        
        elif sys.argv[1] == "--site":
            site_id = sys.argv[2] if len(sys.argv) > 2 else "pvew5"
            if site_id in DEFAULT_SITES:
                result = check_site(site_id, DEFAULT_SITES[site_id])
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"未知站点: {site_id}")
        
        else:
            print("用法:")
            print("  python3 site_probe.py           # 检测所有站点")
            print("  python3 site_probe.py --json    # 输出 JSON")
            print("  python3 site_probe.py --site <id>  # 检测单个站点")
            print("  python3 site_probe.py --suggest <id>  # 建议等待时间")
    else:
        results = check_all_sites()
        print(format_report(results))


if __name__ == "__main__":
    main()
