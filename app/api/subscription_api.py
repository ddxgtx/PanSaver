import json
from flask import Blueprint, request, jsonify
from app.database.db import db_conn, db_transaction
from app.api.auth import login_required
from app.security.crypto import encrypt
from app.services.scheduler_service import SchedulerService
from loguru import logger

subscription_api = Blueprint("subscription_api", __name__)

@subscription_api.route("/api/subscriptions", methods=["GET"])
@login_required
def list_subscriptions():
    with db_conn() as conn:
        rows = conn.execute("""
        SELECT s.id, s.name, s.source_type, s.source_url, s.share_url, 
               s.account_id, s.target_path, s.cron_expression, s.transfer_strategy,
               s.filter_rules, s.rename_rules, s.enabled, s.last_snapshot_hash,
               s.last_checked_at, s.next_run_at, a.name as account_name
        FROM subscriptions s
        LEFT JOIN accounts a ON s.account_id = a.id
        """).fetchall()
    return jsonify([dict(row) for row in rows])

@subscription_api.route("/api/subscriptions", methods=["POST"])
@login_required
def add_subscription():
    data = request.json or {}
    name = data.get("name", "").strip()
    source_type = data.get("source_type", "baidu_share")
    source_url = data.get("source_url", "").strip()
    share_url = data.get("share_url", "").strip()
    share_password = data.get("share_password", "").strip()
    account_id = data.get("account_id")
    target_path = data.get("target_path", "").strip()
    cron_expression = data.get("cron_expression", "*/30 * * * *").strip()
    transfer_strategy = data.get("transfer_strategy", "incremental")
    filter_rules = data.get("filter_rules", "") # Stored as JSON string
    rename_rules = data.get("rename_rules", "") # Stored as JSON string
    enabled = int(data.get("enabled", 1))

    if not name or not target_path:
        return jsonify({"errno": 400, "error": "Subscription name and target path are required."}), 400

    # Validate cron expression
    try:
        from apscheduler.triggers.cron import CronTrigger
        CronTrigger.from_crontab(cron_expression)
    except Exception:
        return jsonify({"errno": 400, "error": f"Invalid Cron expression format '{cron_expression}'. Please check syntax."}), 400

    # Ensure target_path starts with '/'
    if not target_path.startswith("/"):
        target_path = "/" + target_path

    # Encrypt password if present
    pwd_encrypted = ""
    if share_password:
        try:
            pwd_encrypted = encrypt(share_password)
        except Exception as e:
            logger.error(f"Failed to encrypt share password: {e}")
            return jsonify({"errno": 500, "error": "Password encryption failed."}), 500

    try:
        with db_transaction() as conn:
            cursor = conn.execute("""
            INSERT INTO subscriptions (
                name, source_type, source_url, share_url, share_password_encrypted,
                account_id, target_path, cron_expression, transfer_strategy,
                filter_rules, rename_rules, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, source_type, source_url, share_url, pwd_encrypted,
                account_id, target_path, cron_expression, transfer_strategy,
                filter_rules, rename_rules, enabled
            ))
            sub_id = cursor.lastrowid
            
        # Update Scheduler Job
        if enabled:
            SchedulerService.add_subscription_job(sub_id, cron_expression, name)
            
        return jsonify({"errno": 0, "message": "Subscription added successfully.", "id": sub_id})
    except Exception as e:
        logger.error(f"Failed to add subscription: {e}")
        return jsonify({"errno": 500, "error": str(e)}), 500

@subscription_api.route("/api/subscriptions/<int:sub_id>", methods=["PUT"])
@login_required
def update_subscription(sub_id):
    data = request.json or {}
    name = data.get("name", "").strip()
    source_type = data.get("source_type", "baidu_share")
    source_url = data.get("source_url", "").strip()
    share_url = data.get("share_url", "").strip()
    share_password = data.get("share_password", "").strip()
    account_id = data.get("account_id")
    target_path = data.get("target_path", "").strip()
    cron_expression = data.get("cron_expression", "*/30 * * * *").strip()
    transfer_strategy = data.get("transfer_strategy", "incremental")
    filter_rules = data.get("filter_rules", "")
    rename_rules = data.get("rename_rules", "")
    enabled = int(data.get("enabled", 1))

    if not name or not target_path:
        return jsonify({"errno": 400, "error": "Subscription name and target path are required."}), 400

    # Validate cron expression
    try:
        from apscheduler.triggers.cron import CronTrigger
        CronTrigger.from_crontab(cron_expression)
    except Exception:
        return jsonify({"errno": 400, "error": f"Invalid Cron expression format '{cron_expression}'. Please check syntax."}), 400

    # Ensure target_path starts with '/'
    if not target_path.startswith("/"):
        target_path = "/" + target_path

    # Encrypt password if updated
    pwd_encrypted = None
    if share_password:
        try:
            pwd_encrypted = encrypt(share_password)
        except Exception as e:
            return jsonify({"errno": 500, "error": "Password encryption failed."}), 500

    try:
        with db_transaction() as conn:
            # Update password only if provided
            if pwd_encrypted is not None:
                conn.execute("""
                UPDATE subscriptions SET 
                    name=?, source_type=?, source_url=?, share_url=?, share_password_encrypted=?,
                    account_id=?, target_path=?, cron_expression=?, transfer_strategy=?,
                    filter_rules=?, rename_rules=?, enabled=?, last_snapshot_hash=NULL, updated_at=datetime('now', 'localtime')
                WHERE id = ?
                """, (
                    name, source_type, source_url, share_url, pwd_encrypted,
                    account_id, target_path, cron_expression, transfer_strategy,
                    filter_rules, rename_rules, enabled, sub_id
                ))
            else:
                conn.execute("""
                UPDATE subscriptions SET 
                    name=?, source_type=?, source_url=?, share_url=?,
                    account_id=?, target_path=?, cron_expression=?, transfer_strategy=?,
                    filter_rules=?, rename_rules=?, enabled=?, last_snapshot_hash=NULL, updated_at=datetime('now', 'localtime')
                WHERE id = ?
                """, (
                    name, source_type, source_url, share_url,
                    account_id, target_path, cron_expression, transfer_strategy,
                    filter_rules, rename_rules, enabled, sub_id
                ))
                
        # Update scheduler
        if enabled:
            SchedulerService.add_subscription_job(sub_id, cron_expression, name)
        else:
            SchedulerService.remove_subscription_job(sub_id)
            
        return jsonify({"errno": 0, "message": "Subscription updated successfully."})
    except Exception as e:
        logger.error(f"Failed to update subscription: {e}")
        return jsonify({"errno": 500, "error": str(e)}), 500

@subscription_api.route("/api/subscriptions/<int:sub_id>", methods=["DELETE"])
@login_required
def delete_subscription(sub_id):
    try:
        # Cancel scheduler job first
        SchedulerService.remove_subscription_job(sub_id)
        
        with db_transaction() as conn:
            conn.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
            
        return jsonify({"errno": 0, "message": "Subscription deleted successfully."})
    except Exception as e:
        logger.error(f"Failed to delete subscription: {e}")
        return jsonify({"errno": 500, "error": str(e)}), 500

@subscription_api.route("/api/subscriptions/<int:sub_id>/trigger", methods=["POST"])
@login_required
def trigger_subscription(sub_id):
    try:
        SchedulerService.trigger_now(sub_id)
        return jsonify({"errno": 0, "message": "Task triggered successfully in background."})
    except Exception as e:
        logger.error(f"Failed to trigger task: {e}")
        return jsonify({"errno": 500, "error": str(e)}), 500

@subscription_api.route("/api/subscriptions/test-rules", methods=["POST"])
@login_required
def test_subscription_rules():
    import re, os
    data = request.json or {}
    filter_rules = data.get("filter_rules", "")
    rename_rules = data.get("rename_rules", "")
    test_filenames = data.get("test_filenames", [])

    if not isinstance(test_filenames, list):
        return jsonify({"errno": 400, "error": "test_filenames must be a list of strings."}), 400

    include_pat = None
    exclude_pat = None
    rename_list = []

    if filter_rules:
        try:
            rules = json.loads(filter_rules)
            inc = rules.get("include")
            exc = rules.get("exclude")
            if inc:
                include_pat = re.compile(inc, re.IGNORECASE)
            if exc:
                exclude_pat = re.compile(exc, re.IGNORECASE)
        except Exception:
            pass

    if rename_rules:
        try:
            rename_list = json.loads(rename_rules)
        except Exception:
            pass

    results = []
    for orig in test_filenames:
        orig = orig.strip()
        if not orig:
            continue
        
        name = os.path.basename(orig)
        path = orig

        # Filter check
        is_allowed = True
        if include_pat and not include_pat.search(name) and not include_pat.search(path):
            is_allowed = False
        if exclude_pat and (exclude_pat.search(name) or exclude_pat.search(path)):
            is_allowed = False

        if not is_allowed:
            results.append({
                "original": orig,
                "status": "filtered",
                "renamed": ""
            })
            continue

        # Rename check
        new_name = name
        for rule in rename_list:
            pat = rule.get("pattern")
            repl = rule.get("replace")
            if pat and repl is not None:
                try:
                    new_name = re.sub(pat, repl, new_name)
                except Exception:
                    pass

        results.append({
            "original": orig,
            "status": "allowed",
            "renamed": new_name if new_name != name else ""
        })

    return jsonify({"errno": 0, "results": results})
