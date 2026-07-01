import unittest
import json
import hashlib
import os
from app.security.crypto import hash_password, verify_password, encrypt, decrypt, init_crypto
from app.parsers.base import extract_baidu_links
from app.services.snapshot_service import SnapshotService
from app.services.transfer_service import TransferService

class TestPanSave(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Initialize crypto key for tests (creates secret.key in data dir)
        init_crypto()

    def test_01_crypto_encryption(self):
        """Test symmetric encryption and decryption of netdisk credentials."""
        secret_cookie = "BDUSS=XYZ123456789; STOKEN=ABC987654321"
        encrypted = encrypt(secret_cookie)
        self.assertNotEqual(secret_cookie, encrypted)
        
        decrypted = decrypt(encrypted)
        self.assertEqual(secret_cookie, decrypted)

    def test_02_crypto_password_hash(self):
        """Test PBKDF2 administrator password hashing and verification."""
        password = "mySecretPassword123"
        hashed = hash_password(password)
        self.assertTrue(hashed.startswith("pbkdf2_sha256$"))
        
        # Verify correct password
        self.assertTrue(verify_password(password, hashed))
        # Verify incorrect password
        self.assertFalse(verify_password("wrongPassword", hashed))

    def test_03_baidu_link_extraction(self):
        """Test parsing and auto-extracting Baidu share URLs and passwords from text."""
        sample_text = (
            "这里是分享内容，包含一个网盘链接：\n"
            "链接: https://pan.baidu.com/s/1h7ySj98D_-Gk123abcXYZ66\n"
            "提取码: a1b2 或者是密码：c3d4，还有其他字样。\n"
            "另外一个没有提取码的链接：https://pan.baidu.com/s/1o7uTw9a"
        )
        
        extracted = extract_baidu_links(sample_text)
        self.assertEqual(len(extracted), 2)
        
        # First link with extracted password
        self.assertEqual(extracted[0]["url"], "https://pan.baidu.com/s/1h7ySj98D_-Gk123abcXYZ66")
        self.assertEqual(extracted[0]["password"], "a1b2")
        
        # Second link without password
        self.assertEqual(extracted[1]["url"], "https://pan.baidu.com/s/1o7uTw9a")
        self.assertEqual(extracted[1]["password"], "")

    def test_04_snapshot_comparison(self):
        """Test Snapshot comparison engine diffing logic (added, modified, renamed, deleted)."""
        # Create helper to compute file hash
        def make_hash(path, size, mtime, file_id):
            record = f"{path}|{size}|{mtime}|{file_id}"
            return hashlib.sha256(record.encode("utf-8")).hexdigest()

        # 1. Setup Old Snapshot Files
        old_files = [
            # Unchanged file
            {"relative_path": "Photos/a.jpg", "file_name": "a.jpg", "file_size": 1000, "modified_time": 100, "file_id": "1001", "is_directory": 0, "file_hash": ""},
            # Modified file (size/mtime will change)
            {"relative_path": "Photos/b.jpg", "file_name": "b.jpg", "file_size": 2000, "modified_time": 200, "file_id": "1002", "is_directory": 0, "file_hash": ""},
            # Renamed file (path will change, file_id stays same)
            {"relative_path": "Videos/old_name.mp4", "file_name": "old_name.mp4", "file_size": 5000, "modified_time": 500, "file_id": "1003", "is_directory": 0, "file_hash": ""},
            # Deleted file
            {"relative_path": "Doc/readme.txt", "file_name": "readme.txt", "file_size": 50, "modified_time": 50, "file_id": "1004", "is_directory": 0, "file_hash": ""}
        ]
        for f in old_files:
            f["file_hash"] = make_hash(f["relative_path"], f["file_size"], f["modified_time"], f["file_id"])

        # 2. Setup New Snapshot Files
        new_files = [
            # Unchanged
            {"relative_path": "Photos/a.jpg", "file_name": "a.jpg", "file_size": 1000, "modified_time": 100, "file_id": "1001", "is_directory": 0, "file_hash": ""},
            # Modified (Size changed 2000 -> 2500)
            {"relative_path": "Photos/b.jpg", "file_name": "b.jpg", "file_size": 2500, "modified_time": 220, "file_id": "1002", "is_directory": 0, "file_hash": ""},
            # Renamed (Path changed from Videos/old_name.mp4 to Videos/new_name.mp4)
            {"relative_path": "Videos/new_name.mp4", "file_name": "new_name.mp4", "file_size": 5000, "modified_time": 500, "file_id": "1003", "is_directory": 0, "file_hash": ""},
            # Added file
            {"relative_path": "Doc/new_doc.pdf", "file_name": "new_doc.pdf", "file_size": 1500, "modified_time": 600, "file_id": "1005", "is_directory": 0, "file_hash": ""}
        ]
        for f in new_files:
            f["file_hash"] = make_hash(f["relative_path"], f["file_size"], f["modified_time"], f["file_id"])

        # Compare
        diff = SnapshotService.compare_snapshots(old_files, new_files)
        
        # Verify Added
        self.assertEqual(len(diff["added"]), 1)
        self.assertEqual(diff["added"][0]["relative_path"], "Doc/new_doc.pdf")
        
        # Verify Modified
        self.assertEqual(len(diff["modified"]), 1)
        self.assertEqual(diff["modified"][0]["relative_path"], "Photos/b.jpg")
        
        # Verify Deleted
        self.assertEqual(len(diff["deleted"]), 1)
        self.assertEqual(diff["deleted"][0]["relative_path"], "Doc/readme.txt")
        
        # Verify Renamed
        self.assertEqual(len(diff["renamed"]), 1)
        old_renamed, new_renamed = diff["renamed"][0]
        self.assertEqual(old_renamed["relative_path"], "Videos/old_name.mp4")
        self.assertEqual(new_renamed["relative_path"], "Videos/new_name.mp4")

    def test_05_filters_and_rename_rules(self):
        """Test regex filtering (include/exclude) and name renaming rules."""
        diffs = {
            "added": [
                {"relative_path": "Videos/lesson1.mp4", "file_name": "lesson1.mp4", "file_id": "1", "is_directory": 0, "file_hash": ""},
                {"relative_path": "Videos/lesson1.tmp", "file_name": "lesson1.tmp", "file_id": "2", "is_directory": 0, "file_hash": ""},
                {"relative_path": "Doc/notes.pdf", "file_name": "notes.pdf", "file_id": "3", "is_directory": 0, "file_hash": ""}
            ],
            "modified": [],
            "deleted": [],
            "renamed": []
        }
        
        # Mock subscription with filter rules (include only mp4)
        sub_filter = {
            "filter_rules": json.dumps({
                "include": r"\.mp4$",
                "exclude": r"\.tmp$"
            }),
            "rename_rules": ""
        }
        
        filtered = TransferService.apply_rules(diffs, sub_filter)
        self.assertEqual(len(filtered["added"]), 1)
        self.assertEqual(filtered["added"][0]["file_name"], "lesson1.mp4")

        # Mock subscription with rename rules (01.mp4 -> Part 01.mp4)
        diffs_rename = {
            "added": [
                {"relative_path": "Videos/01.mp4", "file_name": "01.mp4", "file_id": "1", "is_directory": 0, "file_hash": ""},
                {"relative_path": "Videos/02.mp4", "file_name": "02.mp4", "file_id": "2", "is_directory": 0, "file_hash": ""}
            ],
            "modified": [],
            "deleted": [],
            "renamed": []
        }
        sub_rename = {
            "filter_rules": "",
            "rename_rules": json.dumps([
                {"pattern": r"^(\d+)\.mp4$", "replace": r"第\1集.mp4"}
            ])
        }
        
        renamed = TransferService.apply_rules(diffs_rename, sub_rename)
        self.assertEqual(len(renamed["added"]), 2)
        self.assertEqual(renamed["added"][0]["file_name"], "第01集.mp4")
        self.assertEqual(renamed["added"][0]["relative_path"], "Videos/第01集.mp4")
        self.assertEqual(renamed["added"][1]["file_name"], "第02集.mp4")
        self.assertEqual(renamed["added"][1]["relative_path"], "Videos/第02集.mp4")

    def test_06_login_rate_limiting(self):
        """Test brute-force protection and lockout for failed login attempts."""
        from web_app import app, failed_attempts
        from app.database.db import db_transaction
        
        # Initialize admin password in settings to prevent 400 response
        dummy_hash = hash_password("dummy_admin_password")
        with db_transaction() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value, is_sensitive) VALUES ('admin_password_hash', ?, 0)", (json.dumps(dummy_hash),))
            
        client = app.test_client()
        # Reset failed attempts for test
        ip = "127.0.0.1"
        if ip in failed_attempts:
            del failed_attempts[ip]
            
        # Trigger 5 failed attempts
        for i in range(5):
            res = client.post("/api/auth/login", json={"password": "wrongpassword"})
            if i < 4:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 429)
                self.assertIn("locked", res.json["error"].lower())
                
        # Subsequent requests should be blocked (429)
        res = client.post("/api/auth/login", json={"password": "wrongpassword"})
        self.assertEqual(res.status_code, 429)
        
        # Clean up
        if ip in failed_attempts:
            del failed_attempts[ip]
        # Clean up settings password
        with db_transaction() as conn:
            conn.execute("DELETE FROM settings WHERE key = 'admin_password_hash'")

    def test_07_log_masking(self):
        """Test masking of sensitive tokens and passwords in logger_helper."""
        from app.utils.logger_helper import mask_sensitive_info
        
        raw_log = "User logged in. BDUSS=bdus_val_12345678; STOKEN=stok_val_abcdef12; pwd=pass; 提取码：a1b2"
        masked = mask_sensitive_info(raw_log)
        
        self.assertNotIn("bdus_val_12345678", masked)
        self.assertNotIn("stok_val_abcdef12", masked)
        self.assertNotIn("pass", masked)
        self.assertNotIn("a1b2", masked)
        
        self.assertIn("BDUSS=bdus***...***", masked)
        self.assertIn("STOKEN=stok***...***", masked)
        self.assertIn("pwd=****", masked)
        self.assertIn("提取码: ****", masked)

    def test_08_cron_validation(self):
        """Test validation of invalid Cron expressions on subscription endpoints."""
        from web_app import app, active_sessions
        client = app.test_client()
        
        # Setup dummy session
        dummy_token = "test_token_12345"
        active_sessions.add(dummy_token)
        
        # Test creating with invalid cron
        payload = {
            "name": "Test Cron Job",
            "source_type": "baidu_share",
            "target_path": "/test",
            "cron_expression": "invalid_cron_string",
            "transfer_strategy": "incremental"
        }
        headers = {"Authorization": f"Bearer {dummy_token}"}
        res = client.post("/api/subscriptions", json=payload, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid Cron expression", res.json["error"])
        
        # Clean up
        active_sessions.remove(dummy_token)

    def test_09_rule_tester(self):
        """Test rule testing endpoint for regex matching and renaming."""
        from web_app import app, active_sessions
        client = app.test_client()
        
        # Setup dummy session
        dummy_token = "test_token_12345"
        active_sessions.add(dummy_token)
        
        payload = {
            "filter_rules": json.dumps({"include": r"\.mp4$", "exclude": r"temp"}),
            "rename_rules": json.dumps([{"pattern": r"^(\d+)\.mp4$", "replace": r"Part_\1.mp4"}]),
            "test_filenames": [
                "01.mp4",
                "02temp.mp4",
                "notes.txt"
            ]
        }
        headers = {"Authorization": f"Bearer {dummy_token}"}
        res = client.post("/api/subscriptions/test-rules", json=payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        
        results = res.json["results"]
        self.assertEqual(len(results), 3)
        
        # "01.mp4" -> allowed, renamed to "Part_01.mp4"
        self.assertEqual(results[0]["original"], "01.mp4")
        self.assertEqual(results[0]["status"], "allowed")
        self.assertEqual(results[0]["renamed"], "Part_01.mp4")
        
        # "02temp.mp4" -> filtered out (due to temp exclude)
        self.assertEqual(results[1]["original"], "02temp.mp4")
        self.assertEqual(results[1]["status"], "filtered")
        
        # "notes.txt" -> filtered out (due to .mp4 include only)
        self.assertEqual(results[2]["original"], "notes.txt")
        self.assertEqual(results[2]["status"], "filtered")
        
        # Clean up
        active_sessions.remove(dummy_token)

    def test_10_qr_login(self):
        """Test QR code login initialization and mock status polling."""
        from web_app import app, active_sessions
        from app.api.account_api import qr_sessions
        client = app.test_client()
        
        # Setup dummy session
        dummy_token = "test_token_12345"
        active_sessions.add(dummy_token)
        headers = {"Authorization": f"Bearer {dummy_token}"}
        
        # 1. Test QR init
        res = client.get("/api/accounts/qr/init", headers=headers)
        self.assertEqual(res.status_code, 200)
        session_id = res.json["session_id"]
        self.assertTrue(session_id)
        self.assertTrue(res.json["imgurl"])
        
        # Verify it was added to qr_sessions
        self.assertIn(session_id, qr_sessions)
        
        # 2. Test QR status
        res_status = client.get(f"/api/accounts/qr/status?session_id={session_id}", headers=headers)
        self.assertEqual(res_status.status_code, 200)
        self.assertIn("status", res_status.json)
        
        # 3. Test invalid session status request
        res_invalid = client.get("/api/accounts/qr/status?session_id=invalid_session", headers=headers)
        self.assertEqual(res_invalid.status_code, 400)
        
        # Clean up
        active_sessions.remove(dummy_token)
        qr_sessions.pop(session_id, None)

    def test_11_pcs_response_parser(self):
        """Test standardized BaiduPCSClient response parsing for errno and exists."""
        from app.providers.baidu.client import BaiduPCSClient
        
        # Instantiate with dummy BDUSS
        client = BaiduPCSClient(bduss="dummy_bduss_value_12345")
        
        # Test success response standardization (adds errno=0)
        success_raw = {"list": [{"path": "/test"}]}
        parsed_success = client._parse_pcs_response(success_raw)
        self.assertEqual(parsed_success["errno"], 0)
        
        # Test error response standardization (maps error_code to errno)
        error_raw = {"error_code": 31066, "error_msg": "file does not exist"}
        parsed_error = client._parse_pcs_response(error_raw)
        self.assertEqual(parsed_error["errno"], 31066)
        
        # Test invalid response fallback
        invalid_raw = "string_response"
        parsed_invalid = client._parse_pcs_response(invalid_raw)
        self.assertEqual(parsed_invalid["errno"], -1)

if __name__ == "__main__":
    unittest.main()
