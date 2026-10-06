import sys
import os
import json
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta

# ================= 💡 1. 新增：自動限制 Log 檔案大小 (自動瘦身) =================
def trim_log_file():
    try:
        region_arg = sys.argv[1].lower() if len(sys.argv) > 1 else "hk"
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(base_dir, "log")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"cron_{region_arg}.log")
        
        max_size = 3 * 1024 * 1024  # 當檔案大於 3MB 時觸發清理
        keep_size = 1 * 1024 * 1024 # 觸發後，只保留最新的 1MB 歷史紀錄

        if os.path.exists(log_path) and os.path.getsize(log_path) > max_size:
            with open(log_path, 'rb') as f:
                f.seek(-keep_size, os.SEEK_END)
                tail_data = f.read()
            
            # 尋找第一個換行符號，避免第一行的字被切斷一半
            first_newline = tail_data.find(b'\n')
            if first_newline != -1:
                tail_data = tail_data[first_newline + 1:]
                
            # 原地覆蓋（保持 cron 的附加寫入特性不中斷）
            with open(log_path, 'wb') as f:
                f.write(b"=== [Log Truncated by System - Retaining latest 1MB] ===\n" + tail_data)
    except Exception:
        pass # 失敗也直接跳過，絕不影響爬蟲主程式運行

# 在程式開始輸出任何文字前，先執行瘦身
trim_log_file()
# =========================================================================

# ================= 💡 2. 新增：自動為所有輸出加上 UTC+8 時間戳 =================
class UTC8LogWrapper:
    def __init__(self, stream):
        self.stream = stream
        self.tz_utc8 = timezone(timedelta(hours=8))
        self.needs_prefix = True

    def write(self, text):
        if not text: 
            return
        # 逐行檢查，並在每行開頭插入時間戳記
        for line in text.splitlines(True):
            if self.needs_prefix and line.strip():
                now = datetime.now(self.tz_utc8).strftime('[%Y-%m-%d %H:%M:%S]')
                self.stream.write(f"{now} ")
            self.stream.write(line)
            self.needs_prefix = line.endswith('\n')

    def flush(self):
        self.stream.flush()

# 全局替換系統的標準輸出 (stdout) 與錯誤輸出 (stderr)
sys.stdout = UTC8LogWrapper(sys.stdout)
sys.stderr = UTC8LogWrapper(sys.stderr)
# =========================================================================
# 核心：直接把爬蟲當成模組載入，不透過檔案傳遞！
from bandai_tracker import fetch_bandai_data

# ================= 郵件設定 =================
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 465,                 
    "sender_email": "wongsiuming1992@gmail.com", 
    "sender_password": "dmtfveeytymslars",    
    "receiver_email": "wsm1992@hotmail.com"
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "bandai_tracker.db")

def init_db():
    """初始化 SQLite 資料庫，建立獨立的香港與美國資料表，並包含 product_name"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 建立香港專屬資料表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products_hk (
            product_id TEXT PRIMARY KEY,
            product_name TEXT,
            data_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 建立美國專屬資料表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products_us (
            product_id TEXT PRIMARY KEY,
            product_name TEXT,
            data_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 【自動升級邏輯】如果資料表已經存在且沒有 product_name 欄位，自動補上
    try:
        cursor.execute("ALTER TABLE products_hk ADD COLUMN product_name TEXT")
    except sqlite3.OperationalError:
        pass # 欄位已存在則忽略

    try:
        cursor.execute("ALTER TABLE products_us ADD COLUMN product_name TEXT")
    except sqlite3.OperationalError:
        pass # 欄位已存在則忽略
    
    conn.commit()
    conn.close()

def send_email_alert(subject, content):
    """使用 SMTP_SSL 發送 Email 通知"""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_CONFIG["sender_email"]
        msg["To"] = EMAIL_CONFIG["receiver_email"]
        msg["Subject"] = subject
        msg.attach(MIMEText(content, "plain", "utf-8"))

        with smtplib.SMTP_SSL(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
            server.ehlo()
            server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
            server.sendmail(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["receiver_email"], msg.as_string())
            
        print("[通知] Email 警報信件已成功發送！")
    except Exception as e:
        print(f"Email 發送失敗: {e}")

def process_region(region_arg, region_name):
    table_name = f"products_{region_arg}"

    print(f"🚀 正在呼叫爬蟲抓取【{region_name}】數據...")
    result = fetch_bandai_data(region_arg)

    if result["status"] == "error":
        print(f"❌ 爬蟲遭遇錯誤：{result['message']}")
        send_email_alert(
            f"⚠️ 【Bandai 異常】{region_name} 伺服器阻擋或異常", 
            f"目標網址: {result.get('url')}\n異常細節: {result['message']}"
        )
        return
    elif result["status"] == "empty":
        print(f"ℹ️ {region_name} 目前查無任何商品。")
        return

    crawled_dict = result["data"]

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 讀取對應地區的 SQLite 歷史紀錄
    cursor.execute(f"SELECT product_id, data_json FROM {table_name}")
    db_records = {row[0]: json.loads(row[1]) for row in cursor.fetchall()}

    changes = []
    is_first_run = (len(db_records) == 0)

    # 比對邏輯：在 Email 訊息中加入商品名稱
    if is_first_run:
        print(f"【{region_name}】`{table_name}` 資料表為空（首次運行），將這 {len(crawled_dict)} 個商品視為新上架...")
        for prod_id, item_data in crawled_dict.items():
            title = item_data.get("title", "未命名商品")
            changes.append(f"➕ 【新上架】 {title}\n    (ID: {prod_id})")
    else:
        for prod_id, item_data in crawled_dict.items():
            if prod_id not in db_records:
                title = item_data.get("title", "未命名商品")
                changes.append(f"➕ 【新上架】 {title}\n    (ID: {prod_id})")

    tz_utc8 = timezone(timedelta(hours=8))
    now_utc8 = datetime.now(tz_utc8).strftime('%Y-%m-%d %H:%M:%S')

    # 更新 SQLite 資料表（包含獨立寫入 product_name 欄位與 UTC+8 updated_at）
    for prod_id, new_item in crawled_dict.items():
        product_name = new_item.get("title", "未命名商品")
        cursor.execute(f"""
            INSERT INTO {table_name} (product_id, product_name, data_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                product_name = excluded.product_name,
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
        """, (prod_id, product_name, json.dumps(new_item, ensure_ascii=False), now_utc8))
    
    conn.commit()
    conn.close()
    print(f"[成功] 【{region_name}】數據已同步更新至 `{table_name}` 表格。")

    if changes:
        print(f"偵測到有 {len(changes)} 項商品變動，正在發送 Email 通知...")
        subject = f"🚨 【Bandai 追蹤】{region_name} 地區商品更新！"
        body = f"偵測到 Bandai {region_name} 地區商品有新變動：\n\n" + "\n\n".join(changes[:30]) + f"\n\n前往查看: {result.get('url')}"
        send_email_alert(subject, body)
    else:
        print(f"【{region_name}】無新商品上架，不發送 Email。")

def main():
    if len(sys.argv) < 2:
        print("❌ 用法錯誤！請指定地區參數：\n   python3 run_cron.py hk\n   python3 run_cron.py us")
        sys.exit(1)
        
    region_arg = sys.argv[1].lower()
    if region_arg == "hk":
        region_name = "香港 (HK)"
    elif region_arg == "us":
        region_name = "美國 (US)"
    else:
        print(f"❌ 未知的區域參數 '{region_arg}'，請使用 hk 或 us")
        sys.exit(1)

    init_db()
    process_region(region_arg, region_name)

if __name__ == "__main__":
    main()