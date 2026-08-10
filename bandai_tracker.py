import sys
import os
import json
import time
import random
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

TZ_LOCAL = timezone(timedelta(hours=8))

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
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    items_dict = {pid: {"first_seen": "Legacy"} for pid in data}
                    return {"last_500_email_time": None, "last_success_time": None, "items": items_dict}
                elif isinstance(data, dict):
                    if "items" not in data:
                        data["items"] = {}
                    if "last_success_time" not in data:
                        data["last_success_time"] = None
                    return data
        except Exception as e:
            print(f"⚠️ 讀取歷史紀錄失敗: {e}")
    return {"last_500_email_time": None, "last_success_time": None, "items": {}}


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def handle_error_alert(history, error_msg):
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_display = datetime.now(TZ_LOCAL).strftime('%Y-%m-%d %H:%M:%S (UTC+8)')

    last_email_str = history.get("last_500_email_time")
    should_send_email = True

    if last_email_str:
        try:
            last_email_time = datetime.fromisoformat(last_email_str)
            hours_passed = (now - last_email_time).total_seconds() / 3600
            if hours_passed < 12:
                should_send_email = False
                print(f"⚠️ 偵測到伺服器異常 [{error_msg}]，冷卻時間未滿 12 小時，跳過發信。")
        except Exception as e:
            print(f"⚠️ 解析時間失敗: {e}")

    if should_send_email:
        print(f"🚨 觸發異常通知電郵 (時間: {now_display})")
        alert_text = (
            f"⚠️ 【{REGION_NAME} 伺服器異常/阻擋通知】\n\n"
            f"檢查時間: {now_display}\n"
            f"目標網址: {URL}\n"
            f"異常細節: {error_msg}\n\n"
            f"請點擊上方網址檢查網站狀況。"
        )
        with open("mail_alert.txt", "w", encoding="utf-8") as f:
            f.write(alert_text)
        
        history["last_500_email_time"] = now_iso
        save_history(history)


def check_bandai_updates():
    if os.path.exists("mail_alert.txt"):
        os.remove("mail_alert.txt")

    history = load_history()
    current_ids = []
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now(TZ_LOCAL)
    now_display = now_local.strftime('%Y-%m-%d %H:%M:%S (UTC+8)')

    # 隨機延遲 1~5 秒，避免定時發起請求過於僵硬
    time.sleep(random.uniform(1.0, 5.0))

    MAX_RETRIES = 3  # 最多重試 3 次
    last_error_reason = ""

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
            timezone_id="Asia/Macau" if region == "hk" else "America/New_York",
            extra_http_headers={
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
        )

        # 💡 隱藏 navigator.webdriver 標記
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = context.new_page()

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"🌐 嘗試連線目標網址 (第 {attempt}/{MAX_RETRIES} 次): {URL}")
            try:
                response = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
                
                # 檢查 HTTP 狀態碼
                if response and response.status >= 500:
                    last_error_reason = f"HTTP Status {response.status}"
                    print(f"⚠️ 伺服器回覆 {last_error_reason}，等待 15 秒後重試...")
                    time.sleep(15)
                    continue

                # 檢查內容是否被反爬阻擋
                page_title = page.title()
                page_content = page.content()
                if "Access Denied" in page_title or "403" in page_title or "PAGE NOT AVAILABLE" in page_content:
                    last_error_reason = f"網頁顯示 Access Denied/403/崩潰 ('{page_title}')"
                    print(f"⚠️ 偵測到阻擋特徵: {last_error_reason}，等待 20 秒後重試...")
                    time.sleep(20)
                    continue

                # 輪詢檢測商品 (最長等 30 秒)
                product_items = []
                for poll in range(1, 7):
                    soup = BeautifulSoup(page.content(), 'html.parser')
                    product_items = soup.find_all("div", {"data-id": "search-product-item", "class": "p-col__item"})
                    if len(product_items) > 0:
                        break
                    page.wait_for_timeout(5000)

                for item in product_items:
                    product_id = item.get("data-product-list-item")
                    if product_id:
                        current_ids.append(product_id)

                # 順利完成爬取（無論是否有商品都代表連線成功）
                last_error_reason = ""
                break

            except Exception as e:
                last_error_reason = f"連線或載入超時: {e}"
                print(f"⚠️ 第 {attempt} 次嘗試失敗: {last_error_reason}")
                if attempt < MAX_RETRIES:
                    time.sleep(15)

        if last_error_reason:
            print(f"❌ 已耗盡 {MAX_RETRIES} 次重試機會，確定遭遇異常。")
            try:
                page.screenshot(path=f"screenshot_{region}.png", full_page=True)
            except Exception:
                pass
            handle_error_alert(history, last_error_reason)
            browser.close()
            return

        browser.close()

    # ==========================================
    # 邏輯判斷：無商品時的定時健康檢查 (保底機制)
    # ==========================================
    if not current_ids:
        print(f"ℹ️ 檢查完畢：目前 [{REGION_NAME}] 該分類查無任何商品（當前商品數為 0）。")
        current_hour = now_local.hour
        
        is_hk_check_window = (region == "hk" and current_hour == 14)
        is_us_check_window = (region == "us" and current_hour == 6)

        if is_hk_check_window or is_us_check_window:
            had_recent_success = False
            last_success_str = history.get("last_success_time")

            if last_success_str:
                try:
                    last_success_dt = datetime.fromisoformat(last_success_str)
                    hours_diff = (now_utc - last_success_dt).total_seconds() / 3600
                    max_allowed_hours = 3.5 if region == "hk" else 4.5
                    if hours_diff <= max_allowed_hours:
                        had_recent_success = True
                except Exception as e:
                    print(f"⚠️ 解析時間失敗: {e}")

            if not had_recent_success:
                window_desc = "12:00~15:00" if region == "hk" else "03:00~07:00"
                err_msg = f"【定時健康檢查失敗】在 {window_desc} 時段內均未能成功抓取到商品！"
                print(f"❌ {err_msg}")
                handle_error_alert(history, err_msg)
            else:
                save_history(history)
        else:
            save_history(history)
        return

    # 成功抓取商品
    print(f"✅ 成功抓取商品！當前商品總數: {len(current_ids)}")
    history["last_success_time"] = now_utc.isoformat()

    old_items_dict = history.get("items", {})
    new_ids = [pid for pid in current_ids if pid not in old_items_dict]

    if new_ids and len(old_items_dict) > 0:
        alert_message = (
            f"您好，監控腳本偵測到 【{REGION_NAME}】 有新商品上架或狀態更新囉！\n\n"
            f"檢查時間: {now_display}\n"
            f"目標網址: {URL}\n\n"
            f"新變動的商品 ID 列表:\n" + "\n".join([f"- {pid}" for pid in new_ids]) +
            f"\n\n請點擊以上連結前往查看。"
        )
        print(f"🚨 偵測到新商品！正在產生通知內容...")
        with open("mail_alert.txt", "w", encoding="utf-8") as f:
            f.write(alert_message)

    for pid in current_ids:
        if pid not in history["items"]:
            history["items"][pid] = {"first_seen": now_display}

    save_history(history)
    print(f"💾 [{REGION_NAME}] 歷史紀錄資料庫已更新。")


if __name__ == "__main__":
    check_bandai_updates()
