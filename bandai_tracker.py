import sys
import os
import json
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# 從命令列參數獲取區域（hk 或 us），預設為 hk
region = sys.argv[1].lower() if len(sys.argv) > 1 else "hk"

if region == "us":
    URL = "https://p-bandai.com/us/search?offset=0&limit=20&sortType=NewArrival&_f_categories=04-011&_f_productStatuses=Waiting,On,End"
    REGION_NAME = "US Premium Bandai"
    HISTORY_FILE = "pb_us_history.json"
else:
    URL = "https://p-bandai.com/hk/search?_lc=zh-HK&offset=0&limit=20&sortType=Relevance&_f_productStatuses=Waiting,On,End&_f_categories=04-011"
    REGION_NAME = "HK Premium Bandai"
    HISTORY_FILE = "pb_hk_history.json"

def check_bandai_updates():
    current_ids = []
    
    with sync_playwright() as p:
        print(f"🚀 正在啟動雲端瀏覽器，準備檢查 [{REGION_NAME}]...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        try:
            print(f"🌐 正在前往網址: {URL}")
            page.goto(URL, wait_until="networkidle", timeout=60000)
            
            print("⏳ 開始動態輪詢檢測商品（每 5 秒檢查一次，最高限時 60 秒）...")
            product_items = []
            
            for attempt in range(1, 13):
                page_title = page.title()
                
                if "Access Denied" in page_title or "403" in page_title:
                    print(f"❌ 糟糕！偵測到網頁標題為 '{page_title}'，已被防爬蟲系統阻擋！")
                    # 被阻擋時也立刻拍下一張照片留存
                    page.screenshot(path=f"screenshot_{region}.png", full_page=True)
                    browser.close()
                    return
                
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                product_items = soup.find_all("div", {"data-id": "search-product-item", "class": "p-col__item"})
                
                if len(product_items) > 0:
                    print(f"✨ 第 {attempt} 次檢查成功！已成功偵測到商品載入（約耗時 {attempt * 5} 秒）。")
                    break
                
                if attempt < 12:
                    print(f"⏱️ 第 {attempt} 次檢查：網頁尚未長出商品，等待 5 秒後重新檢測...")
                    page.wait_for_timeout(5000)
                else:
                    print("🚨 已達到 60 秒最大等待極限，判定目前網頁上確實沒有商品。")
                    # 💡 聽從建議：滿一分鐘仍為 0 時，強制拍下整頁長截圖
                    screenshot_path = f"screenshot_{region}.png"
                    page.screenshot(path=screenshot_path, full_page=True)
                    print(f"📸 已成功將當前網頁畫面截圖保存至: {screenshot_path}")
            
            for item in product_items:
                product_id = item.get("data-product-list-item")
                if product_id:
                    current_ids.append(product_id)
                    
        except Exception as e:
            print(f"❌ 瀏覽器自動化執行發生錯誤: {e}")
            # 發生未預期崩潰時也順便截圖，方便定位錯誤
            try:
                page.screenshot(path=f"screenshot_{region}.png", full_page=True)
            except:
                pass
        finally:
            browser.close()

    if not current_ids:
        print(f"ℹ️ 檢查完畢：目前 [{REGION_NAME}] 該分類查無任何商品（當前商品數為 0）。")
        if not os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "w") as f:
                json.dump([], f)
        return

    print(f"✅ 成功抓取商品！當前商品總數: {len(current_ids)}")

    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            old_ids = json.load(f)
    else:
        old_ids = []

    new_ids = [pid for pid in current_ids if pid not in old_ids]
    
    if new_ids and old_ids:
        alert_message = (
            f"您好，監控腳本偵測到 【{REGION_NAME}】 有新商品上架或狀態更新囉！\n\n"
            f"新變動的商品 ID 列表:\n" + "\n".join([f"- {pid}" for pid in new_ids]) + 
            f"\n\n請點擊以下連結前往查看：\n{URL}"
        )
        print(f"🚨 偵測到新商品！正在產生 {REGION_NAME} 的 Email 通知內容...")
        with open("mail_alert.txt", "w", encoding="utf-8") as f:
            f.write(alert_message)
    else:
        print(f"▶ 比對完畢：對比昨天，[{REGION_NAME}] 沒有發現新的商品 ID 變化。")

    with open(HISTORY_FILE, "w") as f:
        json.dump(current_ids, f)
        print(f"💾 [{REGION_NAME}] 歷史紀錄資料庫已更新。")

if __name__ == "__main__":
    check_bandai_updates()