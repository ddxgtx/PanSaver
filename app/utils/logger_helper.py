import sqlite3
import re
import queue
import threading
import time
from loguru import logger
from app.database.db import get_db_path

def mask_sensitive_info(msg: str) -> str:
    """Masks sensitive credentials (BDUSS, STOKEN, passwords) inside log strings."""
    if not msg:
        return msg
        
    # 1. Mask BDUSS (e.g. BDUSS=xxxx or BDUSS: xxxx -> BDUS***...***)
    def replace_bduss(m):
        val = m.group(1)
        if len(val) > 4:
            return f"BDUSS={val[:4]}***...***"
        return "BDUSS=***"
    msg = re.sub(r'BDUSS=([a-zA-Z0-9_-]+)', replace_bduss, msg)
    msg = re.sub(r'BDUSS\s*[:：]\s*([a-zA-Z0-9_-]+)', lambda m: f"BDUSS: {m.group(1)[:4]}***...***", msg)

    # 2. Mask STOKEN
    def replace_stoken(m):
        val = m.group(1)
        if len(val) > 4:
            return f"STOKEN={val[:4]}***...***"
        return "STOKEN=***"
    msg = re.sub(r'STOKEN=([a-zA-Z0-9_-]+)', replace_stoken, msg)
    msg = re.sub(r'STOKEN\s*[:：]\s*([a-zA-Z0-9_-]+)', lambda m: f"STOKEN: {m.group(1)[:4]}***...***", msg)

    # 3. Mask extraction passwords (4-character alphanumeric passwords)
    msg = re.sub(r'pwd=([a-zA-Z0-9]{4})\b', r'pwd=****', msg)
    msg = re.sub(r'password=([a-zA-Z0-9]{4})\b', r'password=****', msg)
    msg = re.sub(r'提取码\s*[:：\s]\s*([a-zA-Z0-9]{4})\b', r'提取码: ****', msg)
    
    return msg

def mask_filter(record) -> bool:
    """Loguru filter that automatically populates a masked message in record['extra']."""
    record["extra"]["masked_message"] = mask_sensitive_info(record["message"])
    return True

# Thread-safe queue for database logs
db_log_queue = queue.Queue()

def db_log_worker():
    """Background worker thread that writes log messages sequentially to the database."""
    while True:
        try:
            item = db_log_queue.get()
            if item is None:
                break
            
            task_run_id, level, stage, msg = item
            
            # Retry mechanism for database lock conflicts
            success = False
            for attempt in range(5):
                try:
                    conn = sqlite3.connect(get_db_path(), timeout=10.0)
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA foreign_keys=ON;")
                    conn.execute(
                        "INSERT INTO operation_logs (task_run_id, level, stage, message) VALUES (?, ?, ?, ?)",
                        (int(task_run_id), level, stage, msg)
                    )
                    conn.commit()
                    conn.close()
                    success = True
                    break
                except sqlite3.OperationalError as oe:
                    if "locked" in str(oe).lower():
                        # Exponential backoff retry
                        time.sleep(0.05 * (attempt + 1))
                    else:
                        break
                except Exception:
                    break
                    
            db_log_queue.task_done()
        except Exception:
            pass

class DBLogHandler:
    """Loguru custom handler that pushes masked log entries to the background queue."""
    def write(self, message):
        try:
            record = message.record
            extra = record.get("extra", {})
            task_run_id = extra.get("task_run_id")
            
            if task_run_id is not None:
                level = record["level"].name.lower()
                stage = extra.get("stage", "general")
                msg = mask_sensitive_info(record["message"])
                
                db_log_queue.put((task_run_id, level, stage, msg))
        except Exception:
            pass

_worker_thread = None
_lock = threading.Lock()

def setup_db_logging():
    """Binds the DB log handler to Loguru and starts the worker thread if not already running."""
    global _worker_thread
    with _lock:
        if _worker_thread is None:
            _worker_thread = threading.Thread(target=db_log_worker, name="DBLogWorkerThread", daemon=True)
            _worker_thread.start()
            
    logger.add(DBLogHandler().write, level="INFO")
