import sys
import os
import json
import time
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
            page_loaded_successfully = False
            for retry in range(1, 6):
                print(f"🌐 正在前往網址 (第 {retry}/5 次嘗試): {URL}")
                page.goto(URL, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(3000)
                
                page_title = page.title()
                html_content = page.content()
                
                # 檢查是否撞到 500 牆
                if "500" in page_title or "PAGE NOT AVAILABLE" in page_title or "無法顯示網頁" in html_content or "Access Denied" in page_title:
                    print(f"⚠️ 警告：偵測到萬代返回錯誤頁面 (500/阻擋)！")
                    if retry < 5:
                        print("⏳ 觸發防爬蟲保護，讓伺服器冷卻 30 秒後重新整理...")
                        page.wait_for_timeout(30000)
                        continue
                    else:
                        print("❌ 已經連續重試 5 次依然返回 500 錯誤，判定本次任務被徹底阻擋。")
                        page.screenshot(path=f"screenshot_{region}.png", full_page=True)
                        browser.close()
                        return
                else:
                    page_loaded_successfully = True
                    break
            
            if not page_loaded_successfully:
                browser.close()
                return

            print("⏳ 網頁載入成功！開始動態輪詢檢測商品...")
            product_items = []
            
            for attempt in range(1, 13):
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                product_items = soup.find_all("div", {"data-id": "search-product-item", "class": "p-col__item"})
                
                if len(product_items) > 0:
                    print(f"✨ 第 {attempt} 次檢查成功！已成功偵測到商品載入。")
                    break
                
                if attempt < 12:
                    print(f"⏱️ 第 {attempt} 次檢查：商品尚未渲染完成，等待 5 秒...")
                    page.wait_for_timeout(5000)
                else:
                    print("🚨 已達到 60 秒最大等待極限，畫面上依然沒有商品。")
                    page.screenshot(path=f"screenshot_{region}.png", full_page=True)
            
            # 提取商品 ID
            for item in product_items:
                product_id = item.get("data-product-list-item")
                if product_id:
                    current_ids.append(product_id)
                    
        except Exception as e:
            print(f"❌ 瀏覽器自動化執行發生錯誤: {e}")
            try:
                page.screenshot(path=f"screenshot_{region}.png", full_page=True)
            except:
                pass
        finally:
            browser.close()

    # 💡 測試修改 1：如果商品數量為 0（不論是沒商品還是撞牆阻擋），也強制發送 Email
    if not current_ids:
        print(f"ℹ️ 檢查完畢：當前商品數為 0。強制產生 Email 通知以供測試...")
        alert_message = (
            f"⚠️【{REGION_NAME} 監控報告 - 商品數為 0】\n\n"
            f"您好，腳本已成功執行完畢，但本次抓取到的商品數量為 0。\n"
            f"這代表目前該分類可能真的沒有商品，或者依然被伺服器阻擋。\n\n"
            f"請至 GitHub Actions 下載 Artifacts 截圖進行確認。\n"
            f"前往確認網址：\n{URL}"
        )
        with open("mail_alert.txt", "w", encoding="utf-8") as f:
            f.write(alert_message)
            
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
    
    # 💡 測試修改 2：不論是否有變更，都強制發送 Email
    if new_ids and old_ids:
        alert_message = (
            f"🚨【{REGION_NAME} 監控報告 - 偵測到新商品！】\n\n"
            f"新變動的商品 ID 列表:\n" + "\n".join([f"- {pid}" for pid in new_ids]) + 
            f"\n\n請點擊以下連結前往查看：\n{URL}"
        )
        print(f"🚨 偵測到新商品！已產生 Email 通知內容。")
    else:
        # 當商品沒有變化時的測試報告內容
        status_desc = "這是首次執行，已建立初始資料庫。" if not old_ids else "商品列表與上一次相比沒有變化。"
        alert_message = (
            f"📧【{REGION_NAME} 監控報告 - 定時無變更回報】\n\n"
            f"您好！監控腳本正在雲端健康運行中。\n\n"
            f"【本次檢查結果】\n"
            f"● 變更狀態：{status_desc}\n"
            f"● 當前商品總數：{len(current_ids)} 件\n\n"
            f"請點擊以下連結前往查看：\n{URL}"
        )
        print(f"📧 [測試模式] 商品無變更，但依然產生 Email 通知以供測試...")

    # 寫入 mail_alert.txt，強制觸發 GitHub Actions 的寄信步驟
    with open("mail_alert.txt", "w", encoding="utf-8") as f:
        f.write(alert_message)

    with open(HISTORY_FILE, "w") as f:
        json.dump(current_ids, f)
        print(f"💾 [{REGION_NAME}] 歷史紀錄資料庫已更新。")

if __name__ == "__main__":
    check_bandai_updates()
