import time
import random
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def fetch_bandai_data(region):
    """純淨版爬蟲：負責抓取 ID 與名稱，直接回傳字典結果"""
    if region == "us":
        URL = "https://p-bandai.com/us/search?offset=0&limit=20&sortType=NewArrival&_f_categories=04-011&_f_productStatuses=Waiting,On,End"
        REGION_NAME = "US Premium Bandai"
    else:
        URL = "https://p-bandai.com/hk/search?_lc=zh-HK&offset=0&limit=20&sortType=Relevance&_f_productStatuses=Waiting,On,End&_f_categories=04-011"
        REGION_NAME = "HK Premium Bandai"

    time.sleep(random.uniform(1.0, 5.0))
    MAX_RETRIES = 3
    last_error_reason = ""
    crawled_dict = {}  # 改用字典直接儲存爬到的詳細數據

    with sync_playwright() as p:
        print(f"🚀 啟動擬真雲端瀏覽器 [{REGION_NAME}]...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="zh-TW" if region == "hk" else "en-US",
            timezone_id="Asia/Macau" if region == "hk" else "America/New_York"
        )

        context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = context.new_page()

        for attempt in range(1, MAX_RETRIES + 1):
            crawled_dict = {}
            print(f"🌐 嘗試連線目標網址 (第 {attempt}/{MAX_RETRIES} 次): {URL}")
            try:
                response = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
                
                if response and response.status >= 500:
                    last_error_reason = f"HTTP Status {response.status}"
                    if attempt < MAX_RETRIES: time.sleep(15)
                    continue

                page_title = page.title()
                page_content = page.content()
                if "Access Denied" in page_title or "403" in page_title or "PAGE NOT AVAILABLE" in page_content:
                    last_error_reason = f"網頁顯示阻擋特徵 ('{page_title}')"
                    if attempt < MAX_RETRIES: time.sleep(20)
                    continue

                product_items = []
                for poll in range(1, 7):
                    soup = BeautifulSoup(page.content(), 'html.parser')
                    product_items = soup.find_all("div", {"data-id": "search-product-item", "class": "p-col__item"})
                    if len(product_items) > 0:
                        break
                    page.wait_for_timeout(5000)

                # 💡 核心修改：同時抓取 ID 和 Title
                for item in product_items:
                    pid = item.get("data-product-list-item")
                    if pid:
                        # 尋找 <p class="c-product__title">
                        title_elem = item.find("p", class_="c-product__title")
                        title = title_elem.text.strip() if title_elem else "未命名商品"
                        # 寫入字典
                        crawled_dict[pid] = {"id": pid, "title": title}

                if len(crawled_dict) == 0:
                    last_error_reason = "網頁載入成功但未抓取到任何商品 (0 件)"
                    if attempt < MAX_RETRIES:
                        time.sleep(60)
                        continue

                last_error_reason = ""
                break

            except Exception as e:
                last_error_reason = f"連線或載入超時: {e}"
                if attempt < MAX_RETRIES: time.sleep(15)

        if last_error_reason:
            try: page.screenshot(path=f"screenshot_{region}.png", full_page=True)
            except: pass
            browser.close()
            return {"status": "error", "message": last_error_reason, "url": URL}

        browser.close()

    if not crawled_dict:
        return {"status": "empty", "message": "查無任何商品", "url": URL}

    print(f"✅ 成功抓取商品！當前商品總數: {len(crawled_dict)}")
    
    # 已經是字典格式，直接回傳
    return {"status": "success", "data": crawled_dict, "url": URL}