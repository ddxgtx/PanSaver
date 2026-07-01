from flask import Blueprint, request, jsonify
from app.database.db import db_conn
from app.api.auth import login_required
from app.services.snapshot_service import SnapshotService
from loguru import logger

task_api = Blueprint("task_api", __name__)

@task_api.route("/api/tasks/runs", methods=["GET"])
@login_required
def list_task_runs():
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    sub_id = request.args.get("subscription_id")
    
    query = """
    SELECT tr.*, s.name as sub_name 
    FROM task_runs tr
    JOIN subscriptions s ON tr.subscription_id = s.id
    """
    params = []
    
    if sub_id:
        query += " WHERE tr.subscription_id = ?"
        params.append(sub_id)
        
    query += " ORDER BY tr.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with db_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        
    return jsonify([dict(row) for row in rows])

@task_api.route("/api/tasks/runs/<int:run_id>/logs", methods=["GET"])
@login_required
def get_run_logs(run_id):
    with db_conn() as conn:
        rows = conn.execute("""
        SELECT level, stage, message, created_at 
        FROM operation_logs 
        WHERE task_run_id = ? 
        ORDER BY id ASC
        """, (run_id,)).fetchall()
    return jsonify([dict(row) for row in rows])

@task_api.route("/api/tasks/runs/<int:run_id>/diff", methods=["GET"])
@login_required
def get_run_diff(run_id):
    with db_conn() as conn:
        run = conn.execute("""
        SELECT old_snapshot_id, new_snapshot_id 
        FROM task_runs WHERE id = ?
        """, (run_id,)).fetchone()
        
    if not run:
        return jsonify({"errno": 404, "error": "Task run not found"}), 404
        
    old_id = run["old_snapshot_id"]
    new_id = run["new_snapshot_id"]
    
    if not new_id:
        return jsonify({
            "added": [],
            "modified": [],
            "deleted": [],
            "renamed": []
        })

    try:
        old_files = SnapshotService.load_snapshot_files(old_id) if old_id else []
        new_files = SnapshotService.load_snapshot_files(new_id)
        diff = SnapshotService.compare_snapshots(old_files, new_files)
        
        # Standardize renamed list for JSON serialization (tuples cannot be serialized directly)
        serialized_renamed = []
        for old_f, new_f in diff["renamed"]:
            serialized_renamed.append({
                "from": old_f["relative_path"],
                "to": new_f["relative_path"],
                "file_size": new_f["file_size"]
            })
        diff["renamed"] = serialized_renamed
        
        return jsonify(diff)
    except Exception as e:
        logger.error(f"Failed to load snapshot diffs for run {run_id}: {e}")
        return jsonify({"errno": 500, "error": str(e)}), 500
