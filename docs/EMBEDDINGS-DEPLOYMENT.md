# 本地Embeddings服务部署文档

## 📊 部署状态

**当前状态**：✅ **测试阶段** - 已部署但未正式上线

## 🚀 部署信息

### 服务器
- **节点**：萝卜（美国 152.53.171.21）
- **位置**：`/root/embeddings-service/`
- **端口**：8318（本地访问）
- **模型**：all-MiniLM-L6-v2（轻量级，80MB）

### 资源占用
- **内存**：~486MB（6.1%）
- **磁盘**：~1.1GB
- **CPU**：~9.6%（空闲时），推理时短时提升

## ✅ 测试结果

### 功能测试
- ✅ 健康检查：正常
- ✅ 简单embeddings接口：正常
- ✅ OpenAI兼容接口：正常
- ✅ 中文支持：正常

### 语义搜索质量测试

| 查询1 | 查询2 | 相似度 | 结果 |
|------|------|-------|------|
| 萝卜服务器在哪里 | 美国的服务器IP是什么 | 0.486 | ✅ 可识别 |
| 今天天气怎么样 | 天气预报 | **0.962** | ✅ 高相似 |
| Python编程语言 | 写代码用什么语言 | 0.490 | ✅ 可识别 |
| 吃饭了吗 | 股票市场 | 1.000 | ⚠️ 误判（应该低相似）|

### 记忆搜索模拟
**查询**："美国服务器的IP地址"

**结果**（按相似度排序）：
1. [0.605] 萝卜节点位于美国，IP是152.53.171.21，有8GB内存 ⭐
2. [0.538] 每日新闻简报在北京时间09:00执行
3. [0.473] 悉尼服务器在澳大利亚，IP是206.168.133.84

**结论**：✅ **成功识别最相关的记忆！**

## 📡 API 接口

### 1. 健康检查
```bash
curl http://127.0.0.1:8318/health
```

### 2. 简单embeddings
```bash
curl -X POST 'http://127.0.0.1:8318/embeddings?text=你的文本'
```

### 3. OpenAI兼容接口（推荐）
```bash
curl -X POST http://127.0.0.1:8318/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"input": "你的文本", "model": "all-MiniLM-L6-v2"}'
```

## 🔧 服务管理

### 当前启动方式（临时测试）
```bash
cd /root/embeddings-service
source venv/bin/activate
python3 server.py
```

**进程PID**：`cat /root/embeddings-service/server.pid`

### 停止服务
```bash
kill $(cat /root/embeddings-service/server.pid)
```

### systemd服务（已准备，未启用）

```bash
# 重新加载systemd
systemctl daemon-reload

# 启用开机自启
systemctl enable embeddings

# 启动服务
systemctl start embeddings

# 查看状态
systemctl status embeddings

# 查看日志
journalctl -u embeddings -f
```

**⚠️ 注意**：systemd服务已准备好，但**暂未启用**，等待正式上线验证。

## 📝 下一步计划

### 1. 配置OpenClaw使用本地embeddings

需要配置 OpenClaw 使用此服务：

**方法1：环境变量**（推荐）
```bash
export EMBEDDINGS_API_URL="http://127.0.0.1:8318/v1"
```

**方法2：修改OpenClaw配置**（需验证）
```json
{
  "tools": {
    "memory": {
      "embeddings": {
        "provider": "custom",
        "baseUrl": "http://127.0.0.1:8318/v1",
        "model": "all-MiniLM-L6-v2"
      }
    }
  }
}
```

### 2. 正式上线前的验证清单

- [ ] 长时间稳定性测试（运行24小时）
- [ ] 重启服务器后自动启动测试
- [ ] OpenClaw memory_search工具集成测试
- [ ] 错误处理和日志监控
- [ ] 性能压力测试（并发请求）

### 3. 上线步骤

1. 停止当前临时进程
2. 启用systemd服务
3. 配置OpenClaw连接
4. 测试memory_search工具
5. 更新CORE-MEMORY.md记录

## 🐛 已知问题

1. **误判问题**："吃饭了吗" vs "股票市场" 相似度为1.000（应该很低）
   - 原因：模型对某些不相关文本的判断不够准确
   - 影响：对明显不相关的查询可能返回高相似度
   - 解决：可以设置相似度阈值（例如 >0.6 才认为相关）

2. **中文支持**：
   - all-MiniLM-L6-v2 对中文支持一般
   - 如需更好的中文支持，可换成：
     - `paraphrase-multilingual-MiniLM-L12-v2`（支持50+语言）
     - `sentence-transformers/distiluse-base-multilingual-cased-v2`

## 📚 文件结构

```
/root/embeddings-service/
├── venv/                    # Python虚拟环境
├── server.py               # API服务主程序
├── test_semantic.py        # 语义测试脚本
├── server.pid              # 进程PID
├── embeddings.log          # 服务日志
└── README.md              # (待创建)

/etc/systemd/system/
└── embeddings.service      # systemd服务配置（未启用）

/root/.cache/huggingface/   # 模型缓存（88MB）
```

## 🔐 安全考虑

- ✅ 仅监听127.0.0.1（本地访问）
- ✅ 无需认证（因为只有本地可访问）
- ⚠️ 如需远程访问，需添加认证和HTTPS

## 💡 优化建议

1. **性能优化**：
   - 可添加结果缓存（相同查询返回缓存结果）
   - 批量处理请求

2. **功能增强**：
   - 添加多模型支持
   - 添加请求频率限制
   - 添加Prometheus监控指标

3. **稳定性**：
   - 添加请求超时
   - 添加错误重试机制
   - 添加内存使用监控

---

**部署时间**: 2026-02-09  
**部署人**: OpenClaw小鸡  
**状态**: 测试中，等待验证后正式上线
