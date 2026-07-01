import time
import threading
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from typing import Dict, Any, List, Optional
from loguru import logger
from app.database.db import db_conn

class NotificationService:
    """Handles formatted notifications across Bark, PushPlus, Webhook, and SMTP channels with debouncing."""
    
    _queue_lock = threading.Lock()
    _notification_queue: List[Dict[str, str]] = []
    _timer: Optional[threading.Timer] = None
    
    @staticmethod
    def _get_channel_settings() -> Dict[str, Any]:
        """Loads notification configurations from the database."""
        with db_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'notification_settings'").fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except Exception:
                    pass
        # Default empty settings
        return {
            "pushplus": {"enabled": False, "token": ""},
            "bark": {"enabled": False, "device_key": "", "url": "https://api.day.app"},
            "webhook": {"enabled": False, "url": ""},
            "smtp": {"enabled": False, "host": "", "port": 465, "ssl": True, "username": "", "password": "", "to": ""}
        }

    @staticmethod
    def send(title: str, content: str):
        """Queues a notification and schedules a debounced flush (e.g. wait 5s for other concurrent runs)."""
        with NotificationService._queue_lock:
            NotificationService._notification_queue.append({"title": title, "content": content})
            
            # Reset or start the debouncing timer
            if NotificationService._timer:
                NotificationService._timer.cancel()
                
            NotificationService._timer = threading.Timer(8.0, NotificationService._flush_queue)
            NotificationService._timer.start()
            logger.debug(f"Queued notification: '{title}'. Flush scheduled in 8 seconds.")

    @staticmethod
    def _flush_queue():
        """Aggregates all queued notifications and delivers them to enabled channels."""
        with NotificationService._queue_lock:
            items = list(NotificationService._notification_queue)
            NotificationService._notification_queue.clear()
            NotificationService._timer = None

        if not items:
            return

        # Aggregate content
        if len(items) == 1:
            title = items[0]["title"]
            content = items[0]["content"]
        else:
            title = f"PanSave 任务运行汇总 ({len(items)} 个事件)"
            content_blocks = []
            for item in items:
                content_blocks.append(f"### {item['title']}\n{item['content']}")
            content = "\n\n---\n\n".join(content_blocks)

        logger.info(f"Flushing notifications to channels: {title}")
        settings = NotificationService._get_channel_settings()
        
        # 1. Send PushPlus
        pp_cfg = settings.get("pushplus", {})
        if pp_cfg.get("enabled") and pp_cfg.get("token"):
            NotificationService._send_pushplus(pp_cfg["token"], title, content)
            
        # 2. Send Bark
        bark_cfg = settings.get("bark", {})
        if bark_cfg.get("enabled") and bark_cfg.get("device_key"):
            NotificationService._send_bark(bark_cfg.get("url", "https://api.day.app"), bark_cfg["device_key"], title, content)
            
        # 3. Send Webhook
        webhook_cfg = settings.get("webhook", {})
        if webhook_cfg.get("enabled") and webhook_cfg.get("url"):
            NotificationService._send_webhook(webhook_cfg["url"], title, content)
            
        # 4. Send SMTP
        smtp_cfg = settings.get("smtp", {})
        if smtp_cfg.get("enabled") and smtp_cfg.get("host"):
            NotificationService._send_smtp(smtp_cfg, title, content)

    @staticmethod
    def _send_pushplus(token: str, title: str, content: str):
        url = "http://www.pushplus.plus/send"
        payload = {
            "token": token,
            "title": title,
            "content": content.replace("\n", "<br>"),  # Simple newline translation
            "template": "html"
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            logger.info(f"PushPlus response: {resp.text}")
        except Exception as e:
            logger.error(f"Failed to send PushPlus: {e}")

    @staticmethod
    def _send_bark(api_url: str, device_key: str, title: str, content: str):
        # Format Bark endpoint
        # Use url/device_key/title/body structure
        base_url = api_url.rstrip("/")
        url = f"{base_url}/{device_key}"
        payload = {
            "title": title,
            "body": content,
            "group": "PanSave"
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            logger.info(f"Bark response: {resp.status_code}")
        except Exception as e:
            logger.error(f"Failed to send Bark: {e}")

    @staticmethod
    def _send_webhook(webhook_url: str, title: str, content: str):
        payload = {
            "title": title,
            "message": content,
            "timestamp": int(time.time())
        }
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            logger.info(f"Webhook status: {resp.status_code}")
        except Exception as e:
            logger.error(f"Failed to send Webhook: {e}")

    @staticmethod
    def _send_smtp(cfg: Dict[str, Any], title: str, content: str):
        try:
            msg = MIMEText(content, 'plain', 'utf-8')
            msg['From'] = Header(f"PanSave <{cfg['username']}>", 'utf-8')
            msg['To'] = Header(cfg['to'], 'utf-8')
            msg['Subject'] = Header(title, 'utf-8')
            
            if cfg.get("ssl"):
                server = smtplib.SMTP_SSL(cfg["host"], cfg.get("port", 465), timeout=10)
            else:
                server = smtplib.SMTP(cfg["host"], cfg.get("port", 25), timeout=10)
                
            server.login(cfg["username"], cfg["password"])
            server.sendmail(cfg["username"], [cfg["to"]], msg.as_string())
            server.quit()
            logger.info("SMTP notification sent successfully.")
        except Exception as e:
            logger.error(f"Failed to send SMTP notification: {e}")

    @staticmethod
    def send_transfer_notification(run_id: int):
        """Compiles details of a task run and queues a nice summary notification."""
        with db_conn() as conn:
            run = conn.execute("""
            SELECT tr.*, s.name as sub_name, s.transfer_strategy
            FROM task_runs tr
            JOIN subscriptions s ON tr.subscription_id = s.id
            WHERE tr.id = ?
            """, (run_id,)).fetchone()
            
        if not run:
            return
        run = dict(run)
        
        sub_name = run["sub_name"]
        status = run["status"]
        strategy = run["transfer_strategy"]
        
        title = f"PanSave 任务汇报: {sub_name} - {'成功' if status == 'success' else '失败'}"
        
        # Build Markdown content
        lines = []
        lines.append(f"**任务名称**: {sub_name}")
        lines.append(f"**运行编号**: Run #{run['id']}")
        lines.append(f"**转存策略**: {strategy}")
        lines.append(f"**执行时间**: {run['started_at']} 至 {run['finished_at'] or 'N/A'}")
        
        if status == "success":
            lines.append("\n**更新统计**:")
            lines.append(f"- 新增文件数: {run['added_count']}")
            lines.append(f"- 修改文件数: {run['modified_count']}")
            lines.append(f"- 删除文件数: {run['deleted_count']}")
            lines.append(f"- 成功转存数: {run['transferred_count']}")
        else:
            lines.append("\n**执行出错**:")
            lines.append(f"- 错误信息: {run['error_message'] or '未知异常'}")
            
        content = "\n".join(lines)
        NotificationService.send(title, content)
