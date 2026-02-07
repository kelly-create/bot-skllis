#!/usr/bin/env python3
"""
和风天气 API 集成脚本（简化版）
使用预设城市 ID，支持实时天气、预报、空气质量查询
"""

import requests
import json
import sys
from typing import Dict, Any

# API 配置
API_KEY = "27222a4250fe4df79f8c01109d0e22e1"
API_HOST = "nd3yfrpv26.re.qweatherapi.com"
BASE_URL = f"https://{API_HOST}"

# 常用城市 Location ID 映射
CITIES = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280101",
    "深圳": "101280601",
    "成都": "101270101",
    "杭州": "101210101",
    "重庆": "101040100",
    "西安": "101110101",
    "苏州": "101190401",
    "武汉": "101200101",
    "南京": "101190101",
    "天津": "101030100",
    "郑州": "101180101",
    "长沙": "101250101",
    "沈阳": "101070101",
    "青岛": "101120201",
    "宁波": "101210401",
    "厦门": "101230201",
    "济南": "101120101",
    "哈尔滨": "101050101",
    "福州": "101230101",
    "大连": "101070201",
    "昆明": "101290101",
    "无锡": "101190201",
    "合肥": "101220101",
    "佛山": "101280800",
    "兰州": "101160101",
    "石家庄": "101090101",
    "南宁": "101300101",
    "太原": "101100101",
}


def get_location_id(location: str) -> str:
    """获取城市 ID"""
    # 如果已经是数字ID，直接返回
    if location.isdigit():
        return location
    # 从映射表查找
    return CITIES.get(location, location)


def make_request(endpoint: str, params: Dict[str, str]) -> Dict[str, Any]:
    """通用 API 请求"""
    url = f"{BASE_URL}{endpoint}"
    params["key"] = API_KEY
    
    try:
        headers = {"Accept-Encoding": "gzip"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != "200":
            return {"error": f"API返回错误: code={data.get('code')}", "raw": data}
        
        return data
    except requests.RequestException as e:
        return {"error": str(e)}
    except json.JSONDecodeError as e:
        return {"error": f"JSON解析失败: {e}"}


def get_weather_now(location: str) -> Dict[str, Any]:
    """获取实时天气"""
    location_id = get_location_id(location)
    city_name = location if location in CITIES else f"ID:{location_id}"
    
    data = make_request("/v7/weather/now", {"location": location_id})
    
    if "error" in data:
        return data
    
    now = data["now"]
    return {
        "city": city_name,
        "update_time": data["updateTime"],
        "temperature": f"{now['temp']}°C",
        "feels_like": f"{now['feelsLike']}°C",
        "condition": now["text"],
        "icon": now["icon"],
        "wind": f"{now['windDir']} {now['windScale']}级 ({now['windSpeed']}km/h)",
        "humidity": f"{now['humidity']}%",
        "pressure": f"{now['pressure']}hPa",
        "visibility": f"{now['vis']}km",
        "cloud": f"{now.get('cloud', 'N/A')}%",
        "precip": f"{now.get('precip', '0.0')}mm"
    }


def get_weather_forecast(location: str, days: int = 3) -> Dict[str, Any]:
    """获取天气预报"""
    location_id = get_location_id(location)
    city_name = location if location in CITIES else f"ID:{location_id}"
    
    # 选择端点
    if days <= 3:
        endpoint = "/v7/weather/3d"
    elif days <= 7:
        endpoint = "/v7/weather/7d"
    else:
        endpoint = "/v7/weather/15d"
    
    data = make_request(endpoint, {"location": location_id})
    
    if "error" in data:
        return data
    
    forecasts = []
    for day in data["daily"][:days]:
        forecasts.append({
            "date": day["fxDate"],
            "day": day["textDay"],
            "night": day["textNight"],
            "temp_max": f"{day['tempMax']}°C",
            "temp_min": f"{day['tempMin']}°C",
            "wind_day": f"{day['windDirDay']} {day['windScaleDay']}级",
            "humidity": f"{day['humidity']}%",
            "precip": f"{day['precip']}mm",
            "uv": day.get("uvIndex", "N/A"),
            "sunrise": day.get("sunrise", ""),
            "sunset": day.get("sunset", "")
        })
    
    return {
        "city": city_name,
        "forecast": forecasts
    }


def get_air_quality(location: str) -> Dict[str, Any]:
    """获取空气质量"""
    location_id = get_location_id(location)
    city_name = location if location in CITIES else f"ID:{location_id}"
    
    data = make_request("/v7/air/now", {"location": location_id})
    
    if "error" in data:
        return data
    
    air = data["now"]
    return {
        "city": city_name,
        "update_time": data["updateTime"],
        "aqi": air["aqi"],
        "category": air["category"],
        "level": f"等级 {air['level']}",
        "primary": air.get("primary", "无"),
        "pm2.5": air["pm2p5"],
        "pm10": air["pm10"],
        "no2": air["no2"],
        "so2": air["so2"],
        "co": air["co"],
        "o3": air["o3"]
    }


def get_life_indices(location: str) -> Dict[str, Any]:
    """获取生活指数（全部）"""
    location_id = get_location_id(location)
    city_name = location if location in CITIES else f"ID:{location_id}"
    
    data = make_request("/v7/indices/1d", {"location": location_id, "type": "0"})
    
    if "error" in data:
        return data
    
    indices = {}
    for idx in data["daily"]:
        indices[idx["name"]] = {
            "level": idx["level"],
            "category": idx["category"],
            "text": idx["text"]
        }
    
    return {
        "city": city_name,
        "date": data["daily"][0]["date"] if data["daily"] else "",
        "indices": indices
    }


def get_warning(location: str) -> Dict[str, Any]:
    """获取灾害预警"""
    location_id = get_location_id(location)
    city_name = location if location in CITIES else f"ID:{location_id}"
    
    data = make_request("/v7/warning/now", {"location": location_id})
    
    if "error" in data:
        return data
    
    warnings = []
    for warn in data.get("warning", []):
        warnings.append({
            "title": warn["title"],
            "type": warn["typeName"],
            "level": warn["level"],
            "text": warn["text"],
            "pub_time": warn["pubTime"]
        })
    
    return {
        "city": city_name,
        "count": len(warnings),
        "warnings": warnings
    }


def list_cities():
    """列出支持的城市"""
    print("支持的城市列表：")
    for city, location_id in sorted(CITIES.items()):
        print(f"  {city}: {location_id}")


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("Usage: qweather.py <command> [location] [options]")
        print("\n命令:")
        print("  now <城市>              - 实时天气")
        print("  forecast <城市> [天数]  - 天气预报 (3/7/15天，默认3)")
        print("  air <城市>              - 空气质量")
        print("  indices <城市>          - 生活指数")
        print("  warning <城市>          - 灾害预警")
        print("  cities                  - 列出支持的城市")
        print("\n示例:")
        print("  python3 qweather.py now 北京")
        print("  python3 qweather.py forecast 上海 7")
        print("  python3 qweather.py air 深圳")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "cities":
        list_cities()
        return
    
    if len(sys.argv) < 3:
        print(f"错误: {command} 命令需要指定城市")
        sys.exit(1)
    
    location = sys.argv[2]
    result = {}
    
    if command == "now":
        result = get_weather_now(location)
    elif command == "forecast":
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        result = get_weather_forecast(location, days)
    elif command == "air":
        result = get_air_quality(location)
    elif command == "indices":
        result = get_life_indices(location)
    elif command == "warning":
        result = get_warning(location)
    else:
        result = {"error": f"未知命令: {command}"}
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
