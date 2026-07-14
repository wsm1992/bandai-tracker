import os
import json
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

URL = "https://p-bandai.com/hk/search?_lc=zh-HK&offset=0&limit=20&sortType=Relevance&_f_productStatuses=Waiting,On&_f_categories=04-011"
HISTORY_FILE = "pb_product_history.json"

def check_bandai_updates():
    current_ids = []
    
    # 啟動 Playwright 真實瀏覽器模擬
    with sync_playwright() as p:
        print("🚀 正在啟動雲端瀏覽器...")
        browser = p.chromium.launch(headless=True)
        
        # 偽裝成一般的 Mac 桌面瀏覽器環境
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        try:
            print("🌐 正在前往 Premium Bandai 網頁...")
            page.goto(URL, wait_until="networkidle", timeout=60000)
            
            # 關鍵步驟：強制等待畫面上出現你指定的商品元件，最多等 15 秒
            print("⏳ 等待商品列表動態載入...")
            page.wait_for_selector('div[data-id="search-product-item"]', timeout=15000)
            
            # 抓取瀏覽器渲染完成後的完整 HTML
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            product_items = soup.find_all("div", {"data-id": "search-product-item", "class": "p-col__item"})
            
            for item in product_items:
                product_id = item.get("data-product-list-item")
                if product_id:
                    current_ids.append(product_id)
                    
        except Exception as e:
            print(f"❌ 瀏覽器自動化執行發生錯誤: {e}")
        finally:
            browser.close()

    # 判斷是否成功抓到資料
    if not current_ids:
        print("⚠️ 仍未抓取到任何商品 ID，可能被強力的防爬蟲機制拒絕，或網頁結構有重大變更。")
        return

    print(f"✅ 成功抓取到商品！當前商品總數: {len(current_ids)}")

    # 讀取昨天的紀錄進行比對
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            old_ids = json.load(f)
    else:
        old_ids = []

    # 找出新商品 ID
    new_ids = [pid for pid in current_ids if pid not in old_ids]
    
    if new_ids and old_ids:
        alert_message = (
            f"您好，監控腳本偵測到 Premium Bandai 有新商品上架囉！\n\n"
            f"新商品 ID 列表:\n" + "\n".join([f"- {pid}" for pid in new_ids]) + 
            f"\n\n請點擊以下連結前往查看：\n{URL}"
        )
        print("🚨 偵測到新商品！正在產生 Email 通知內容...")
        with open("mail_alert.txt", "w", encoding="utf-8") as f:
            f.write(alert_message)
    else:
        print("▶ 比對完畢：對比昨天，沒有發現新的商品 ID。")

    # 更新歷史紀錄，供明天比對
    with open(HISTORY_FILE, "w") as f:
        json.dump(current_ids, f)
        print("💾 歷史紀錄資料庫已更新。")

if __name__ == "__main__":
    check_bandai_updates()