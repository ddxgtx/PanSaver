import re
import json
import time
import random
import urllib.parse
from typing import Optional, Dict, List, Any
import requests
from loguru import logger

PAN_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.75 Safari/537.36"
PCS_UA = "softxm;netdisk"

class BaiduPCSClient:
    """Pure Python adapter for Baidu Netdisk PCS & Web APIs.
    No Cython or binary compilation dependencies.
    """
    def __init__(self, bduss: str, stoken: Optional[str] = None):
        if not bduss:
            raise ValueError("BDUSS cookie is required.")
        self.bduss = bduss
        self.stoken = stoken
        self._bdstoken = None
        
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": PAN_UA})
        
        # Inject cookies
        cookies = {"BDUSS": bduss}
        if stoken:
            cookies["STOKEN"] = stoken
        self.session.cookies.update(cookies)
        
        # Initialize a separate anonymous session for crawling public share links
        self.share_session = requests.Session()
        self.share_session.headers.update({"User-Agent": PAN_UA})

    def _get_bdstoken(self) -> str:
        """Fetch the account bdstoken dynamically if not already cached."""
        if self._bdstoken:
            return self._bdstoken
        
        url = "https://pan.baidu.com/disk/home"
        try:
            resp = self.session.get(url, headers={"User-Agent": PAN_UA}, timeout=10)
            html = resp.text
            match = re.search(r'bdstoken[\'":\s]+([0-9a-f]{32})', html)
            if match:
                self._bdstoken = match.group(1)
                logger.info(f"Successfully fetched bdstoken: {self._bdstoken[:4]}...")
                return self._bdstoken
            
            # Fallback check
            match_any = re.search(r'"bdstoken":"(.*?)"', html)
            if match_any:
                self._bdstoken = match_any.group(1)
                return self._bdstoken
        except Exception as e:
            logger.error(f"Failed to fetch bdstoken: {e}")
        
        return "null"

    def verify(self) -> Dict[str, Any]:
        """Verifies cookie validity and returns account capacity & nickname info."""
        # 1. Fetch Quota
        quota_url = "https://pcs.baidu.com/rest/2.0/pcs/quota"
        params = {
            "method": "info",
            "app_id": "778750"
        }
        
        quota_resp = self.session.get(quota_url, params=params, headers={"User-Agent": PCS_UA}, timeout=10)
        if quota_resp.status_code != 200:
            raise Exception(f"Baidu PCS Quota API returned status {quota_resp.status_code}")
            
        quota_data = quota_resp.json()
        if "error_code" in quota_data:
            raise Exception(f"PCS API Error: {quota_data.get('error_msg')} (Code: {quota_data.get('error_code')})")

        total = quota_data.get("quota", 0)
        used = quota_data.get("used", 0)

        # 2. Fetch Nickname (Try pan.baidu.com user info first)
        nickname = "百度网盘用户"
        try:
            info_url = "https://pan.baidu.com/api/user/getinfo"
            info_resp = self.session.get(info_url, params={"need_relation": "0"}, timeout=10)
            if info_resp.status_code == 200:
                info_data = info_resp.json()
                if info_data.get("errno") == 0 and info_data.get("records"):
                    nickname = info_data["records"][0].get("uname", nickname)
        except Exception as e:
            logger.warning(f"Failed to get nickname via getinfo: {e}. Using fallback.")

        return {
            "nickname": nickname,
            "quota_total": total,
            "quota_used": used
        }

    def access_share(self, share_url: str, password: Optional[str] = None) -> Dict[str, Any]:
        """Verifies the share password (extraction code) and injects verification cookies into session."""
        # Extract surl
        parsed = urllib.parse.urlparse(share_url)
        # Handle formats like https://pan.baidu.com/s/1xxxx or surl=xxxx
        surl = ""
        if "/s/1" in parsed.path:
            surl = parsed.path.split("/s/1")[-1]
        elif "/s/" in parsed.path:
            surl = parsed.path.split("/s/")[-1]
            if surl.startswith("1"):
                surl = surl[1:]
        
        query = urllib.parse.parse_qs(parsed.query)
        if not surl and "surl" in query:
            surl = query["surl"][0]

        if not surl:
            raise ValueError(f"Could not parse surl from share URL: {share_url}")

        init_url = f"https://pan.baidu.com/share/init?surl={surl}"
        
        # Use our clean, anonymous session for share page retrieval to prevent redirection loops
        # If there's a password, verify it in the anonymous session
        if password:
            verify_url = "https://pan.baidu.com/share/verify"
            params = {
                "surl": surl,
                "t": str(int(time.time() * 1000)),
                "channel": "chunlei",
                "web": "1",
                "bdstoken": "null",
                "clienttype": "0",
            }
            data = {
                "pwd": password,
                "vcode": "",
                "vcode_str": "",
            }
            headers = {
                "User-Agent": PAN_UA,
                "Referer": init_url,
                "X-Requested-With": "XMLHttpRequest"
            }
            resp = self.share_session.post(verify_url, params=params, data=data, headers=headers, timeout=10)
            res_json = resp.json()
            
            errno = res_json.get("errno", 0)
            if errno != 0:
                if errno in (-9, -62):
                    raise Exception("Extraction code requires verification code (Captcha), not supported in headless mode.")
                elif errno == -12:
                    raise Exception("Incorrect extraction code.")
                else:
                    raise Exception(f"Verify share code failed, error code: {errno}")
            
            # Update share session cookies with verify response cookies (contains randsk)
            self.share_session.cookies.update(resp.cookies)

        # Access share page to get share information (shareid, uk, bdstoken)
        headers = {
            "User-Agent": PAN_UA,
            "Referer": "https://pan.baidu.com/disk/home"
        }
        try:
            page_resp = self.share_session.get(share_url, headers=headers, timeout=15, allow_redirects=True)
        except requests.exceptions.TooManyRedirects:
            logger.warning("Share page request hit too many redirects, attempting without redirects.")
            page_resp = self.share_session.get(share_url, headers=headers, timeout=15, allow_redirects=False)
            
        # Copy all cookies (including randsk) to the main authenticated session for the transfer step
        self.session.cookies.update(self.share_session.cookies)
        
        html = page_resp.text
        if "链接不存在" in html or "分享已失效" in html:
            raise Exception("Share link has expired or is invalid.")

        # Extract yunData.setData(...) or locals.mset(...)
        match = re.search(r"(?:yunData.setData|locals.mset)\((.+?)\);", html, re.DOTALL)
        if not match:
            # Try alternate extraction for modern page formats
            # Look for shareid/uk in json strings inside HTML
            share_id_match = re.search(r'"shareid":(\d+)', html)
            uk_match = re.search(r'"uk":(\d+)', html)
            bdstoken_match = re.search(r'"bdstoken":"([0-9a-f]{32})"', html)
            
            if share_id_match and uk_match:
                share_id = int(share_id_match.group(1))
                uk = int(uk_match.group(1))
                bdstoken = bdstoken_match.group(1) if bdstoken_match else "null"
                
                # Try to find file list json
                file_list = []
                file_list_match = re.search(r'"file_list":(\[.*?\])', html)
                if file_list_match:
                    try:
                        file_list = json.loads(file_list_match.group(1))
                    except Exception:
                        pass
                
                return {
                    "share_id": share_id,
                    "uk": uk,
                    "bdstoken": bdstoken,
                    "file_list": file_list,
                    "surl": surl
                }
            raise Exception("Could not retrieve share information (shareid, uk) from the share page.")
            
        try:
            shared_data = json.loads(match.group(1).strip())
            
            # Extract list of files from page variables
            file_list = []
            if "file_list" in shared_data:
                file_list = shared_data["file_list"]
            elif "file_list" in shared_data.get("fileinfo", {}):
                file_list = shared_data["fileinfo"]["file_list"]
                
            return {
                "share_id": int(shared_data.get("shareid", 0)),
                "uk": int(shared_data.get("uk", 0)),
                "bdstoken": shared_data.get("bdstoken", "null"),
                "file_list": file_list,
                "surl": surl
            }
        except Exception as e:
            logger.error(f"Error parsing share json data: {e}")
            raise Exception(f"Failed to parse share page data: {e}")

    def list_shared_dir(self, share_url: str, share_id: int, uk: int, dir_path: str, page: int = 1, size: int = 100) -> List[Dict[str, Any]]:
        """Lists files inside a subfolder of a shared directory."""
        url = "https://pan.baidu.com/share/list"
        params = {
            "channel": "chunlei",
            "clienttype": "0",
            "web": "1",
            "page": str(page),
            "num": str(size),
            "dir": dir_path,
            "t": str(random.random()),
            "uk": str(uk),
            "shareid": str(share_id),
            "desc": "1",
            "order": "time",
            "bdstoken": "null",
            "showempty": "0",
        }
        
        headers = {
            "User-Agent": PAN_UA,
            "Referer": share_url,
            "X-Requested-With": "XMLHttpRequest"
        }
        resp = self.share_session.get(url, params=params, headers=headers, timeout=10)
        res_json = resp.json()
        
        errno = res_json.get("errno", 0)
        if errno != 0:
            raise Exception(f"List shared path failed, error code: {errno}")
            
        return res_json.get("list", [])

    def transfer(self, share_id: int, uk: int, bdstoken: str, share_url: str, fs_ids: List[int], target_dir: str) -> Dict[str, Any]:
        """Saves shared files into the specified directory of user's Netdisk."""
        # Ensure bdstoken is valid
        if not bdstoken or bdstoken == "null":
            bdstoken = self._get_bdstoken()
            
        url = "https://pan.baidu.com/share/transfer"
        params = {
            "shareid": str(share_id),
            "from": str(uk),
            "bdstoken": bdstoken,
            "channel": "chunlei",
            "clienttype": "0",
            "web": "1",
        }
        data = {
            "fsidlist": json.dumps(fs_ids),
            "path": target_dir,
        }
        headers = {
            "User-Agent": PAN_UA,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://pan.baidu.com",
            "Referer": share_url
        }
        
        resp = self.session.post(url, params=params, data=data, headers=headers, timeout=15)
        res_json = resp.json()
        
        # Standardizing output response
        # If response has a child 'info' list, check first entry's errno
        if res_json.get("info") and isinstance(res_json["info"], list) and len(res_json["info"]) > 0:
            first_err = res_json["info"][0].get("errno", 0)
            if first_err != 0:
                res_json["errno"] = first_err
                
        return res_json

    def _parse_pcs_response(self, res_json: Dict[str, Any]) -> Dict[str, Any]:
        """Standardizes PCS responses to include errno: 0 on success, or map error_code to errno."""
        if not isinstance(res_json, dict):
            return {"errno": -1, "error_msg": "Invalid response format"}
        if "error_code" in res_json:
            res_json["errno"] = res_json["error_code"]
        elif "errno" not in res_json:
            res_json["errno"] = 0
        return res_json

    def exists(self, remotepath: str) -> bool:
        """Checks if remote path exists in user's Netdisk."""
        url = "https://pcs.baidu.com/rest/2.0/pcs/file"
        params = {
            "method": "meta",
            "app_id": "778750",
            "path": remotepath
        }
        try:
            resp = self.session.post(url, params=params, headers={"User-Agent": PCS_UA}, timeout=10)
            res_json = self._parse_pcs_response(resp.json())
            return res_json["errno"] == 0
        except Exception:
            return False

    def makedir(self, directory: str) -> Dict[str, Any]:
        """Creates a directory in user's Netdisk."""
        url = "https://pcs.baidu.com/rest/2.0/pcs/file"
        params = {
            "method": "mkdir",
            "app_id": "778750",
            "path": directory
        }
        resp = self.session.post(url, params=params, headers={"User-Agent": PCS_UA}, timeout=10)
        return self._parse_pcs_response(resp.json())

    def rename(self, source: str, dest: str) -> Dict[str, Any]:
        """Renames or moves a file/directory in user's Netdisk."""
        url = "https://pcs.baidu.com/rest/2.0/pcs/file"
        params = {
            "method": "move",
            "app_id": "778750"
        }
        param_list = [{"from": source, "to": dest}]
        data = {
            "param": json.dumps({"list": param_list})
        }
        resp = self.session.post(url, params=params, data=data, headers={"User-Agent": PCS_UA}, timeout=10)
        return self._parse_pcs_response(resp.json())

    def remove(self, *remotepaths: str) -> Dict[str, Any]:
        """Deletes files or directories from user's Netdisk."""
        url = "https://pcs.baidu.com/rest/2.0/pcs/file"
        params = {
            "method": "delete",
            "app_id": "778750"
        }
        param_list = [{"path": p} for p in remotepaths]
        data = {
            "param": json.dumps({"list": param_list})
        }
        resp = self.session.post(url, params=params, data=data, headers={"User-Agent": PCS_UA}, timeout=10)
        return self._parse_pcs_response(resp.json())

    def list_dir(self, remotepath: str) -> List[Dict[str, Any]]:
        """Lists files and subdirectories within a Netdisk folder."""
        url = "https://pcs.baidu.com/rest/2.0/pcs/file"
        params = {
            "method": "list",
            "by": "name",
            "limit": "0-2147483647",
            "order": "asc",
            "path": remotepath,
            "app_id": "778750"
        }
        resp = self.session.get(url, params=params, headers={"User-Agent": PCS_UA}, timeout=15)
        res_json = resp.json()
        
        if "error_code" in res_json or "list" not in res_json:
            # Return empty list if folder does not exist or error occurs
            return []
            
        return res_json["list"]
