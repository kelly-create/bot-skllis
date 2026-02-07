# 项目记忆库 (MEMORY)

## 架构设计
- **主Agent**: Antigravity (Current)
  - 负责：战略决策、复杂推理、任务分发
  - 模型：Gemini 3 Pro / Gemini Claude Sonnet 4.5 Thinking
- **执行节点 1**: 皮特 (Pete/cjwgx0ermi5b1pl, 1C1G x86_64)
  - 负责：轻量级任务、定时签到、配置管理、简单脚本
  - 角色：无独立大脑，作为执行端点
- **执行节点 2**: 萝卜 (ARM-Node-4C6G, 4C6G ARM64)
  - 负责：主力开发、编译、数据处理、重型任务
  - 角色：无独立大脑，作为开发机和性能节点
- **协作模式**: Sessions Spawn
  - 主Agent创建临时子Agent
  - 子Agent通过 `nodes` 工具指挥执行节点
  - 子Agent默认模型：`sydney-proxy/gpt-5.2-codex`

## 基础设施
- **代码仓库**: `kelly-create/bot-skllis` (GitHub)
- **知识库同步**: 通过 Git 仓库同步 MEMORY.md

## 搜索引擎 API 配置
- **Brave Search**: `BSAE-ShJ1YElUxKC_QmZKqvNaMoFc9I` ✅ 已配置
- **Exa API**: `1c0d0b70-108e-4e2b-abd8-6ae88705e8f8` ✅ 已集成
- **Tavily API**: `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` ✅ 已集成

**多源搜索策略**：
- 当前 OpenClaw 内置 `web_search` 仅支持 Brave 和 Perplexity
- Exa 和 Tavily 需通过自定义脚本或未来版本集成
- 已实现：`scripts/multi_search.py` 整合三个 API，返回综合结果

## 天气 API 配置
- **和风天气 API Key**: `27222a4250fe4df79f8c01109d0e22e1` ✅ 已集成
- **专属 Host**: `nd3yfrpv26.re.qweatherapi.com`
- **功能**: 实时天气、预报（3/7/15天）、生活指数、灾害预警
- **支持城市**: 30个主要城市（北京、上海、广州等）
- **脚本**: `scripts/qweather.py`

## 当前状态
- 已配置 10 个 GPT 模型到 Gateway
- 已设置子 Agent 默认使用 GPT-5.2 Codex
- 知识库初始化完成
- 多节点集群（皮特 x86 + 萝卜 ARM64）已就绪
- Brave Search API 已配置并测试通过
- 多源搜索（Brave+Exa+Tavily）已实现并测试通过
- 和风天气 API 已对接并测试通过

## 节点分工策略
- **萝卜**：主力开发、重活
- **皮特**：轻量任务、辅助
- **主**：大脑、验收
