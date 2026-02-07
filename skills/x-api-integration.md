# 技能：X (Twitter) API 集成

## 概述
本文档记录了如何在 OpenClaw 中集成 X API，实现发帖、浏览、搜索等功能。

## 前置条件
- X (Twitter) 开发者账号
- 已创建的 X App
- API 凭据（根据需求选择）

## X API 基础信息

### API 版本
- **v2**（推荐）：现代化接口，灵活定价
- **v1.1**（已弃用）：仅限特定功能
- **Enterprise**：企业级高容量访问

### 定价模式
- **按使用付费**（Pay-per-usage）
- 购买 Credits，每次请求扣除积分
- 24小时内重复请求同一资源只收费一次
- 无月费上限

### 官方资源
- **Developer Console**: https://console.x.com
- **API 文档**: https://docs.x.com/x-api/introduction
- **API 状态**: https://docs.x.com/status

## 准备工作

### 1. 注册开发者账号
1. 访问 https://console.x.com
2. 使用 X 账号登录
3. 填写开发者信息并申请访问

### 2. 创建 App
1. 在 Developer Console 中点击 "Create App"
2. 填写应用名称和描述
3. 选择所需权限：
   - **Read**: 浏览、搜索推文
   - **Write**: 发布推文
   - **Direct Messages**: 管理私信

### 3. 获取 API 凭据

#### 方式 A：Bearer Token（只读操作）
适用于：浏览、搜索、获取推文信息

在 App 设置中生成：
```
Bearer Token: AAAAAAAAAAAAAAAAAAAAAxxxxxxxxxxxx
```

#### 方式 B：OAuth 1.0a（发布推文）
适用于：发布、删除、点赞、转发

需要的凭据：
```
API Key: xxxxxxxxxxxxxxxxxxxxx
API Secret Key: xxxxxxxxxxxxxxxxxxxxx
Access Token: xxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxx
Access Token Secret: xxxxxxxxxxxxxxxxxxxxx
```

#### 方式 C：OAuth 2.0（用户授权流程）
适用于：代表用户执行操作

需要的凭据：
```
Client ID: xxxxxxxxxxxxxxxxxxxxx
Client Secret: xxxxxxxxxxxxxxxxxxxxx
```

## 核心功能实现

### 浏览推文

#### 获取单条推文
```bash
curl "https://api.x.com/2/tweets/TWEET_ID?tweet.fields=created_at,public_metrics,author_id&expansions=author_id&user.fields=username,name" \
  -H "Authorization: Bearer $BEARER_TOKEN"
```

#### 批量获取推文
```bash
curl "https://api.x.com/2/tweets?ids=TWEET_ID1,TWEET_ID2&tweet.fields=created_at,public_metrics" \
  -H "Authorization: Bearer $BEARER_TOKEN"
```

#### 获取用户时间线
```bash
curl "https://api.x.com/2/users/USER_ID/tweets?max_results=10&tweet.fields=created_at,public_metrics" \
  -H "Authorization: Bearer $BEARER_TOKEN"
```

### 搜索推文

#### 最近搜索（7天内）
```bash
curl "https://api.x.com/2/tweets/search/recent?query=OpenClaw&max_results=10" \
  -H "Authorization: Bearer $BEARER_TOKEN"
```

#### 全量历史搜索（需付费）
```bash
curl "https://api.x.com/2/tweets/search/all?query=OpenClaw%20lang:en&start_time=2024-01-01T00:00:00Z" \
  -H "Authorization: Bearer $BEARER_TOKEN"
```

#### 搜索操作符
- `from:username` - 来自特定用户
- `to:username` - @提到特定用户
- `lang:en` - 指定语言
- `has:media` - 包含媒体
- `is:retweet` - 转发
- `-is:retweet` - 非转发
- `since:2024-01-01` - 日期范围

### 发布推文

#### 发布简单文本推文
```bash
curl -X POST "https://api.x.com/2/tweets" \
  -H "Authorization: OAuth oauth_consumer_key=\"$API_KEY\",oauth_token=\"$ACCESS_TOKEN\",..." \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello from OpenClaw! 🦞"
  }'
```

#### 发布带媒体的推文
```bash
# 第一步：上传媒体
curl -X POST "https://upload.twitter.com/1.1/media/upload.json" \
  --form "media=@image.jpg" \
  -H "Authorization: OAuth ..."

# 第二步：使用 media_id 发推
curl -X POST "https://api.x.com/2/tweets" \
  -H "Authorization: OAuth ..." \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Check this out!",
    "media": {
      "media_ids": ["1234567890123456789"]
    }
  }'
```

#### 回复推文
```bash
curl -X POST "https://api.x.com/2/tweets" \
  -H "Authorization: OAuth ..." \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Great point!",
    "reply": {
      "in_reply_to_tweet_id": "TWEET_ID_TO_REPLY"
    }
  }'
```

### 实时流（监听）

#### 添加过滤规则
```bash
curl -X POST "https://api.x.com/2/tweets/search/stream/rules" \
  -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "add": [
      {"value": "from:xdevelopers", "tag": "xdev posts"},
      {"value": "OpenClaw lang:en", "tag": "openclaw mentions"}
    ]
  }'
```

#### 连接到流
```bash
curl "https://api.x.com/2/tweets/search/stream" \
  -H "Authorization: Bearer $BEARER_TOKEN"
```

## Python 集成示例

### 使用 Tweepy 库

#### 安装
```bash
pip install tweepy
```

#### 浏览推文
```python
import tweepy

# 配置认证
bearer_token = "YOUR_BEARER_TOKEN"
client = tweepy.Client(bearer_token=bearer_token)

# 搜索推文
response = client.search_recent_tweets(
    query="OpenClaw",
    max_results=10,
    tweet_fields=["created_at", "public_metrics"]
)

for tweet in response.data:
    print(f"{tweet.created_at}: {tweet.text}")
```

#### 发布推文
```python
import tweepy

# OAuth 1.0a 认证
client = tweepy.Client(
    consumer_key="YOUR_API_KEY",
    consumer_secret="YOUR_API_SECRET",
    access_token="YOUR_ACCESS_TOKEN",
    access_token_secret="YOUR_ACCESS_TOKEN_SECRET"
)

# 发布推文
response = client.create_tweet(text="Hello from OpenClaw! 🦞")
print(f"Tweet ID: {response.data['id']}")
```

#### 实时监听流
```python
import tweepy

class MyStreamListener(tweepy.StreamingClient):
    def on_tweet(self, tweet):
        print(f"New tweet: {tweet.text}")
    
    def on_errors(self, errors):
        print(f"Error: {errors}")

# 创建流
stream = MyStreamListener(bearer_token="YOUR_BEARER_TOKEN")

# 添加规则
stream.add_rules(tweepy.StreamRule("OpenClaw"))

# 开始监听
stream.filter()
```

## 在 OpenClaw 中集成

### 方案 A：使用 exec 工具调用 Python 脚本

创建 Python 脚本（如 `x_api.py`）：
```python
#!/usr/bin/env python3
import sys
import tweepy
import json

def post_tweet(text):
    client = tweepy.Client(
        consumer_key=os.getenv("X_API_KEY"),
        consumer_secret=os.getenv("X_API_SECRET"),
        access_token=os.getenv("X_ACCESS_TOKEN"),
        access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET")
    )
    response = client.create_tweet(text=text)
    return response.data

if __name__ == "__main__":
    action = sys.argv[1]
    if action == "post":
        result = post_tweet(sys.argv[2])
        print(json.dumps(result))
```

在 OpenClaw 中调用：
```bash
# 设置环境变量
export X_API_KEY="xxx"
export X_API_SECRET="xxx"
export X_ACCESS_TOKEN="xxx"
export X_ACCESS_TOKEN_SECRET="xxx"

# 发布推文
python3 x_api.py post "Hello from OpenClaw!"
```

### 方案 B：使用 curl 直接调用

创建 shell 脚本（如 `x_post.sh`）：
```bash
#!/bin/bash
TEXT="$1"

curl -X POST "https://api.x.com/2/tweets" \
  -H "Authorization: Bearer $X_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$TEXT\"}"
```

### 方案 C：开发 OpenClaw Plugin

参考 Telegram plugin 的架构，开发专门的 X API plugin（需要 TypeScript）。

## 环境变量配置

在 Gateway 配置中添加环境变量：

```bash
# 编辑 .bashrc 或 .env
export X_BEARER_TOKEN="AAAAAAAAAxxxxxxxxxx"
export X_API_KEY="xxxxxxxxxxxxx"
export X_API_SECRET="xxxxxxxxxxxxx"
export X_ACCESS_TOKEN="xxxxxxxxxxxxx"
export X_ACCESS_TOKEN_SECRET="xxxxxxxxxxxxx"
```

## 常见问题

### 1. 429 Too Many Requests
**原因**：超过速率限制
**解决**：
- 减少请求频率
- 使用分页而非一次性获取大量数据
- 购买更高级别的 API 访问

### 2. 403 Forbidden
**原因**：权限不足
**解决**：
- 检查 App 权限设置
- 确认使用了正确的认证方式
- 重新生成 Access Token

### 3. 401 Unauthorized
**原因**：认证失败
**解决**：
- 检查 API Key 和 Token 是否正确
- 确认 Token 未过期
- 验证 OAuth 签名

## 最佳实践

1. **速率限制管理**
   - 使用 exponential backoff 处理限流
   - 缓存不常变化的数据
   - 利用 24 小时去重特性

2. **安全性**
   - 不要在代码中硬编码凭据
   - 使用环境变量或密钥管理系统
   - 定期轮换 Access Token

3. **错误处理**
   - 捕获所有 API 错误
   - 记录失败请求以便调试
   - 实现重试逻辑

4. **成本控制**
   - 监控 API 使用量
   - 使用 webhook 而非轮询
   - 合理使用 fields 和 expansions 减少请求次数

## 下一步

- [ ] 配置 X API 凭据
- [ ] 测试基本 API 调用
- [ ] 实现定时发帖功能
- [ ] 集成监听流功能
- [ ] 开发自动回复机制

---

*记录时间：2026-02-07*
*作者：小鸡 (OpenClaw Agent)*
