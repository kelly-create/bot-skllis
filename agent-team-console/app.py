#!/usr/bin/env python3
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import shutil
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta
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
ROLE_DEFAULT_API_BASE = os.getenv("ATC_ROLE_DEFAULT_API_BASE", "").strip()
ROLE_DEFAULT_API_KEY = os.getenv("ATC_ROLE_DEFAULT_API_KEY", "").strip()
ROLE_DEFAULT_TIMEOUT = int(os.getenv("ATC_ROLE_TIMEOUT_SECONDS", "180"))
ROLE_MAX_REWORK_ROUNDS = max(0, min(5, int(os.getenv("ATC_MAX_REWORK_ROUNDS", "2"))))
ROLE_STAGE_REVIEW_MAX_RETRIES = max(0, min(5, int(os.getenv("ATC_STAGE_REVIEW_MAX_RETRIES", "2"))))

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


def to_beijing_time(ts_text: str) -> str:
    raw = (ts_text or "").strip()
    if not raw:
        return "-"
    try:
        if raw.endswith(" UTC"):
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S UTC")
        else:
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        dt_bj = dt + timedelta(hours=8)
        return dt_bj.strftime("%Y-%m-%d %H:%M:%S 北京时间")
    except Exception:
        return raw


def epoch_to_beijing(ts_epoch: float) -> str:
    try:
        dt_bj = datetime.utcfromtimestamp(ts_epoch) + timedelta(hours=8)
        return dt_bj.strftime("%Y-%m-%d %H:%M:%S 北京时间")
    except Exception:
        return "-"


app.jinja_env.filters["bjt"] = to_beijing_time


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
                    "mtime": epoch_to_beijing(st.st_mtime),
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
                "mtime": epoch_to_beijing(st.st_mtime),
                "ts": st.st_mtime,
            }
        )
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out


def infer_business_phase(task) -> str:
    status = (task["status"] or "").strip().lower()
    if status in ("pending", "failed"):
        return "待处理"
    if status == "running":
        return "执行中"
    if status == "done":
        return "待确认"
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


def load_multiagent_summary(output_dir: str):
    audit_path = os.path.join(output_dir, "多Agent_会话审计.json")
    if not os.path.isfile(audit_path):
        return None

    try:
        data = json.load(open(audit_path, "r", encoding="utf-8"))
    except Exception:
        return None

    dynamic = data.get("dynamicAssignments") or {}
    dispatch_items = [{"stage": k, "role": v} for k, v in dynamic.items()]

    review_pass = 0
    review_fail = 0
    quality_fail = 0
    called_roles = []
    role_seen = set()
    stage_tracks = []

    intake_role = "-"
    intake_model = "-"

    for s in data.get("stages") or []:
        role = s.get("role") or "-"
        if role not in role_seen:
            role_seen.add(role)
            called_roles.append(role)

        rd_obj = s.get("reviewDecision") or {}
        rd = rd_obj.get("decision", "")
        if rd == "PASS":
            review_pass += 1
        elif rd == "FAIL":
            review_fail += 1

        q_obj = (s.get("qualityGate") or {}).get("decision") or {}
        qd = q_obj.get("decision", "")
        if qd == "FAIL":
            quality_fail += 1

        if rd:
            track_status = f"复核{rd}"
            reason = rd_obj.get("reason", "")
            if rd == "FAIL" and rd_obj.get("send_back_role"):
                reason = f"打回 {rd_obj.get('send_back_role')}｜{reason}"
        elif qd:
            track_status = f"质控{qd}"
            reason = q_obj.get("reason", "")
        else:
            track_status = "完成"
            reason = ""

        stage_name = s.get("stage") or "-"
        model_name = s.get("model") or "-"
        if intake_role == "-" and any(k in stage_name for k in ["需求接收", "分发", "需求分析", "需求理解"]):
            intake_role = role
            intake_model = model_name

        stage_tracks.append(
            {
                "executionNo": s.get("executionNo") or "-",
                "stage": stage_name,
                "role": role,
                "model": model_name,
                "reworkRound": s.get("reworkRound") or 0,
                "duration_sec": s.get("durationSec"),
                "status": track_status,
                "reason": (reason or "")[:180],
            }
        )

    if intake_role == "-" and stage_tracks:
        intake_role = stage_tracks[0].get("role") or "-"
        intake_model = stage_tracks[0].get("model") or "-"

    return {
        "workflow": data.get("workflow") or "-",
        "steps": len(data.get("stages") or []),
        "rework_used": data.get("reworkRoundsUsed") or 0,
        "rework_max": data.get("maxReworkRounds") or 0,
        "dispatch_items": dispatch_items,
        "review_pass": review_pass,
        "review_fail": review_fail,
        "quality_fail": quality_fail,
        "called_roles": called_roles,
        "stage_tracks": stage_tracks,
        "intake_role": intake_role,
        "intake_model": intake_model,
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


def ensure_column(conn, table: str, column: str, decl: str):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS role_session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                role_code TEXT NOT NULL,
                stage TEXT,
                turn TEXT NOT NULL,
                content TEXT,
                created_at TEXT
            )
            """
        )

        # 历史库兼容：按需补字段
        ensure_column(conn, "tasks", "workflow_code", "TEXT")
        ensure_column(conn, "roles", "api_base", "TEXT")
        ensure_column(conn, "roles", "api_key", "TEXT")
        ensure_column(conn, "roles", "system_prompt", "TEXT")
        ensure_column(conn, "roles", "temperature", "REAL DEFAULT 0.3")
        ensure_column(conn, "roles", "max_tokens", "INTEGER DEFAULT 1200")
        ensure_column(conn, "workflows", "stage_roles_json", "TEXT")

        # 默认全局角色（创建一次，后续可在页面维护）
        default_roles = [
            ("Lead Agent", "Lead Agent", "任务总控与编排", "gpt-5.3-codex"),
            ("@developer", "开发 Agent", "实现功能、改代码、修复问题", "gpt-5.3-codex"),
            ("@tester", "测试 Agent", "回归测试、边界验证、复现问题", "gpt-5.3-codex"),
            ("@verifier", "验证 Agent", "按验收标准做最终核对", "gpt-5.3-codex"),
            ("@release", "发布 Agent", "发布、回滚、变更审计", "gpt-5.3-codex"),
            ("@research", "调研 Agent", "信息检索、数据分析、报告沉淀", "gpt-5.3-codex"),
        ]
        for code, name, desc, model in default_roles:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles(code, name, description, default_model, enabled, created_at, updated_at)
                VALUES(?,?,?,?,1,?,?)
                """,
                (code, name, desc, model, now_str(), now_str()),
            )

        # 默认角色词（system prompt）
        role_prompts = {
            "Lead Agent": "你是总控角色。负责拆解任务、定义阶段目标、串联各角色输出，最终给出可交付结果与结论。输出要简洁、结构化。",
            "@developer": "你是开发角色。聚焦实现方案、关键步骤、代码/流程改动点。不要泛泛而谈，给出可执行内容。",
            "@tester": "你是测试角色。基于开发输出设计验证点、边界用例、回归清单，并标记风险与缺陷。",
            "@verifier": "你是验证角色。按任务目标与交付标准做最终核对，明确通过/不通过和理由。",
            "@release": "你是发布交付角色。负责整理最终交付、发布步骤、回滚要点与风险提示。",
            "@research": "你是调研分析角色。负责信息提炼、结构化总结、关键证据和结论。",
            "@pm": "你是产品经理角色。负责需求澄清、验收标准、优先级与范围边界。",
        }
        for role_code, prompt in role_prompts.items():
            conn.execute(
                """
                UPDATE roles
                SET system_prompt = CASE WHEN system_prompt IS NULL OR system_prompt='' THEN ? ELSE system_prompt END,
                    updated_at=?
                WHERE code=?
                """,
                (prompt, now_str(), role_code),
            )

        # 给未配置角色注入环境级默认 API（可为空，不强制）
        if ROLE_DEFAULT_API_BASE:
            conn.execute(
                """
                UPDATE roles
                SET api_base = CASE WHEN api_base IS NULL OR api_base='' THEN ? ELSE api_base END,
                    updated_at=?
                """,
                (ROLE_DEFAULT_API_BASE, now_str()),
            )
        if ROLE_DEFAULT_API_KEY:
            conn.execute(
                """
                UPDATE roles
                SET api_key = CASE WHEN api_key IS NULL OR api_key='' THEN ? ELSE api_key END,
                    updated_at=?
                """,
                (ROLE_DEFAULT_API_KEY, now_str()),
            )

        # 默认全局工作流模板（可复用，不绑定单一业务）
        default_workflows = [
            (
                "custom_brief",
                "通用口语任务",
                "口语化描述 + 附件输入，适配任意任务",
                json.dumps(["需求接收与分发", "执行", "复核", "交付"], ensure_ascii=False),
                "general",
                "Lead Agent",
                "",
            ),
            (
                "dev_test_verify",
                "开发→测试→验证",
                "面向代码任务的标准闭环",
                json.dumps(["需求接收与分发", "开发", "测试", "验证", "交付"], ensure_ascii=False),
                "backend",
                "Lead Agent",
                "",
            ),
            (
                "research_report",
                "调研→提炼→交付",
                "面向信息分析与内容生产任务",
                json.dumps(["需求接收与分发", "调研", "提炼", "复核", "交付"], ensure_ascii=False),
                "research",
                "Lead Agent",
                "",
            ),
            (
                "novel_multiagent",
                "小说类目爆款文包（多Agent）",
                "采集→清洗→复核→文包",
                json.dumps(["需求接收与分发", "采集", "清洗", "复核", "文包"], ensure_ascii=False),
                "research",
                "Lead Agent",
                "",
            ),
            (
                "xhs_virtual_keywords",
                "小红书高频词分析",
                "关键词采集与高频词报告",
                json.dumps(["需求接收与分发", "采集", "清洗", "复核", "交付"], ensure_ascii=False),
                "research",
                "Lead Agent",
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

        stage_role_defaults = {
            "custom_brief": {"需求接收与分发": "Lead Agent", "执行": "@developer", "复核": "@verifier", "交付": "Lead Agent"},
            "dev_test_verify": {"需求接收与分发": "Lead Agent", "开发": "@developer", "测试": "@tester", "验证": "@verifier", "交付": "@release"},
            "research_report": {"需求接收与分发": "Lead Agent", "调研": "@research", "提炼": "@research", "复核": "@verifier", "交付": "Lead Agent"},
            "novel_multiagent": {"需求接收与分发": "Lead Agent", "采集": "@research", "清洗": "@developer", "复核": "@verifier", "文包": "@release"},
            "xhs_virtual_keywords": {"需求接收与分发": "Lead Agent", "采集": "@research", "清洗": "@developer", "复核": "@verifier", "交付": "Lead Agent"},
        }
        for wf_code, mapping in stage_role_defaults.items():
            conn.execute(
                """
                UPDATE workflows
                SET stage_roles_json = ?,
                    updated_at=?
                WHERE code=?
                """,
                (json.dumps(mapping, ensure_ascii=False), now_str(), wf_code),
            )

        workflow_stage_defaults = {
            "custom_brief": ["需求接收与分发", "执行", "复核", "交付"],
            "dev_test_verify": ["需求接收与分发", "开发", "测试", "验证", "交付"],
            "research_report": ["需求接收与分发", "调研", "提炼", "复核", "交付"],
            "novel_multiagent": ["需求接收与分发", "采集", "清洗", "复核", "文包"],
            "xhs_virtual_keywords": ["需求接收与分发", "采集", "清洗", "复核", "交付"],
        }
        for wf_code, stages in workflow_stage_defaults.items():
            conn.execute(
                """
                UPDATE workflows
                SET stages_json=?,
                    default_assignee='Lead Agent',
                    updated_at=?
                WHERE code=?
                """,
                (json.dumps(stages, ensure_ascii=False), now_str(), wf_code),
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

    out = []
    for r in rows:
        d = dict(r)
        d["api_ready"] = bool((d.get("api_base") or "").strip() and (d.get("api_key") or "").strip() and (d.get("default_model") or "").strip())
        d["api_key_masked"] = mask_secret(d.get("api_key") or "")
        out.append(d)
    return out


def get_workflow_by_code(code: str):
    if not code:
        return None
    with db_conn() as conn:
        return conn.execute("SELECT * FROM workflows WHERE code=?", (code,)).fetchone()


def get_role_by_code(code: str):
    if not code:
        return None
    with db_conn() as conn:
        return conn.execute("SELECT * FROM roles WHERE code=?", (code,)).fetchone()


def mask_secret(secret: str) -> str:
    s = (secret or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return s[:4] + "..." + s[-4:]


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
    return [x.strip() for x in re.split(r"[,，\n]+", raw) if x.strip()]


def parse_stage_roles(stage_roles_json: str):
    raw = (stage_roles_json or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if str(k).strip() and str(v).strip()}
    except Exception:
        pass

    out = {}
    for part in re.split(r"[,，\n]+", raw):
        p = part.strip()
        if not p:
            continue
        if ":" in p:
            k, v = p.split(":", 1)
        elif "=" in p:
            k, v = p.split("=", 1)
        else:
            continue
        k = k.strip()
        v = v.strip()
        if k and v:
            out[k] = v
    return out


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
        d["stage_roles"] = parse_stage_roles(d.get("stage_roles_json"))
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


def save_role_message(task_id: int, role_code: str, stage: str, turn: str, content: str):
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO role_session_messages(task_id, role_code, stage, turn, content, created_at) VALUES(?,?,?,?,?,?)",
            (task_id, role_code, stage, turn, (content or "")[:12000], now_str()),
        )


def load_role_messages(task_id: int, role_code: str, limit: int = 8):
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT turn, content FROM role_session_messages WHERE task_id=? AND role_code=? ORDER BY id DESC LIMIT ?",
            (task_id, role_code, max(1, int(limit))),
        ).fetchall()
    return list(reversed(rows))


def parse_task_sections(description: str):
    text = (description or "").strip()
    out = {"task": "", "delivery": "", "extra": text}
    if not text:
        return out

    m_task = re.search(r"【任务描述】\n([\s\S]*?)(?:\n\n【|$)", text)
    m_delivery = re.search(r"【期望交付】\n([\s\S]*?)(?:\n\n【|$)", text)
    m_extra = re.search(r"【补充说明】\n([\s\S]*?)$", text)

    if m_task:
        out["task"] = m_task.group(1).strip()
    if m_delivery:
        out["delivery"] = m_delivery.group(1).strip()
    if m_extra:
        out["extra"] = m_extra.group(1).strip()
    return out


def ensure_not_stopped(task_id: int):
    if task_id not in running_processes:
        raise RuntimeError("任务被手动停止")


def _extract_content_from_chat_response(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = (choices[0] or {}).get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text") or "")
                elif "text" in item:
                    parts.append(str(item.get("text")))
            else:
                parts.append(str(item))
        return "\n".join([p for p in parts if p]).strip()
    return (content or "").strip()


def call_role_llm(role, messages):
    api_base = (role["api_base"] or ROLE_DEFAULT_API_BASE or "").strip()
    api_key = (role["api_key"] or ROLE_DEFAULT_API_KEY or "").strip()
    model = (role["default_model"] or "").strip()

    if not api_base:
        raise RuntimeError(f"角色 {role['code']} 未配置 api_base")
    if not api_key:
        raise RuntimeError(f"角色 {role['code']} 未配置 api_key")
    if not model:
        raise RuntimeError(f"角色 {role['code']} 未配置模型")

    base = api_base.rstrip("/")
    url = (base + "/chat/completions") if base.endswith("/v1") else (base + "/v1/chat/completions")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(role["temperature"] if role["temperature"] is not None else 0.3),
        "max_tokens": int(role["max_tokens"] if role["max_tokens"] is not None else 1200),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    timeout = max(30, ROLE_DEFAULT_TIMEOUT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
        raise RuntimeError(f"角色 {role['code']} 模型请求失败: HTTP {getattr(e, 'code', '?')} {detail[:200]}")
    except Exception as e:
        raise RuntimeError(f"角色 {role['code']} 模型请求异常: {e}")

    try:
        data = json.loads(raw)
    except Exception:
        raise RuntimeError(f"角色 {role['code']} 返回非JSON: {raw[:200]}")

    text = _extract_content_from_chat_response(data)
    if not text:
        raise RuntimeError(f"角色 {role['code']} 返回空内容")
    return text


def is_verifier_stage(stage: str, role_code: str) -> bool:
    s = (stage or "")
    r = (role_code or "")
    return r == "@verifier" or any(k in s for k in ["验证", "复核", "验收", "review"])


def parse_verifier_feedback(text: str) -> dict:
    raw = (text or "").strip()
    out = {
        "decision": "UNKNOWN",
        "reason": "",
        "issues": [],
        "send_back_role": "",
        "rework_instructions": "",
    }
    if not raw:
        return out

    # 优先解析 JSON
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            data = json.loads(m.group(0))
            dec = str(data.get("decision", "")).strip().upper()
            if dec in ("PASS", "FAIL"):
                out["decision"] = dec
            out["reason"] = str(data.get("reason", "")).strip()
            issues = data.get("issues") or []
            if isinstance(issues, list):
                out["issues"] = [str(x).strip() for x in issues if str(x).strip()]
            out["send_back_role"] = str(data.get("send_back_role", "")).strip()
            out["rework_instructions"] = str(data.get("rework_instructions", "")).strip()
            return out
        except Exception:
            pass

    upper = raw.upper()
    if "FAIL" in upper or "不通过" in raw or "打回" in raw:
        out["decision"] = "FAIL"
    elif "PASS" in upper or "通过" in raw:
        out["decision"] = "PASS"

    role_hit = re.search(r"(@[a-zA-Z0-9_\-]+)", raw)
    if role_hit:
        out["send_back_role"] = role_hit.group(1)

    lines = [ln.strip("- •\t ") for ln in raw.splitlines() if ln.strip()]
    if lines:
        out["reason"] = lines[0][:300]
        out["issues"] = lines[1:6]
        out["rework_instructions"] = "；".join(lines[1:4])[:800]
    return out


def find_stage_index_by_role(stages: list, stage_roles: dict, role_code: str, before_idx: int, fallback_idx: int = 0) -> int:
    rc = (role_code or "").strip()
    if not rc:
        return fallback_idx
    for i in range(max(0, before_idx - 1), -1, -1):
        st = stages[i]
        if (stage_roles.get(st) or "").strip() == rc:
            return i
    return fallback_idx


def parse_dispatch_assignments(text: str, allowed_stages: list, enabled_role_codes: set) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}

    payload = None
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            payload = json.loads(m.group(0))
        except Exception:
            payload = None

    out = {}
    if isinstance(payload, dict):
        assignments = payload.get("assignments") or payload.get("dispatch") or []
        if isinstance(assignments, list):
            for item in assignments:
                if not isinstance(item, dict):
                    continue
                stage = str(item.get("stage") or "").strip()
                role = str(item.get("role") or item.get("assignee") or "").strip()
                if stage in allowed_stages and role in enabled_role_codes:
                    out[stage] = role
        # 兼容直接 map
        if not out:
            for k, v in payload.items():
                ks = str(k).strip()
                vs = str(v).strip() if isinstance(v, (str, int, float)) else ""
                if ks in allowed_stages and vs in enabled_role_codes:
                    out[ks] = vs

    return out


def run_multi_agent_workflow(task_id: int, task, wf, output_dir: str):
    stages = parse_stages(wf["stages_json"])
    stage_roles = parse_stage_roles(wf["stage_roles_json"])
    if not stages:
        raise RuntimeError("工作流没有配置阶段")

    sections = parse_task_sections(task["description"] or "")
    previous_output = ""
    handoff_note = ""
    rework_round = 0
    stage_idx = 0
    execution_no = 0
    max_rework_rounds = ROLE_MAX_REWORK_ROUNDS
    max_stage_review_retries = ROLE_STAGE_REVIEW_MAX_RETRIES
    max_iterations = len(stages) * (max_rework_rounds + max_stage_review_retries + 4) + 12
    iterations = 0
    stage_retry_counts = {s: 0 for s in stages}

    enabled_role_codes = {r["code"] for r in get_roles(enabled_only=True)}

    audit = {
        "taskId": task_id,
        "workflow": wf["code"],
        "maxReworkRounds": max_rework_rounds,
        "maxStageReviewRetries": max_stage_review_retries,
        "reworkRoundsUsed": 0,
        "stages": [],
        "dynamicAssignments": {},
        "startedAt": now_str(),
    }

    while stage_idx < len(stages):
        iterations += 1
        if iterations > max_iterations:
            raise RuntimeError(f"超过最大迭代限制（{max_iterations}），已自动终止避免循环")

        ensure_not_stopped(task_id)
        stage = stages[stage_idx]
        role_code = stage_roles.get(stage) or (wf["default_assignee"] or "") or (task["assignee"] or "Lead Agent")
        role = get_role_by_code(role_code)
        if not role:
            raise RuntimeError(f"阶段 {stage} 找不到角色: {role_code}")
        if int(role["enabled"] or 0) != 1:
            raise RuntimeError(f"阶段 {stage} 角色未启用: {role_code}")

        stage_retry = stage_retry_counts.get(stage, 0)
        append_log(task_id, f"[Lead Agent] 阶段{stage_idx+1}/{len(stages)}：{stage} -> {role_code}（返工轮次={rework_round}，本阶段重试={stage_retry}/{max_stage_review_retries}）")

        history = load_role_messages(task_id, role_code, limit=10)
        sys_prompt = (role["system_prompt"] or "").strip()
        if not sys_prompt:
            sys_prompt = f"你是{role['name']}（{role['code']}），职责：{role['description'] or '完成被分配阶段并输出可执行结果'}。"

        verifier_mode = is_verifier_stage(stage, role_code)
        lead_dispatch_mode = (role_code == "Lead Agent" and ("分发" in stage or stage_idx == 0))
        if verifier_mode:
            stage_instruction = (
                "你只负责当前复核阶段，不负责开发实现。请严格依据任务要求判定是否通过。"
                "必须返回 JSON："
                '{"decision":"PASS|FAIL","reason":"...","issues":["..."],"send_back_role":"@developer 或 @tester","rework_instructions":"..."}'
                "。如果通过，issues可为空，send_back_role可空。"
            )
        elif lead_dispatch_mode:
            stage_instruction = (
                "你是总控分发阶段：先接收需求，再按后续角色分发任务。"
                "请输出“分发清单”，至少包含：角色、该角色目标、输入、输出、验收标准。"
                "不要替执行角色完成实现，只做拆解和分发。"
                "并在结尾附上 JSON（assignments）用于动态分发，例如："
                '{"assignments":[{"stage":"开发","role":"@developer"},{"stage":"测试","role":"@tester"}]}'
                "。stage 必须是现有阶段名，role 必须是可用角色 code。"
            )
        else:
            stage_instruction = (
                "你只负责当前阶段，不要替下一阶段做决定。"
                "输出本阶段可直接交接给下阶段的结果（中文、结构化、可执行）。"
            )

        user_prompt = (
            f"你当前负责阶段：{stage}\n"
            f"任务标题：{task['title']}\n"
            f"任务描述：{sections.get('task') or task['description'] or ''}\n"
            f"期望交付：{sections.get('delivery') or ''}\n"
            f"补充说明：{sections.get('extra') or ''}\n"
            f"上一个阶段输出（若为空可忽略）：\n{previous_output}\n\n"
            f"返工/交接说明（若为空可忽略）：\n{handoff_note}\n\n"
            f"阶段规则：{stage_instruction}"
        )

        messages = [{"role": "system", "content": sys_prompt}]
        for h in history:
            turn = (h["turn"] or "").strip().lower()
            if turn in ("user", "assistant", "system"):
                messages.append({"role": turn, "content": h["content"] or ""})
        messages.append({"role": "user", "content": user_prompt})

        stage_started_at = now_str()
        stage_t0 = time.perf_counter()
        save_role_message(task_id, role_code, stage, "user", user_prompt)
        output = call_role_llm(role, messages)
        save_role_message(task_id, role_code, stage, "assistant", output)
        stage_duration_sec = round(time.perf_counter() - stage_t0, 2)

        execution_no += 1
        stage_file = os.path.join(
            output_dir,
            f"步骤{execution_no}_阶段{stage_idx+1}_{stage}_{role_code.replace('@', 'at_').replace(' ', '_')}.md",
        )
        with open(stage_file, "w", encoding="utf-8") as f:
            f.write(f"# 步骤{execution_no}｜阶段{stage_idx+1}：{stage}\n\n")
            f.write(f"角色：{role['name']}（{role['code']}）\n")
            f.write(f"返工轮次：{rework_round}\n\n")
            f.write(output + "\n")

        stage_audit = {
            "executionNo": execution_no,
            "index": stage_idx + 1,
            "stage": stage,
            "role": role_code,
            "model": role["default_model"],
            "reworkRound": rework_round,
            "startedAt": stage_started_at,
            "durationSec": stage_duration_sec,
            "outputFile": os.path.basename(stage_file),
            "outputChars": len(output),
            "finishedAt": now_str(),
        }

        # 动态分发：Lead 在“需求接收与分发”阶段可动态改写后续阶段角色
        if lead_dispatch_mode:
            dynamic = parse_dispatch_assignments(output, stages[stage_idx + 1 :], enabled_role_codes)
            if dynamic:
                stage_roles.update(dynamic)
                audit["dynamicAssignments"].update(dynamic)
                stage_audit["dynamicAssignments"] = dynamic
                append_log(task_id, f"[Lead Agent] 动态分发生效：{json.dumps(dynamic, ensure_ascii=False)}")
            else:
                append_log(task_id, "[Lead Agent] 未解析到有效动态分发JSON，沿用工作流默认分配")

        # 每个执行角色完成后都做阶段质控（由 @verifier 复核）
        if (not verifier_mode) and (not lead_dispatch_mode):
            reviewer_role = get_role_by_code("@verifier")
            if reviewer_role and int(reviewer_role["enabled"] or 0) == 1:
                review_stage = f"{stage}-阶段质控"
                review_prompt = (
                    "你是阶段质控复核。请只对当前阶段输出进行验收，不要重写实现。"
                    f"当前阶段：{stage}，执行角色：{role_code}。\n"
                    f"任务目标：{sections.get('task') or task['description'] or ''}\n"
                    f"期望交付：{sections.get('delivery') or ''}\n"
                    f"本阶段输出：\n{output}\n\n"
                    "请返回 JSON："
                    '{"decision":"PASS|FAIL","reason":"...","issues":["..."],"send_back_role":"当前角色code","rework_instructions":"..."}'
                    "。若 FAIL，send_back_role 优先填当前角色。"
                )
                review_msgs = [
                    {
                        "role": "system",
                        "content": (reviewer_role["system_prompt"] or "你是严格质控复核角色。"),
                    },
                    {"role": "user", "content": review_prompt},
                ]
                save_role_message(task_id, "@verifier", review_stage, "user", review_prompt)
                review_output = call_role_llm(reviewer_role, review_msgs)
                save_role_message(task_id, "@verifier", review_stage, "assistant", review_output)
                quality = parse_verifier_feedback(review_output)
                stage_audit["qualityGate"] = {"raw": review_output, "decision": quality}

                q_dec = quality.get("decision", "UNKNOWN")
                append_log(task_id, f"[@verifier] 阶段质控结论：{q_dec} | stage={stage} | reason={quality.get('reason','')[:120]}")

                if q_dec != "PASS":
                    if stage_retry >= max_stage_review_retries:
                        stage_audit["terminatedByStageReview"] = True
                        audit["stages"].append(stage_audit)
                        raise RuntimeError(f"阶段 {stage} 质控未通过，且已达本阶段最大重试 {max_stage_review_retries}")

                    stage_retry_counts[stage] = stage_retry + 1
                    handoff_note = (
                        f"阶段质控未通过（{stage}，第{stage_retry_counts[stage]}次重试）。"
                        f"原因：{quality.get('reason','')}。"
                        f"问题：{'；'.join(quality.get('issues') or [])}。"
                        f"修改要求：{quality.get('rework_instructions','请根据质控意见修改后重新提交本阶段。')}"
                    )
                    append_log(
                        task_id,
                        f"[Lead Agent] 阶段质控未通过，打回当前阶段重做：{stage}（{stage_retry_counts[stage]}/{max_stage_review_retries}）",
                    )
                    previous_output = output
                    audit["stages"].append(stage_audit)
                    continue
                else:
                    stage_retry_counts[stage] = 0
            else:
                stage_audit["qualityGate"] = {"decision": {"decision": "SKIP", "reason": "@verifier不可用，跳过阶段质控"}}

        # 工作流中的“验证/复核”正式阶段：可触发跨阶段打回
        if verifier_mode:
            decision = parse_verifier_feedback(output)
            stage_audit["reviewDecision"] = decision
            dec = decision.get("decision", "UNKNOWN")
            append_log(task_id, f"[{role_code}] 复核结论：{dec} | reason={decision.get('reason','')[:120]}")

            if dec != "PASS":
                if rework_round >= max_rework_rounds:
                    stage_audit["terminatedByMaxRework"] = True
                    audit["stages"].append(stage_audit)
                    audit["reworkRoundsUsed"] = rework_round
                    raise RuntimeError(f"复核未通过，已达最大返工轮次 {max_rework_rounds}，任务终止")

                target_role = (decision.get("send_back_role") or "").strip()
                target_idx = find_stage_index_by_role(stages, stage_roles, target_role, stage_idx, fallback_idx=max(0, stage_idx - 1))
                rework_round += 1
                audit["reworkRoundsUsed"] = rework_round
                handoff_note = (
                    f"复核不通过（第{rework_round}轮返工）。"
                    f"原因：{decision.get('reason','')}。"
                    f"问题：{'；'.join(decision.get('issues') or [])}。"
                    f"修改要求：{decision.get('rework_instructions','请根据复核意见修改后提交。')}"
                )
                append_log(
                    task_id,
                    f"[Lead Agent] 复核未通过，打回到阶段{target_idx+1}（{stages[target_idx]}），返工轮次={rework_round}/{max_rework_rounds}",
                )
                previous_output = output
                audit["stages"].append(stage_audit)
                stage_idx = target_idx
                continue

        previous_output = output
        handoff_note = ""
        audit["stages"].append(stage_audit)
        append_log(task_id, f"[{role_code}] 阶段完成，输出长度={len(output)}，耗时={stage_duration_sec}s")
        stage_idx += 1

    final_file = os.path.join(output_dir, "多Agent_最终交付.md")
    with open(final_file, "w", encoding="utf-8") as f:
        f.write(f"# 多Agent最终交付\n\n任务：{task['title']}\n\n")
        f.write(previous_output + "\n")

    audit["finishedAt"] = now_str()
    audit["finalFile"] = os.path.basename(final_file)
    audit_file = os.path.join(output_dir, "多Agent_会话审计.json")
    with open(audit_file, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    append_log(task_id, f"[Lead Agent] 多Agent独立会话完成，最终交付：{os.path.basename(final_file)}")


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
            wf_code = (task["workflow_code"] or "").strip() if "workflow_code" in task.keys() else ""
            if wf_code:
                try:
                    wf = get_workflow_by_code(wf_code)
                    if not wf:
                        raise RuntimeError(f"未找到工作流: {wf_code}")
                    append_log(task_id, f"[SYSTEM] 启动多Agent独立会话流程：{wf_code}")
                    run_multi_agent_workflow(task_id, task, wf, output_dir)
                    update_task(task_id, status="done", finished_at=now_str(), return_code=0)
                    append_log(task_id, "[SYSTEM] 任务完成（多Agent独立会话）")
                except Exception as e:
                    update_task(task_id, status="failed", finished_at=now_str(), return_code=1)
                    append_log(task_id, f"[SYSTEM] 多Agent流程失败：{e}")
                finally:
                    running_processes.pop(task_id, None)
                return

            # 无工作流时保留演示流程
            try:
                for step in [
                    "Lead Agent 正在拆解任务...",
                    "Developer Agent 正在执行任务...",
                    "Tester Agent 正在复核结果...",
                    "Verifier Agent 正在做最终核验...",
                    "Lead Agent 正在汇总交付...",
                ]:
                    ensure_not_stopped(task_id)
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

    phase_order = ["待处理", "执行中", "待确认"]
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
    default_model = (request.form.get("default_model") or "").strip() or "gpt-5.3-codex"
    api_base = (request.form.get("api_base") or "").strip()
    api_key = (request.form.get("api_key") or "").strip()
    system_prompt = (request.form.get("system_prompt") or "").strip()
    enabled = 1 if (request.form.get("enabled") or "1") == "1" else 0

    if not code or not name:
        flash("角色创建失败：code 和 name 不能为空")
        return redirect(url_for("dashboard"))

    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO roles(code, name, description, default_model, api_base, api_key, system_prompt, enabled, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (code, name, description, default_model, api_base, api_key, system_prompt, enabled, now_str(), now_str()),
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


@app.post("/roles/<int:role_id>/config")
@login_required
def update_role_config(role_id: int):
    default_model = (request.form.get("default_model") or "").strip()
    api_base = (request.form.get("api_base") or "").strip()
    api_key = (request.form.get("api_key") or "").strip()
    system_prompt = (request.form.get("system_prompt") or "").strip()
    temperature = (request.form.get("temperature") or "").strip()
    max_tokens = (request.form.get("max_tokens") or "").strip()

    with db_conn() as conn:
        row = conn.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()
        if not row:
            flash("角色不存在")
            return redirect(url_for("dashboard"))

        fields = {
            "default_model": default_model or row["default_model"],
            "api_base": api_base or row["api_base"],
            "system_prompt": system_prompt if system_prompt else (row["system_prompt"] or ""),
            "updated_at": now_str(),
        }

        # api_key 为空时保持原值
        fields["api_key"] = api_key if api_key else (row["api_key"] or "")

        try:
            fields["temperature"] = float(temperature) if temperature else (row["temperature"] if row["temperature"] is not None else 0.3)
        except Exception:
            fields["temperature"] = row["temperature"] if row["temperature"] is not None else 0.3

        try:
            fields["max_tokens"] = int(max_tokens) if max_tokens else (row["max_tokens"] if row["max_tokens"] is not None else 1200)
        except Exception:
            fields["max_tokens"] = row["max_tokens"] if row["max_tokens"] is not None else 1200

        conn.execute(
            """
            UPDATE roles
            SET default_model=?, api_base=?, api_key=?, system_prompt=?, temperature=?, max_tokens=?, updated_at=?
            WHERE id=?
            """,
            (
                fields["default_model"],
                fields["api_base"],
                fields["api_key"],
                fields["system_prompt"],
                fields["temperature"],
                fields["max_tokens"],
                fields["updated_at"],
                role_id,
            ),
        )

    flash(f"角色配置已更新：{row['name']}")
    return redirect(url_for("dashboard"))


@app.post("/workflows")
@login_required
def create_workflow():
    code = (request.form.get("code") or "").strip()
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    stages_text = (request.form.get("stages") or "").strip()
    stage_roles_text = (request.form.get("stage_roles") or "").strip()
    default_task_type = (request.form.get("default_task_type") or "general").strip()
    default_assignee = (request.form.get("default_assignee") or "Lead Agent").strip()
    command_template = (request.form.get("command_template") or "").strip()
    enabled = 1 if (request.form.get("enabled") or "1") == "1" else 0

    if not code or not name:
        flash("工作流创建失败：code 和 name 不能为空")
        return redirect(url_for("dashboard"))

    stages = [x.strip() for x in re.split(r"[,，\n]+", stages_text) if x.strip()]
    stage_roles = parse_stage_roles(stage_roles_text)
    stages_json = json.dumps(stages, ensure_ascii=False)
    stage_roles_json = json.dumps(stage_roles, ensure_ascii=False)

    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO workflows(code, name, description, stages_json, stage_roles_json, default_task_type, default_assignee, command_template, enabled, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    code,
                    name,
                    description,
                    stages_json,
                    stage_roles_json,
                    default_task_type,
                    default_assignee,
                    command_template,
                    enabled,
                    now_str(),
                    now_str(),
                ),
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
            INSERT INTO tasks(title, description, task_type, assignee, priority, status, command, workflow_code, created_at, updated_at)
            VALUES(?,?,?,?,?,'pending',?,?,?,?)
            """,
            (title, description, task_type, assignee, priority, command, workflow_template, now_str(), now_str()),
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
            conn.execute("DELETE FROM role_session_messages WHERE task_id=?", (task_id,))
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
    multiagent = load_multiagent_summary(output_dir)

    return render_template(
        "task_detail.html",
        task=task,
        logs=logs,
        delivery=delivery,
        multiagent=multiagent,
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
