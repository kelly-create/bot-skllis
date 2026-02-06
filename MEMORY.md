# 项目记忆库 (MEMORY)

## 架构设计
- **主Agent**: Antigravity (Current)
  - 负责：战略决策、复杂推理、任务分发
  - 模型：Gemini 3 Pro / Gemini Claude Sonnet 4.5 Thinking
- **执行节点**: 皮特 (Pete/cjwgx0ermi5b1pl)
  - 负责：本地执行、系统命令、浏览器操作
  - 角色：无独立大脑，作为执行端点
- **协作模式**: Sessions Spawn
  - 主Agent创建临时子Agent
  - 子Agent通过 `nodes` 工具指挥皮特节点
  - 子Agent默认模型：`sydney-proxy/gpt-5.2-codex`

## 基础设施
- **代码仓库**: `kelly-create/bot-skllis` (GitHub)
- **知识库同步**: 通过 Git 仓库同步 MEMORY.md

## 当前状态
- 已配置 10 个 GPT 模型到 Gateway
- 已设置子 Agent 默认使用 GPT-5.2 Codex
- 知识库初始化完成
