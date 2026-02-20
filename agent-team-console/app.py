#!/usr/bin/env python3
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import shutil
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("ATC_DB_PATH", os.path.join(BASE_DIR, "data", "tasks.db"))
ADMIN_USERNAME = os.getenv("ATC_ADMIN_USERNAME", "root")
ADMIN_PASSWORD = os.getenv("ATC_ADMIN_PASSWORD", "k5348988")
APP_SECRET = os.getenv("ATC_APP_SECRET", "change-me-now")
WORKDIR = os.getenv("ATC_WORKDIR", BASE_DIR)
DEFAULT_MAX_CONCURRENT = int(os.getenv("ATC_MAX_CONCURRENT", "4"))
ARTIFACT_ROOT = os.getenv("ATC_ARTIFACT_ROOT", os.path.join(BASE_DIR, "artifacts"))

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(ARTIFACT_ROOT, exist_ok=True)

app = Flask(__name__)
app.secret_key = APP_SECRET
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB

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


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024


def list_artifacts(max_items: int = 300):
    out = []
    for root, _, files in os.walk(ARTIFACT_ROOT):
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, ARTIFACT_ROOT)
            try:
                st = os.stat(full)
            except FileNotFoundError:
                continue
            out.append(
                {
                    "name": name,
                    "rel_path": rel,
                    "size": st.st_size,
                    "size_human": format_size(st.st_size),
                    "mtime": datetime.utcfromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "ts": st.st_mtime,
                }
            )
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out[:max_items]


def task_artifact_dirs(task_id: int):
    base = os.path.join(ARTIFACT_ROOT, f"task_{task_id}")
    in_dir = os.path.join(base, "input")
    out_dir = os.path.join(base, "output")
    os.makedirs(in_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    return base, in_dir, out_dir


def list_task_files(task_id: int, kind: str):
    base, in_dir, out_dir = task_artifact_dirs(task_id)
    target = in_dir if kind == "input" else out_dir
    out = []
    if not os.path.isdir(target):
        return out
    for name in os.listdir(target):
        full = os.path.join(target, name)
        if not os.path.isfile(full):
            continue
        st = os.stat(full)
        rel = os.path.relpath(full, base)
        out.append(
            {
                "name": name,
                "rel_path": rel,
                "size_human": format_size(st.st_size),
                "mtime": datetime.utcfromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "ts": st.st_mtime,
            }
        )
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out


def infer_business_phase(task) -> str:
    status = (task["status"] or "").strip().lower()
    if status == "pending":
        return "待理解"
    if status == "running":
        return "执行中"
    if status == "done":
        return "待你确认"
    if status == "failed":
        return "需返工"
    return "其他"


def classify_output_files(output_files):
    packs, reports, audits, others = [], [], [], []
    for f in output_files:
        name = (f.get("name") or "").lower()
        is_pack = name.endswith(".zip") or name.endswith(".7z") or name.endswith(".tar.gz") or name.endswith(".tgz")
        is_audit = ("audit" in name) or ("审计" in name) or name.endswith(".log")
        is_report = name.endswith(".md") or name.endswith(".json") or name.endswith(".txt") or name.endswith(".csv") or name.endswith(".pdf")

        if is_pack:
            packs.append(f)
        elif is_audit:
            audits.append(f)
        elif is_report:
            reports.append(f)
        else:
            others.append(f)
    return {"packs": packs, "reports": reports, "audits": audits, "others": others}


def build_delivery_overview(task, output_files, logs):
    status = (task["status"] or "").strip().lower()
    rc = task["return_code"]
    if status == "done" and (rc in (0, "0", None) or rc == 0):
        headline = "✅ 任务已完成，可直接查看并下载交付物"
        next_action = "优先下载“交付压缩包”，确认结果后可归档任务。"
        progress = 100
    elif status == "running":
        headline = "⏳ 任务执行中，正在持续产出"
        next_action = "可先查看实时日志，等待进入“待你确认”。"
        progress = 60
    elif status == "failed":
        headline = "❌ 任务执行失败，需要返工"
        next_action = "查看失败日志并重置任务，必要时补充附件或说明。"
        progress = 100
    else:
        headline = "📝 任务待执行"
        next_action = "确认任务描述与附件后，点击“启动”。"
        progress = 12

    latest_line = ""
    for row in reversed(logs):
        line = (row["line"] or "").strip()
        if not line:
            continue
        latest_line = line
        if not line.startswith("[SYSTEM]"):
            break

    groups = classify_output_files(output_files)
    primary_pack = groups["packs"][0] if groups["packs"] else None

    return {
        "headline": headline,
        "next_action": next_action,
        "progress": progress,
        "latest_line": latest_line,
        "groups": groups,
        "primary_pack": primary_pack,
    }


def safe_join_under(root: str, rel_path: str):
    safe_full = os.path.realpath(os.path.join(root, rel_path))
    root_real = os.path.realpath(root)
    if not safe_full.startswith(root_real + os.sep) and safe_full != root_real:
        return None
    return safe_full


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                default_model TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                stages_json TEXT,
                default_task_type TEXT,
                default_assignee TEXT,
                command_template TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        # 默认全局角色（创建一次，后续可在页面维护）
        default_roles = [
            ("Lead Agent", "Lead Agent", "任务总控与编排", "sydney-proxy/claude-opus-4-6-thinking"),
            ("@developer", "开发 Agent", "实现功能、改代码、修复问题", "sydney-proxy/gpt-5.3-codex"),
            ("@tester", "测试 Agent", "回归测试、边界验证、复现问题", "sydney-proxy/gpt-5.2-codex"),
            ("@verifier", "验证 Agent", "按验收标准做最终核对", "sydney-proxy/claude-opus-4-6-thinking"),
            ("@release", "发布 Agent", "发布、回滚、变更审计", "sydney-proxy/claude-opus-4-6-thinking"),
            ("@research", "调研 Agent", "信息检索、数据分析、报告沉淀", "sydney-proxy/gpt-5.2-codex"),
        ]
        for code, name, desc, model in default_roles:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles(code, name, description, default_model, enabled, created_at, updated_at)
                VALUES(?,?,?,?,1,?,?)
                """,
                (code, name, desc, model, now_str(), now_str()),
            )

        # 默认全局工作流模板（可复用，不绑定单一业务）
        default_workflows = [
            (
                "custom_brief",
                "通用口语任务",
                "口语化描述 + 附件输入，适配任意任务",
                json.dumps(["需求理解", "执行", "复核", "交付"], ensure_ascii=False),
                "general",
                "Lead Agent",
                "",
            ),
            (
                "dev_test_verify",
                "开发→测试→验证",
                "面向代码任务的标准闭环",
                json.dumps(["开发", "测试", "验证", "交付"], ensure_ascii=False),
                "backend",
                "@developer",
                "",
            ),
            (
                "research_report",
                "调研→提炼→交付",
                "面向信息分析与内容生产任务",
                json.dumps(["调研", "提炼", "复核", "交付"], ensure_ascii=False),
                "research",
                "@research",
                "",
            ),
            (
                "novel_multiagent",
                "小说类目爆款文包（多Agent）",
                "采集→清洗→复核→文包",
                json.dumps(["采集", "清洗", "复核", "文包"], ensure_ascii=False),
                "research",
                "Lead Agent",
                "",
            ),
            (
                "xhs_virtual_keywords",
                "小红书高频词分析",
                "关键词采集与高频词报告",
                json.dumps(["采集", "清洗", "复核", "交付"], ensure_ascii=False),
                "research",
                "@research",
                "cd __PROJECT_DIR__ && python3 scripts/xhs_virtual_keywords.py --keywords '虚拟产品,数字产品,PPT模板,简历模板,教程课程,AI提示词,素材包,资料包' --cookie-file $TASK_INPUT_DIR/xhs_cookies.json --scrolls 4 --auto-related 2 --max-keywords 24 --domain general --strict --min-usable 4 --out-md $TASK_OUTPUT_DIR/xhs_virtual_keywords.md --out-json $TASK_OUTPUT_DIR/xhs_virtual_keywords.json",
            ),
        ]
        for code, name, desc, stages, task_type, assignee, cmd in default_workflows:
            conn.execute(
                """
                INSERT OR IGNORE INTO workflows(
                    code, name, description, stages_json, default_task_type, default_assignee, command_template, enabled, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,1,?,?)
                """,
                (code, name, desc, stages, task_type, assignee, cmd, now_str(), now_str()),
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


def get_roles(enabled_only: bool = False):
    q = "SELECT * FROM roles"
    if enabled_only:
        q += " WHERE enabled=1"
    q += " ORDER BY CASE WHEN code='Lead Agent' THEN 0 ELSE 1 END, id ASC"
    with db_conn() as conn:
        rows = conn.execute(q).fetchall()
    return rows


def get_workflow_by_code(code: str):
    if not code:
        return None
    with db_conn() as conn:
        return conn.execute("SELECT * FROM workflows WHERE code=?", (code,)).fetchone()


def parse_stages(stages_json: str):
    raw = (stages_json or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return [x.strip() for x in raw.split(",") if x.strip()]


def get_workflows(enabled_only: bool = False):
    q = "SELECT * FROM workflows"
    if enabled_only:
        q += " WHERE enabled=1"
    q += " ORDER BY id ASC"
    with db_conn() as conn:
        rows = conn.execute(q).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        d["stages"] = parse_stages(d.get("stages_json"))
        out.append(d)
    return out


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


@app.errorhandler(413)
def payload_too_large(_):
    flash("上传文件过大（单次请求上限 200MB），请压缩后重试。")
    return redirect(url_for("dashboard")), 413


def run_task(task_id: int):
    task = get_task(task_id)
    if not task:
        running_processes.pop(task_id, None)
        return

    with limiter.acquire():
        update_task(task_id, status="running", started_at=now_str(), return_code=None)
        base_dir, input_dir, output_dir = task_artifact_dirs(task_id)
        append_log(task_id, f"[SYSTEM] 任务启动，当前并发上限={limiter.get_limit()}")
        append_log(task_id, f"[SYSTEM] 任务产物目录: {base_dir}")
        append_log(task_id, f"[SYSTEM] 输入附件目录: {input_dir}")
        append_log(task_id, f"[SYSTEM] 输出产物目录: {output_dir}")

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
            env = os.environ.copy()
            env.update(
                {
                    "TASK_ID": str(task_id),
                    "TASK_ARTIFACT_DIR": base_dir,
                    "TASK_INPUT_DIR": input_dir,
                    "TASK_OUTPUT_DIR": output_dir,
                }
            )
            proc = subprocess.Popen(
                cmd,
                shell=True,
                cwd=WORKDIR,
                executable="/bin/bash",
                env=env,
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
    g.artifact_root = ARTIFACT_ROOT
    g.workdir = WORKDIR


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

    phase_order = ["待理解", "执行中", "待你确认", "需返工"]
    tasks_by_phase = {k: [] for k in phase_order}
    for t in tasks:
        phase = infer_business_phase(t)
        tasks_by_phase.setdefault(phase, []).append(t)

    roles = get_roles(enabled_only=False)
    workflows = get_workflows(enabled_only=False)

    queue_count = max(0, len(running_processes) - limiter.get_running())
    return render_template(
        "dashboard.html",
        tasks=tasks,
        stats=stats,
        tasks_by_phase=tasks_by_phase,
        phase_order=phase_order,
        roles=roles,
        workflows=workflows,
        running_count=len(running_processes),
        queue_count=queue_count,
    )


@app.route("/artifacts")
@login_required
def artifacts_page():
    files = list_artifacts()
    return render_template("artifacts.html", files=files, artifact_root=ARTIFACT_ROOT)


@app.route("/artifacts/download/<path:rel_path>")
@login_required
def artifacts_download(rel_path: str):
    safe_full = safe_join_under(ARTIFACT_ROOT, rel_path)
    if not safe_full:
        abort(400)
    if not os.path.isfile(safe_full):
        abort(404)
    return send_from_directory(ARTIFACT_ROOT, rel_path, as_attachment=True)


@app.post("/artifacts/clear")
@login_required
def artifacts_clear_note():
    flash("当前版本为安全起见未开放网页删除文件；请在服务器上手动清理产物目录。")
    return redirect(url_for("artifacts_page"))


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


@app.post("/roles")
@login_required
def create_role():
    code = (request.form.get("code") or "").strip()
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    default_model = (request.form.get("default_model") or "").strip()
    enabled = 1 if (request.form.get("enabled") or "1") == "1" else 0

    if not code or not name:
        flash("角色创建失败：code 和 name 不能为空")
        return redirect(url_for("dashboard"))

    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO roles(code, name, description, default_model, enabled, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (code, name, description, default_model, enabled, now_str(), now_str()),
            )
        flash(f"角色已创建：{name}（{code}）")
    except sqlite3.IntegrityError:
        flash("角色创建失败：code 已存在")
    except Exception as e:
        flash(f"角色创建失败：{e}")

    return redirect(url_for("dashboard"))


@app.post("/roles/<int:role_id>/toggle")
@login_required
def toggle_role(role_id: int):
    with db_conn() as conn:
        row = conn.execute("SELECT enabled, name FROM roles WHERE id=?", (role_id,)).fetchone()
        if not row:
            flash("角色不存在")
            return redirect(url_for("dashboard"))
        nxt = 0 if int(row["enabled"] or 0) == 1 else 1
        conn.execute("UPDATE roles SET enabled=?, updated_at=? WHERE id=?", (nxt, now_str(), role_id))
    flash(f"角色已{'启用' if nxt == 1 else '停用'}：{row['name']}")
    return redirect(url_for("dashboard"))


@app.post("/workflows")
@login_required
def create_workflow():
    code = (request.form.get("code") or "").strip()
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    stages_text = (request.form.get("stages") or "").strip()
    default_task_type = (request.form.get("default_task_type") or "general").strip()
    default_assignee = (request.form.get("default_assignee") or "Lead Agent").strip()
    command_template = (request.form.get("command_template") or "").strip()
    enabled = 1 if (request.form.get("enabled") or "1") == "1" else 0

    if not code or not name:
        flash("工作流创建失败：code 和 name 不能为空")
        return redirect(url_for("dashboard"))

    stages = [x.strip() for x in re.split(r"[,，\n]+", stages_text) if x.strip()]
    stages_json = json.dumps(stages, ensure_ascii=False)

    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO workflows(code, name, description, stages_json, default_task_type, default_assignee, command_template, enabled, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (code, name, description, stages_json, default_task_type, default_assignee, command_template, enabled, now_str(), now_str()),
            )
        flash(f"工作流已创建：{name}（{code}）")
    except sqlite3.IntegrityError:
        flash("工作流创建失败：code 已存在")
    except Exception as e:
        flash(f"工作流创建失败：{e}")

    return redirect(url_for("dashboard"))


@app.post("/workflows/<int:workflow_id>/toggle")
@login_required
def toggle_workflow(workflow_id: int):
    with db_conn() as conn:
        row = conn.execute("SELECT enabled, name FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        if not row:
            flash("工作流不存在")
            return redirect(url_for("dashboard"))
        nxt = 0 if int(row["enabled"] or 0) == 1 else 1
        conn.execute("UPDATE workflows SET enabled=?, updated_at=? WHERE id=?", (nxt, now_str(), workflow_id))
    flash(f"工作流已{'启用' if nxt == 1 else '停用'}：{row['name']}")
    return redirect(url_for("dashboard"))


def derive_title(title_raw: str, brief: str, template_name: str) -> str:
    title = (title_raw or "").strip()
    if title:
        return title
    brief_line = re.sub(r"\s+", " ", (brief or "").strip())
    if brief_line:
        return (brief_line[:36] + "...") if len(brief_line) > 36 else brief_line
    mapping = {
        "novel_multiagent": "小说类目爆款文包任务",
        "xhs_virtual_keywords": "小红书高频词任务",
        "custom_brief": "口语化任务",
    }
    return mapping.get(template_name, "新任务")


def build_command_from_template(template_name: str, project_dir: str, task_brief: str) -> str:
    workdir = (project_dir or WORKDIR).strip() or WORKDIR

    if template_name == "novel_multiagent":
        keywords = "小说推文,小说推荐,网文,言情小说,悬疑小说,完结小说,书荒推荐,番茄小说,爽文小说,推理小说"
        if "小红书" not in task_brief and "小说" in task_brief:
            keywords = "小说推荐,网文推荐,言情小说,悬疑小说,推理小说,书荒推荐,完结小说"
        return (
            f"cd {workdir} && python3 scripts/xhs_novel_multiagent_pipeline.py "
            f"--keywords '{keywords}' "
            "--cookie-file $TASK_INPUT_DIR/xhs_cookies.json "
            "--output-dir $TASK_OUTPUT_DIR "
            "--max-rounds 3 --min-usable 8 --min-domain-ratio 0.75 --max-noise-ratio 0.35 "
            "--pack-format zip"
        )

    # 优先使用工作流中心配置的命令模板
    wf = get_workflow_by_code(template_name)
    if wf and (wf["command_template"] or "").strip():
        return (wf["command_template"] or "").replace("__PROJECT_DIR__", workdir)

    if template_name == "xhs_virtual_keywords":
        return (
            f"cd {workdir} && python3 scripts/xhs_virtual_keywords.py "
            "--keywords '虚拟产品,数字产品,PPT模板,简历模板,教程课程,AI提示词,素材包,资料包' "
            "--cookie-file $TASK_INPUT_DIR/xhs_cookies.json "
            "--scrolls 4 --auto-related 2 --max-keywords 24 --domain general "
            "--strict --min-usable 4 "
            "--out-md $TASK_OUTPUT_DIR/xhs_virtual_keywords.md "
            "--out-json $TASK_OUTPUT_DIR/xhs_virtual_keywords.json"
        )

    return ""


@app.post("/tasks")
@login_required
def create_task():
    workflow_template = (request.form.get("workflow_template") or "custom_brief").strip()
    task_brief = (request.form.get("task_brief") or "").strip()
    delivery_expectation = (request.form.get("delivery_expectation") or "").strip()
    project_dir = (request.form.get("project_dir") or "").strip()

    title = derive_title(request.form.get("title", ""), task_brief, workflow_template)
    if not title:
        flash("请至少填写任务描述或标题")
        return redirect(url_for("dashboard"))

    description_raw = (request.form.get("description", "") or "").strip()
    desc_parts = []
    if task_brief:
        desc_parts.append(f"【任务描述】\n{task_brief}")
    if delivery_expectation:
        desc_parts.append(f"【期望交付】\n{delivery_expectation}")
    if description_raw:
        desc_parts.append(f"【补充说明】\n{description_raw}")
    description = "\n\n".join(desc_parts).strip()

    wf = get_workflow_by_code(workflow_template)

    task_type = (request.form.get("task_type") or "general").strip()
    assignee = (request.form.get("assignee") or "Lead Agent").strip()
    priority = (request.form.get("priority") or "P2").strip()

    # 若未手工指定，优先套用工作流默认角色/类型
    if wf:
        if task_type == "general" and (wf["default_task_type"] or "").strip():
            task_type = (wf["default_task_type"] or "general").strip()
        if assignee == "Lead Agent" and (wf["default_assignee"] or "").strip():
            assignee = (wf["default_assignee"] or "Lead Agent").strip()

    command = (request.form.get("command") or "").strip()
    if not command:
        command = build_command_from_template(workflow_template, project_dir, task_brief)

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
    append_log(task_id, f"[SYSTEM] 工作流模板：{workflow_template}")
    if task_brief:
        append_log(task_id, f"[SYSTEM] 口语化任务描述：{task_brief[:1200]}")
    if delivery_expectation:
        append_log(task_id, f"[SYSTEM] 期望交付：{delivery_expectation[:800]}")

    _, input_dir, _ = task_artifact_dirs(task_id)
    uploaded = 0
    for f in request.files.getlist("attachments"):
        if not f or not f.filename:
            continue
        safe_name = secure_filename(f.filename)
        if not safe_name:
            continue
        target = os.path.join(input_dir, safe_name)
        f.save(target)
        uploaded += 1
        append_log(task_id, f"[SYSTEM] 已上传附件: {safe_name}")

    if uploaded > 0:
        flash(f"任务 #{task_id} 创建成功，已上传 {uploaded} 个附件")
    else:
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


@app.post("/tasks/<int:task_id>/delete")
@login_required
def delete_task(task_id: int):
    task = get_task(task_id)
    if not task:
        flash("任务不存在")
        return redirect(url_for("dashboard"))

    if task_id in running_processes:
        flash(f"任务 #{task_id} 正在运行或排队中，请先停止后再删除")
        return redirect(url_for("dashboard"))

    try:
        with db_conn() as conn:
            conn.execute("DELETE FROM task_logs WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))

        task_dir = os.path.join(ARTIFACT_ROOT, f"task_{task_id}")
        if os.path.isdir(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)

        flash(f"任务 #{task_id} 已删除（含日志和任务附件/产物）")
    except Exception as e:
        flash(f"删除任务失败: {e}")

    return redirect(url_for("dashboard"))


@app.post("/tasks/<int:task_id>/upload")
@login_required
def task_upload(task_id: int):
    task = get_task(task_id)
    if not task:
        flash("任务不存在")
        return redirect(url_for("dashboard"))

    _, input_dir, _ = task_artifact_dirs(task_id)
    uploaded = 0
    for f in request.files.getlist("attachments"):
        if not f or not f.filename:
            continue
        safe_name = secure_filename(f.filename)
        if not safe_name:
            continue
        target = os.path.join(input_dir, safe_name)
        f.save(target)
        uploaded += 1
        append_log(task_id, f"[SYSTEM] 已追加上传附件: {safe_name}")

    if uploaded == 0:
        flash("未检测到可上传文件")
    else:
        flash(f"任务 #{task_id} 附件上传完成：{uploaded} 个")
    return redirect(url_for("task_detail", task_id=task_id))


@app.route("/tasks/<int:task_id>/download/<path:rel_path>")
@login_required
def task_artifact_download(task_id: int, rel_path: str):
    task = get_task(task_id)
    if not task:
        abort(404)
    base, _, _ = task_artifact_dirs(task_id)
    safe_full = safe_join_under(base, rel_path)
    if not safe_full:
        abort(400)
    if not os.path.isfile(safe_full):
        abort(404)
    return send_from_directory(base, rel_path, as_attachment=True)


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

    base, input_dir, output_dir = task_artifact_dirs(task_id)
    input_files = list_task_files(task_id, "input")
    output_files = list_task_files(task_id, "output")
    delivery = build_delivery_overview(task, output_files, logs)

    return render_template(
        "task_detail.html",
        task=task,
        logs=logs,
        delivery=delivery,
        base_dir=base,
        input_dir=input_dir,
        output_dir=output_dir,
        input_files=input_files,
        output_files=output_files,
    )


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
