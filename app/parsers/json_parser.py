import requests
from typing import List, Dict, Any, Optional
import datetime
from loguru import logger
from app.parsers.base import BaseParser, extract_baidu_links

class JSONParser(BaseParser):
    """Parses JSON endpoints.
    Allows specifying keys for listing items, extracting URLs, titles, and passwords.
    """
    
    def parse(self, url: str, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        logger.info(f"Fetching JSON from: {url}")
        headers = {"User-Agent": "Mozilla/5.0 PanSave JSONFetcher"}
        
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch or parse JSON: {e}")
            raise Exception(f"JSON fetch error: {e}")

        config = config or {}
        
        # 1. Resolve root array of items
        items = []
        root_path = config.get("root_path", "") # e.g. "data.items" or "list"
        if root_path:
            parts = root_path.split(".")
            curr = data
            for part in parts:
                if isinstance(curr, dict) and part in curr:
                    curr = curr[part]
                else:
                    curr = None
                    break
            if isinstance(curr, list):
                items = curr
        else:
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = [data]

        # 2. Extract fields
        resources = []
        title_key = config.get("title_key", "title")
        url_key = config.get("url_key", "url")
        pwd_key = config.get("password_key", "password")
        ver_key = config.get("version_key", "version")
        time_key = config.get("time_key", "published_at")
        
        # If no items could be resolved, fall back to scanning the entire JSON as string
        if not items:
            logger.warning("No JSON items resolved by config. Falling back to global string scan.")
            json_str = json.dumps(data)
            found_links = extract_baidu_links(json_str)
            for idx, match in enumerate(found_links):
                resources.append({
                    "title": f"JSON Resource {idx + 1}",
                    "version": match["url"],
                    "share_url": match["url"],
                    "password": match["password"],
                    "published_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "source_url": url
                })
            return resources

        for item in items:
            if not isinstance(item, dict):
                continue
                
            share_url = item.get(url_key, "")
            # If no URL key, try scanning the entire item dict as string
            if not share_url:
                item_str = json.dumps(item)
                found = extract_baidu_links(item_str)
                if found:
                    share_url = found[0]["url"]
                    password = found[0]["password"]
                else:
                    continue
            else:
                password = item.get(pwd_key, "")
                if not password:
                    # Scan nearby fields or query string if URL contains pwd query
                    # e.g., pan.baidu.com/s/xxx?pwd=yyyy
                    parsed_url = urllib.parse.urlparse(share_url)
                    query = urllib.parse.parse_qs(parsed_url.query)
                    if "pwd" in query:
                        password = query["pwd"][0]
                    else:
                        # Scan the whole item text for a password
                        found = extract_baidu_links(json.dumps(item))
                        for f in found:
                            if f["url"] == share_url:
                                password = f["password"]
                                break
            
            title = item.get(title_key, "Unnamed JSON Item")
            version = str(item.get(ver_key, ""))
            pub_date = item.get(time_key, "")
            
            if not pub_date:
                pub_date = datetime.datetime.utcnow().isoformat() + "Z"
            if not version:
                version = f"{pub_date}_{share_url}"
                
            resources.append({
                "title": title,
                "version": version,
                "share_url": share_url,
                "password": password,
                "published_at": pub_date,
                "source_url": url
            })
            
        return resources
import urllib.parse
