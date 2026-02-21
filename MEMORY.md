# 🧠 小鸡记忆系统

## 快速回忆指南

当上下文被压缩后，我可以通过以下方式快速回忆：

### 1. 搜索记忆
```
memory_search "关键词"
```

### 2. 读取特定日期
```
memory_get path="memory/2026-02-08.md"
```

### 3. 查看所有记忆文件
```
ls memory/
```

### 4. 查看技能文档
```
ls skills/
```

## 记忆结构

```
/root/.openclaw/workspace/
├── MEMORY.md              # 长期规则（必读）
├── CRITICAL-CONFIG-RULES.md  # 配置安全规则（必读）
├── credentials/           # 🔐 凭证信息（必读）
│   ├── nodes.md          # 节点SSH/Tailscale信息
│   ├── apis.md           # API密钥汇总
│   └── owner.md          # 主人信息和偏好
├── memory/               # 每日记忆存档
│   └── YYYY-MM-DD.md
├── skills/               # 技能文档
│   └── *.md
└── scripts/              # 可执行脚本
    └── *.py
```

## ⚠️ 上下文压缩后必读

1. `credentials/owner.md` - 知道主人是谁
2. `credentials/nodes.md` - 节点SSH信息
3. `credentials/apis.md` - API凭证
4. `CRITICAL-CONFIG-RULES.md` - 配置安全
5. 最近的 `memory/*.md` - 近期工作

## 自动备份

脚本 `scripts/context_backup.py` 可以：
- 生成结构化的每日摘要
- 自动推送到 GitHub

使用方法：
```bash
python3 scripts/context_backup.py '{"summary": "今日摘要..."}'
```

## 重要规则提醒

**每次压缩后必读：**
1. `CRITICAL-CONFIG-RULES.md` - 配置安全规则
2. `MEMORY.md` - 用户偏好和教训
3. 最近的 `memory/*.md` - 近期工作内容

## 用户偏好

- **称呼**：AI 叫"小鸡"，用户叫"你"
- **语言**：必须用中文回应
- **完成任务后**：主动汇报，不静默等待
- **配置修改**：先验证，优先用脚本

## 教训记录

### ⚠️ 【最重要】配置文件修改规则

**详见：`CRITICAL-CONFIG-RULES.md`**

> **黄金法则**：没有验证通过或百分百确认，**绝对不得修改 openclaw.json 文件**！

### 🎯 【重要】输出大小控制规则

**详见：`CRITICAL-OUTPUT-CONTROL.md`**

> **核心原则**：主动控制所有工具输出大小，防止session累积过大导致400错误！

**强制执行**：
- ✅ read 必须加 `limit` 参数
- ✅ 日志查看用 `grep` + `tail`
- ✅ 配置查看用 `jq` 提取
- ✅ 单次输出 ≤2000字符

### 🔧 【重要】OpenClaw配置技巧

#### 修改上下文大小
- ❌ 不要改 `sessions.json` → Gateway重启会覆盖
- ✅ 用 `agents.defaults.contextTokens` 配置字段
- ✅ 用 `config.patch` 安全更新

#### 模型名称必须精确
- ❌ 不要猜模型名，先用API查询：`curl .../v1/models | jq '.data[].id'`
- ✅ 例：`claude-opus-4-6-thinking` 而不是 `gemini-claude-opus-4-6-thinking`
- ⚠️ 错误的模型名会导致502错误

#### 查看所有可用配置字段
- ✅ `gateway config.schema` → 查看完整schema
- ✅ 关键字段：`agents.defaults.contextTokens`、`agents.defaults.model.primary`

#### CLIProxyAPI升级流程
1. 备份当前二进制：`cp cli-proxy-api cli-proxy-api.vX.X.X.backup`
2. 查API获取下载链接：`curl -s "https://api.github.com/repos/router-for-me/CLIProxyAPI/releases/tags/vX.X.X" | grep browser_download_url`
3. 下载tar.gz（不是单独的二进制）
4. 解压替换：`tar -xzf xxx.tar.gz cli-proxy-api`
5. 重启服务：`systemctl restart cliproxyapi`
6. ⚠️ **升级期间OpenClaw会断连** → 需要备用API路线

### 📝 【重要】及时同步规则

> **每次操作后**：必须将学到的技能、确定的规则、获得的配置及时同步到本地记忆文件和GitHub！

**同步检查清单**：
- [ ] 更新 `MEMORY.md`（长期规则/技能）
- [ ] 更新 `memory/YYYY-MM-DD.md`（当日记录）
- [ ] `git add -A && git commit && git push`

**2026-02-12补充教训**：出现“先回复用户、后补同步”的延迟，属于流程违规；今后必须在任务收尾阶段立刻完成本地+GitHub同步再汇报完成。

- 修改 openclaw.json 极易导致 Gateway 断连/无限重启
- 必须先查 Schema 确认字段存在
- 用独立脚本能解决的问题，不要改配置
- 必须改配置时，先在**皮特**或**萝卜**上验证
- 出现问题立即汇报，不静默重试

### 2026-02-07 重启事故
- **原因**: 配置 hooks 时添加了无效字段 `hooks.port`
- **后果**: Gateway 无限重启，小鸡完全失联
- **修复**: `openclaw doctor --fix`
- **教训**: 配置验证失败 = 服务崩溃

## 节点分工

```
萝卜(开发) → 皮特(验证) → 小鸡(最终核对)
```

| 节点 | 定位 | 架构 | 说明 |
|------|------|------|------|
| **萝卜** | 🔧 开发 | ARM64 | 新功能/脚本开发 |
| **皮特** | ✅ 验证 | x86_64 | 测试验证、生产任务 |
| **小鸡** | 🎯 核对 | Gateway | 最终审核确认 |

## 定时任务

| 任务 | 时间(北京) | 节点 | 通知 |
|------|-----------|------|------|
| xsijishe签到 | 00:00 | 皮特 | ✅ Telegram |
| pvew5回帖 | 01:00 | 皮特 | ✅ Telegram |
| 每日全球热点简报 | 09:00 | 本地 | ✅ Telegram + 邮件 |
| X每日任务-美国晚上 | 12:00 (04:00 UTC) | 萝卜 | ✅ Telegram |
| X每日任务-美国中午 | 04:00次日 (20:00 UTC) | 萝卜 | ✅ Telegram |
| Daily Git Sync | 08:00 (00:00 UTC) | 本地 | ✅ Telegram |

## 当前模型配置

| 模型ID | 上下文 | 用途 |
|--------|-------|------|
| claude-opus-4-6-thinking | 1M | **默认模型** |
| gemini-claude-opus-4-5-thinking | 200k | 备用 |
| gemini-claude-sonnet-4-5-thinking | 200k | 备用 |
| gemini-claude-sonnet-4-5 | 200k | 备用 |
| gemini-3-pro-preview | 200k | 备用 |
| gpt-5.2-codex | 200k | subagent默认 |

**API**: CLIProxyAPI v6.8.8 @ 萝卜节点  
**contextTokens**: 1,000,000 (通过agents.defaults.contextTokens设置)

## CLIProxyAPI版本

- **当前**: v6.8.8 (2026-02-09)
- **备份**: v6.8.5 在萝卜节点 `/root/cliproxyapi/cli-proxy-api.v6.8.5.backup`
- **已知问题**: #1433 (280KB请求截断) - **实际是Nginx问题，非CPA问题**
- **升级策略**: 已升级到v6.8.8

### 280KB问题真相（2026-02-10确认）
- ❌ **不是CPA的限制** - 开发者确认CPA上行无请求体大小限制，下行缓冲50MB
- ✅ **是Nginx配置缺失** - `xiaoji.caopi.de.conf`没有设置`client_max_body_size`
- ✅ **已修复** - 添加了`client_max_body_size 100M;`
- 📝 **Nginx默认**：`client_max_body_size`默认1MB

## 凭证位置（已脱敏）

- Gmail: `scripts/gmail_client.py` (zbobo9001@gmail.com)
- 和风天气 API: `scripts/qweather.py`
- 皮特 .env: `/root/.openclaw/workspace/.env`

## 2026-02-18 关键运维结论（X 自动任务）

- ⚠️ 当前版本周期 cron（`kind=cron`）存在“`nextRunAtMs`滚动但不落 `runs` 执行记录”的漏触发风险。
- ✅ `kind=at` 一次性任务可稳定自动执行并写入 `/root/.openclaw/cron/runs/*.jsonl`。
- ✅ 已临时重构：
  - 关闭旧的两条周期 X 任务（`0cdb...`、`ba97...`）。
  - 改为“AT 预排程”7天窗口（中午20:00 UTC + 晚上04:00 UTC），每次都带 Telegram 回报。
- ✅ X 执行链路统一为 SSH 直连萝卜执行 `python3 -u /root/x_daily.py`。
- ✅ 汇报规范：必须拿到最终 rc（禁止“still running”提前报成功）。
- 后续：修复周期 cron 漏触发后，再考虑迁回 `kind=cron`。
- 🔴 追加（同日）：用户确认 X 账号已冻结后，已紧急停用全部 X 自动任务（含 AT 预排程），先人工解封与通过安全验证，再恢复自动化。

## 2026-02-19 关键交付（Agent Team 控制台）

- ✅ 在萝卜节点上线浏览器可访问的 Agent Team 控制台：`https://agent.caopi.de`。
- ✅ 已完成独立 Nginx 站点与 Let’s Encrypt 证书（`agent.caopi.de`）。
- ✅ 功能覆盖：账号密码登录、任务创建/启动/停止/重置、进度看板、日志查看、并发控制（默认4）。
- ✅ 已支持页面内动态调整并发（1-16，实时生效）并补全中文提示文案。
- ✅ 已补充任务类型/角色下拉的中文注释（英文标识 + 中文释义），降低配置门槛。
- ✅ 已将“执行命令”改为新手友好的“业务模板 + 一键填充命令 + 高级模式”双轨交互。
- ✅ 已修复任务创建页“自动刷新导致输入丢失”问题（改为空闲刷新 + 可手动开关）。
- ✅ 已支持任务产物浏览器下载（统一产物目录 `/opt/agent-team-console/artifacts` + 下载页）。
- ✅ 已升级为“任务级上传/下载”：新建任务可上传附件，任务详情页可按任务直接下载 input/output 文件。
- ✅ 控制台新建任务页已支持“口语化任务单”（大段描述+期望交付+附件），高级命令/路径默认折叠，模板可自动生成命令。
- ✅ 交付页新增“交付总览”与一键下载；首页新增“业务阶段看板”（当前精简为：待处理/执行中/待确认，失败以返工标签标记）。
- ✅ 已新增平台级“全局角色中心 + 工作流模板中心”，角色/模板可复用到所有任务（不再按单任务临时造角色）。
- ✅ 控制台完成整站UI重排（首页/任务详情/产物页/登录页），信息层级与可读性明显提升。
- ✅ 角色中心已支持按角色独立模型/API；当前策略：`@verifier` 保持 `gpt-5.3-codex`，其余主角色使用 `MiniMax-M2.5`（中国区端点）。
- ✅ 任务列表已支持“删除任务”（含日志与任务产物清理，运行中保护）。
- ✅ 控制台时间展示已切换为北京时间（UTC+8），看板标题改为“#ID+标题”并去掉蓝色下划线风格。
- ✅ 已落地“真多Agent独立会话执行链路”（按工作流阶段分配角色、角色各自模型/API、分阶段产物与会话审计）。
- ✅ 已完成“混合模型”联调跑通（`@verifier=gpt-5.3-codex`，其余角色=`MiniMax-M2.5`；`dev_test_verify` 任务 rc=0）。
- ✅ 多Agent角色词（system prompt）已补齐并落库，角色会话调用优先使用各自角色词。
- ✅ 多Agent已支持“复核FAIL自动打回重跑”闭环，并带最大返工轮次限制（当前默认5）防止无限循环。
- ✅ 内置工作流已改为“Lead先接收需求并分发”（需求接收与分发为第一阶段），再交由开发/测试/验证/交付角色顺序处理。
- ✅ 多Agent已支持“Lead动态分发 + 每阶段质控打回”（@verifier 阶段质控 FAIL 打回当前阶段，带重试上限）。
- ✅ 任务详情页已新增“Lead 分发与复核轨迹”卡片（动态分发/返工/质控统计可视化）。
- ✅ 轨迹卡片已补充“实际调用角色 + 阶段执行轨迹（角色/模型/状态）”明细，降低误读。
- ✅ 详情轨迹新增“本轮需求分析角色/模型 + 每步骤耗时(s)”并隐藏“目录与环境变量”卡片。
- ✅ 失败任务详情已新增“失败原因 + 关键证据 + 处理建议”诊断区，便于快速定位与修复。
- ✅ 多Agent执行阶段已接入“角色工具执行桥”（run_command/final 协议 + 实际命令执行回传 + 安全拦截）。
- ✅ 已为“爬取/关键词/文包”任务加入执行产物硬校验；并对该类 custom_brief 任务自动路由到 `novel_multiagent` 专用链路。
- ✅ 已新增“小红书虚拟产品高频词”业务模板（任务级产物输出 md/json）。
- ✅ 已为小红书模板增加风控识别+strict 质量闸门，防止“拦截页词频”伪结果。
- ✅ 小红书模板已支持更深采样参数与相关词扩展参数（用于扩大关键词源）。
- ✅ 已增加“小说域噪声过滤 + 领域命中率校验”参数，降低无关词污染。
- ✅ 已追加“小说域噪声模式过滤（素材/变现/账号等）+ 相关词扩展按域过滤”，继续纯化结果。
- ✅ Lead 分发机制已升级为“先评估再分配”：支持 `active_stages/skip_stages`，可按任务只执行必要角色，并在审计中记录被跳过阶段。
- ✅ 小说流水线已补“最近7天采样硬门槛”（`min_recent_7d`）并修复“strict未通过仍返回rc=0”漏洞；默认任务命令已强制 `--min-recent-7d 7`。
- ✅ 每次重跑已增加 `run_id` 日志前缀 + 自动清理旧输出/角色会话；停止任务改为进程组级终止，减少残留子进程导致的结果混杂。
- ✅ 小红书采集已新增“频控识别+反拦截自适应轮次”（降速、关键词级冷却重试、禁扩词切换），避免被拦截后机械重跑。
- ✅ Agent Team 已收敛为四角色精简架构：`Lead Agent(gpt-5.3-codex)` + `frontend(MiniMax-M2.5)` + `backend(gpt-5.3-codex)` + `reviewer(gpt-5.3-codex)`；仅保留 `intelligent_dual` 工作流（Lead评估调度，前后端执行，reviewer复核打回）。
- ✅ 控制台完成“去臃肿”连续改造：主页新增快速筛选、角色/工作流/提示默认折叠，并重排为 chatgpt 风格的“轻侧栏+主工作区”；任务详情支持按运行ID与异常过滤日志。
- ✅ 主页侧栏已升级为深色风格，任务概览支持点击即筛选，补齐“概览不可点”的交互短板。
- ✅ 已完成整页视觉协调修复（统一配色Token、顶栏与侧栏同层级、交互反馈一致），减少“拼接感”。
- ✅ 任务详情页已同步重构为与主页一致的布局体系（深色侧栏+浅色主区），信息层级更清晰。
- ✅ 已补充“小说爆款文包”生成脚本（关键词报告 + 标题/开头模板 + 打包下载）。
- ✅ 已上线“小说类目多Agent复核流水线”（Collector/Cleaner/Reviewer/Packager）。
- ✅ 多Agent产物已支持中文文件名与 zip/7z 可选压缩（默认 zip，7z 不可用时自动回退 zip）。
- ✅ 已修复模板默认路径与部署路径不一致导致的 `rc=1`（默认项目路径改为运行时工作目录）。
- ✅ 代码已同步 GitHub（提交 `df2deff`）。
