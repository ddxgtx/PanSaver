import time
import hashlib
import json
from typing import List, Dict, Any, Tuple, Optional
from app.providers.baidu.client import BaiduPCSClient
from app.database.db import db_conn, db_transaction
from loguru import logger

class SnapshotService:
    """Service to create, store, and compare sharing folder snapshots."""
    
    @staticmethod
    def fetch_share_file_tree(client: BaiduPCSClient, share_url: str, password: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Recursively lists all files in the share and returns the file records and share info."""
        share_info = client.access_share(share_url, password)
        share_id = share_info["share_id"]
        uk = share_info["uk"]
        top_files = share_info["file_list"]
        
        file_tree: List[Dict[str, Any]] = []
        
        def recurse(items: List[Dict[str, Any]], parent_rel_path: str):
            for item in items:
                name = item.get("server_filename") or item.get("filename") or ""
                if not name:
                    continue
                    
                isdir = item.get("isdir")
                if isdir is None:
                    isdir = 1 if item.get("is_dir") or item.get("isdir") == 1 else 0
                
                # Compute relative path
                rel_path = f"{parent_rel_path}/{name}" if parent_rel_path else name
                
                fs_id = str(item.get("fs_id") or "")
                size = int(item.get("size") or 0)
                mtime = int(item.get("server_mtime") or item.get("mtime") or 0)
                
                file_record = {
                    "relative_path": rel_path,
                    "file_name": name,
                    "file_size": size,
                    "modified_time": mtime,
                    "file_id": fs_id,
                    "is_directory": 1 if isdir else 0,
                }
                
                # File hash: SHA256(relative_path + size + modified_time + file_id)
                record_str = f"{rel_path}|{size}|{mtime}|{fs_id}"
                file_record["file_hash"] = hashlib.sha256(record_str.encode("utf-8")).hexdigest()
                
                file_tree.append(file_record)
                
                if isdir:
                    item_path = item.get("path") or ""
                    if item_path:
                        # Introduce a configurable delay to prevent API rate limiting
                        time.sleep(0.3)
                        try:
                            sub_items = client.list_shared_dir(share_url, share_id, uk, item_path)
                            recurse(sub_items, rel_path)
                        except Exception as e:
                            logger.error(f"Error listing shared sub-directory '{item_path}': {e}")
                            raise e
                            
        recurse(top_files, "")
        return file_tree, share_info

    @staticmethod
    def calculate_tree_hash(file_tree: List[Dict[str, Any]]) -> str:
        """Sorts all file hashes in the tree and computes a single SHA-256 hash representing the tree footprint."""
        if not file_tree:
            return hashlib.sha256(b"").hexdigest()
        # Sort by relative path to ensure deterministic output
        hashes = [f["file_hash"] for f in sorted(file_tree, key=lambda x: x["relative_path"])]
        concat_str = "".join(hashes)
        return hashlib.sha256(concat_str.encode("utf-8")).hexdigest()

    @staticmethod
    def save_snapshot(subscription_id: int, source_version: str, source_hash: str, share_url: str, file_tree: List[Dict[str, Any]]) -> int:
        """Saves a snapshot and its flat files catalog to the database."""
        file_tree_hash = SnapshotService.calculate_tree_hash(file_tree)
        file_count = len(file_tree)
        total_size = sum(f["file_size"] for f in file_tree if not f["is_directory"])
        raw_data = json.dumps(file_tree)

        with db_transaction() as conn:
            # 1. Insert snapshot record
            cursor = conn.execute("""
            INSERT INTO snapshots (subscription_id, source_version, source_hash, file_tree_hash, share_url, file_count, total_size, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (subscription_id, source_version, source_hash, file_tree_hash, share_url, file_count, total_size, raw_data))
            
            snapshot_id = cursor.lastrowid
            
            # 2. Insert snapshot files catalog in batches
            batch_size = 200
            file_records = []
            for f in file_tree:
                file_records.append((
                    snapshot_id,
                    f["relative_path"],
                    f["file_name"],
                    f["file_size"],
                    f["modified_time"],
                    f["file_id"],
                    f["is_directory"],
                    f["file_hash"]
                ))
                
                if len(file_records) >= batch_size:
                    conn.executemany("""
                    INSERT INTO snapshot_files (snapshot_id, relative_path, file_name, file_size, modified_time, file_id, is_directory, file_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, file_records)
                    file_records = []
                    
            if file_records:
                conn.executemany("""
                INSERT INTO snapshot_files (snapshot_id, relative_path, file_name, file_size, modified_time, file_id, is_directory, file_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, file_records)
                
            # 3. Update subscription's last_snapshot_hash
            conn.execute("""
            UPDATE subscriptions SET last_snapshot_hash = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """, (file_tree_hash, subscription_id))
            
            return snapshot_id

    @staticmethod
    def load_snapshot_files(snapshot_id: int) -> List[Dict[str, Any]]:
        """Loads all file records belonging to a snapshot."""
        with db_conn() as conn:
            rows = conn.execute("""
            SELECT relative_path, file_name, file_size, modified_time, file_id, is_directory, file_hash
            FROM snapshot_files WHERE snapshot_id = ?
            """, (snapshot_id,)).fetchall()
            
            return [dict(row) for row in rows]

    @staticmethod
    def compare_snapshots(old_files: List[Dict[str, Any]], new_files: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
        """Compares two snapshots and generates file-level differences (added, modified, deleted, renamed)."""
        old_by_path = {f["relative_path"]: f for f in old_files}
        old_by_id = {f["file_id"]: f for f in old_files if f.get("file_id")}
        
        new_by_path = {f["relative_path"]: f for f in new_files}
        new_by_id = {f["file_id"]: f for f in new_files if f.get("file_id")}

        added = []
        modified = []
        deleted = []
        renamed = [] # List of tuples: (old_record, new_record)

        # 1. Detect added and renamed files
        for new_path, new_file in new_by_path.items():
            old_file = old_by_path.get(new_path)
            
            if old_file is None:
                # File is not in old path. Check if it was renamed (same file_id)
                new_id = new_file.get("file_id")
                if new_id and new_id in old_by_id:
                    old_renamed_file = old_by_id[new_id]
                    renamed.append((old_renamed_file, new_file))
                else:
                    added.append(new_file)
            else:
                # File exists in both paths. Check if modified
                if new_file["file_hash"] != old_file["file_hash"]:
                    modified.append(new_file)

        # 2. Detect deleted files
        for old_path, old_file in old_by_path.items():
            new_file = new_by_path.get(old_path)
            
            if new_file is None:
                # File is not in new path. Check if it was renamed
                old_id = old_file.get("file_id")
                if old_id and old_id in new_by_id:
                    # Already captured in renamed loop, do nothing
                    pass
                else:
                    deleted.append(old_file)

        return {
            "added": added,
            "modified": modified,
            "deleted": deleted,
            "renamed": renamed
        }
