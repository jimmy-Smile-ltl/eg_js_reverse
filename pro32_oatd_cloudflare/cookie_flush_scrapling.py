
import time
import requests
from util.tool import build_url_with_params
from scrapling.fetchers import StealthyFetcher,DynamicFetcher
class CookieFlush:
    """Ovid PDF 获取器，复用浏览器实例"""

    def __init__(self,port = 9223,headless= True):
        """初始化时启动浏览器"""
        self.fetcher = StealthyFetcher()
    # 目标 URL
        self.url = "https://oatd.org/oatd/search?q=%2A%3A%2A%20AND%20pub_dt%3A%5B1801-01-01T00%3A00%3A00Z%20TO%201802-01-01T00%3A00%3A00Z%5D"

    def flush(self, url, params={} , wait_sec=2, headless=True):
        success = False
        while not success:
            try:
                full_url = build_url_with_params(url, params)
                if not full_url:
                    full_url = self.url
                response = self.fetcher.fetch(
                    full_url,
                    headless=False,  # 开启有头模式，查看浏览器界面
                    network_idle=True,  # 等待网络请求稳定
                    solve_cloudflare=True
                )

                # DrissionPage 返回 cookies 列表，这里转成 dict
                cookies_list = list(response.cookies)  # list of dicts
                cookies_dict = {c.get('name'): c.get('value') for c in cookies_list if c.get('name')}
                success =  self.test_cookie(cookies_dict)
                print(f"cookie test :{ success }")

            except Exception as e:
                print(f"cookir flush error scrapling {str(e)}")
        return cookies_dict


    def test_cookie(self,cookies_dict):
        start_time = time.time()
        cookies = {
            # "__utmc": "EXAMPLE_EXPIRED_ANALYTICS",
            # "__utmz": "EXAMPLE_EXPIRED_ANALYTICS",
            # "_pk_id.4.c2fb": "EXAMPLE_EXPIRED_ANALYTICS",
            # "__utma": "EXAMPLE_EXPIRED_ANALYTICS",
            # "cf_clearance": "EXAMPLE_EXPIRED_CF_CLEARANCE"
        }
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en,en-CN;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "cache-control": "max-age=0",
            "priority": "u=0, i",
            "sec-ch-ua": "\"Google Chrome\";v=\"147\", \"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"147\"",
            "sec-ch-ua-arch": "\"x86\"",
            "sec-ch-ua-bitness": "\"64\"",
            "sec-ch-ua-full-version": "\"147.0.7727.55\"",
            "sec-ch-ua-full-version-list": "\"Google Chrome\";v=\"147.0.7727.55\", \"Not.A/Brand\";v=\"8.0.0.0\", \"Chromium\";v=\"147.0.7727.55\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-model": "\"\"",
            "sec-ch-ua-platform": "\"Linux\"",
            "sec-ch-ua-platform-version": "\"\"",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
        }
        url = "https://oatd.org/oatd/search"
        params = {
            "q": "*:* AND pub_dt:[1800-01-01T00:00:00Z TO 1801-01-01T00:00:00Z]"
        }
        if cookies_dict:
            cookies.update(cookies_dict)
            for retry in range(3):
                try:
                    response = requests.get(url, headers=headers, cookies=cookies, params=params,timeout=5)
                    if response and response.status_code == 200:
                        end_time = time.time()
                        print(f"success  when retry = {retry}  耗时 {end_time - start_time:.4f}s")
                        return True
                except Exception as e:
                    print(f"error timeout retry {retry}，{str(e)}")
                    time.sleep(5)
            else:
                return False
        return False

    def close(self):
        """关闭浏览器"""
        print("\n关闭浏览器...")
        self.page.close()
        print("浏览器已关闭")

if __name__ == "__main__":
    import requests
    cookies_flusher = CookieFlush(headless=False,port=9995)
    flush_url = "https://oatd.org/oatd/search?q=%2A%3A%2A%20AND%20pub_dt%3A%5B1801-01-01T00%3A00%3A00Z%20TO%201802-01-01T00%3A00%3A00Z%5D"
    cookies_dict = cookies_flusher.flush(flush_url)
    print("获取到的 cookies：", cookies_dict)
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en,en-CN;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "cache-control": "max-age=0",
        "priority": "u=0, i",
        "sec-ch-ua": "\"Google Chrome\";v=\"147\", \"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"147\"",
        "sec-ch-ua-arch": "\"x86\"",
        "sec-ch-ua-bitness": "\"64\"",
        "sec-ch-ua-full-version": "\"147.0.7727.55\"",
        "sec-ch-ua-full-version-list": "\"Google Chrome\";v=\"147.0.7727.55\", \"Not.A/Brand\";v=\"8.0.0.0\", \"Chromium\";v=\"147.0.7727.55\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"Linux\"",
        "sec-ch-ua-platform-version": "\"\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    }
    url = "https://oatd.org/oatd/search"
    params = {
        "q": "*:* AND pub_dt:[1800-01-01T00:00:00Z TO 1801-01-01T00:00:00Z]"
    }
    if cookies_dict:
        for retry in range(10):
            response = requests.get(url, headers=headers, cookies=cookies_dict, params=params)
            # print(response.text)
            print(retry ,response.status_code)
            time.sleep(retry)


