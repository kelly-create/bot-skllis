#!/usr/bin/env python3
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import shutil
import signal
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
ROLE_MAX_REWORK_ROUNDS = max(0, min(5, int(os.getenv("ATC_MAX_REWORK_ROUNDS", "5"))))
ROLE_STAGE_REVIEW_MAX_RETRIES = max(0, min(5, int(os.getenv("ATC_STAGE_REVIEW_MAX_RETRIES", "5"))))
ROLE_MAX_TOOL_ROUNDS = max(1, min(10, int(os.getenv("ATC_ROLE_MAX_TOOL_ROUNDS", "5"))))
ROLE_REASONING_EFFORT = (os.getenv("ATC_ROLE_REASONING_EFFORT", "high") or "high").strip()
ROLE_CROSS_REVIEW_ROUNDS = max(0, min(6, int(os.getenv("ATC_ROLE_CROSS_REVIEW_ROUNDS", "3"))))
ROLE_HISTORY_LIMIT = max(8, min(50, int(os.getenv("ATC_ROLE_HISTORY_LIMIT", "20"))))

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(ARTIFACT_ROOT, exist_ok=True)

app = Flask(__name__)
app.secret_key = APP_SECRET
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB

running_processes = {}
task_run_context = {}


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


def build_task_run_id(task_id: int) -> str:
    return f"run-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{task_id}-{int(time.time()*1000)%100000}"


def clear_dir_contents(path: str) -> int:
    if not os.path.isdir(path):
        return 0
    removed = 0
    for name in os.listdir(path):
        p = os.path.join(path, name)
        try:
            if os.path.isfile(p) or os.path.islink(p):
                os.remove(p)
            else:
                shutil.rmtree(p, ignore_errors=True)
            removed += 1
        except Exception:
            continue
    return removed


def clear_role_session_messages(task_id: int) -> int:
    with db_conn() as conn:
        cur = conn.execute("DELETE FROM role_session_messages WHERE task_id=?", (task_id,))
        return int(cur.rowcount or 0)


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


def _latest_run_id_from_logs(logs):
    for row in reversed(logs):
        line = (row["line"] or "")
        m = re.search(r"\[run:([^\]]+)\]", line)
        if m:
            return m.group(1)
    return ""


def _strip_log_meta(line: str) -> str:
    s = (line or "").strip()
    # 仅剥离前缀元信息（时间/run/角色），保留正文
    for _ in range(4):
        ns = re.sub(r"^\[[^\]]+\]\s*", "", s)
        if ns == s:
            break
        s = ns
    return s.strip()


def _short_line(line: str, max_len: int = 220) -> str:
    s = _strip_log_meta(line)
    if "工具执行 round=" in s:
        m = re.search(r"(工具执行\s+round=\d+/\d+\s+rc=\d+\s+timedOut=(?:True|False))", s)
        if m:
            s = m.group(1)
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def extract_failure_diagnosis(logs):
    reason = ""
    evidences = []
    latest_run_id = _latest_run_id_from_logs(logs)

    scoped_logs = logs
    if latest_run_id:
        scoped = [r for r in logs if f"[run:{latest_run_id}]" in (r["line"] or "")]
        if scoped:
            scoped_logs = scoped

    for row in reversed(scoped_logs):
        line = (row["line"] or "").strip()
        if not line:
            continue
        if ("多Agent流程失败：" in line) or ("任务失败：" in line) or ("执行异常：" in line):
            reason = line
            break

    if not reason:
        for row in reversed(scoped_logs):
            line = (row["line"] or "").strip()
            if any(k in line for k in ["FAIL", "失败", "异常", "打回"]):
                reason = line
                break

    for row in reversed(scoped_logs):
        line = (row["line"] or "").strip()
        if any(
            k in line
            for k in [
                "多Agent流程失败",
                "阶段质控结论：FAIL",
                "复核结论：FAIL",
                "打回当前阶段重做",
                "工具执行 round=",
                "模型请求失败",
                "未配置 api",
            ]
        ):
            evidences.append(_short_line(line))
        if len(evidences) >= 4:
            break

    # 去重但保序
    seen = set()
    dedup_evidences = []
    for e in evidences:
        if e in seen:
            continue
        seen.add(e)
        dedup_evidences.append(e)
    evidences = dedup_evidences

    reason_plain = _strip_log_meta(reason)
    friendly_reason = reason_plain

    m_retry = re.search(r"阶段\s+(.+?)\s+质控未通过，且已达本阶段最大重试\s*(\d+)", reason_plain)
    m_rework = re.search(r"最大返工轮次\s*(\d+)", reason_plain)
    m_http = re.search(r"HTTP\s*(\d{3})", reason_plain)

    if m_retry:
        stage, n = m_retry.group(1), m_retry.group(2)
        friendly_reason = f"{stage}阶段连续质控不通过，已达到最大重试 {n} 次，任务终止。"
    elif m_rework:
        friendly_reason = f"复核/返工达到上限（{m_rework.group(1)} 轮），任务终止。"
    elif "未配置 api_base" in reason_plain or "未配置 api_key" in reason_plain:
        friendly_reason = "角色配置不完整（缺少 API Base 或 API Key），任务无法继续。"
    elif m_http and "模型请求失败" in reason_plain:
        friendly_reason = f"模型调用失败（HTTP {m_http.group(1)}），流程中断。"
    elif "质控未通过" in reason_plain:
        friendly_reason = "阶段质控不通过，当前产物未达到验收标准。"

    suggestion = "请根据失败原因修正后重置任务；若不确定，可把“失败原因+最近3条证据”发给我，我会给出具体修复步骤。"
    combo = reason_plain + "\n" + "\n".join(evidences)
    if "未配置 api_base" in combo or "未配置 api_key" in combo:
        suggestion = "先到角色中心补齐该角色的 API Base / API Key / 模型，再重置任务。"
    elif "质控未通过" in combo and "最大重试" in combo:
        suggestion = "这是“阶段质控不通过 + 重试耗尽”。先明确该阶段的必交付文件（例如统计JSON/最终报告），要求角色一次性产出并附关键数字，再重置任务。"
    elif "质控未通过" in combo:
        suggestion = "当前阶段产出不满足验收标准。请按质控原因补齐“可验收结果”（例如实际数据/文件/结论），再重置任务。"
    elif "最大重试" in combo or "最大返工轮次" in combo:
        suggestion = "已触发重试上限。建议先优化当前阶段提示词或放宽验收条件，再重置任务；必要时提高重试上限。"
    elif "HTTP" in combo or "模型请求失败" in combo:
        suggestion = "模型/API调用失败。请检查角色 API 可用性、密钥有效性、模型名是否正确；网络波动时可直接重试。"

    return {
        "run_id": latest_run_id,
        "reason": friendly_reason or "未定位到明确失败主因（请查看日志）",
        "evidences": evidences,
        "suggestion": suggestion,
    }


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
        next_action = "查看“失败诊断”后按建议处理，再重置任务。"
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

    failure = extract_failure_diagnosis(logs) if status == "failed" else None

    return {
        "headline": headline,
        "next_action": next_action,
        "progress": progress,
        "latest_line": latest_line,
        "groups": groups,
        "primary_pack": primary_pack,
        "failure": failure,
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
            ("frontend", "前端 Agent", "前端页面、交互、可视化与体验优化", "MiniMax-M2.5"),
            ("backend", "后端 Agent", "后端业务、数据流、接口与自动化执行", "gpt-5.3-codex"),
            ("reviewer", "复核 Agent", "按验收标准复核并给出打回意见", "gpt-5.3-codex"),
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
            "Lead Agent": "你是总控角色。负责评估需求、制定执行计划、调度前后端角色、汇总最终交付。遇到阻塞时要先诊断再调整策略。",
            "frontend": "你是前端角色。负责页面结构、交互流程、可视化与可读性优化，按验收标准交付前端结果。",
            "backend": "你是后端角色。负责后端业务、数据/接口/脚本执行与故障排查。遇到反爬或失败时必须先诊断原因，再切换策略。",
            "reviewer": "你是复核角色。只做验收复核，不替代实现。若不通过必须给出可执行的打回意见。",
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

        # 角色默认模型（允许在角色中心手动覆盖）
        conn.execute(
            """
            UPDATE roles
            SET default_model = CASE WHEN default_model IS NULL OR default_model='' THEN 'gpt-5.3-codex' ELSE default_model END,
                updated_at=?
            WHERE code='Lead Agent'
            """,
            (now_str(),),
        )
        conn.execute(
            """
            UPDATE roles
            SET default_model = CASE WHEN default_model IS NULL OR default_model='' THEN 'MiniMax-M2.5' ELSE default_model END,
                updated_at=?
            WHERE code='frontend'
            """,
            (now_str(),),
        )
        conn.execute(
            """
            UPDATE roles
            SET default_model = CASE WHEN default_model IS NULL OR default_model='' THEN 'gpt-5.3-codex' ELSE default_model END,
                updated_at=?
            WHERE code='backend'
            """,
            (now_str(),),
        )
        conn.execute(
            """
            UPDATE roles
            SET default_model = CASE WHEN default_model IS NULL OR default_model='' THEN 'gpt-5.3-codex' ELSE default_model END,
                updated_at=?
            WHERE code='reviewer'
            """,
            (now_str(),),
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

        # 默认工作流（当前仅保留智能双角色）
        default_workflows = [
            (
                "intelligent_dual",
                "智能三角色（Lead+前端+后端+复核）",
                "Lead先评估并分配，前后端执行，复核失败会给意见并打回",
                json.dumps(["需求评估与分配", "前端实现", "后端实现", "复核", "联合交付"], ensure_ascii=False),
                "general",
                "Lead Agent",
                "",
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
            "intelligent_dual": {"需求评估与分配": "Lead Agent", "前端实现": "frontend", "后端实现": "backend", "复核": "reviewer", "联合交付": "Lead Agent"},
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
            "intelligent_dual": ["需求评估与分配", "前端实现", "后端实现", "复核", "联合交付"],
        }
        workflow_assignee_defaults = {
            "intelligent_dual": "Lead Agent",
        }
        for wf_code, stages in workflow_stage_defaults.items():
            conn.execute(
                """
                UPDATE workflows
                SET stages_json=?,
                    default_assignee=?,
                    updated_at=?
                WHERE code=?
                """,
                (
                    json.dumps(stages, ensure_ascii=False),
                    workflow_assignee_defaults.get(wf_code, "Lead Agent"),
                    now_str(),
                    wf_code,
                ),
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


def get_reviewer_role():
    # 新架构优先 reviewer，兼容旧 @verifier
    r = get_role_by_code("reviewer")
    if r:
        return r, "reviewer"
    r = get_role_by_code("@verifier")
    if r:
        return r, "@verifier"
    return None, "reviewer"


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
    rid = task_run_context.get(task_id)
    text = (line or "")
    if rid and not text.startswith("[run:"):
        text = f"[run:{rid}] {text}"
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO task_logs(task_id, ts, line) VALUES(?,?,?)",
            (task_id, now_str(), text[:4000]),
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


def build_default_acceptance_contract(task_title: str, sections: dict) -> dict:
    task_goal = (sections.get("task") or task_title or "").strip()
    delivery_hint = (sections.get("delivery") or "").strip()
    must_answer = [
        f"围绕任务目标给出可验证结论：{task_goal}" if task_goal else "围绕任务目标给出可验证结论",
        "给出关键数字/判断依据，并说明来源或计算方式",
        "给出可复现路径（命令、参数、数据来源或处理步骤）",
    ]
    if delivery_hint:
        must_answer.append(f"覆盖用户期望交付：{delivery_hint}")

    return {
        "must_answer": must_answer,
        "evidence_requirements": [
            "至少包含可核验的关键证据（来源片段、统计明细、或产物片段）",
            "需要说明结论与证据的对应关系",
        ],
        "delivery_form": "交付形式可自由选择（md/json/csv/txt/zip等），不强制固定文件名",
        "forbidden": [
            "只给命令或脚本片段，不给执行结果",
            "只做诊断不收敛到结论",
        ],
    }


def normalize_acceptance_contract(contract: dict, task_title: str, sections: dict) -> dict:
    base = build_default_acceptance_contract(task_title, sections)
    if not isinstance(contract, dict):
        return base

    out = dict(base)
    for k in ["must_answer", "evidence_requirements", "forbidden"]:
        v = contract.get(k)
        if isinstance(v, list):
            vv = [str(x).strip() for x in v if str(x).strip()]
            if vv:
                out[k] = vv

    if isinstance(contract.get("delivery_form"), str) and contract.get("delivery_form").strip():
        out["delivery_form"] = contract.get("delivery_form").strip()

    return out


def contract_to_text(contract: dict) -> str:
    c = contract or {}
    lines = ["【任务验收契约】"]
    ma = c.get("must_answer") or []
    er = c.get("evidence_requirements") or []
    fb = c.get("forbidden") or []
    if ma:
        lines.append("- 必须回答：")
        lines.extend([f"  - {x}" for x in ma])
    if er:
        lines.append("- 证据要求：")
        lines.extend([f"  - {x}" for x in er])
    if c.get("delivery_form"):
        lines.append(f"- 交付形式：{c.get('delivery_form')}")
    if fb:
        lines.append("- 禁止行为：")
        lines.extend([f"  - {x}" for x in fb])
    return "\n".join(lines)


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

    # GPT/Codex 角色默认开启深度思考参数（MiniMax等模型不注入）
    ml = model.lower()
    if ml.startswith("gpt-") or ("codex" in ml):
        effort = ROLE_REASONING_EFFORT if ROLE_REASONING_EFFORT in ("low", "medium", "high") else "high"
        payload["reasoning"] = {"effort": effort}
        payload["thinking"] = effort
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
    return r in ("reviewer", "@verifier") or any(k in s for k in ["验证", "复核", "验收", "review"])


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


def parse_role_action(text: str) -> dict:
    raw = (text or "").strip()
    out = {"action": "final", "content": raw, "command": "", "reason": ""}
    if not raw:
        return out

    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return out

    try:
        data = json.loads(m.group(0))
    except Exception:
        return out

    action = str(data.get("action") or "").strip().lower()
    if action == "run_command":
        out["action"] = "run_command"
        out["command"] = str(data.get("command") or data.get("cmd") or "").strip()
        out["reason"] = str(data.get("reason") or "").strip()
        return out

    if action == "final":
        out["action"] = "final"
        out["content"] = str(data.get("content") or raw).strip()
        return out

    return out


def list_output_file_names(output_dir: str) -> set:
    if not os.path.isdir(output_dir):
        return set()
    out = set()
    for name in os.listdir(output_dir):
        full = os.path.join(output_dir, name)
        if os.path.isfile(full):
            out.add(name)
    return out


def is_system_generated_output(name: str) -> bool:
    n = (name or "").strip()
    return n.startswith("步骤") or n in ("多Agent_最终交付.md", "多Agent_会话审计.json")


def task_requires_real_artifacts(task_text: str) -> bool:
    t = (task_text or "")
    keys = ["爬取", "采集", "关键词", "文包", "报告", "导出", "csv", "json", "zip", "附件"]
    return any(k in t for k in keys)


def is_safe_role_command(command: str) -> tuple[bool, str]:
    cmd = (command or "").strip()
    if not cmd:
        return False, "命令为空"
    if len(cmd) > 800:
        return False, "命令过长（>800）"
    if "\n" in cmd or "\r" in cmd:
        return False, "命令不能包含换行"

    blocked = [
        "rm -rf /",
        "shutdown",
        "reboot",
        "mkfs",
        "fdisk",
        "poweroff",
        ":(){",
        "halt",
        "systemctl stop",
        "systemctl disable",
    ]
    lower = cmd.lower()
    for b in blocked:
        if b in lower:
            return False, f"命中高危命令片段: {b}"
    return True, "ok"


def execute_role_command(command: str, task_id: int, base_dir: str, input_dir: str, output_dir: str, timeout_sec: int = 240) -> dict:
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
        command,
        shell=True,
        cwd=WORKDIR,
        executable="/bin/bash",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        out, _ = proc.communicate(timeout=max(30, int(timeout_sec)))
        rc = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        rc = 124
        timed_out = True

    out = (out or "")[-6000:]
    return {"rc": rc, "output": out, "timedOut": timed_out}


def run_role_stage_with_tools(
    task_id: int,
    stage: str,
    role,
    messages: list,
    base_dir: str,
    input_dir: str,
    output_dir: str,
    max_tool_rounds: int = ROLE_MAX_TOOL_ROUNDS,
):
    tool_round = 0
    tool_events = []

    while True:
        ensure_not_stopped(task_id)
        assistant_text = call_role_llm(role, messages)
        save_role_message(task_id, role["code"], stage, "assistant", assistant_text)

        action = parse_role_action(assistant_text)
        if action["action"] == "run_command" and tool_round < max_tool_rounds:
            cmd = action.get("command", "")
            ok, reason = is_safe_role_command(cmd)
            if not ok:
                result = {"rc": 1, "output": f"[TOOL_BRIDGE] 拒绝执行：{reason}", "timedOut": False}
            else:
                result = execute_role_command(cmd, task_id, base_dir, input_dir, output_dir)

            tool_events.append(
                {
                    "round": tool_round + 1,
                    "command": cmd,
                    "rc": result["rc"],
                    "timedOut": result["timedOut"],
                }
            )
            append_log(
                task_id,
                f"[{role['code']}] 工具执行 round={tool_round+1}/{max_tool_rounds} rc={result['rc']} timedOut={result['timedOut']} cmd={cmd}",
            )

            tool_feedback = (
                "工具执行结果如下，请基于结果继续。\n"
                f"命令: {cmd}\n"
                f"返回码: {result['rc']}\n"
                f"是否超时: {result['timedOut']}\n"
                f"输出片段:\n{result['output']}\n\n"
                "若还需要执行工具，可继续返回 run_command JSON；若已完成，请返回 final JSON。"
            )
            messages.append({"role": "assistant", "content": assistant_text})
            messages.append({"role": "user", "content": tool_feedback})
            save_role_message(task_id, role["code"], stage, "user", tool_feedback)
            tool_round += 1
            continue

        final_content = action.get("content") if action.get("action") == "final" else assistant_text
        return final_content, tool_events


def find_stage_index_by_role(stages: list, stage_roles: dict, role_code: str, before_idx: int, fallback_idx: int = 0) -> int:
    rc = (role_code or "").strip()
    if not rc:
        return fallback_idx
    for i in range(max(0, before_idx - 1), -1, -1):
        st = stages[i]
        if (stage_roles.get(st) or "").strip() == rc:
            return i
    return fallback_idx


def parse_dispatch_plan(text: str, allowed_stages: list, enabled_role_codes: set) -> dict:
    raw = (text or "").strip()
    out = {
        "assignments": {},
        "active_stages": None,  # None=不改，list=改写
        "skipped_stages": [],
        "acceptance_contract": None,
        "collision_rounds": None,
    }
    if not raw:
        return out

    payload = None
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            payload = json.loads(m.group(0))
        except Exception:
            payload = None

    if not isinstance(payload, dict):
        return out

    assignments = payload.get("assignments") or payload.get("dispatch") or []
    if isinstance(assignments, list):
        for item in assignments:
            if not isinstance(item, dict):
                continue
            stage = str(item.get("stage") or "").strip()
            role = str(item.get("role") or item.get("assignee") or "").strip()
            if stage in allowed_stages and role in enabled_role_codes:
                out["assignments"][stage] = role

    # 兼容直接 map
    if not out["assignments"]:
        for k, v in payload.items():
            ks = str(k).strip()
            vs = str(v).strip() if isinstance(v, (str, int, float)) else ""
            if ks in allowed_stages and vs in enabled_role_codes:
                out["assignments"][ks] = vs

    active_raw = payload.get("active_stages")
    if isinstance(active_raw, list):
        active = [str(x).strip() for x in active_raw if str(x).strip() in allowed_stages]
        out["active_stages"] = active

    skip_raw = payload.get("skip_stages") or payload.get("skipped_stages")
    if isinstance(skip_raw, list):
        skips = [str(x).strip() for x in skip_raw if str(x).strip() in allowed_stages]
        out["skipped_stages"] = skips
        if out["active_stages"] is None:
            out["active_stages"] = [s for s in allowed_stages if s not in skips]

    contract_raw = payload.get("acceptance_contract")
    if isinstance(contract_raw, dict):
        out["acceptance_contract"] = contract_raw

    rounds_raw = payload.get("collision_rounds")
    if isinstance(rounds_raw, (int, float, str)):
        try:
            rr = int(float(rounds_raw))
            out["collision_rounds"] = max(0, min(6, rr))
        except Exception:
            pass

    return out


def run_stage_collision(
    task_id: int,
    stage: str,
    role,
    reviewer_role,
    sections: dict,
    contract_text: str,
    previous_output: str,
    handoff_note: str,
    current_output: str,
    base_dir: str,
    input_dir: str,
    output_dir: str,
    rounds: int,
):
    if not reviewer_role or rounds <= 0:
        return current_output, [], []

    reviewer_code = reviewer_role["code"]
    output = current_output
    extra_tool_events = []
    collision_records = []

    for i in range(1, rounds + 1):
        ensure_not_stopped(task_id)
        review_stage = f"{stage}-对抗评审"
        review_prompt = (
            "你是对抗评审角色。目标不是复述，而是找出当前输出离‘可验收交付’还差什么。"
            "请严格返回 JSON："
            '{"decision":"PASS|FAIL","reason":"...","issues":["..."],"send_back_role":"当前角色code","rework_instructions":"..."}'
            "。FAIL 时必须给出可执行修改要求。\n"
            f"任务目标：{sections.get('task') or ''}\n"
            f"期望交付：{sections.get('delivery') or ''}\n"
            f"{contract_text}\n\n"
            f"当前阶段输出：\n{output}\n"
        )
        review_msgs = [
            {"role": "system", "content": (reviewer_role["system_prompt"] or "你是严苛评审。")},
            {"role": "user", "content": review_prompt},
        ]
        save_role_message(task_id, reviewer_code, review_stage, "user", review_prompt)
        review_output = call_role_llm(reviewer_role, review_msgs)
        save_role_message(task_id, reviewer_code, review_stage, "assistant", review_output)
        decision = parse_verifier_feedback(review_output)
        dec = decision.get("decision", "UNKNOWN")

        collision_item = {
            "round": i,
            "reviewer": reviewer_code,
            "decision": decision,
        }
        collision_records.append(collision_item)
        append_log(task_id, f"[{reviewer_code}] 对抗评审 第{i}/{rounds}轮：{dec} | reason={decision.get('reason','')[:120]}")

        if dec == "PASS":
            break

        revise_instruction = (
            "你收到评审挑战，请只针对缺口补齐可验收结果。"
            "允许继续使用 run_command；若完成请返回 final。"
            "不要重复诊断，优先输出新增证据与新增结论。\n"
            f"评审原因：{decision.get('reason','')}\n"
            f"评审问题：{'；'.join(decision.get('issues') or [])}\n"
            f"修改要求：{decision.get('rework_instructions','请补齐缺口后提交。')}\n"
            f"{contract_text}"
        )

        history = load_role_messages(task_id, role["code"], limit=ROLE_HISTORY_LIMIT)
        msgs = [{"role": "system", "content": (role["system_prompt"] or f"你是{role['code']}") }]
        for h in history:
            turn = (h["turn"] or "").strip().lower()
            if turn in ("user", "assistant", "system"):
                msgs.append({"role": turn, "content": h["content"] or ""})
        revise_prompt = (
            f"你当前负责阶段：{stage}\n"
            f"任务描述：{sections.get('task') or ''}\n"
            f"期望交付：{sections.get('delivery') or ''}\n"
            f"上一个阶段输出（可忽略）：\n{previous_output}\n\n"
            f"返工/交接说明（可忽略）：\n{handoff_note}\n\n"
            f"当前阶段已有输出：\n{output}\n\n"
            f"本轮挑战与修改要求：\n{revise_instruction}"
        )
        msgs.append({"role": "user", "content": revise_prompt})
        save_role_message(task_id, role["code"], stage, "user", revise_prompt)

        new_output, new_tools = run_role_stage_with_tools(
            task_id=task_id,
            stage=stage,
            role=role,
            messages=msgs,
            base_dir=base_dir,
            input_dir=input_dir,
            output_dir=output_dir,
            max_tool_rounds=ROLE_MAX_TOOL_ROUNDS,
        )
        output = new_output
        extra_tool_events.extend(new_tools)
        collision_item["toolEvents"] = new_tools
        collision_item["revisedChars"] = len(new_output)
        append_log(task_id, f"[{role['code']}] 对抗评审后修订完成（第{i}/{rounds}轮），输出长度={len(new_output)}")

    return output, extra_tool_events, collision_records


def run_multi_agent_workflow(task_id: int, task, wf, base_dir: str, input_dir: str, output_dir: str):
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
    active_stage_set = set(stages)
    acceptance_contract = build_default_acceptance_contract(task["title"] or "", sections)
    collision_rounds = ROLE_CROSS_REVIEW_ROUNDS
    last_execution_output = ""
    last_execution_stage = ""
    last_execution_role = ""
    lead_acceptance_result = None

    audit = {
        "taskId": task_id,
        "workflow": wf["code"],
        "maxReworkRounds": max_rework_rounds,
        "maxStageReviewRetries": max_stage_review_retries,
        "reworkRoundsUsed": 0,
        "stages": [],
        "dynamicAssignments": {},
        "acceptanceContract": acceptance_contract,
        "collisionRounds": collision_rounds,
        "startedAt": now_str(),
    }

    while stage_idx < len(stages):
        iterations += 1
        if iterations > max_iterations:
            raise RuntimeError(f"超过最大迭代限制（{max_iterations}），已自动终止避免循环")

        ensure_not_stopped(task_id)
        stage = stages[stage_idx]

        # 动态分发后可跳过非必要阶段
        if (stage_idx > 0) and (stage not in active_stage_set):
            append_log(task_id, f"[Lead Agent] 跳过阶段{stage_idx+1}：{stage}（本轮未分配）")
            audit["stages"].append(
                {
                    "executionNo": None,
                    "index": stage_idx + 1,
                    "stage": stage,
                    "role": stage_roles.get(stage) or "-",
                    "model": "-",
                    "status": "SKIPPED",
                    "reason": "动态分发未纳入本轮执行",
                    "finishedAt": now_str(),
                }
            )
            stage_idx += 1
            continue

        role_code = stage_roles.get(stage) or (wf["default_assignee"] or "") or (task["assignee"] or "Lead Agent")
        role = get_role_by_code(role_code)
        if not role:
            raise RuntimeError(f"阶段 {stage} 找不到角色: {role_code}")
        if int(role["enabled"] or 0) != 1:
            raise RuntimeError(f"阶段 {stage} 角色未启用: {role_code}")

        stage_retry = stage_retry_counts.get(stage, 0)
        append_log(task_id, f"[Lead Agent] 阶段{stage_idx+1}/{len(stages)}：{stage} -> {role_code}（返工轮次={rework_round}，本阶段重试={stage_retry}/{max_stage_review_retries}）")

        history = load_role_messages(task_id, role_code, limit=ROLE_HISTORY_LIMIT)
        sys_prompt = (role["system_prompt"] or "").strip()
        if not sys_prompt:
            sys_prompt = f"你是{role['name']}（{role['code']}），职责：{role['description'] or '完成被分配阶段并输出可执行结果'}。"

        verifier_mode = is_verifier_stage(stage, role_code)
        dispatch_stage = ("分发" in stage) or (stage_idx == 0 and any(k in stage for k in ["评估", "拆解", "规划"]))
        lead_dispatch_mode = bool(dispatch_stage)
        lead_acceptance_mode = (
            role_code == "Lead Agent"
            and (not lead_dispatch_mode)
            and any(k in stage for k in ["联合交付", "验收", "交付"])
        )
        if verifier_mode:
            stage_instruction = (
                "你只负责当前复核阶段，不负责开发实现。请严格依据任务要求判定是否通过。"
                "必须返回 JSON："
                '{"decision":"PASS|FAIL","reason":"...","issues":["..."],"send_back_role":"frontend 或 backend","rework_instructions":"..."}'
                "。如果通过，issues可为空，send_back_role可空。"
            )
        elif lead_dispatch_mode:
            stage_instruction = (
                "你是当前总控分发阶段：先评估需求复杂度、阻塞风险与执行成本，再按后续角色分发任务。"
                "请输出“分发清单”，至少包含：角色、该角色目标、输入、输出、验收标准。"
                "不要替执行角色完成实现，只做评估、拆解和分发。"
                "并在结尾附上 JSON（assignments + active_stages + acceptance_contract + collision_rounds）用于动态分发，例如："
                '{"assignments":[{"stage":"前端实现","role":"frontend"},{"stage":"后端实现","role":"backend"}],"active_stages":["前端实现","后端实现","复核","联合交付"],"skip_stages":[],"acceptance_contract":{"must_answer":["必须回答的问题"],"evidence_requirements":["证据要求"],"delivery_form":"交付形式不限"},"collision_rounds":3}'
                "。stage 必须是现有阶段名，role 必须是可用角色 code。"
                "若某阶段本轮不需要执行，请明确写入 skip_stages。"
                "acceptance_contract 只定义验收维度，不要写死具体文件名。"
            )
        elif lead_acceptance_mode:
            stage_instruction = (
                "你是Lead最终验收阶段：必须对前序执行与复核结果做最终裁决。"
                "请依据任务验收契约判断，不要写死具体文件名。"
                "如通过，请返回 JSON："
                '{"decision":"PASS","reason":"...","issues":[],"send_back_role":"","rework_instructions":""}'
                "。"
                "如不通过，必须返回 JSON："
                '{"decision":"FAIL","reason":"...","issues":["..."],"send_back_role":"frontend 或 backend","rework_instructions":"明确可执行的修改要求"}'
                "。FAIL 时必须给出可执行的打回意见。"
            )
        else:
            stage_instruction = (
                "你只负责当前阶段，不要替下一阶段做决定。"
                "输出本阶段可直接交接给下阶段的结果（中文、结构化、可执行）。"
                "如果执行遇到拦截/失败，必须先给出诊断，再切换策略后继续执行，不要机械重复同一命令。"
                "如果任务涉及爬取/采集/关键词/文包，必须通过 run_command 产出真实文件到 $TASK_OUTPUT_DIR。"
                "如果需要实际执行工具/脚本，请只输出 JSON："
                '{"action":"run_command","command":"python3 scripts/xxx.py ...","reason":"为什么要执行"}'
                "。系统会执行后把结果回传给你。"
                "当阶段完成时，请输出 JSON："
                '{"action":"final","content":"你的阶段交付内容"}'
            )

        task_text_all = "\n".join([
            sections.get("task") or "",
            sections.get("delivery") or "",
            sections.get("extra") or "",
            task["title"] or "",
        ])
        command_hint = ""
        if any(k in task_text_all for k in ["小说", "关键词", "文包", "爬取", "采集"]):
            command_hint = (
                "\n\n可直接执行的参考命令（如适配本任务请优先使用）：\n"
                f"cd {WORKDIR} && python3 scripts/xhs_novel_multiagent_pipeline.py "
                "--keywords '小说推文,小说推荐,网文,言情小说,悬疑小说,完结小说,书荒推荐,番茄小说,爽文小说,推理小说' "
                "--cookie-file $TASK_INPUT_DIR/xhs_cookies.json "
                "--output-dir $TASK_OUTPUT_DIR --max-rounds 3 --min-usable 8 --min-recent-7d 7 --min-domain-ratio 0.75 --max-noise-ratio 0.35 --pack-format zip"
            )

        contract_text = contract_to_text(acceptance_contract)

        user_prompt = (
            f"你当前负责阶段：{stage}\n"
            f"任务标题：{task['title']}\n"
            f"任务描述：{sections.get('task') or task['description'] or ''}\n"
            f"期望交付：{sections.get('delivery') or ''}\n"
            f"补充说明：{sections.get('extra') or ''}\n"
            f"上一个阶段输出（若为空可忽略）：\n{previous_output}\n\n"
            f"返工/交接说明（若为空可忽略）：\n{handoff_note}\n\n"
            f"{contract_text}\n\n"
            f"阶段规则：{stage_instruction}"
            f"{command_hint}"
        )

        messages = [{"role": "system", "content": sys_prompt}]
        for h in history:
            turn = (h["turn"] or "").strip().lower()
            if turn in ("user", "assistant", "system"):
                messages.append({"role": turn, "content": h["content"] or ""})
        messages.append({"role": "user", "content": user_prompt})

        stage_files_before = list_output_file_names(output_dir)
        stage_started_at = now_str()
        stage_t0 = time.perf_counter()
        save_role_message(task_id, role_code, stage, "user", user_prompt)
        output, tool_events = run_role_stage_with_tools(
            task_id=task_id,
            stage=stage,
            role=role,
            messages=messages,
            base_dir=base_dir,
            input_dir=input_dir,
            output_dir=output_dir,
            max_tool_rounds=ROLE_MAX_TOOL_ROUNDS,
        )
        stage_duration_sec = round(time.perf_counter() - stage_t0, 2)
        stage_files_after = list_output_file_names(output_dir)
        produced_files = sorted(list(stage_files_after - stage_files_before))
        produced_non_system = [x for x in produced_files if not is_system_generated_output(x)]
        existing_non_system = [x for x in sorted(stage_files_after) if not is_system_generated_output(x)]

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
            "toolEvents": tool_events,
            "producedFiles": produced_files,
            "producedNonSystemFiles": produced_non_system,
            "existingNonSystemFiles": existing_non_system,
            "outputFile": os.path.basename(stage_file),
            "outputChars": len(output),
            "finishedAt": now_str(),
        }

        # 动态分发：Lead 在“需求接收与分发”阶段可动态改写后续阶段角色 + 阶段激活计划
        if lead_dispatch_mode:
            allowed_following_stages = stages[stage_idx + 1 :]
            plan = parse_dispatch_plan(output, allowed_following_stages, enabled_role_codes)
            dynamic = plan.get("assignments") or {}
            if dynamic:
                stage_roles.update(dynamic)
                audit["dynamicAssignments"].update(dynamic)
                stage_audit["dynamicAssignments"] = dynamic
                append_log(task_id, f"[Lead Agent] 动态分发生效：{json.dumps(dynamic, ensure_ascii=False)}")

            contract_raw = plan.get("acceptance_contract")
            if isinstance(contract_raw, dict):
                acceptance_contract = normalize_acceptance_contract(contract_raw, task["title"] or "", sections)
                audit["acceptanceContract"] = acceptance_contract
                stage_audit["acceptanceContract"] = acceptance_contract
                append_log(task_id, "[Lead Agent] 已更新任务验收契约（动态生成）")

            rounds_raw = plan.get("collision_rounds")
            if isinstance(rounds_raw, int):
                collision_rounds = max(0, min(6, rounds_raw))
                audit["collisionRounds"] = collision_rounds
                stage_audit["collisionRounds"] = collision_rounds
                append_log(task_id, f"[Lead Agent] 已设置角色碰撞轮次：{collision_rounds}")

            active_stages = plan.get("active_stages")
            if isinstance(active_stages, list):
                # 守住末端质控/交付类阶段，避免被误跳过
                safety_stages = [s for s in allowed_following_stages if ("验证" in s or "复核" in s or "交付" in s)]
                active_final = list(dict.fromkeys(active_stages + safety_stages))

                # 防呆：若Lead把所有执行阶段都跳过，自动补回至少一个执行阶段，避免“只复核不执行”死循环
                exec_candidates = [
                    s
                    for s in allowed_following_stages
                    if any(k in s for k in ["前端", "后端", "执行", "采集", "开发", "文包"])
                ]
                if exec_candidates and all(s not in active_final for s in exec_candidates):
                    preferred = None
                    for p in ["后端实现", "执行", "开发", "采集", "前端实现"]:
                        if p in exec_candidates:
                            preferred = p
                            break
                    if not preferred:
                        preferred = exec_candidates[0]
                    active_final = list(dict.fromkeys(active_final + [preferred]))
                    stage_audit["autoAddedExecutionStage"] = preferred
                    append_log(task_id, f"[Lead Agent] 检测到执行阶段被全部跳过，已自动补回：{preferred}")

                active_stage_set = {stages[0], *active_final}
                skipped = [s for s in allowed_following_stages if s not in active_stage_set]
                stage_audit["activeStages"] = active_final
                stage_audit["skippedStages"] = skipped
                append_log(task_id, f"[Lead Agent] 阶段执行计划：active={active_final} | skipped={skipped}")
            elif not dynamic:
                append_log(task_id, "[Lead Agent] 未解析到有效动态分发JSON，沿用工作流默认分配")

        # 多角色碰撞：执行阶段先做 reviewer 对抗评审，再由当前角色修订（可多轮）
        if (not verifier_mode) and (not lead_dispatch_mode) and (not lead_acceptance_mode) and collision_rounds > 0:
            reviewer_role, reviewer_code = get_reviewer_role()
            if reviewer_role and int(reviewer_role["enabled"] or 0) == 1:
                output, extra_tools, collision_records = run_stage_collision(
                    task_id=task_id,
                    stage=stage,
                    role=role,
                    reviewer_role=reviewer_role,
                    sections=sections,
                    contract_text=contract_text,
                    previous_output=previous_output,
                    handoff_note=handoff_note,
                    current_output=output,
                    base_dir=base_dir,
                    input_dir=input_dir,
                    output_dir=output_dir,
                    rounds=collision_rounds,
                )
                if extra_tools:
                    tool_events.extend(extra_tools)
                    stage_audit["toolEvents"] = tool_events
                if collision_records:
                    stage_audit["collisionRecords"] = collision_records

                # 碰撞轮次后重新计算产物与输出统计
                stage_files_after = list_output_file_names(output_dir)
                produced_files = sorted(list(stage_files_after - stage_files_before))
                produced_non_system = [x for x in produced_files if not is_system_generated_output(x)]
                existing_non_system = [x for x in sorted(stage_files_after) if not is_system_generated_output(x)]
                stage_audit["producedFiles"] = produced_files
                stage_audit["producedNonSystemFiles"] = produced_non_system
                stage_audit["existingNonSystemFiles"] = existing_non_system
                stage_audit["outputChars"] = len(output)

                with open(stage_file, "w", encoding="utf-8") as f:
                    f.write(f"# 步骤{execution_no}｜阶段{stage_idx+1}：{stage}\n\n")
                    f.write(f"角色：{role['name']}（{role['code']}）\n")
                    f.write(f"返工轮次：{rework_round}\n")
                    f.write(f"对抗评审轮次：{len(collision_records)}\n\n")
                    f.write(output + "\n")

        # 每个执行角色完成后都做阶段质控（由 reviewer 复核）
        if (not verifier_mode) and (not lead_dispatch_mode) and (not lead_acceptance_mode):
            auto_fail_reason = ""
            if tool_events and all(int(e.get("rc", 1)) != 0 for e in tool_events):
                auto_fail_reason = "执行了工具命令但全部失败（rc非0），请先修复命令/环境后再提交。"

            needs_artifacts = task_requires_real_artifacts(task_text_all)
            if (not auto_fail_reason) and needs_artifacts and (stage in ["执行", "采集", "开发", "文包", "交付", "联合交付"]) and len(existing_non_system) == 0:
                auto_fail_reason = "任务要求包含可验收产物（爬取/关键词/文包等），但当前输出目录无可验收真实文件。"

            quality = None
            review_output = ""
            if auto_fail_reason:
                quality = {
                    "decision": "FAIL",
                    "reason": auto_fail_reason,
                    "issues": ["缺少真实产物文件或工具执行失败"],
                    "send_back_role": role_code,
                    "rework_instructions": "请通过 run_command 真实执行并产出文件到 $TASK_OUTPUT_DIR，再提交 final。",
                }
                stage_audit["qualityGate"] = {"raw": "", "decision": quality, "autoRule": "artifact_or_tool_guard"}
                append_log(task_id, f"[reviewer] 阶段质控结论：FAIL | stage={stage} | reason={auto_fail_reason}")
            else:
                reviewer_role, reviewer_code = get_reviewer_role()
                if reviewer_role and int(reviewer_role["enabled"] or 0) == 1:
                    review_stage = f"{stage}-阶段质控"
                    review_prompt = (
                        "你是阶段质控复核。请只对当前阶段输出进行验收，不要重写实现。"
                        f"当前阶段：{stage}，执行角色：{role_code}。\n"
                        f"任务目标：{sections.get('task') or task['description'] or ''}\n"
                        f"期望交付：{sections.get('delivery') or ''}\n"
                        f"{contract_text}\n"
                        f"本阶段输出：\n{output}\n\n"
                        f"本阶段新增产出（非系统生成）：{produced_non_system}\n"
                        f"当前可验收产物（非系统生成）：{existing_non_system}\n"
                        "注意：不要把固定文件名当成硬约束，按验收契约判断是否满足任务。"
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
                    save_role_message(task_id, reviewer_code, review_stage, "user", review_prompt)
                    review_output = call_role_llm(reviewer_role, review_msgs)
                    save_role_message(task_id, reviewer_code, review_stage, "assistant", review_output)
                    quality = parse_verifier_feedback(review_output)
                    stage_audit["qualityGate"] = {"raw": review_output, "decision": quality}

                    q_dec = quality.get("decision", "UNKNOWN")
                    append_log(task_id, f"[{reviewer_code}] 阶段质控结论：{q_dec} | stage={stage} | reason={quality.get('reason','')[:120]}")
                else:
                    quality = {"decision": "SKIP", "reason": "reviewer不可用，跳过阶段质控"}
                    stage_audit["qualityGate"] = {"decision": quality}

            q_dec = (quality or {}).get("decision", "UNKNOWN")
            if q_dec != "PASS" and q_dec != "SKIP":
                if stage_retry >= max_stage_review_retries:
                    stage_audit["terminatedByStageReview"] = True
                    audit["stages"].append(stage_audit)
                    raise RuntimeError(f"阶段 {stage} 质控未通过，且已达本阶段最大重试 {max_stage_review_retries}")

                stage_retry_counts[stage] = stage_retry + 1
                handoff_note = (
                    f"阶段质控未通过（{stage}，第{stage_retry_counts[stage]}次重试）。"
                    f"原因：{(quality or {}).get('reason','')}。"
                    f"问题：{'；'.join((quality or {}).get('issues') or [])}。"
                    f"修改要求：{(quality or {}).get('rework_instructions','请根据质控意见修改后重新提交本阶段。')}"
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

        # Lead 最终验收阶段：Lead 也有打回权限
        if lead_acceptance_mode:
            decision = parse_verifier_feedback(output)
            lead_acceptance_result = decision
            stage_audit["leadAcceptance"] = decision
            dec = decision.get("decision", "UNKNOWN")
            append_log(task_id, f"[Lead Agent] 验收结论：{dec} | reason={decision.get('reason','')[:120]}")

            if dec != "PASS":
                if rework_round >= max_rework_rounds:
                    stage_audit["terminatedByMaxRework"] = True
                    audit["stages"].append(stage_audit)
                    audit["reworkRoundsUsed"] = rework_round
                    raise RuntimeError(f"Lead验收未通过，已达最大返工轮次 {max_rework_rounds}，任务终止")

                target_role = (decision.get("send_back_role") or "").strip()
                target_idx = find_stage_index_by_role(stages, stage_roles, target_role, stage_idx, fallback_idx=max(0, stage_idx - 1))
                rework_round += 1
                audit["reworkRoundsUsed"] = rework_round
                handoff_note = (
                    f"Lead验收不通过（第{rework_round}轮返工）。"
                    f"原因：{decision.get('reason','')}。"
                    f"问题：{'；'.join(decision.get('issues') or [])}。"
                    f"修改要求：{decision.get('rework_instructions','请根据Lead验收意见修改后提交。')}"
                )
                append_log(
                    task_id,
                    f"[Lead Agent] 验收未通过，打回到阶段{target_idx+1}（{stages[target_idx]}），返工轮次={rework_round}/{max_rework_rounds}",
                )
                previous_output = output
                audit["stages"].append(stage_audit)
                stage_idx = target_idx
                continue

        if (not verifier_mode) and (not lead_dispatch_mode) and (not lead_acceptance_mode):
            last_execution_output = output
            last_execution_stage = stage
            last_execution_role = role_code

        previous_output = output
        handoff_note = ""
        audit["stages"].append(stage_audit)
        append_log(task_id, f"[{role_code}] 阶段完成，输出长度={len(output)}，耗时={stage_duration_sec}s")
        stage_idx += 1

    final_non_system_files = [x for x in sorted(list_output_file_names(output_dir)) if not is_system_generated_output(x)]
    final_body = previous_output

    if lead_acceptance_result and (lead_acceptance_result.get("decision") == "PASS") and last_execution_output:
        reason = lead_acceptance_result.get("reason") or "通过最终验收。"
        issues = lead_acceptance_result.get("issues") or []
        final_body = (
            "## Lead 最终验收\n"
            f"- 结论：PASS\n"
            f"- 原因：{reason}\n"
            + (f"- 注意事项：{'；'.join(issues)}\n" if issues else "")
            + "\n## 核心交付正文\n"
            f"（来源：阶段【{last_execution_stage}】角色【{last_execution_role}】）\n\n"
            f"{last_execution_output}\n"
        )

    final_file = os.path.join(output_dir, "多Agent_最终交付.md")
    with open(final_file, "w", encoding="utf-8") as f:
        f.write(f"# 多Agent最终交付\n\n任务：{task['title']}\n\n")
        if final_non_system_files:
            f.write("## 可验收产物清单\n")
            for fn in final_non_system_files:
                f.write(f"- {fn}\n")
            f.write("\n")
        f.write(final_body + "\n")

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
        task_run_context.pop(task_id, None)
        return

    with limiter.acquire():
        update_task(task_id, status="running", started_at=now_str(), return_code=None)
        base_dir, input_dir, output_dir = task_artifact_dirs(task_id)

        run_id = build_task_run_id(task_id)
        task_run_context[task_id] = run_id

        removed_outputs = clear_dir_contents(output_dir)
        cleared_msgs = clear_role_session_messages(task_id)

        append_log(task_id, f"[SYSTEM] 本次运行ID: {run_id}")
        append_log(task_id, f"[SYSTEM] 任务启动，当前并发上限={limiter.get_limit()}")
        append_log(task_id, f"[SYSTEM] 任务产物目录: {base_dir}")
        append_log(task_id, f"[SYSTEM] 输入附件目录: {input_dir}")
        append_log(task_id, f"[SYSTEM] 输出产物目录: {output_dir}")
        append_log(task_id, f"[SYSTEM] 已清理上一轮输出文件: {removed_outputs} 项")
        if cleared_msgs > 0:
            append_log(task_id, f"[SYSTEM] 已清理上一轮角色会话消息: {cleared_msgs} 条")

        cmd = (task["command"] or "").strip()
        if not cmd:
            wf_code = (task["workflow_code"] or "").strip() if "workflow_code" in task.keys() else ""
            if wf_code:
                try:
                    wf = get_workflow_by_code(wf_code)
                    if not wf:
                        raise RuntimeError(f"未找到工作流: {wf_code}")
                    append_log(task_id, f"[SYSTEM] 启动多Agent独立会话流程：{wf_code}")
                    run_multi_agent_workflow(task_id, task, wf, base_dir, input_dir, output_dir)
                    update_task(task_id, status="done", finished_at=now_str(), return_code=0)
                    append_log(task_id, "[SYSTEM] 任务完成（多Agent独立会话）")
                except Exception as e:
                    update_task(task_id, status="failed", finished_at=now_str(), return_code=1)
                    append_log(task_id, f"[SYSTEM] 多Agent流程失败：{e}")
                finally:
                    running_processes.pop(task_id, None)
                    task_run_context.pop(task_id, None)
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
                task_run_context.pop(task_id, None)
            return

        try:
            append_log(task_id, f"[SYSTEM] 执行命令: {cmd}")
            env = os.environ.copy()
            env.update(
                {
                    "TASK_ID": str(task_id),
                    "TASK_RUN_ID": run_id,
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
                start_new_session=True,
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
            task_run_context.pop(task_id, None)


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
        "intelligent_dual": "智能三角色任务",
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
            "--max-rounds 3 --min-usable 8 --min-recent-7d 7 --min-domain-ratio 0.75 --max-noise-ratio 0.35 "
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
    workflow_template = (request.form.get("workflow_template") or "intelligent_dual").strip()
    task_brief = (request.form.get("task_brief") or "").strip()
    delivery_expectation = (request.form.get("delivery_expectation") or "").strip()
    project_dir = (request.form.get("project_dir") or "").strip()
    raw_command = (request.form.get("command") or "").strip()

    # 重构后默认不做“强制自动路由”，让双角色自主评估与分配执行路径
    auto_routed = False

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
        if assignee in ("", "Lead Agent", "backend") and (wf["default_assignee"] or "").strip():
            assignee = (wf["default_assignee"] or "Lead Agent").strip()

    command = raw_command
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
    if auto_routed:
        append_log(task_id, "[SYSTEM] 已根据任务内容自动路由到 novel_multiagent 专用流水线")
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
        task_run_context.pop(task_id, None)
        update_task(task_id, status="failed", finished_at=now_str(), return_code=137)
        append_log(task_id, "[SYSTEM] 任务在启动阶段被停止")
        flash(f"任务 #{task_id} 已停止")
        return redirect(url_for("dashboard"))

    if not proc:
        flash("任务未运行")
        return redirect(url_for("dashboard"))

    try:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            append_log(task_id, f"[SYSTEM] 已发送停止信号到进程组 pgid={pgid}")
        except Exception:
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
