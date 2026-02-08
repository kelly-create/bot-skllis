#!/usr/bin/env python3
"""
代理/IP 轮换管理
- 管理代理池
- 遇到限制时自动切换
- 检测代理可用性
"""

import asyncio
import aiohttp
import json
import os
import random
import sys
from datetime import datetime
from typing import List, Dict, Optional

# 代理配置文件
PROXY_CONFIG_FILE = os.path.expanduser("~/.openclaw/workspace/config/proxies.json")

# 默认代理池（需要用户配置）
DEFAULT_PROXIES = {
    "http": [],
    "socks5": [],
    "current": None,
    "last_rotation": None
}


class ProxyManager:
    def __init__(self, config_file: str = PROXY_CONFIG_FILE):
        self.config_file = config_file
        self.proxies = self._load_config()
        self.failed_proxies = set()
    
    def _load_config(self) -> dict:
        """加载代理配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return DEFAULT_PROXIES.copy()
    
    def _save_config(self):
        """保存代理配置"""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(self.proxies, f, indent=2, default=str)
    
    def add_proxy(self, proxy: str, proxy_type: str = "http"):
        """添加代理"""
        if proxy_type not in self.proxies:
            self.proxies[proxy_type] = []
        
        if proxy not in self.proxies[proxy_type]:
            self.proxies[proxy_type].append(proxy)
            self._save_config()
            print(f"✅ 已添加代理: {proxy}")
    
    def remove_proxy(self, proxy: str):
        """移除代理"""
        for proxy_type in ["http", "socks5"]:
            if proxy in self.proxies.get(proxy_type, []):
                self.proxies[proxy_type].remove(proxy)
                self._save_config()
                print(f"✅ 已移除代理: {proxy}")
                return
        print(f"❌ 代理不存在: {proxy}")
    
    def get_all_proxies(self) -> List[str]:
        """获取所有代理"""
        proxies = []
        proxies.extend(self.proxies.get("http", []))
        proxies.extend(self.proxies.get("socks5", []))
        return proxies
    
    def get_current_proxy(self) -> Optional[str]:
        """获取当前代理"""
        return self.proxies.get("current")
    
    def rotate_proxy(self) -> Optional[str]:
        """轮换代理"""
        all_proxies = self.get_all_proxies()
        
        if not all_proxies:
            print("⚠️ 代理池为空")
            return None
        
        # 过滤掉失败的代理
        available = [p for p in all_proxies if p not in self.failed_proxies]
        
        if not available:
            # 所有代理都失败了，重置
            self.failed_proxies.clear()
            available = all_proxies
        
        # 选择不同于当前的代理
        current = self.get_current_proxy()
        if current in available and len(available) > 1:
            available.remove(current)
        
        new_proxy = random.choice(available)
        self.proxies["current"] = new_proxy
        self.proxies["last_rotation"] = datetime.now().isoformat()
        self._save_config()
        
        print(f"🔄 切换代理: {new_proxy}")
        return new_proxy
    
    def mark_failed(self, proxy: str):
        """标记代理失败"""
        self.failed_proxies.add(proxy)
        print(f"❌ 标记代理失败: {proxy}")
    
    async def check_proxy(self, proxy: str, test_url: str = "https://httpbin.org/ip") -> dict:
        """检测代理可用性"""
        result = {
            "proxy": proxy,
            "available": False,
            "response_time": None,
            "ip": None,
            "error": None
        }
        
        try:
            import time
            start = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    test_url,
                    proxy=proxy,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False
                ) as resp:
                    result["response_time"] = round((time.time() - start) * 1000)
                    
                    if resp.status == 200:
                        data = await resp.json()
                        result["available"] = True
                        result["ip"] = data.get("origin", "unknown")
        
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    async def check_all_proxies(self) -> List[dict]:
        """检测所有代理"""
        results = []
        
        for proxy in self.get_all_proxies():
            result = await self.check_proxy(proxy)
            results.append(result)
            
            if result["available"]:
                print(f"✅ {proxy} - {result['response_time']}ms - {result['ip']}")
            else:
                print(f"❌ {proxy} - {result['error']}")
        
        return results
    
    def get_status(self) -> dict:
        """获取代理状态"""
        return {
            "total": len(self.get_all_proxies()),
            "http": len(self.proxies.get("http", [])),
            "socks5": len(self.proxies.get("socks5", [])),
            "current": self.get_current_proxy(),
            "last_rotation": self.proxies.get("last_rotation"),
            "failed": len(self.failed_proxies)
        }


async def main():
    """主函数"""
    manager = ProxyManager()
    
    if len(sys.argv) < 2:
        print("代理/IP 轮换管理")
        print()
        print("用法:")
        print("  python3 proxy_rotator.py status             # 查看状态")
        print("  python3 proxy_rotator.py list               # 列出所有代理")
        print("  python3 proxy_rotator.py add <proxy>        # 添加代理")
        print("  python3 proxy_rotator.py remove <proxy>     # 移除代理")
        print("  python3 proxy_rotator.py rotate             # 轮换代理")
        print("  python3 proxy_rotator.py check              # 检测所有代理")
        print("  python3 proxy_rotator.py current            # 获取当前代理")
        print()
        print("代理格式:")
        print("  HTTP:   http://user:pass@host:port")
        print("  SOCKS5: socks5://user:pass@host:port")
        return
    
    action = sys.argv[1]
    
    if action == "status":
        status = manager.get_status()
        print("📊 代理状态")
        print(f"   总数: {status['total']}")
        print(f"   HTTP: {status['http']}")
        print(f"   SOCKS5: {status['socks5']}")
        print(f"   当前: {status['current'] or '无'}")
        print(f"   失败: {status['failed']}")
        if status['last_rotation']:
            print(f"   上次轮换: {status['last_rotation']}")
    
    elif action == "list":
        proxies = manager.get_all_proxies()
        if proxies:
            current = manager.get_current_proxy()
            for p in proxies:
                marker = " (当前)" if p == current else ""
                print(f"  {p}{marker}")
        else:
            print("代理池为空")
            print()
            print("添加代理示例:")
            print("  python3 proxy_rotator.py add http://127.0.0.1:7890")
    
    elif action == "add":
        if len(sys.argv) < 3:
            print("❌ 请指定代理地址")
            return
        proxy = sys.argv[2]
        proxy_type = "socks5" if "socks5" in proxy else "http"
        manager.add_proxy(proxy, proxy_type)
    
    elif action == "remove":
        if len(sys.argv) < 3:
            print("❌ 请指定代理地址")
            return
        manager.remove_proxy(sys.argv[2])
    
    elif action == "rotate":
        manager.rotate_proxy()
    
    elif action == "check":
        await manager.check_all_proxies()
    
    elif action == "current":
        current = manager.get_current_proxy()
        if current:
            print(current)
        else:
            print("无当前代理")
    
    else:
        print(f"❌ 未知操作: {action}")


if __name__ == "__main__":
    asyncio.run(main())
