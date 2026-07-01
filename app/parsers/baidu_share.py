from typing import List, Dict, Any, Optional
from app.parsers.base import BaseParser
import time

class BaiduShareParser(BaseParser):
    """Direct Baidu Netdisk share parser.
    It doesn't crawl any external web pages but returns the subscription configuration itself.
    """
    def parse(self, url: str, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        config = config or {}
        password = config.get("password", "")
        title = config.get("name", "Baidu Share Item")
        
        # Generates a version based on the link and password or current timestamp if not cached
        return [{
            "title": title,
            "version": config.get("last_snapshot_hash", "initial"),
            "share_url": url,
            "password": password,
            "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_url": url
        }]
