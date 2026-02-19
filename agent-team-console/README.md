# Agent Team Console (MVP)

浏览器任务控制台：创建任务、指派 Agent、启动执行、查看实时进度日志。

## 功能
- 账号密码登录
- 任务创建（类型/优先级/执行者）
- 任务执行（支持命令执行）
- 并发控制（默认 4）
- 状态看板（pending/running/done/failed）
- 任务日志页自动刷新

## 本地运行
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

访问：`http://127.0.0.1:3100`

## 环境变量
- `ATC_ADMIN_USERNAME` 默认 `root`
- `ATC_ADMIN_PASSWORD` 默认 `k5348988`
- `ATC_APP_SECRET` 默认 `change-me-now`
- `ATC_MAX_CONCURRENT` 默认 `4`
- `ATC_WORKDIR` 默认项目目录
- `ATC_DB_PATH` 默认 `data/tasks.db`

## 生产部署建议
- Gunicorn 监听 `127.0.0.1:3100`
- Nginx 反向代理 + HTTPS
- Systemd 托管
