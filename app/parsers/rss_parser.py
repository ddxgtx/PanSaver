import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import email.utils
import datetime
from loguru import logger
from app.parsers.base import BaseParser, extract_baidu_links

class RSSParser(BaseParser):
    """Parses RSS 2.0 and Atom feeds, extracting Netdisk links and passwords from entry contents."""
    
    def parse(self, url: str, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        logger.info(f"Fetching RSS feed from: {url}")
        headers = {"User-Agent": "Mozilla/5.0 PanSave FeedFetcher"}
        
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            xml_content = resp.content
        except Exception as e:
            logger.error(f"Failed to fetch RSS feed: {e}")
            raise Exception(f"RSS fetch error: {e}")

        resources = []
        try:
            root = ET.fromstring(xml_content)
        except Exception as e:
            logger.error(f"Failed to parse XML: {e}")
            raise Exception(f"XML parse error: {e}")

        # Check if RSS 2.0 or Atom
        # RSS 2.0 uses <channel><item>...
        # Atom uses <feed><entry>...
        
        # 1. Parse RSS 2.0
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                title = item.findtext("title", "Unnamed RSS Item")
                link = item.findtext("link", "")
                description = item.findtext("description", "")
                pub_date_str = item.findtext("pubDate", "")
                
                # Try to parse published date
                published_at = self._parse_pubdate(pub_date_str)
                
                # Combine title, link, description to scan for Baidu links
                full_text = f"{title}\n{link}\n{description}"
                found_links = extract_baidu_links(full_text)
                
                for idx, match in enumerate(found_links):
                    # If multiple links found, append index to title
                    item_title = title if len(found_links) == 1 else f"{title} (Part {idx + 1})"
                    resources.append({
                        "title": item_title,
                        "version": f"{published_at}_{match['url']}",
                        "share_url": match["url"],
                        "password": match["password"],
                        "published_at": published_at,
                        "source_url": link or url
                    })
            return resources

        # 2. Parse Atom
        # Handle namespaces if present in Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        # Check if root tag ends with 'feed'
        if root.tag.endswith("feed") or root.find("atom:entry", ns) is not None:
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall("atom:entry", ns) or root.findall("entry")
            for entry in entries:
                # Find tag with namespace or fallback
                title_elem = entry.find("{http://www.w3.org/2005/Atom}title") or entry.find("title")
                title = title_elem.text if title_elem is not None else "Unnamed Atom Item"
                
                link_elem = entry.find("{http://www.w3.org/2005/Atom}link") or entry.find("link")
                link = ""
                if link_elem is not None:
                    link = link_elem.attrib.get("href", "")
                    
                summary_elem = entry.find("{http://www.w3.org/2005/Atom}summary") or entry.find("summary")
                content_elem = entry.find("{http://www.w3.org/2005/Atom}content") or entry.find("content")
                
                content_text = ""
                if content_elem is not None and content_elem.text:
                    content_text = content_elem.text
                elif summary_elem is not None and summary_elem.text:
                    content_text = summary_elem.text
                    
                updated_elem = entry.find("{http://www.w3.org/2005/Atom}updated") or entry.find("updated") or entry.find("{http://www.w3.org/2005/Atom}published") or entry.find("published")
                published_at = updated_elem.text if updated_elem is not None else datetime.datetime.utcnow().isoformat() + "Z"
                
                full_text = f"{title}\n{link}\n{content_text}"
                found_links = extract_baidu_links(full_text)
                
                for idx, match in enumerate(found_links):
                    item_title = title if len(found_links) == 1 else f"{title} (Part {idx + 1})"
                    resources.append({
                        "title": item_title,
                        "version": f"{published_at}_{match['url']}",
                        "share_url": match["url"],
                        "password": match["password"],
                        "published_at": published_at,
                        "source_url": link or url
                    })
            return resources

        logger.warning("XML root tag matched neither RSS 2.0 nor Atom feed.")
        return []

    def _parse_pubdate(self, pubdate_str: str) -> str:
        if not pubdate_str:
            return datetime.datetime.utcnow().isoformat() + "Z"
        try:
            parsed = email.utils.parsedate_to_datetime(pubdate_str)
            return parsed.isoformat()
        except Exception:
            return pubdate_str
