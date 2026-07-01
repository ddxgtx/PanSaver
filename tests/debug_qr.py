import requests
import json
import time

def debug_baidu_qr():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://passport.baidu.com/"
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    init_url = f"https://passport.baidu.com/v2/api/getqrcode?lp=pc&qrloginfrom=pc&tpl=netdisk&apiver=v3&tt={int(time.time()*1000)}"
    
    print(f"Requesting URL: {init_url}")
    try:
        res = session.get(init_url, timeout=10.0)
        print(f"Response status code: {res.status_code}")
        print(f"Response body: {res.text}")
        try:
            data = res.json()
            print("Successfully parsed as JSON:")
            print(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Failed to parse JSON: {e}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    debug_baidu_qr()
