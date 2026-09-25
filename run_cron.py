import subprocess
import requests

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
    
    # 1. 執行原本的追蹤腳本 (python bandai_tracker.py hk / us)
    subprocess.run(["python3", "bandai_tracker.py", region_arg])
    
    # 2. 檢查 Git 狀態，判斷數據是否有變動
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    git_status = result.stdout
    
    # 如果偵測到資料檔案有被修改，代表有新內容或狀態變更
    if region_arg in git_status or "history" in git_status or "json" in git_status:
        print(f"偵測到【{region_name}】數據有更新！發送通知並同步至 Git...")
        
        # 💡 加上這一行，實際發送 Bark 手機通知
        send_bark("🚨 Bandai 庫存更新", f"【{region_name}】地區偵測到商品變動或新商品上架！")
        
        # 自動 Git 提交並推送到遠端 GitHub
        subprocess.run(["git", "add", "."])
        subprocess.run(["git", "commit", "-m", f"🤖 本地自動更新：{region_name} 狀態變更"])
        
        push_result = subprocess.run(["git", "push"], capture_output=True, text=True)
        if push_result.returncode != 0:
            print(f"[警告] Git Push 失敗，可能是遠端憑證問題：{push_result.stderr}")
        else:
            print(f"[成功] {region_name} 資料已自動推送到 GitHub 遠端！")
    else:
        print(f"【{region_name}】無數據變動。")

if __name__ == "__main__":
    # 依序執行香港與美國監控
    check_and_track("香港 (HK)", "hk")
    check_and_track("美國 (US)", "us")