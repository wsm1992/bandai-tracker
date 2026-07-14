import requests
from bs4 import BeautifulSoup
import os
import json

# 你指定的 Premium Bandai 搜尋網址
URL = "https://p-bandai.com/hk/search?_lc=zh-HK&offset=0&limit=20&sortType=Relevance&_f_productStatuses=Waiting,On&_f_categories=04-011"

# 模擬瀏覽器標頭，避免被萬代網站封鎖
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-HK,zh;q=0.9"
}

HISTORY_FILE = "pb_product_history.json"
# 這裡可以換成你的 Discord Webhook 網址，或者 Telegram Bot Token
NOTIFY_WEBHOOK_URL = os.environ.get("NOTIFY_WEBHOOK")

def check_bandai_updates():
    # 1. 抓取網頁內容
    response = requests.get(URL, headers=HEADERS)
    if response.status_code != 200:
        print(f"網頁抓取失敗，狀態碼: {response.status_code}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 2. 根據你提供的結構，找出所有商品節點
    product_items = soup.find_all("div", {"data-id": "search-product-item", "class": "p-col__item"})
    
    # 3. 提取當前的商品 ID 列表
    current_ids = []
    for item in product_items:
        product_id = item.get("data-product-list-item")
        if product_id:
            current_ids.append(product_id)
            
    if not current_ids:
        print("警告：未抓取到任何商品 ID，可能是網頁結構改變或觸發防爬蟲機制。")
        return

    # 4. 讀取昨天的紀錄進行比對
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            old_ids = json.load(f)
    else:
        old_ids = []

    # 5. 找出「今天有，但昨天沒有」的新商品 ID
    new_ids = [pid for pid in current_ids if pid not in old_ids]
    
    # 6. 如果有新商品，發送通知
    if new_ids and old_ids:  # 確保不是第一次執行
        alert_message = f"🚨 【Premium Bandai 通知】發現新商品上架！\n新商品 ID: {', '.join(new_ids)}\n前往查看: {URL}"
        print(alert_message)
        
        if NOTIFY_WEBHOOK_URL:
            # 以 Discord Webhook 為例發送通知
            requests.post(NOTIFY_WEBHOOK_URL, json={"content": alert_message})
    else:
        print(f"檢查完畢：對比昨天，沒有發現新的商品 ID。目前上架商品數: {len(current_ids)}")

    # 7. 更新歷史紀錄，供明天比對
    with open(HISTORY_FILE, "w") as f:
        json.dump(current_ids, f)

if __name__ == "__main__":
    check_bandai_updates()