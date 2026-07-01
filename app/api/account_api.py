import json
from flask import Blueprint, request, jsonify
from app.database.db import db_conn, db_transaction
from app.api.auth import login_required
from app.security.crypto import encrypt, decrypt
from app.providers.baidu.client import BaiduPCSClient
from loguru import logger

account_api = Blueprint("account_api", __name__)

@account_api.route("/api/accounts", methods=["GET"])
@login_required
def list_accounts():
    with db_conn() as conn:
        rows = conn.execute("SELECT id, name, status, quota_total, quota_used, last_verified_at, created_at FROM accounts").fetchall()
    return jsonify([dict(row) for row in rows])

@account_api.route("/api/accounts", methods=["POST"])
@login_required
def add_account():
    data = request.json or {}
    name = data.get("name", "").strip()
    bduss = data.get("bduss", "").strip()
    stoken = data.get("stoken", "").strip()
    
    if not name or not bduss:
        return jsonify({"errno": 400, "error": "Account name and BDUSS are required."}), 400

    try:
        # Encrypt cookie
        cookie_data = {"BDUSS": bduss}
        if stoken:
            cookie_data["STOKEN"] = stoken
        encrypted_cookie = encrypt(json.dumps(cookie_data))
        
        # Verify instantly
        client = BaiduPCSClient(bduss, stoken)
        acc_info = client.verify()
        
        with db_transaction() as conn:
            conn.execute("""
            INSERT INTO accounts (name, cookie_encrypted, status, quota_total, quota_used, last_verified_at)
            VALUES (?, ?, 'active', ?, ?, datetime('now', 'localtime'))
            """, (name, encrypted_cookie, acc_info["quota_total"], acc_info["quota_used"]))
            
        return jsonify({"errno": 0, "message": "Account added successfully.", "nickname": acc_info["nickname"]})
    except Exception as e:
        logger.error(f"Failed to add account: {e}")
        return jsonify({"errno": 500, "error": f"Failed to add account: {str(e)}"}), 500

@account_api.route("/api/accounts/<int:account_id>", methods=["DELETE"])
@login_required
def delete_account(account_id):
    with db_transaction() as conn:
        # Check if there are active subscriptions using this account
        sub = conn.execute("SELECT id FROM subscriptions WHERE account_id = ?", (account_id,)).fetchone()
        if sub:
            return jsonify({"errno": 400, "error": "Cannot delete account, it is currently in use by one or more subscriptions."}), 400
            
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    return jsonify({"errno": 0, "message": "Account deleted successfully."})

@account_api.route("/api/accounts/verify", methods=["POST"])
@login_required
def verify_account_cookies():
    data = request.json or {}
    bduss = data.get("bduss", "").strip()
    stoken = data.get("stoken", "").strip()
    
    if not bduss:
        return jsonify({"errno": 400, "error": "BDUSS is required for verification."}), 400
        
    try:
        client = BaiduPCSClient(bduss, stoken)
        acc_info = client.verify()
        return jsonify({
            "errno": 0, 
            "message": "Cookies are valid.", 
            "nickname": acc_info["nickname"],
            "quota_total": acc_info["quota_total"],
            "quota_used": acc_info["quota_used"]
        })
    except Exception as e:
        return jsonify({"errno": 500, "error": f"Verification failed: {str(e)}"}), 500

import uuid
import time
import requests
import re

# Global dictionary to store Baidu QR login sessions
# structure: session_id -> {"session": requests.Session, "sign": str, "created_at": float}
qr_sessions = {}

def cleanup_old_qr_sessions():
    now = time.time()
    expired = [k for k, v in qr_sessions.items() if now - v["created_at"] > 300]
    for k in expired:
        qr_sessions.pop(k, None)

@account_api.route("/api/accounts/qr/init", methods=["GET"])
@login_required
def qr_init():
    cleanup_old_qr_sessions()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://passport.baidu.com/"
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    # Baidu Passport getqrcode URL
    init_url = f"https://passport.baidu.com/v2/api/getqrcode?lp=pc&qrloginfrom=pc&tpl=netdisk&apiver=v3&tt={int(time.time()*1000)}"
    
    try:
        res = session.get(init_url, timeout=10.0)
        data = res.json()
        
        sign = data.get("sign")
        imgurl = data.get("imgurl")
        
        if not sign or not imgurl:
            return jsonify({"errno": 500, "error": "Baidu passport returned invalid QR code data."}), 500
            
        # imgurl comes back escaped, ensure HTTPS
        if not imgurl.startswith("http://") and not imgurl.startswith("https://"):
            if imgurl.startswith("//"):
                imgurl = "https:" + imgurl
            else:
                imgurl = "https://" + imgurl
        
        session_id = str(uuid.uuid4())
        qr_sessions[session_id] = {
            "session": session,
            "sign": sign,
            "created_at": time.time()
        }
        
        return jsonify({
            "errno": 0,
            "session_id": session_id,
            "imgurl": imgurl
        })
    except Exception as e:
        logger.error(f"Failed to initialize Baidu QR login: {e}")
        return jsonify({"errno": 500, "error": f"Failed to initialize QR code: {str(e)}"}), 500

@account_api.route("/api/accounts/qr/status", methods=["GET"])
@login_required
def qr_status():
    session_id = request.args.get("session_id")
    if not session_id or session_id not in qr_sessions:
        return jsonify({"errno": 400, "error": "Invalid or expired login session."}), 400
        
    qr_info = qr_sessions[session_id]
    session = qr_info["session"]
    sign = qr_info["sign"]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://passport.baidu.com/"
    }
    
    poll_url = f"https://passport.baidu.com/channel/unicast?channel_id={sign}&tpl=netdisk&apiver=v3&tt={int(time.time()*1000)}"
    
    try:
        # Polling unicast endpoint with a short timeout to prevent blocking Flask threads.
        # Catch timeouts gracefully to return a 'waiting' status status.
        try:
            res = session.get(poll_url, headers=headers, timeout=25.0)
            text = res.text
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return jsonify({"errno": 0, "status": "waiting", "message": "Waiting for user to scan (connection refreshed)."}), 200
        
        # Unicast returns a JSONP string (often wrapped), extract JSON
        match = re.search(r'\{.*\}', text)
        if not match:
            return jsonify({"errno": 500, "error": "Baidu passport status response parse error."}), 500
            
        data = json.loads(match.group(0))
        
        # Check errno
        errno = data.get("errno")
        if errno != 0:
            return jsonify({"errno": 0, "status": "expired", "message": "QR code expired or invalid."})
            
        # Parse nested channel_v JSON string
        channel_v_str = data.get("channel_v")
        channel_data = {}
        if channel_v_str:
            try:
                channel_data = json.loads(channel_v_str)
            except Exception:
                pass
                
        # If channel_v is missing or empty, it means we are still waiting for scan
        if not channel_v_str or not channel_data:
            return jsonify({"errno": 0, "status": "waiting", "message": "Waiting for user to scan."})
            
        status_val = channel_data.get("status")
        try:
            status = int(status_val) if status_val is not None else -1
        except (TypeError, ValueError):
            status = -1
            
        if status == 1:
            return jsonify({"errno": 0, "status": "scanned", "message": "Scanned! Please confirm login on your phone."})
        elif status == 0 or status == 2:
            # User confirmed! We get temporary ticket
            ticket = channel_data.get("v")
            if not ticket:
                return jsonify({"errno": 500, "error": "Confirmation succeeded but passport ticket is missing."}), 500
                
            # Exchange ticket for actual cookies
            login_url = f"https://passport.baidu.com/v3/login/main/qrbdusslogin?bduss={ticket}&tpl=netdisk&apiver=v3&tt={int(time.time()*1000)}"
            session.get(login_url, headers=headers, timeout=10.0)
            
            # Retrieve BDUSS & STOKEN from cookie jar
            cookies_dict = {}
            for cookie in session.cookies:
                cookies_dict[cookie.name] = cookie.value
                
            bduss = cookies_dict.get("BDUSS")
            stoken = cookies_dict.get("STOKEN")
            
            if not bduss:
                return jsonify({"errno": 500, "error": "Login succeeded, but failed to retrieve BDUSS cookie."}), 500
                
            # Verify and save the account
            client = BaiduPCSClient(bduss, stoken)
            acc_info = client.verify()
            
            nickname = acc_info["nickname"]
            name = f"百度网盘_{nickname}"
            
            # Encrypt cookies
            cookie_data = {"BDUSS": bduss}
            if stoken:
                cookie_data["STOKEN"] = stoken
            encrypted_cookie = encrypt(json.dumps(cookie_data))
            
            with db_transaction() as conn:
                # Check if account already exists to overwrite or update
                existing = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
                if existing:
                    conn.execute("""
                    UPDATE accounts SET cookie_encrypted = ?, status = 'active', quota_total = ?, quota_used = ?, last_verified_at = datetime('now', 'localtime')
                    WHERE id = ?
                    """, (encrypted_cookie, acc_info["quota_total"], acc_info["quota_used"], existing["id"]))
                else:
                    conn.execute("""
                    INSERT INTO accounts (name, cookie_encrypted, status, quota_total, quota_used, last_verified_at)
                    VALUES (?, ?, 'active', ?, ?, datetime('now', 'localtime'))
                    """, (name, encrypted_cookie, acc_info["quota_total"], acc_info["quota_used"]))
                    
            # Success. Clean session
            qr_sessions.pop(session_id, None)
            
            return jsonify({
                "errno": 0,
                "status": "success",
                "nickname": nickname
            })
            
        return jsonify({"errno": 0, "status": "expired", "message": "QR code expired."})
            
    except Exception as e:
        logger.error(f"Error checking Baidu QR login status: {e}")
        return jsonify({"errno": 500, "error": f"Status check failed: {str(e)}"}), 500

@account_api.route("/api/accounts/<int:account_id>/files", methods=["GET"])
@login_required
def get_account_files(account_id):
    path = request.args.get("path", "/")
    if not path.startswith("/"):
        path = "/" + path
        
    with db_conn() as conn:
        row = conn.execute("SELECT cookie_encrypted FROM accounts WHERE id = ?", (account_id,)).fetchone()
        
    if not row:
        return jsonify({"errno": 404, "error": "Account not found"}), 404
        
    try:
        cookie_data = json.loads(decrypt(row["cookie_encrypted"]))
        bduss = cookie_data.get("BDUSS")
        stoken = cookie_data.get("STOKEN")
        
        client = BaiduPCSClient(bduss, stoken)
        files = client.list_dir(path)
        return jsonify({"errno": 0, "list": files})
    except Exception as e:
        logger.error(f"Failed to list files for account {account_id} path {path}: {e}")
        return jsonify({"errno": 500, "error": str(e)}), 500

