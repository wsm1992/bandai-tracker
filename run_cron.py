import subprocess
import requests
import urllib.parse

# 你的 Bark 專屬 Key
BARK_KEY = "qNRxAfYURwGKQbBTjvdnee"

def send_bark(title, body):
    """使用 POST 方式發送 Bark 推播"""
    try:
        url = f"https://api.day.app/{BARK_KEY}"
        payload = {
            "title": title,
            "body": body,
            "group": "BandaiMonitor",
            "ttl": 600
        }
        requests.post(url, data=payload)
    except Exception as e:
        print(f"推播失敗: {e}")

def check_and_track(region_name, region_arg):
    print(f"執行【{region_name}】追蹤...")
    
    # 1. 執行原本的追蹤腳本
    subprocess.run(["python3", "bandai_tracker.py", region_arg])
    
    # 2. 檢查 Git 狀態，看對應的資料檔案是否被修改
    # (Git 會幫我們完美比對出數據有沒有改變，完全不需要自己寫邏輯)
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    git_status = result.stdout
    
    # 判斷該地區的資料檔案是否有變動
    if region_arg in git_status or "history" in git_status or "json" in git_status:
        print(f"偵測到【{region_name}】數據有更新！發送通知...")
        send_bark("🚨 Bandai 庫存更新", f"【{region_name}】地區偵測到商品變動或新商品上架！")
        
        # 可選：順便把變動自動 commit 起來保持乾淨
        subprocess.run(["git", "add", "."])
        subprocess.run(["git", "commit", "-m", f"auto-update: {region_name} status changed"])
    else:
        print(f"【{region_name}】無數據變動。")

if __name__ == "__main__":
    # 依序檢查香港與美國
    check_and_track("香港 (HK)", "hk")
    check_and_track("美國 (US)", "us")