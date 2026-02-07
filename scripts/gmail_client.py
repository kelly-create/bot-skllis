#!/usr/bin/env python3
"""
Gmail 客户端脚本
使用 IMAP/SMTP 协议，通过应用专用密码访问 Gmail
独立运行，不依赖 Gateway 配置
"""

import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
import json
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional

# Gmail 配置
GMAIL_ACCOUNT = "zbobo9001@gmail.com"
GMAIL_APP_PASSWORD = "uxcu tnjl sjgr ohwb"  # 应用专用密码（带空格）

# IMAP/SMTP 服务器
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def decode_mime_header(header: str) -> str:
    """解码邮件头（处理中文等编码）"""
    if not header:
        return ""
    
    decoded_parts = decode_header(header)
    result = []
    
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            except:
                result.append(part.decode('utf-8', errors='replace'))
        else:
            result.append(part)
    
    return ''.join(result)


def get_email_body(msg) -> str:
    """提取邮件正文"""
    body = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    body = part.get_payload(decode=True).decode(charset, errors='replace')
                    break
                except:
                    pass
    else:
        try:
            charset = msg.get_content_charset() or 'utf-8'
            body = msg.get_payload(decode=True).decode(charset, errors='replace')
        except:
            body = str(msg.get_payload())
    
    return body.strip()


def connect_imap() -> imaplib.IMAP4_SSL:
    """连接到 Gmail IMAP 服务器"""
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(GMAIL_ACCOUNT, GMAIL_APP_PASSWORD)
    return mail


def list_folders() -> List[str]:
    """列出所有邮件文件夹"""
    mail = connect_imap()
    
    try:
        status, folders = mail.list()
        folder_list = []
        
        for folder in folders:
            # 解析文件夹名称
            folder_str = folder.decode('utf-8')
            # 提取文件夹名
            parts = folder_str.split(' "/" ')
            if len(parts) >= 2:
                folder_list.append(parts[-1].strip('"'))
        
        return folder_list
    finally:
        mail.logout()


def get_inbox(count: int = 10, unread_only: bool = False) -> List[Dict[str, Any]]:
    """
    获取收件箱邮件
    
    Args:
        count: 获取邮件数量
        unread_only: 只获取未读邮件
    
    Returns:
        邮件列表
    """
    mail = connect_imap()
    
    try:
        mail.select("INBOX")
        
        # 搜索条件
        search_criteria = "(UNSEEN)" if unread_only else "ALL"
        status, messages = mail.search(None, search_criteria)
        
        if status != "OK":
            return []
        
        email_ids = messages[0].split()
        # 获取最新的 count 封邮件
        email_ids = email_ids[-count:] if len(email_ids) > count else email_ids
        email_ids.reverse()  # 最新的排前面
        
        emails = []
        
        for email_id in email_ids:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            
            if status != "OK":
                continue
            
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # 解析邮件信息
            subject = decode_mime_header(msg["Subject"])
            from_addr = decode_mime_header(msg["From"])
            to_addr = decode_mime_header(msg["To"])
            date = msg["Date"]
            body = get_email_body(msg)
            
            # 截取正文预览
            preview = body[:500] + "..." if len(body) > 500 else body
            
            emails.append({
                "id": email_id.decode('utf-8'),
                "subject": subject,
                "from": from_addr,
                "to": to_addr,
                "date": date,
                "preview": preview,
                "body_length": len(body)
            })
        
        return emails
    finally:
        mail.logout()


def read_email(email_id: str) -> Dict[str, Any]:
    """
    读取指定邮件的完整内容
    
    Args:
        email_id: 邮件ID
    
    Returns:
        邮件完整信息
    """
    mail = connect_imap()
    
    try:
        mail.select("INBOX")
        status, msg_data = mail.fetch(email_id.encode(), "(RFC822)")
        
        if status != "OK":
            return {"error": f"无法获取邮件 {email_id}"}
        
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        subject = decode_mime_header(msg["Subject"])
        from_addr = decode_mime_header(msg["From"])
        to_addr = decode_mime_header(msg["To"])
        date = msg["Date"]
        body = get_email_body(msg)
        
        return {
            "id": email_id,
            "subject": subject,
            "from": from_addr,
            "to": to_addr,
            "date": date,
            "body": body
        }
    finally:
        mail.logout()


def search_emails(query: str, count: int = 10) -> List[Dict[str, Any]]:
    """
    搜索邮件
    
    Args:
        query: 搜索关键词（在主题或发件人中搜索）
        count: 返回结果数量
    
    Returns:
        匹配的邮件列表
    """
    mail = connect_imap()
    
    try:
        mail.select("INBOX")
        
        # 搜索主题或发件人包含关键词的邮件
        # IMAP 搜索语法
        search_criteria = f'(OR SUBJECT "{query}" FROM "{query}")'
        status, messages = mail.search(None, search_criteria)
        
        if status != "OK":
            return []
        
        email_ids = messages[0].split()
        email_ids = email_ids[-count:] if len(email_ids) > count else email_ids
        email_ids.reverse()
        
        emails = []
        
        for email_id in email_ids:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            
            if status != "OK":
                continue
            
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            subject = decode_mime_header(msg["Subject"])
            from_addr = decode_mime_header(msg["From"])
            date = msg["Date"]
            body = get_email_body(msg)
            preview = body[:200] + "..." if len(body) > 200 else body
            
            emails.append({
                "id": email_id.decode('utf-8'),
                "subject": subject,
                "from": from_addr,
                "date": date,
                "preview": preview
            })
        
        return emails
    finally:
        mail.logout()


def send_email(to: str, subject: str, body: str, html: bool = False) -> Dict[str, Any]:
    """
    发送邮件
    
    Args:
        to: 收件人邮箱
        subject: 邮件主题
        body: 邮件正文
        html: 是否为 HTML 格式
    
    Returns:
        发送结果
    """
    try:
        # 创建邮件
        msg = MIMEMultipart()
        msg["From"] = GMAIL_ACCOUNT
        msg["To"] = to
        msg["Subject"] = subject
        
        # 添加正文
        content_type = "html" if html else "plain"
        msg.attach(MIMEText(body, content_type, "utf-8"))
        
        # 连接 SMTP 服务器
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(GMAIL_ACCOUNT, GMAIL_APP_PASSWORD)
        
        # 发送邮件
        server.send_message(msg)
        server.quit()
        
        return {
            "success": True,
            "message": f"邮件已发送至 {to}",
            "subject": subject,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def mark_as_read(email_id: str) -> Dict[str, Any]:
    """标记邮件为已读"""
    mail = connect_imap()
    
    try:
        mail.select("INBOX")
        mail.store(email_id.encode(), '+FLAGS', '\\Seen')
        return {"success": True, "message": f"邮件 {email_id} 已标记为已读"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        mail.logout()


def mark_as_unread(email_id: str) -> Dict[str, Any]:
    """标记邮件为未读"""
    mail = connect_imap()
    
    try:
        mail.select("INBOX")
        mail.store(email_id.encode(), '-FLAGS', '\\Seen')
        return {"success": True, "message": f"邮件 {email_id} 已标记为未读"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        mail.logout()


def get_unread_count() -> int:
    """获取未读邮件数量"""
    mail = connect_imap()
    
    try:
        mail.select("INBOX")
        status, messages = mail.search(None, "(UNSEEN)")
        
        if status != "OK":
            return 0
        
        email_ids = messages[0].split()
        return len(email_ids)
    finally:
        mail.logout()


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("Usage: gmail_client.py <command> [options]")
        print("\n命令:")
        print("  inbox [count] [--unread]  - 查看收件箱")
        print("  read <email_id>           - 读取邮件")
        print("  search <query> [count]    - 搜索邮件")
        print("  send <to> <subject> <body>- 发送邮件")
        print("  unread                    - 查看未读邮件数")
        print("  folders                   - 列出文件夹")
        print("  mark-read <email_id>      - 标记已读")
        print("  mark-unread <email_id>    - 标记未读")
        print("\n示例:")
        print("  python3 gmail_client.py inbox 5")
        print("  python3 gmail_client.py inbox 10 --unread")
        print("  python3 gmail_client.py send test@example.com '主题' '正文'")
        sys.exit(1)
    
    command = sys.argv[1]
    result = {}
    
    try:
        if command == "inbox":
            count = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 10
            unread_only = "--unread" in sys.argv
            result = {"emails": get_inbox(count, unread_only), "unread_only": unread_only}
        
        elif command == "read":
            if len(sys.argv) < 3:
                result = {"error": "请指定邮件ID"}
            else:
                result = read_email(sys.argv[2])
        
        elif command == "search":
            if len(sys.argv) < 3:
                result = {"error": "请指定搜索关键词"}
            else:
                query = sys.argv[2]
                count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
                result = {"query": query, "emails": search_emails(query, count)}
        
        elif command == "send":
            if len(sys.argv) < 5:
                result = {"error": "用法: send <to> <subject> <body>"}
            else:
                to = sys.argv[2]
                subject = sys.argv[3]
                body = sys.argv[4]
                result = send_email(to, subject, body)
        
        elif command == "unread":
            count = get_unread_count()
            result = {"unread_count": count}
        
        elif command == "folders":
            result = {"folders": list_folders()}
        
        elif command == "mark-read":
            if len(sys.argv) < 3:
                result = {"error": "请指定邮件ID"}
            else:
                result = mark_as_read(sys.argv[2])
        
        elif command == "mark-unread":
            if len(sys.argv) < 3:
                result = {"error": "请指定邮件ID"}
            else:
                result = mark_as_unread(sys.argv[2])
        
        else:
            result = {"error": f"未知命令: {command}"}
    
    except Exception as e:
        result = {"error": str(e), "type": type(e).__name__}
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
