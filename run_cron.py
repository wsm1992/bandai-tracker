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
        print("[通知] Bark 手機推播已成功發送！")
    except Exception as e:
        print(f"推播失敗: {e}")

def check_and_track(region_name, region_arg):
    print(f"執行【{region_name}】追蹤...")
    
    # 1. 執行原本的追蹤腳本
    subprocess.run(["python3", "bandai_tracker.py", region_arg])
    
    # 2. 檢查 Git 狀態，看有哪些檔案被修改
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    git_status = result.stdout
    
    # 判斷該地區的資料檔案是否有變動
    if region_arg in git_status or "history" in git_status or "json" in git_status:
        
        # 【核心優化】精確檢查 git diff 的內容，過濾掉單純的 last_success_time 變動
        diff_result = subprocess.run(["git", "diff"], capture_output=True, text=True)
        diff_content = diff_result.stdout
        
        # 檢查 diff 裡除了 last_success_time 之外，還有沒有其他真正的數據變動
        # (例如商品清單、庫存狀態等)
        lines = diff_content.splitlines()
        content_changed = False
        for line in lines:
            # 如果有新增(+)或刪除(-)的行，且不是 last_success_time 相關的行
            if (line.startswith("+") or line.startswith("-")) and not line.startswith("+++") and not line.startswith("---"):
                if "last_success_time" not in line:
                    content_changed = True
                    break

        if content_changed:
            print(f"偵測到【{region_name}】商品內容有實質變更！發送 Bark 通知並同步至 Git...")
            # 實際發送 Bark 手機通知
            send_bark("🚨 Bandai 商品更新", f"【{region_name}】地區偵測到商品內容變更或新商品上架！")
        else:
            print(f"【{region_name}】僅有時間戳記 (last_success_time) 改變，商品內容無實質變動，不發送通知。")
        
        # 無論是否有新商品，只要歷史檔案更新了，就順便 commit 並 push 保持同步
        subprocess.run(["git", "add", "."])
        subprocess.run(["git", "commit", "-m", f"🤖 本地自動更新：{region_name} 狀態變更"])
        
        push_result = subprocess.run(["git", "push"], capture_output=True, text=True)
        if push_result.returncode != 0:
            print(f"[警告] Git Push 失敗：{push_result.stderr}")
        else:
            print(f"[成功] {region_name} 資料已自動推送到 GitHub 遠端！")
    else:
        print(f"【{region_name}】無數據變動。")

if __name__ == "__main__":
    check_and_track("香港 (HK)", "hk")
    #check_and_track("美國 (US)", "us")