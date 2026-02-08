#!/usr/bin/env python3
"""
配置安全检查器
- 修改配置前自动验证 Schema
- 自动备份当前配置
- 异常时自动回滚
"""

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

CONFIG_PATH = os.path.expanduser("~/.openclaw/openclaw.json")
BACKUP_DIR = os.path.expanduser("~/.openclaw/config_backups")


def ensure_backup_dir():
    """确保备份目录存在"""
    os.makedirs(BACKUP_DIR, exist_ok=True)


def backup_config() -> str:
    """备份当前配置"""
    ensure_backup_dir()
    
    if not os.path.exists(CONFIG_PATH):
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{BACKUP_DIR}/openclaw_{timestamp}.json"
    
    shutil.copy2(CONFIG_PATH, backup_path)
    print(f"✅ 配置已备份: {backup_path}")
    
    # 只保留最近 10 个备份
    backups = sorted(Path(BACKUP_DIR).glob("openclaw_*.json"))
    if len(backups) > 10:
        for old_backup in backups[:-10]:
            old_backup.unlink()
            print(f"🗑️ 删除旧备份: {old_backup}")
    
    return backup_path


def get_latest_backup() -> str:
    """获取最新备份"""
    ensure_backup_dir()
    backups = sorted(Path(BACKUP_DIR).glob("openclaw_*.json"))
    return str(backups[-1]) if backups else None


def restore_config(backup_path: str = None) -> bool:
    """恢复配置"""
    if backup_path is None:
        backup_path = get_latest_backup()
    
    if not backup_path or not os.path.exists(backup_path):
        print("❌ 没有可用的备份")
        return False
    
    shutil.copy2(backup_path, CONFIG_PATH)
    print(f"✅ 配置已恢复: {backup_path}")
    return True


def validate_json(config_path: str) -> tuple:
    """验证 JSON 格式"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return True, config, None
    except json.JSONDecodeError as e:
        return False, None, f"JSON 格式错误: {e}"
    except Exception as e:
        return False, None, f"读取错误: {e}"


def check_schema(config: dict) -> list:
    """检查配置是否符合已知 Schema"""
    warnings = []
    
    # 已知的顶级字段
    known_fields = {
        "version", "agent", "llm", "tools", "plugins", "hooks",
        "auth", "limits", "logging", "experimental", "sessions",
        "channels", "messaging", "memory", "sandbox"
    }
    
    # 检查未知字段
    for key in config.keys():
        if key not in known_fields:
            warnings.append(f"⚠️ 未知字段: {key}")
    
    # 检查危险的 hooks 配置
    if "hooks" in config:
        hooks = config["hooks"]
        # 这些字段曾导致问题
        dangerous_fields = ["port", "host", "bind"]
        for field in dangerous_fields:
            if field in hooks:
                warnings.append(f"🚨 危险字段 hooks.{field} - 可能导致启动失败!")
    
    return warnings


def run_doctor() -> tuple:
    """运行 openclaw doctor 检查"""
    try:
        result = subprocess.run(
            ["openclaw", "doctor"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Doctor 检查超时"
    except FileNotFoundError:
        return True, "openclaw 命令不可用，跳过检查"
    except Exception as e:
        return False, f"检查失败: {e}"


def safe_apply_config(new_config_path: str) -> bool:
    """安全地应用新配置"""
    print("🔍 开始配置安全检查...\n")
    
    # 1. 验证 JSON 格式
    valid, config, error = validate_json(new_config_path)
    if not valid:
        print(f"❌ {error}")
        return False
    print("✅ JSON 格式正确")
    
    # 2. 检查 Schema
    warnings = check_schema(config)
    if warnings:
        print("\n⚠️ Schema 警告:")
        for w in warnings:
            print(f"   {w}")
        
        # 如果有危险字段，拒绝应用
        if any("🚨" in w for w in warnings):
            print("\n❌ 检测到危险字段，拒绝应用配置!")
            print("请先移除危险字段后重试。")
            return False
    else:
        print("✅ Schema 检查通过")
    
    # 3. 备份当前配置
    print()
    backup_path = backup_config()
    
    # 4. 应用新配置
    try:
        shutil.copy2(new_config_path, CONFIG_PATH)
        print(f"✅ 新配置已应用")
    except Exception as e:
        print(f"❌ 应用配置失败: {e}")
        return False
    
    # 5. 运行 doctor 检查
    print("\n🔍 运行 doctor 检查...")
    ok, output = run_doctor()
    
    if not ok:
        print(f"❌ Doctor 检查失败:")
        print(output)
        print("\n🔄 自动回滚到之前的配置...")
        restore_config(backup_path)
        return False
    
    print("✅ Doctor 检查通过")
    print("\n✅ 配置安全应用完成!")
    return True


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("配置安全检查器")
        print()
        print("用法:")
        print("  python3 config_guard.py backup          # 备份当前配置")
        print("  python3 config_guard.py restore         # 恢复最新备份")
        print("  python3 config_guard.py restore <path>  # 恢复指定备份")
        print("  python3 config_guard.py check           # 检查当前配置")
        print("  python3 config_guard.py apply <path>    # 安全应用新配置")
        print("  python3 config_guard.py list            # 列出所有备份")
        return
    
    action = sys.argv[1]
    
    if action == "backup":
        backup_config()
    
    elif action == "restore":
        path = sys.argv[2] if len(sys.argv) > 2 else None
        restore_config(path)
    
    elif action == "check":
        valid, config, error = validate_json(CONFIG_PATH)
        if not valid:
            print(f"❌ {error}")
            return
        
        print("✅ JSON 格式正确")
        warnings = check_schema(config)
        if warnings:
            print("\n⚠️ 警告:")
            for w in warnings:
                print(f"   {w}")
        else:
            print("✅ Schema 检查通过")
        
        print("\n🔍 运行 doctor 检查...")
        ok, output = run_doctor()
        if ok:
            print("✅ Doctor 检查通过")
        else:
            print(f"❌ {output}")
    
    elif action == "apply":
        if len(sys.argv) < 3:
            print("❌ 请指定新配置文件路径")
            return
        safe_apply_config(sys.argv[2])
    
    elif action == "list":
        ensure_backup_dir()
        backups = sorted(Path(BACKUP_DIR).glob("openclaw_*.json"))
        if not backups:
            print("没有备份")
        else:
            print(f"备份目录: {BACKUP_DIR}\n")
            for b in backups:
                size = b.stat().st_size
                print(f"  {b.name} ({size} bytes)")
    
    else:
        print(f"❌ 未知操作: {action}")


if __name__ == "__main__":
    main()
