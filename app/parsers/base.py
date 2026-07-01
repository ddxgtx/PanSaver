import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseParser(ABC):
    @abstractmethod
    def parse(self, url: str, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Parses the subscription source and returns list of resources.
        
        Returned structure:
        {
          "title": str,
          "version": str, (unique identifier/hash or date)
          "share_url": str,
          "password": str,
          "published_at": str, (ISO 8601)
          "source_url": str
        }
        """
        pass

def extract_baidu_links(text: str) -> List[Dict[str, str]]:
    """Scans text for Baidu Netdisk sharing links and attempts to locate their extraction codes.
    Returns a list of dicts: [{'url': '...', 'password': '...'}]
    """
    # Pattern to match Baidu share URLs (standard and short forms)
    url_pattern = re.compile(
        r'(https?://pan\.baidu\.com/s/[a-zA-Z0-9_-]+|https?://pan\.baidu\.com/init\?surl=[a-zA-Z0-9_-]+)'
    )
    
    # Password patterns to check nearby text (e.g. 提取码: abcd, 密码: abcd, 提取码abcd)
    pwd_patterns = [
        re.compile(r'(?:提取码|提取码是|提取|密码|密|码|提取码：|密码：)[:：\s]*([a-zA-Z0-9]{4})\b'),
        re.compile(r'\b([a-zA-Z0-9]{4})\b') # Fallback match for any 4-character alphanum nearby
    ]
    
    matches = []
    seen_urls = set()
    
    # Find all sharing URLs in the text
    for match in url_pattern.finditer(text):
        url = match.group(1)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        # Look for password in the surrounding text (up to 100 characters ahead)
        end_pos = match.end()
        surrounding_text = text[end_pos:end_pos + 120]
        
        password = ""
        for pattern in pwd_patterns:
            pwd_match = pattern.search(surrounding_text)
            if pwd_match:
                password = pwd_match.group(1)
                break
                
        matches.append({
            "url": url,
            "password": password
        })
        
    return matches
