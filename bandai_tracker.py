import sys
import os
import json
from datetime import datetime, timezone
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


def load_history():
    """讀取歷史紀錄 JSON，自動處理新舊格式相容性"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 舊格式相容（若原本純粹是 ID List）
                if isinstance(data, list):
                    items_dict = {pid: {"first_seen": "Legacy"} for pid in data}
                    return {"last_500_email_time": None, "items": items_dict}
                elif isinstance(data, dict):
                    if "items" not in data:
                        data["items"] = {}
                    return data
        except Exception as e:
            print(f"⚠️ 讀取歷史紀錄失敗，將重新初始化資料庫: {e}")
    
    return {"last_500_email_time": None, "items": {}}


def save_history(history):
    """寫入歷史紀錄 JSON"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def handle_error_alert(history, error_msg):
    """處理 500 / 阻擋 / 異常與 12 小時電郵冷卻機制"""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_display = now.strftime('%Y-%m-%d %H:%M:%S UTC')

    last_email_str = history.get("last_500_email_time")
    should_send_email = True

    if last_email_str:
        try:
            last_email_time = datetime.fromisoformat(last_email_str)
            hours_passed = (now - last_email_time).total_seconds() / 3600
            if hours_passed < 12:
                should_send_email = False
                print(f"⚠️ 偵測到伺服器異常 [{error_msg}]，但距離上次通知僅 {hours_passed:.1f} 小時（未滿 12 小時），跳過發送電郵。")
        except Exception as e:
            print(f"⚠️ 解析上次電郵時間失敗: {e}")

    if should_send_email:
        print(f"🚨 觸發 500/異常通知電郵 (記錄時間: {now_display})")
        alert_text = (
            f"⚠️ 【{REGION_NAME} 伺服器異常/阻擋通知】\n\n"
            f"檢查時間: {now_display}\n"
            f"目標網址: {URL}\n"
            f"異常細節: {error_msg}\n\n"
            f"請點擊上方網址檢查目標網站狀況或爬蟲環境配置。"
        )
        with open("mail_alert.txt", "w", encoding="utf-8") as f:
            f.write(alert_text)
        
        # 更新最後發送異常電郵的時間並儲存
        history["last_500_email_time"] = now_iso
        save_history(history)


def check_bandai_updates():
    # 確保每次執行前清理舊的 alert 檔
    if os.path.exists("mail_alert.txt"):
        os.remove("mail_alert.txt")

    history = load_history()
    current_ids = []
    now_display = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

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
            response = page.goto(URL, wait_until="networkidle", timeout=60000)

            # 判斷 HTTP 狀態碼是否為 500 等伺服器崩潰狀況
            if response and response.status >= 500:
                err_msg = f"HTTP Status {response.status}"
                print(f"❌ 伺服器回覆 {err_msg}！")
                page.screenshot(path=f"screenshot_{region}.png", full_page=True)
                handle_error_alert(history, err_msg)
                browser.close()
                return

            print("⏳ 開始動態輪詢檢測商品（每 5 秒檢查一次，最高限時 60 秒）...")
            product_items = []

            for attempt in range(1, 13):
                page_title = page.title()
                page_content = page.content()

                # 偵測 Access Denied / 403 / 500 內文
                if "Access Denied" in page_title or "403" in page_title or "PAGE NOT AVAILABLE" in page_content:
                    err_msg = f"網頁標題或內文顯示拒絕存取/崩潰 ('{page_title}')"
                    print(f"❌ 糟糕！{err_msg}")
                    page.screenshot(path=f"screenshot_{region}.png", full_page=True)
                    handle_error_alert(history, err_msg)
                    browser.close()
                    return

                soup = BeautifulSoup(page_content, 'html.parser')
                product_items = soup.find_all("div", {"data-id": "search-product-item", "class": "p-col__item"})

                if len(product_items) > 0:
                    print(f"✨ 第 {attempt} 次檢查成功！已成功偵測到商品載入（約耗時 {attempt * 5} 秒）。")
                    break

                if attempt < 12:
                    print(f"⏱️ 第 {attempt} 次檢查：網頁尚未長出商品，等待 5 秒後重新檢測...")
                    page.wait_for_timeout(5000)
                else:
                    print("🚨 已達到 60 秒最大等待極限，判定目前網頁上確實沒有商品。")
                    screenshot_path = f"screenshot_{region}.png"
                    page.screenshot(path=screenshot_path, full_page=True)
                    print(f"📸 已成功將當前網頁畫面截圖保存至: {screenshot_path}")

            for item in product_items:
                product_id = item.get("data-product-list-item")
                if product_id:
                    current_ids.append(product_id)

        except Exception as e:
            err_msg = f"瀏覽器自動化執行發生未預期錯誤: {e}"
            print(f"❌ {err_msg}")
            try:
                page.screenshot(path=f"screenshot_{region}.png", full_page=True)
            except Exception:
                pass
            handle_error_alert(history, err_msg)
            browser.close()
            return
        finally:
            browser.close()

    if not current_ids:
        print(f"ℹ️ 檢查完畢：目前 [{REGION_NAME}] 該分類查無任何商品（當前商品數為 0）。")
        save_history(history)
        return

    print(f"✅ 成功抓取商品！當前商品總數: {len(current_ids)}")

    old_items_dict = history.get("items", {})
    new_ids = [pid for pid in current_ids if pid not in old_items_dict]

    # 有新商品且並非第一次建檔時發送 Email 通知
    if new_ids and len(old_items_dict) > 0:
        alert_message = (
            f"您好，監控腳本偵測到 【{REGION_NAME}】 有新商品上架或狀態更新囉！\n\n"
            f"檢查時間: {now_display}\n"
            f"目標網址: {URL}\n\n"
            f"新變動的商品 ID 列表:\n" + "\n".join([f"- {pid}" for pid in new_ids]) +
            f"\n\n請點擊以上連結前往查看。"
        )
        print(f"🚨 偵測到新商品！正在產生 {REGION_NAME} 的 Email 通知內容...")
        with open("mail_alert.txt", "w", encoding="utf-8") as f:
            f.write(alert_message)
    else:
        print(f"▶ 比對完畢：[{REGION_NAME}] 沒有發現新的商品 ID 變化。")

    # 更新歷史商品清單並紀錄 timestamp
    for pid in current_ids:
        if pid not in history["items"]:
            history["items"][pid] = {
                "first_seen": now_display
            }

    save_history(history)
    print(f"💾 [{REGION_NAME}] 歷史紀錄資料庫 (帶時間戳) 已更新。")


if __name__ == "__main__":
    check_bandai_updates()
