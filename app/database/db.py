import sqlite3
import threading
from contextlib import contextmanager
from app.utils.paths import get_data_dir
from loguru import logger

# Thread lock for write operations if needed, though WAL mode allows concurrent reads
db_write_lock = threading.Lock()

def get_db_path() -> str:
    return str(get_data_dir() / 'pansave.db')

@contextmanager
def db_conn():
    """Context manager for SQLite connection with WAL mode and thread-safety configurations."""
    conn = sqlite3.connect(get_db_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        # Enable Write-Ahead Logging (WAL) for better concurrent read/write handling
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
    finally:
        conn.close()

@contextmanager
def db_transaction():
    """Context manager for write transactions, protected by a thread lock."""
    with db_write_lock:
        with db_conn() as conn:
            try:
                conn.execute("BEGIN TRANSACTION;")
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database transaction error, rolled back: {e}")
                raise e

def init_db():
    """Initializes the database schema and indexes."""
    logger.info("Initializing database...")
    with db_transaction() as conn:
        # 1. Accounts
        conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cookie_encrypted TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            quota_total INTEGER DEFAULT 0,
            quota_used INTEGER DEFAULT 0,
            last_verified_at TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        """)

        # 2. Subscriptions
        conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL, -- 'baidu_share', 'rss', 'json', 'webpage', 'regex'
            source_url TEXT,
            source_parser TEXT DEFAULT 'default',
            share_url TEXT,
            share_password_encrypted TEXT,
            account_id INTEGER,
            target_path TEXT NOT NULL,
            cron_expression TEXT DEFAULT '0 2 * * *',
            transfer_strategy TEXT NOT NULL DEFAULT 'incremental', -- 'notify_only', 'incremental', 'version_archive', 'safe_overwrite'
            filter_rules TEXT, -- JSON configuration for regex filters
            rename_rules TEXT, -- JSON configuration for regex rename
            enabled INTEGER DEFAULT 1, -- 0=disabled, 1=enabled
            last_snapshot_hash TEXT,
            last_checked_at TEXT,
            next_run_at TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_subs_account ON subscriptions(account_id);")

        # 3. Snapshots
        conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            source_version TEXT,
            source_hash TEXT,
            file_tree_hash TEXT NOT NULL,
            share_url TEXT NOT NULL,
            file_count INTEGER DEFAULT 0,
            total_size INTEGER DEFAULT 0,
            raw_data TEXT, -- Compressed or plain JSON representation of tree
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_sub ON snapshots(subscription_id);")

        # 4. Snapshot Files
        conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshot_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            relative_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            modified_time INTEGER,
            file_id TEXT, -- netdisk fs_id
            is_directory INTEGER DEFAULT 0,
            file_hash TEXT NOT NULL, -- SHA256(path + size + mtime + file_id)
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snap_files_snap ON snapshot_files(snapshot_id);")

        # 5. Task Runs
        conn.execute("""
        CREATE TABLE IF NOT EXISTS task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            trigger_type TEXT NOT NULL, -- 'scheduler', 'manual'
            status TEXT NOT NULL, -- 'running', 'success', 'failed', 'cancelled'
            started_at TEXT DEFAULT (datetime('now', 'localtime')),
            finished_at TEXT,
            old_snapshot_id INTEGER,
            new_snapshot_id INTEGER,
            added_count INTEGER DEFAULT 0,
            modified_count INTEGER DEFAULT 0,
            deleted_count INTEGER DEFAULT 0,
            transferred_count INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            error_code TEXT,
            error_message TEXT,
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_sub ON task_runs(subscription_id);")

        # 6. Operation Logs
        conn.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_run_id INTEGER,
            level TEXT NOT NULL, -- 'info', 'warning', 'error'
            stage TEXT NOT NULL, -- 'parse', 'check', 'transfer', 'backup', 'notification'
            message TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (task_run_id) REFERENCES task_runs(id) ON DELETE CASCADE
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_op_logs_run ON operation_logs(task_run_id);")

        # 7. System Settings
        conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL, -- JSON formatted value
            is_sensitive INTEGER DEFAULT 0 -- 0=false, 1=true
        );
        """)

        # Add initial schema version checking/migration setting if not present
        conn.execute("INSERT OR IGNORE INTO settings (key, value, is_sensitive) VALUES ('schema_version', '\"1.0\"', 0);")
    logger.info("Database initialized successfully.")
