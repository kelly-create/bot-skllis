#!/usr/bin/env python3
import os
import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("ATC_DB_PATH", os.path.join(BASE_DIR, "data", "tasks.db"))
ADMIN_USERNAME = os.getenv("ATC_ADMIN_USERNAME", "root")
ADMIN_PASSWORD = os.getenv("ATC_ADMIN_PASSWORD", "k5348988")
APP_SECRET = os.getenv("ATC_APP_SECRET", "change-me-now")
WORKDIR = os.getenv("ATC_WORKDIR", BASE_DIR)
DEFAULT_MAX_CONCURRENT = int(os.getenv("ATC_MAX_CONCURRENT", "4"))

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

app = Flask(__name__)
app.secret_key = APP_SECRET

running_processes = {}


class ConcurrencyLimiter:
    def __init__(self, limit: int):
        self._limit = max(1, int(limit))
        self._running = 0
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)

    @contextmanager
    def acquire(self):
        with self._cond:
            while self._running >= self._limit:
                self._cond.wait(timeout=1)
            self._running += 1
        try:
            yield
        finally:
            with self._cond:
                self._running -= 1
                self._cond.notify_all()

    def set_limit(self, limit: int):
        with self._cond:
            self._limit = max(1, int(limit))
            self._cond.notify_all()

    def get_limit(self) -> int:
        with self._lock:
            return self._limit

    def get_running(self) -> int:
        with self._lock:
            return self._running


limiter = ConcurrencyLimiter(DEFAULT_MAX_CONCURRENT)


def now_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


@contextmanager
def db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                task_type TEXT,
                assignee TEXT,
                priority TEXT DEFAULT 'P2',
                status TEXT DEFAULT 'pending',
                command TEXT,
                created_at TEXT,
                updated_at TEXT,
                started_at TEXT,
                finished_at TEXT,
                return_code INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                ts TEXT,
                line TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
            """
        )


def get_setting(key: str, default_value: str = "") -> str:
    with db_conn() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default_value
    return row["value"]


def set_setting(key: str, value: str):
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_settings(key, value, updated_at)
            VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, str(value), now_str()),
        )


def sync_runtime_settings():
    raw = get_setting("max_concurrent", str(DEFAULT_MAX_CONCURRENT))
    try:
        val = max(1, min(16, int(raw)))
    except Exception:
        val = DEFAULT_MAX_CONCURRENT
    set_setting("max_concurrent", str(val))
    limiter.set_limit(val)


def append_log(task_id: int, line: str):
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO task_logs(task_id, ts, line) VALUES(?,?,?)",
            (task_id, now_str(), line[:4000]),
        )


def update_task(task_id: int, **fields):
    if not fields:
        return
    fields["updated_at"] = now_str()
    keys = list(fields.keys())
    vals = [fields[k] for k in keys]
    clause = ", ".join([f"{k}=?" for k in keys])
    with db_conn() as conn:
        conn.execute(f"UPDATE tasks SET {clause} WHERE id=?", vals + [task_id])


def get_task(task_id: int):
    with db_conn() as conn:
        return conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


def run_task(task_id: int):
    task = get_task(task_id)
    if not task:
        running_processes.pop(task_id, None)
        return

    with limiter.acquire():
        update_task(task_id, status="running", started_at=now_str(), return_code=None)
        append_log(task_id, f"[SYSTEM] 任务启动，当前并发上限={limiter.get_limit()}")

        cmd = (task["command"] or "").strip()
        if not cmd:
            try:
                for step in [
                    "Lead Agent 正在拆解任务...",
                    "Backend Agent 正在生成接口变更草案...",
                    "Frontend Agent 正在生成页面改动草案...",
                    "QA Agent 正在准备回归测试...",
                    "Lead Agent 正在汇总结果...",
                ]:
                    if task_id in running_processes and running_processes[task_id] is None:
                        raise RuntimeError("任务被手动停止")
                    append_log(task_id, step)
                    time.sleep(2)
                update_task(task_id, status="done", finished_at=now_str(), return_code=0)
                append_log(task_id, "[SYSTEM] 任务完成（演示模式）")
            except Exception as e:
                update_task(task_id, status="failed", finished_at=now_str(), return_code=1)
                append_log(task_id, f"[SYSTEM] 任务失败：{e}")
            finally:
                running_processes.pop(task_id, None)
            return

        try:
            append_log(task_id, f"[SYSTEM] 执行命令: {cmd}")
            proc = subprocess.Popen(
                cmd,
                shell=True,
                cwd=WORKDIR,
                executable="/bin/bash",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            running_processes[task_id] = proc

            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                append_log(task_id, line.rstrip())

            rc = proc.wait()
            update_task(
                task_id,
                status="done" if rc == 0 else "failed",
                finished_at=now_str(),
                return_code=rc,
            )
            append_log(task_id, f"[SYSTEM] 任务结束，rc={rc}")
        except Exception as e:
            update_task(task_id, status="failed", finished_at=now_str(), return_code=1)
            append_log(task_id, f"[SYSTEM] 执行异常：{e}")
        finally:
            running_processes.pop(task_id, None)


def start_task(task_id: int):
    if task_id in running_processes:
        return False, "任务已在运行或排队中"
    task = get_task(task_id)
    if not task:
        return False, "任务不存在"
    if task["status"] == "running":
        return False, "任务状态已是 running"

    running_processes[task_id] = None
    t = threading.Thread(target=run_task, args=(task_id,), daemon=True)
    t.start()
    return True, "已启动（如并发已满会自动排队）"


@app.before_request
def _attach_globals():
    g.max_concurrent = limiter.get_limit()
    g.active_workers = limiter.get_running()


@app.route("/healthz")
def healthz():
    return {
        "ok": True,
        "time": now_str(),
        "maxConcurrent": limiter.get_limit(),
        "activeWorkers": limiter.get_running(),
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("dashboard"))
        flash("账号或密码错误")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    with db_conn() as conn:
        tasks = conn.execute(
            "SELECT * FROM tasks ORDER BY CASE status WHEN 'running' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, id DESC"
        ).fetchall()

        stats = {
            "pending": conn.execute("SELECT COUNT(*) c FROM tasks WHERE status='pending'").fetchone()["c"],
            "running": conn.execute("SELECT COUNT(*) c FROM tasks WHERE status='running'").fetchone()["c"],
            "done": conn.execute("SELECT COUNT(*) c FROM tasks WHERE status='done'").fetchone()["c"],
            "failed": conn.execute("SELECT COUNT(*) c FROM tasks WHERE status='failed'").fetchone()["c"],
        }

    queue_count = max(0, len(running_processes) - limiter.get_running())
    return render_template(
        "dashboard.html",
        tasks=tasks,
        stats=stats,
        running_count=len(running_processes),
        queue_count=queue_count,
    )


@app.post("/settings/concurrency")
@login_required
def set_concurrency():
    raw = (request.form.get("max_concurrent") or "").strip()
    try:
        val = int(raw)
    except Exception:
        flash("并发上限必须是数字（1-16）")
        return redirect(url_for("dashboard"))

    if val < 1 or val > 16:
        flash("并发上限范围必须在 1-16")
        return redirect(url_for("dashboard"))

    set_setting("max_concurrent", str(val))
    limiter.set_limit(val)
    flash(f"并发上限已更新为 {val}（即时生效，无需重启）")
    return redirect(url_for("dashboard"))


@app.post("/tasks")
@login_required
def create_task():
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("标题不能为空")
        return redirect(url_for("dashboard"))

    description = request.form.get("description", "").strip()
    task_type = request.form.get("task_type", "general").strip()
    assignee = request.form.get("assignee", "Lead Agent").strip()
    priority = request.form.get("priority", "P2").strip()
    command = request.form.get("command", "").strip()

    with db_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks(title, description, task_type, assignee, priority, status, command, created_at, updated_at)
            VALUES(?,?,?,?,?,'pending',?,?,?)
            """,
            (title, description, task_type, assignee, priority, command, now_str(), now_str()),
        )
        task_id = cur.lastrowid

    append_log(task_id, f"[SYSTEM] 任务创建：{title}")
    flash(f"任务 #{task_id} 创建成功")
    return redirect(url_for("dashboard"))


@app.post("/tasks/<int:task_id>/start")
@login_required
def start_task_route(task_id: int):
    ok, msg = start_task(task_id)
    flash(f"任务 #{task_id}: {msg}")
    return redirect(url_for("dashboard"))


@app.post("/tasks/<int:task_id>/retry")
@login_required
def retry_task(task_id: int):
    task = get_task(task_id)
    if not task:
        flash("任务不存在")
        return redirect(url_for("dashboard"))

    update_task(task_id, status="pending", finished_at=None, started_at=None, return_code=None)
    append_log(task_id, "[SYSTEM] 任务重置为 pending")
    flash(f"任务 #{task_id} 已重置")
    return redirect(url_for("dashboard"))


@app.post("/tasks/<int:task_id>/stop")
@login_required
def stop_task(task_id: int):
    proc = running_processes.get(task_id)
    if proc is None and task_id in running_processes:
        running_processes.pop(task_id, None)
        update_task(task_id, status="failed", finished_at=now_str(), return_code=137)
        append_log(task_id, "[SYSTEM] 任务在启动阶段被停止")
        flash(f"任务 #{task_id} 已停止")
        return redirect(url_for("dashboard"))

    if not proc:
        flash("任务未运行")
        return redirect(url_for("dashboard"))

    try:
        proc.terminate()
        update_task(task_id, status="failed", finished_at=now_str(), return_code=143)
        append_log(task_id, "[SYSTEM] 手动停止任务")
        flash(f"任务 #{task_id} 已停止")
    except Exception as e:
        flash(f"停止失败: {e}")

    return redirect(url_for("dashboard"))


@app.route("/tasks/<int:task_id>")
@login_required
def task_detail(task_id: int):
    task = get_task(task_id)
    if not task:
        return "Task not found", 404

    with db_conn() as conn:
        logs = conn.execute(
            "SELECT ts, line FROM task_logs WHERE task_id=? ORDER BY id ASC", (task_id,)
        ).fetchall()

    return render_template("task_detail.html", task=task, logs=logs)


@app.route("/api/tasks")
@login_required
def api_tasks():
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 200").fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    sync_runtime_settings()
    app.run(host="127.0.0.1", port=3100, debug=False)
else:
    init_db()
    sync_runtime_settings()
