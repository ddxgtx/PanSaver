import re
import requests
from typing import List, Dict, Any, Optional
import datetime
from loguru import logger
from app.parsers.base import BaseParser

class RegexParser(BaseParser):
    """Parses a web page using a custom regular expression configuration."""
    
    def parse(self, url: str, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        config = config or {}
        pattern_str = config.get("regex_pattern", "")
        if not pattern_str:
            raise ValueError("regex_pattern configuration is required for RegexParser.")
            
        logger.info(f"Fetching Webpage for regex parse from: {url}")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.error(f"Failed to fetch webpage: {e}")
            raise Exception(f"Regex page fetch error: {e}")

        try:
            regex = re.compile(pattern_str, re.DOTALL | re.MULTILINE)
        except Exception as e:
            logger.error(f"Invalid regex pattern: {pattern_str}. Error: {e}")
            raise ValueError(f"Invalid regex pattern: {e}")

        resources = []
        matches = list(regex.finditer(html))
        logger.info(f"Found {len(matches)} matches using regex pattern.")

        for idx, match in enumerate(matches):
            group_dict = match.groupdict()
            
            # Extract via named groups
            title = group_dict.get("title", f"Regex Match {idx + 1}").strip()
            share_url = group_dict.get("url", group_dict.get("share_url", "")).strip()
            password = group_dict.get("password", group_dict.get("pwd", "")).strip()
            version = group_dict.get("version", "").strip()
            published_at = group_dict.get("published_at", group_dict.get("time", "")).strip()

            # If no named groups were matched, fallback to positional groups
            if not share_url and len(match.groups()) >= 1:
                # Guess order: if 3 groups, assume title, url, password
                # if 2 groups, assume url, password
                groups = match.groups()
                if len(groups) == 2:
                    share_url = groups[0]
                    password = groups[1]
                elif len(groups) >= 3:
                    title = groups[0]
                    share_url = groups[1]
                    password = groups[2]

            if not share_url:
                continue

            if not published_at:
                published_at = datetime.datetime.utcnow().isoformat() + "Z"
            if not version:
                version = f"{published_at}_{share_url}"

            resources.append({
                "title": title,
                "version": version,
                "share_url": share_url,
                "password": password,
                "published_at": published_at,
                "source_url": url
            })

        return resources
