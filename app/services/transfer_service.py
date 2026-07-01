import os
import re
import time
import json
import datetime
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from loguru import logger
from app.database.db import db_conn, db_transaction
from app.providers.baidu.client import BaiduPCSClient
from app.services.snapshot_service import SnapshotService
from app.parsers import get_parser
from app.utils.retry import retry_call

class TransferService:
    """Core transfer service coordinating parsers, clients, strategies, filtering, and rollbacks."""
    
    @staticmethod
    def execute_run(subscription_id: int, trigger_type: str = "scheduler") -> int:
        """Executes a full run for a subscription and returns the task run ID."""
        # 1. Fetch subscription details
        with db_conn() as conn:
            sub = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)).fetchone()
            if not sub:
                raise ValueError(f"Subscription with ID {subscription_id} not found.")
            sub = dict(sub)
            
            # Fetch default or specified account
            account_id = sub.get("account_id")
            if not account_id:
                # Use default active account
                account = conn.execute("SELECT * FROM accounts WHERE status = 'active' LIMIT 1").fetchone()
            else:
                account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
                
            if not account:
                raise Exception("No active Baidu Netdisk account available for this task.")
            account = dict(account)

        # 2. Decrypt cookies and passwords
        from app.security.crypto import decrypt
        try:
            cookies = json.loads(decrypt(account["cookie_encrypted"]))
            bduss = cookies.get("BDUSS", "")
            stoken = cookies.get("STOKEN", "")
        except Exception as e:
            logger.error(f"Failed to decrypt account cookies: {e}")
            raise Exception("Account credentials decryption failed.")

        share_password = ""
        if sub.get("share_password_encrypted"):
            try:
                share_password = decrypt(sub["share_password_encrypted"])
            except Exception as e:
                logger.error(f"Failed to decrypt share password: {e}")

        # 3. Create task_run record
        with db_transaction() as conn:
            cursor = conn.execute("""
            INSERT INTO task_runs (subscription_id, trigger_type, status, started_at)
            VALUES (?, ?, 'running', datetime('now', 'localtime'))
            """, (subscription_id, trigger_type))
            run_id = cursor.lastrowid
            
        # Bind run_id to logger
        task_logger = logger.bind(task_run_id=run_id, stage="parse")
        task_logger.info(f"Started task run {run_id} for subscription '{sub['name']}'")

        try:
            client = BaiduPCSClient(bduss, stoken)
            
            # Verify account status
            task_logger.info("Verifying Baidu Netdisk account status...")
            acc_info = retry_call(client.verify)
            with db_transaction() as conn:
                conn.execute("""
                UPDATE accounts SET name = ?, quota_total = ?, quota_used = ?, last_verified_at = datetime('now', 'localtime')
                WHERE id = ?
                """, (acc_info["nickname"], acc_info["quota_total"], acc_info["quota_used"], account["id"]))
                
            # 4. Resolve Subscription Source
            task_logger.info(f"Parsing subscription source page (Type: {sub['source_type']})...")
            parser = get_parser(sub["source_type"])
            
            # Prepare parser configuration
            parser_config = {
                "name": sub["name"],
                "password": share_password,
                "last_snapshot_hash": sub.get("last_snapshot_hash", "")
            }
            if sub.get("filter_rules"):
                try:
                    parser_config.update(json.loads(sub["filter_rules"]))
                except Exception:
                    pass
            
            source_url = sub.get("source_url") or sub.get("share_url")
            parsed_items = parser.parse(source_url, parser_config)
            
            if not parsed_items:
                task_logger.warning("No resources could be extracted from subscription source.")
                with db_transaction() as conn:
                    conn.execute("""
                    UPDATE task_runs SET status = 'failed', finished_at = datetime('now', 'localtime'), error_message = 'No share items found'
                    WHERE id = ?
                    """, (run_id,))
                return run_id
                
            # For simplicity, we process the first parsed resource
            res = parsed_items[0]
            share_url = res["share_url"]
            password = res["password"] or share_password
            version = res["version"]
            
            task_logger.bind(stage="check")
            task_logger.info(f"Extracted share link: {share_url}")

            # 5. Fetch share file tree snapshot
            task_logger.info("Fetching and analyzing shared file tree...")
            file_tree, share_info = retry_call(SnapshotService.fetch_share_file_tree, args=(client, share_url, password))
            tree_hash = SnapshotService.calculate_tree_hash(file_tree)
            
            # Load last successful snapshot to compare
            last_snapshot_id = None
            
            # Fast-path check: if tree_hash matches sub['last_snapshot_hash'], no changes occurred
            if sub.get("last_snapshot_hash") == tree_hash:
                task_logger.info("No file changes detected (matched last snapshot hash). Skipping transfer.")
                with db_transaction() as conn:
                    last_snap_row = conn.execute("""
                    SELECT id FROM snapshots WHERE subscription_id = ? ORDER BY id DESC LIMIT 1
                    """, (subscription_id,)).fetchone()
                    last_snapshot_id = last_snap_row["id"] if last_snap_row else None
                    
                    conn.execute("""
                    UPDATE task_runs 
                    SET status = 'success', finished_at = datetime('now', 'localtime'), 
                        old_snapshot_id = ?, new_snapshot_id = ?,
                        added_count = 0, modified_count = 0, deleted_count = 0, transferred_count = 0
                    WHERE id = ?
                    """, (last_snapshot_id, last_snapshot_id, run_id))
                    
                    conn.execute("""
                    UPDATE subscriptions SET last_checked_at = datetime('now', 'localtime'), updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                    """, (subscription_id,))
                
                # Trigger notification
                try:
                    from app.services.notification_service import NotificationService
                    NotificationService.send_transfer_notification(run_id)
                except Exception as ne:
                    logger.error(f"Failed to send notification: {ne}")
                    
                return run_id

            old_files = []
            with db_conn() as conn:
                last_snap_row = conn.execute("""
                SELECT id FROM snapshots WHERE subscription_id = ? ORDER BY id DESC LIMIT 1
                """, (subscription_id,)).fetchone()
                if last_snap_row:
                    last_snapshot_id = last_snap_row["id"]
                    old_files = SnapshotService.load_snapshot_files(last_snapshot_id)

            # Compare snapshots
            diffs = SnapshotService.compare_snapshots(old_files, file_tree)
            
            added_cnt = len(diffs["added"])
            modified_cnt = len(diffs["modified"])
            deleted_cnt = len(diffs["deleted"])
            renamed_cnt = len(diffs["renamed"])
            
            task_logger.info(
                f"Diff results: Added: {added_cnt}, Modified: {modified_cnt}, "
                f"Deleted: {deleted_cnt}, Renamed: {renamed_cnt}"
            )
            
            # Save new snapshot
            new_snapshot_id = SnapshotService.save_snapshot(
                subscription_id=subscription_id,
                source_version=version,
                source_hash=hashlib.sha256(share_url.encode("utf-8")).hexdigest(),
                share_url=share_url,
                file_tree=file_tree
            )

            # If NO changes, terminate early
            if not diffs["added"] and not diffs["modified"] and not diffs["deleted"] and not diffs["renamed"]:
                task_logger.info("No file changes detected. Skipping transfer.")
                with db_transaction() as conn:
                    conn.execute("""
                    UPDATE task_runs 
                    SET status = 'success', finished_at = datetime('now', 'localtime'), 
                        old_snapshot_id = ?, new_snapshot_id = ?
                    WHERE id = ?
                    """, (last_snapshot_id, new_snapshot_id, run_id))
                return run_id

            # 6. Apply Filter & Rename Rules
            task_logger.bind(stage="transfer")
            filtered_diffs = TransferService.apply_rules(diffs, sub)

            # 7. Execute Transfer Strategy
            strategy = sub["transfer_strategy"]
            task_logger.info(f"Applying transfer strategy: {strategy}")
            
            transferred_count = 0
            
            if strategy == "notify_only":
                task_logger.info("Strategy is notify_only. No files were copied.")
                
            elif strategy == "incremental":
                transferred_count = TransferService._execute_incremental(
                    client, filtered_diffs, sub["target_path"], share_info["share_id"], share_info["uk"], share_info["bdstoken"], share_url, task_logger
                )
                
            elif strategy == "version_archive":
                version_dir_name = version or datetime.datetime.now().strftime("%Y-%m-%d")
                # Strip invalid characters from directory names
                version_dir_name = re.sub(r'[\/:*?"<>|]', "_", version_dir_name)
                target_version_path = f"{sub['target_path']}/{version_dir_name}".rstrip("/")
                
                transferred_count = TransferService._execute_version_archive(
                    client, file_tree, target_version_path, share_info["share_id"], share_info["uk"], share_info["bdstoken"], share_url, task_logger
                )
                
            elif strategy == "safe_overwrite":
                transferred_count = TransferService._execute_safe_overwrite(
                    client, file_tree, sub["target_path"], subscription_id, run_id, share_info, share_url, task_logger
                )

            # 8. Update task_run success status
            with db_transaction() as conn:
                conn.execute("""
                UPDATE task_runs 
                SET status = 'success', finished_at = datetime('now', 'localtime'), 
                    old_snapshot_id = ?, new_snapshot_id = ?,
                    added_count = ?, modified_count = ?, deleted_count = ?, transferred_count = ?
                WHERE id = ?
                """, (last_snapshot_id, new_snapshot_id, added_cnt, modified_cnt, deleted_cnt, transferred_count, run_id))
                
                # Update next run time
                conn.execute("""
                UPDATE subscriptions SET last_checked_at = datetime('now', 'localtime'), updated_at = datetime('now', 'localtime')
                WHERE id = ?
                """, (subscription_id,))
                
            # Trigger notification
            from app.services.notification_service import NotificationService
            NotificationService.send_transfer_notification(run_id)

        except Exception as e:
            task_logger.error(f"Task run failed with error: {e}")
            with db_transaction() as conn:
                conn.execute("""
                UPDATE task_runs 
                SET status = 'failed', finished_at = datetime('now', 'localtime'), error_message = ?
                WHERE id = ?
                """, (str(e), run_id))
            
            # Trigger failure notification
            try:
                from app.services.notification_service import NotificationService
                NotificationService.send_transfer_notification(run_id)
            except Exception as ne:
                logger.error(f"Failed to send failure notification: {ne}")
                
        return run_id

    @staticmethod
    def apply_rules(diffs: Dict[str, List[Any]], sub: Dict[str, Any]) -> Dict[str, List[Any]]:
        """Applies filters and renaming rules to file lists."""
        include_pat = None
        exclude_pat = None
        rename_rules = []

        # Parse filter rules
        if sub.get("filter_rules"):
            try:
                rules = json.loads(sub["filter_rules"])
                inc = rules.get("include")
                exc = rules.get("exclude")
                if inc:
                    include_pat = re.compile(inc, re.IGNORECASE)
                if exc:
                    exclude_pat = re.compile(exc, re.IGNORECASE)
            except Exception as e:
                logger.error(f"Failed to parse filter rules regex: {e}")

        # Parse rename rules
        if sub.get("rename_rules"):
            try:
                rename_rules = json.loads(sub["rename_rules"]) # List of Dict: [{"pattern": "...", "replace": "..."}]
            except Exception as e:
                logger.error(f"Failed to parse rename rules: {e}")

        def process_file(f: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            path = f["relative_path"]
            name = f["file_name"]
            
            # Filter directories: we keep directories, filters only apply to files
            if not f["is_directory"]:
                if include_pat and not include_pat.search(name) and not include_pat.search(path):
                    return None
                if exclude_pat and (exclude_pat.search(name) or exclude_pat.search(path)):
                    return None
            
            # Rename processing
            new_name = name
            for rule in rename_rules:
                pat = rule.get("pattern")
                repl = rule.get("replace")
                if pat and repl is not None:
                    try:
                        new_name = re.sub(pat, repl, new_name)
                    except Exception as e:
                        logger.error(f"Rename pattern substitution error: {e}")
            
            if new_name != name:
                f = dict(f) # Copy
                f["file_name"] = new_name
                # Re-calculate relative path based on new name
                dir_name = os.path.dirname(path)
                f["relative_path"] = f"{dir_name}/{new_name}" if dir_name else new_name
            return f

        new_diffs = {"added": [], "modified": [], "deleted": [], "renamed": []}
        
        for k in ["added", "modified", "deleted"]:
            for f in diffs[k]:
                processed = process_file(f)
                if processed:
                    new_diffs[k].append(processed)
                    
        for old_f, new_f in diffs["renamed"]:
            p_old = process_file(old_f)
            p_new = process_file(new_f)
            if p_old and p_new:
                new_diffs["renamed"].append((p_old, p_new))
                
        return new_diffs

    @staticmethod
    def _execute_incremental(
        client: BaiduPCSClient, 
        diffs: Dict[str, List[Any]], 
        target_dir: str, 
        share_id: int, 
        uk: int, 
        bdstoken: str, 
        share_url: str,
        task_logger
    ) -> int:
        """Saves added/modified files and handles duplicates under incremental strategy."""
        transferred_count = 0
        
        # 1. Batch create required subdirectories
        subdirs = set()
        for f in diffs["added"] + diffs["modified"]:
            rel_dir = os.path.dirname(f["relative_path"])
            if rel_dir:
                subdirs.add(rel_dir)
                
        for subdir in sorted(subdirs):
            full_subdir = f"{target_dir}/{subdir}".replace("\\", "/")
            task_logger.info(f"Ensuring subdirectory exists: {full_subdir}")
            res_mkdir = retry_call(client.makedir, args=(full_subdir,))
            # errno == 0 (created successfully) or 31061 (directory already exists)
            if res_mkdir.get("errno") not in (0, 31061):
                raise Exception(f"Failed to ensure subdirectory {full_subdir}: {res_mkdir.get('error_msg', res_mkdir.get('errno'))}")

        # 2. Transfer added files (group by target directory)
        added_by_dir = {}
        for f in diffs["added"]:
            if f["is_directory"]:
                # Directory creation is already handled, we only transfer files
                continue
            rel_dir = os.path.dirname(f["relative_path"])
            dir_path = f"{target_dir}/{rel_dir}".rstrip("/").replace("\\", "/")
            if dir_path not in added_by_dir:
                added_by_dir[dir_path] = []
            added_by_dir[dir_path].append(int(f["file_id"]))
            
        for dir_path, fs_ids in added_by_dir.items():
            # Chunk transfers into batches of 500 to stay well under Baidu's 1000 limits
            chunk_size = 500
            for i in range(0, len(fs_ids), chunk_size):
                chunk = fs_ids[i:i + chunk_size]
                task_logger.info(f"Transferring batch ({len(chunk)} files) into: {dir_path}")
                res = retry_call(client.transfer, args=(share_id, uk, bdstoken, share_url, chunk, dir_path))
                if res.get("errno") != 0:
                    if res.get("errno") == 12: # Standard Baidu Netdisk quota exceeded errno
                        raise Exception("Netdisk space quota exceeded. Aborting transfer.")
                    raise Exception(f"Baidu Netdisk transfer failed: {res.get('show_msg', res.get('errno'))}")
                transferred_count += len(chunk)

        # 3. Handle modified (duplicate) files
        # Options: Skip, Rename, Delete, Backup (default)
        # For simplicity, we implement "Backup" by default
        for f in diffs["modified"]:
            if f["is_directory"]:
                continue
                
            file_path = f"{target_dir}/{f['relative_path']}".replace("\\", "/")
            if retry_call(client.exists, args=(file_path,)):
                # Backup old file: Move it to backup directory
                backup_root = f"{target_dir}/.pansave/backup/changed_files"
                if not retry_call(client.exists, args=(backup_root,)):
                    retry_call(client.makedir, args=(backup_root,))
                    
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                base_name = f["file_name"]
                name_parts = os.path.splitext(base_name)
                backup_name = f"{name_parts[0]}_{timestamp}{name_parts[1]}"
                backup_path = f"{backup_root}/{backup_name}"
                
                task_logger.info(f"Backing up modified file: {file_path} -> {backup_path}")
                retry_call(client.rename, args=(file_path, backup_path))
                
            # Save new file
            rel_dir = os.path.dirname(f["relative_path"])
            dir_path = f"{target_dir}/{rel_dir}".rstrip("/").replace("\\", "/")
            task_logger.info(f"Saving updated file {f['file_name']} into: {dir_path}")
            res = retry_call(client.transfer, args=(share_id, uk, bdstoken, share_url, [int(f["file_id"])], dir_path))
            if res.get("errno") != 0:
                raise Exception(f"Failed to transfer updated file: {res}")
            transferred_count += 1
            
        return transferred_count

    @staticmethod
    def _execute_version_archive(
        client: BaiduPCSClient, 
        file_tree: List[Dict[str, Any]], 
        version_dir: str, 
        share_id: int, 
        uk: int, 
        bdstoken: str, 
        share_url: str,
        task_logger
    ) -> int:
        """Saves entire snapshot to a version-controlled folder."""
        # Create version archive directory
        if not retry_call(client.exists, args=(version_dir,)):
            task_logger.info(f"Creating version archive directory: {version_dir}")
            retry_call(client.makedir, args=(version_dir,))
            
        # For version archives, we transfer top-level items directly (highly efficient!)
        top_items = [f for f in file_tree if "/" not in f["relative_path"]]
        fs_ids = [int(item["file_id"]) for item in top_items]
        
        # Chunk version archives transfers
        chunk_size = 500
        for i in range(0, len(fs_ids), chunk_size):
            chunk = fs_ids[i:i + chunk_size]
            task_logger.info(f"Transferring batch ({len(chunk)} root items) to: {version_dir}")
            res = retry_call(client.transfer, args=(share_id, uk, bdstoken, share_url, chunk, version_dir))
            if res.get("errno") != 0:
                if res.get("errno") == 12:
                    raise Exception("Netdisk space quota exceeded.")
                raise Exception(f"Baidu Netdisk transfer failed: {res}")
            
        return len(file_tree)

    @staticmethod
    def _execute_safe_overwrite(
        client: BaiduPCSClient,
        file_tree: List[Dict[str, Any]],
        target_path: str,
        sub_id: int,
        run_id: int,
        share_info: Dict[str, Any],
        share_url: str,
        task_logger
    ) -> int:
        """Executes secure overwrite strategy with verification and transactional rollback."""
        staging_dir = f"{target_path}/.pansave/staging/task_{sub_id}/run_{run_id}".replace("\\", "/")
        backup_dir = f"{target_path}/.pansave/backup/task_{sub_id}_{int(time.time())}".replace("\\", "/")
        
        # 1. Clean and create Staging
        if retry_call(client.exists, args=(staging_dir,)):
            task_logger.warning(f"Staging directory {staging_dir} already exists. Cleaning...")
            retry_call(client.remove, args=(staging_dir,))
            
        retry_call(client.makedir, args=(staging_dir,))
        
        # 2. Transfer all root items to Staging
        top_items = [f for f in file_tree if "/" not in f["relative_path"]]
        fs_ids = [int(item["file_id"]) for item in top_items]
        
        # Chunk safe-overwrite transfers to Staging
        chunk_size = 500
        for i in range(0, len(fs_ids), chunk_size):
            chunk = fs_ids[i:i + chunk_size]
            task_logger.info(f"Safe Overwrite: Transferring batch ({len(chunk)} files) to Staging: {staging_dir}")
            res = retry_call(client.transfer, args=(share_info["share_id"], share_info["uk"], share_info["bdstoken"], share_url, chunk, staging_dir))
            if res.get("errno") != 0:
                raise Exception(f"Safe Overwrite: Transfer to staging failed: {res}")

        # 3. Verify Integrity
        task_logger.info("Safe Overwrite: Verifying staging directory file tree integrity...")
        staged_files = retry_call(client.list_dir, args=(staging_dir,))
        # Since files are transferred inside the staging directory, if the share had a single folder 'Photos',
        # staging_dir contains 'Photos'. If it had files directly, staging_dir has those files.
        # Let's count files inside staging recursively to match file_tree.
        # Simple verify: compare count of root folders/files listed in staging.
        if len(staged_files) != len(top_items):
            task_logger.error(f"Safe Overwrite verification failed. Staged root items: {len(staged_files)}, expected: {len(top_items)}")
            retry_call(client.remove, args=(staging_dir,))
            raise Exception("Safe Overwrite: Integrity check failed. File count mismatch.")

        # 4. Backup Existing Target Directory
        target_exists = retry_call(client.exists, args=(target_path,))
        if target_exists:
            task_logger.info(f"Safe Overwrite: Moving current target to backup: {backup_dir}")
            # Ensure backup parent directory exists
            backup_parent = os.path.dirname(backup_dir)
            if not retry_call(client.exists, args=(backup_parent,)):
                retry_call(client.makedir, args=(backup_parent,))
            
            # Move target directory to backup path
            res_backup = retry_call(client.rename, args=(target_path, backup_dir))
            if res_backup.get("errno") != 0:
                # Clean staging
                retry_call(client.remove, args=(staging_dir,))
                raise Exception(f"Safe Overwrite: Failed to move target to backup: {res_backup}")

        # 5. Move Staging to Formal Target
        task_logger.info(f"Safe Overwrite: Moving Staging to target path: {target_path}")
        res_deploy = retry_call(client.rename, args=(staging_dir, target_path))
        if res_deploy.get("errno") != 0:
            task_logger.error(f"Safe Overwrite: Deploy failed: {res_deploy}. Initiating rollback...")
            # ROLLBACK PROCESS
            if target_exists:
                task_logger.warning(f"Rolling back: Restoring target from backup '{backup_dir}'...")
                retry_call(client.rename, args=(backup_dir, target_path))
            raise Exception(f"Safe Overwrite: Deploy from staging failed: {res_deploy}")

        # 6. Success. Clean old backups (keep only last N, e.g. 3)
        task_logger.info("Safe Overwrite: Clean backup history, keeping last 3 backups.")
        try:
            backup_parent = f"{target_path}/.pansave/backup".replace("\\", "/")
            if retry_call(client.exists, args=(backup_parent,)):
                backups = retry_call(client.list_dir, args=(backup_parent,))
                # Sort by path/mtime to find oldest
                backups = sorted(backups, key=lambda x: x.get("mtime", 0))
                # If count exceeds limit, delete oldest
                if len(backups) > 3:
                    to_delete = backups[:-3]
                    for b in to_delete:
                        b_path = b.get("path")
                        if b_path:
                            task_logger.info(f"Removing old backup: {b_path}")
                            retry_call(client.remove, args=(b_path,))
        except Exception as ex:
            task_logger.warning(f"Safe Overwrite: Clean old backups warning: {ex}")

        return len(file_tree)
import hashlib
