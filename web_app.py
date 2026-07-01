import os
import sys
import json
import time
import webbrowser

# Failed login rate limit store: ip -> {"count": int, "lockout_until": float}
failed_attempts = {}
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from loguru import logger

# Import services and helpers
from app.utils.paths import get_data_dir, get_log_dir
from app.database.db import init_db, db_conn, db_transaction
from app.security.crypto import init_crypto, hash_password, verify_password
from app.utils.logger_helper import setup_db_logging
from app.services.scheduler_service import SchedulerService

# Import blueprints
from app.api.account_api import account_api
from app.api.subscription_api import subscription_api
from app.api.task_api import task_api
from app.api.setting_api import setting_api
from app.api.auth import first_run_check, generate_session_token, active_sessions

# Define directories
data_dir = get_data_dir()
log_dir = get_log_dir()

# Initialize Loguru console/file logs with masking filters
from app.utils.logger_helper import mask_filter
log_file_path = log_dir / "pansave.log"
logger.remove() # Remove default handler
log_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {extra[masked_message]}"
logger.add(sys.stderr, format=log_format, filter=mask_filter, level="INFO")
logger.add(str(log_file_path), format=log_format, filter=mask_filter, rotation="10 MB", retention="7 days", level="DEBUG", encoding="utf-8")

logger.info(f"Starting PanSave. Data Directory: {data_dir}. Log Directory: {log_dir}.")

# Initialize database, crypto modules, and db logger
init_db()
init_crypto()
setup_db_logging()

# Initialize background scheduler
SchedulerService.start()

# Flask App setup
# Point static_folder and template_folder to standard path packaged by PyInstaller
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "app", "static"))
os.makedirs(static_dir, exist_ok=True)

app = Flask(__name__, static_folder=static_dir, static_url_path="")
CORS(app) # Enable CORS for frontend development

# Register API blueprints
app.register_blueprint(account_api)
app.register_blueprint(subscription_api)
app.register_blueprint(task_api)
app.register_blueprint(setting_api)

# Authentication endpoints
@app.route("/api/auth/first_run", methods=["GET"])
def check_first_run():
    return jsonify({"first_run": first_run_check()})

@app.route("/api/auth/setup", methods=["POST"])
def setup_admin_password():
    if not first_run_check():
        return jsonify({"errno": 400, "error": "Administrator password has already been configured."}), 400
        
    data = request.json or {}
    password = data.get("password", "")
    if len(password) < 6:
        return jsonify({"errno": 400, "error": "Password must be at least 6 characters long."}), 400
        
    hashed = hash_password(password)
    try:
        with db_transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, is_sensitive) VALUES ('admin_password_hash', ?, 0)",
                (json.dumps(hashed),)
            )
        return jsonify({"errno": 0, "message": "Password initialized successfully."})
    except Exception as e:
        logger.error(f"Failed to save admin password: {e}")
        return jsonify({"errno": 500, "error": str(e)}), 500

@app.route("/api/auth/login", methods=["POST"])
def login():
    ip = request.remote_addr
    now = time.time()
    
    # Check if locked out
    if ip in failed_attempts:
        attempt = failed_attempts[ip]
        if attempt["lockout_until"] > now:
            remaining = int(attempt["lockout_until"] - now)
            return jsonify({"errno": 429, "error": f"Too many failed login attempts. Try again in {remaining} seconds."}), 429
            
    data = request.json or {}
    password = data.get("password", "")
    
    with db_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'admin_password_hash'").fetchone()
        
    if not row:
        return jsonify({"errno": 400, "error": "System not initialized. Please configure password first."}), 400
        
    hashed = json.loads(row["value"])
    if verify_password(password, hashed):
        # Reset attempts on success
        if ip in failed_attempts:
            del failed_attempts[ip]
        token = generate_session_token()
        return jsonify({"errno": 0, "token": token, "message": "Login successful."})
    else:
        # Increment failed attempts
        if ip not in failed_attempts:
            failed_attempts[ip] = {"count": 0, "lockout_until": 0}
        failed_attempts[ip]["count"] += 1
        
        if failed_attempts[ip]["count"] >= 5:
            failed_attempts[ip]["lockout_until"] = now + 900 # 15 minutes lockout
            return jsonify({"errno": 429, "error": "Too many failed login attempts. Login locked for 15 minutes."}), 429
            
        remaining_attempts = 5 - failed_attempts[ip]["count"]
        return jsonify({"errno": 401, "error": f"Invalid administrator password. Remaining attempts: {remaining_attempts}."}), 401

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    token = request.headers.get("Authorization")
    if token and token.startswith("Bearer "):
        token = token.split(" ")[1]
    if token in active_sessions:
        active_sessions.remove(token)
    return jsonify({"errno": 0, "message": "Logged out successfully."})

# Catch-all route to serve the Vue single-page application (HTML5 History Mode)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    if path.startswith("api/") or path.startswith("api"):
        return jsonify({"errno": 404, "error": "Endpoint not found"}), 404
        
    # Serve index.html or other static files in app/static
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
        
    # Fallback to index.html for SPA client-side routing
    return send_from_directory(app.static_folder, "index.html")

if __name__ == "__main__":
    host = "127.0.0.1"
    # Read remote access switch from DB settings
    try:
        with db_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'system_settings'").fetchone()
            if row:
                sys_cfg = json.loads(row["value"])
                # Bind to 0.0.0.0 if user explicitly enabled remote access
                if sys_cfg.get("allow_remote_access") == True:
                    host = "0.0.0.0"
    except Exception:
        pass
        
    port = 5632
    logger.info(f"PanSave Console listening on: http://{host}:{port}")
    
    # Auto-open browser in desktop mode if host is local
    if host == "127.0.0.1" and os.environ.get("PANSAVE_MODE") != "server" and not os.environ.get("WERKZEUG_RUN_MAIN"):
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception as e:
            logger.warning(f"Could not automatically open browser: {e}")
            
    try:
        app.run(host=host, port=port, debug=False)
    finally:
        SchedulerService.shutdown()
