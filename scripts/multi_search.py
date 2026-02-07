#!/usr/bin/env python3
"""
多源搜索引擎集成脚本
整合 Brave、Exa、Tavily 的搜索结果
"""

import requests
import json
import sys
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# API 配置
BRAVE_API_KEY = "BSAE-ShJ1YElUxKC_QmZKqvNaMoFc9I"
EXA_API_KEY = "1c0d0b70-108e-4e2b-abd8-6ae88705e8f8"
TAVILY_API_KEY = "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"

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
EXA_ENDPOINT = "https://api.exa.ai/search"
TAVILY_ENDPOINT = "https://api.tavily.com/search"


def search_brave(query: str, count: int = 5) -> List[Dict[str, Any]]:
    """使用 Brave Search API 搜索"""
    try:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": BRAVE_API_KEY
        }
        params = {"q": query, "count": count}
        
        response = requests.get(BRAVE_ENDPOINT, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        for item in data.get("web", {}).get("results", [])[:count]:
            results.append({
                "source": "brave",
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "published": item.get("age", "")
            })
        
        return results
    except Exception as e:
        print(f"[Brave Error] {e}", file=sys.stderr)
        return []


def search_exa(query: str, count: int = 5) -> List[Dict[str, Any]]:
    """使用 Exa API 搜索"""
    try:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": EXA_API_KEY
        }
        payload = {
            "query": query,
            "num_results": count,
            "use_autoprompt": True,
            "type": "neural"  # 使用神经搜索
        }
        
        response = requests.post(EXA_ENDPOINT, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        for item in data.get("results", [])[:count]:
            results.append({
                "source": "exa",
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("text", ""),
                "score": item.get("score", 0),
                "published": item.get("published_date", "")
            })
        
        return results
    except Exception as e:
        print(f"[Exa Error] {e}", file=sys.stderr)
        return []


def search_tavily(query: str, count: int = 5) -> List[Dict[str, Any]]:
    """使用 Tavily API 搜索"""
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "api_key": TAVILY_API_KEY,
            "query": query,
            "max_results": count,
            "search_depth": "advanced",  # 深度搜索
            "include_answer": True,
            "include_raw_content": False
        }
        
        response = requests.post(TAVILY_ENDPOINT, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        # 添加 AI 生成的答案（如果有）
        if data.get("answer"):
            results.append({
                "source": "tavily_ai_answer",
                "title": "AI Generated Answer",
                "url": "",
                "description": data["answer"],
                "score": 1.0
            })
        
        # 添加搜索结果
        for item in data.get("results", [])[:count]:
            results.append({
                "source": "tavily",
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("content", ""),
                "score": item.get("score", 0),
                "published": item.get("published_date", "")
            })
        
        return results
    except Exception as e:
        print(f"[Tavily Error] {e}", file=sys.stderr)
        return []


def multi_search(query: str, max_results_per_source: int = 5) -> Dict[str, Any]:
    """
    并发搜索所有来源
    
    Args:
        query: 搜索关键词
        max_results_per_source: 每个来源返回的最大结果数
    
    Returns:
        综合搜索结果字典
    """
    all_results = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(search_brave, query, max_results_per_source): "brave",
            executor.submit(search_exa, query, max_results_per_source): "exa",
            executor.submit(search_tavily, query, max_results_per_source): "tavily"
        }
        
        for future in as_completed(futures):
            source_name = futures[future]
            try:
                results = future.result()
                all_results.extend(results)
            except Exception as e:
                print(f"[{source_name} Thread Error] {e}", file=sys.stderr)
    
    # 去重（基于 URL）
    seen_urls = set()
    unique_results = []
    
    for item in all_results:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(item)
        elif not url:  # AI 答案等无 URL 的项
            unique_results.append(item)
    
    return {
        "query": query,
        "total_results": len(unique_results),
        "sources_used": ["brave", "exa", "tavily"],
        "results": unique_results
    }


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("Usage: multi_search.py <query> [max_results_per_source]")
        sys.exit(1)
    
    query = sys.argv[1]
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    print(f"🔍 搜索中: {query}\n", file=sys.stderr)
    
    results = multi_search(query, max_results)
    
    # 输出 JSON 到 stdout（供 OpenClaw 解析）
    print(json.dumps(results, ensure_ascii=False, indent=2))
    
    # 输出统计到 stderr
    print(f"\n✅ 共找到 {results['total_results']} 条结果", file=sys.stderr)
    print(f"📊 来源分布:", file=sys.stderr)
    
    source_count = {}
    for item in results["results"]:
        source = item["source"]
        source_count[source] = source_count.get(source, 0) + 1
    
    for source, count in source_count.items():
        print(f"  - {source}: {count} 条", file=sys.stderr)


if __name__ == "__main__":
    main()
