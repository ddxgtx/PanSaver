import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import datetime
from loguru import logger
from app.parsers.base import BaseParser, extract_baidu_links

class WebpageParser(BaseParser):
    """Fetches a webpage, cleans HTML tags, and extracts all Baidu Netdisk sharing links and extraction codes."""
    
    def parse(self, url: str, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        logger.info(f"Fetching Webpage from: {url}")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            html_content = resp.content
        except Exception as e:
            logger.error(f"Failed to fetch webpage: {e}")
            raise Exception(f"Webpage fetch error: {e}")

        try:
            # Parse and clean HTML
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Extract page title
            title = "网页资源"
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
                
            # Remove scripts, styles, and other non-visible elements
            for element in soup(["script", "style", "meta", "noscript", "link"]):
                element.decompose()
                
            text = soup.get_text(separator="\n")
            
            # Normalize whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = "\n".join(chunk for chunk in chunks if chunk)
            
        except Exception as e:
            logger.error(f"Failed to extract text from HTML: {e}")
            clean_text = resp.text # Fallback to raw text scan

        # Scan text for Baidu links
        found_links = extract_baidu_links(clean_text)
        
        resources = []
        for idx, match in enumerate(found_links):
            item_title = title if len(found_links) == 1 else f"{title} (Link {idx + 1})"
            
            # For webpage updates, we can generate a version string based on URL and current day
            # or the URL hash to track changes. Using date keeps it updating once per day if updated
            # or we can use the URL. To satisfy version checks:
            version = match["url"]
            
            resources.append({
                "title": item_title,
                "version": version,
                "share_url": match["url"],
                "password": match["password"],
                "published_at": datetime.datetime.utcnow().isoformat() + "Z",
                "source_url": url
            })
            
        return resources
