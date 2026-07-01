import json
import datetime
from flask import Blueprint, request, jsonify
from app.database.db import db_conn, db_transaction
from app.api.auth import login_required
from loguru import logger

setting_api = Blueprint("setting_api", __name__)

@setting_api.route("/api/settings", methods=["GET"])
@login_required
def get_settings():
    keys = ["notification_settings", "system_settings", "proxy_settings"]
    settings_dict = {}
    
    with db_conn() as conn:
        for key in keys:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if row:
                try:
                    settings_dict[key] = json.loads(row["value"])
                except Exception:
                    settings_dict[key] = {}
            else:
                settings_dict[key] = {}
                
    return jsonify(settings_dict)

@setting_api.route("/api/settings", methods=["POST"])
@login_required
def save_settings():
    data = request.json or {}
    
    try:
        with db_transaction() as conn:
            for key, val in data.items():
                if key in ["notification_settings", "system_settings", "proxy_settings"]:
                    val_str = json.dumps(val)
                    conn.execute("""
                    INSERT INTO settings (key, value, is_sensitive)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """, (key, val_str, 1 if key == "notification_settings" else 0))
                    
        return jsonify({"errno": 0, "message": "Settings saved successfully."})
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return jsonify({"errno": 500, "error": str(e)}), 500

@setting_api.route("/api/system/stats", methods=["GET"])
@login_required
def get_system_stats():
    """Compiles dashboard overview statistics from SQLite databases."""
    try:
        with db_conn() as conn:
            # 1. Accounts Quota Aggregation
            accounts = conn.execute("SELECT quota_total, quota_used, status FROM accounts").fetchall()
            acc_count = len(accounts)
            active_acc = sum(1 for a in accounts if a["status"] == "active")
            total_quota = sum(a["quota_total"] for a in accounts if a["status"] == "active")
            used_quota = sum(a["quota_used"] for a in accounts if a["status"] == "active")

            # 2. Subscriptions Count
            subs = conn.execute("SELECT enabled FROM subscriptions").fetchall()
            sub_count = len(subs)
            enabled_sub_count = sum(1 for s in subs if s["enabled"] == 1)

            # 3. Today's task run status
            # started_at has format 'YYYY-MM-DD HH:MM:SS'
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            today_runs = conn.execute("""
            SELECT status, count(*) as cnt 
            FROM task_runs 
            WHERE started_at LIKE ? 
            GROUP BY status
            """, (f"{today_str}%",)).fetchall()
            
            success_today = 0
            failed_today = 0
            for r in today_runs:
                if r["status"] == "success":
                    success_today = r["cnt"]
                elif r["status"] == "failed":
                    failed_today = r["cnt"]

            # 4. Recent run history (last 5)
            recent_runs = conn.execute("""
            SELECT tr.id, tr.status, tr.started_at, tr.finished_at, tr.added_count, tr.transferred_count, s.name as sub_name
            FROM task_runs tr
            JOIN subscriptions s ON tr.subscription_id = s.id
            ORDER BY tr.id DESC LIMIT 5
            """).fetchall()

        return jsonify({
            "errno": 0,
            "accounts": {
                "total": acc_count,
                "active": active_acc,
                "quota_total": total_quota,
                "quota_used": used_quota
            },
            "subscriptions": {
                "total": sub_count,
                "enabled": enabled_sub_count
            },
            "runs_today": {
                "success": success_today,
                "failed": failed_today
            },
            "recent_runs": [dict(r) for r in recent_runs]
        })
    except Exception as e:
        logger.error(f"Failed to load system stats: {e}")
        return jsonify({"errno": 500, "error": str(e)}), 500
