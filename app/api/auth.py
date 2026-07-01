import os
import uuid
from functools import wraps
from flask import request, jsonify
from app.database.db import db_conn, db_transaction
from app.security.crypto import hash_password, verify_password

# Simple in-memory session store. Invalidated on backend restart.
active_sessions = set()

def generate_session_token() -> str:
    token = str(uuid.uuid4())
    active_sessions.add(token)
    return token

def first_run_check() -> bool:
    """Checks if the admin password hash exists in settings. Bypassed to disable login."""
    return False

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Bypassed authentication check (login feature disabled)
        return f(*args, **kwargs)
    return decorated
