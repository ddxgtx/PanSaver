from app.parsers.base import BaseParser
from app.parsers.baidu_share import BaiduShareParser
from app.parsers.rss_parser import RSSParser
from app.parsers.json_parser import JSONParser
from app.parsers.webpage_parser import WebpageParser
from app.parsers.regex_parser import RegexParser

def get_parser(source_type: str) -> BaseParser:
    """Returns the parser instance matching the subscription source type."""
    parsers = {
        "baidu_share": BaiduShareParser,
        "rss": RSSParser,
        "json": JSONParser,
        "webpage": WebpageParser,
        "regex": RegexParser
    }
    
    parser_cls = parsers.get(source_type)
    if not parser_cls:
        raise ValueError(f"Unknown parser source type: {source_type}. Supported: {list(parsers.keys())}")
        
    return parser_cls()
