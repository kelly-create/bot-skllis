# 技能：和风天气 API 集成

## 概述
集成和风天气 API，提供实时天气、天气预报、空气质量、生活指数、灾害预警等功能。

## API 配置

- **API Key**: `27222a4250fe4df79f8c01109d0e22e1`
- **API Host**: `nd3yfrpv26.re.qweatherapi.com`（专属域名）
- **文档**: https://dev.qweather.com/docs/api/

## 功能列表

### ✅ 已实现功能

| 功能 | 命令 | 说明 |
|------|------|------|
| **实时天气** | `now <城市>` | 温度、体感、天气状况、风力、湿度等 |
| **天气预报** | `forecast <城市> [天数]` | 3/7/15天预报（默认3天） |
| **生活指数** | `indices <城市>` | 运动、穿衣、洗车、紫外线等指数 |
| **灾害预警** | `warning <城市>` | 台风、暴雨、高温等预警信息 |
| **城市列表** | `cities` | 列出支持的30个主要城市 |

### ⚠️ 受限功能

| 功能 | 状态 | 原因 |
|------|------|------|
| **空气质量** | ❌ 403 Forbidden | 需要更高级别订阅 |
| **城市搜索** | ❌ 不可用 | 端点无响应（使用预设城市表） |

## 使用方法

### 命令行调用

```bash
# 查看实时天气
python3 /root/.openclaw/workspace/scripts/qweather.py now 北京

# 查看7天预报
python3 /root/.openclaw/workspace/scripts/qweather.py forecast 上海 7

# 查看生活指数
python3 /root/.openclaw/workspace/scripts/qweather.py indices 深圳

# 查看灾害预警
python3 /root/.openclaw/workspace/scripts/qweather.py warning 广州

# 列出支持的城市
python3 /root/.openclaw/workspace/scripts/qweather.py cities
```

### 在 OpenClaw 中使用

通过 `exec` 工具调用：

```python
# 小鸡可以这样调用
result = exec(
    command="python3 /root/.openclaw/workspace/scripts/qweather.py now 北京"
)
```

## 支持的城市

当前支持 **30 个主要城市**：

| 城市 | Location ID | 城市 | Location ID |
|------|-------------|------|-------------|
| 北京 | 101010100 | 上海 | 101020100 |
| 广州 | 101280101 | 深圳 | 101280601 |
| 成都 | 101270101 | 杭州 | 101210101 |
| 重庆 | 101040100 | 西安 | 101110101 |
| 苏州 | 101190401 | 武汉 | 101200101 |
| 南京 | 101190101 | 天津 | 101030100 |
| 郑州 | 101180101 | 长沙 | 101250101 |
| 沈阳 | 101070101 | 青岛 | 101120201 |
| 宁波 | 101210401 | 厦门 | 101230201 |
| 济南 | 101120101 | 哈尔滨 | 101050101 |
| 福州 | 101230101 | 大连 | 101070201 |
| 昆明 | 101290101 | 无锡 | 101190201 |
| 合肥 | 101220101 | 佛山 | 101280800 |
| 兰州 | 101160101 | 石家庄 | 101090101 |
| 南宁 | 101300101 | 太原 | 101100101 |

> 💡 也可以直接使用 Location ID，例如：`python3 qweather.py now 101010100`

## 输出格式

### 实时天气 (now)

```json
{
  "city": "北京",
  "update_time": "2026-02-07T17:50+08:00",
  "temperature": "0°C",
  "feels_like": "-7°C",
  "condition": "晴",
  "icon": "150",
  "wind": "西风 2级 (11km/h)",
  "humidity": "14%",
  "pressure": "1029hPa",
  "visibility": "30km",
  "cloud": "0%",
  "precip": "0.0mm"
}
```

### 天气预报 (forecast)

```json
{
  "city": "上海",
  "forecast": [
    {
      "date": "2026-02-07",
      "day": "多云",
      "night": "多云",
      "temp_max": "4°C",
      "temp_min": "-1°C",
      "wind_day": "北风 1-3级",
      "humidity": "42%",
      "precip": "0.0mm",
      "uv": "1",
      "sunrise": "06:44",
      "sunset": "17:35"
    }
  ]
}
```

### 生活指数 (indices)

```json
{
  "city": "北京",
  "date": "2026-02-07",
  "indices": {
    "运动指数": {
      "level": "2",
      "category": "较适宜",
      "text": "天气较好，但..."
    },
    "穿衣指数": {...},
    "洗车指数": {...}
  }
}
```

### 灾害预警 (warning)

```json
{
  "city": "广州",
  "count": 1,
  "warnings": [
    {
      "title": "广东省广州市气象台发布雷电黄色预警",
      "type": "雷电",
      "level": "黄色",
      "text": "预计未来6小时内...",
      "pub_time": "2026-02-07T15:30+08:00"
    }
  ]
}
```

## 天气图标代码

和风天气提供图标代码，可用于显示天气图标：

| 代码 | 天气 | 代码 | 天气 |
|------|------|------|------|
| 100 | 晴 | 101 | 多云 |
| 150 | 晴（夜间）| 151 | 多云（夜间）|
| 300 | 阵雨 | 301 | 强阵雨 |
| 305 | 小雨 | 306 | 中雨 |
| 307 | 大雨 | 308 | 极端降雨 |
| 400 | 小雪 | 401 | 中雪 |
| 500 | 薄雾 | 501 | 雾 |

> 完整图标列表: https://dev.qweather.com/docs/resource/icons/

## 扩展城市

如需添加更多城市，编辑 `scripts/qweather.py`：

```python
CITIES = {
    "北京": "101010100",
    "你的城市": "城市ID",  # 新增
    ...
}
```

查找城市 ID：https://github.com/qwd/LocationList

## API 限额

根据和风天气订阅计划：

- **免费版**: 1000次/天
- **开发版**: 16700次/天
- **标准版**: 100万次/月

当前使用的是专属 Host (`nd3yfrpv26.re.qweatherapi.com`)，具体限额取决于订阅。

## 未来扩展

- [ ] 添加更多城市（自动从官方列表导入）
- [ ] 支持空气质量查询（需升级订阅）
- [ ] 添加小时预报功能
- [ ] 天气图表可视化
- [ ] 集成到 OpenClaw native tools
- [ ] 支持多语言（英文、日文等）

---

*创建时间：2026-02-07*
*作者：小鸡 (OpenClaw Agent)*
