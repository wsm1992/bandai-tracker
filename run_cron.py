import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ================= 郵件設定 =================
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",  # 如果用 Gmail 保持不變
    "smtp_port": 587,                 # TLS 通訊埠
    "sender_email": "wongsiuming1992@gmail.com", # 發信信箱
    "sender_password": "jqoq ytti apuz lmvg",    # 16位數應用程式密碼
    "receiver_email": "wsm1992@hotmail.com"  # 收信信箱（通常跟發信一樣）
}

def send_email_alert(subject, content):
    """使用 SMTP 發送 Email 通知"""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_CONFIG["sender_email"]
        msg["To"] = EMAIL_CONFIG["receiver_email"]
        msg["Subject"] = subject

        # 加入郵件內文
        msg.attach(MIMEText(content, "plain", "utf-8"))

        # 連線至 SMTP 伺服器並發送
        with smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
            server.starttls()  # 升級為加密連線
            server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
            server.sendmail(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["receiver_email"], msg.as_string())
            
        print("[通知] Email 警報信件已成功發送！")
    except Exception as e:
        print(f"Email 發送失敗: {e}")

def check_and_track(region_name, region_arg):
    print(f"執行【{region_name}】追蹤...")
    
    # 1. 執行原本的追蹤腳本
    subprocess.run(["python3", "bandai_tracker.py", region_arg])
    
    # 2. 檢查 Git 狀態，看有哪些檔案被修改
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    git_status = result.stdout
    
    # 判斷該地區的資料檔案是否有變動
    if region_arg in git_status or "history" in git_status or "json" in git_status:
        
        # 檢查 git diff 的內容，過濾掉單純的 last_success_time 變動
        diff_result = subprocess.run(["git", "diff"], capture_output=True, text=True)
        diff_content = diff_result.stdout
        
        lines = diff_content.splitlines()
        content_changed = False
        for line in lines:
            if (line.startswith("+") or line.startswith("-")) and not line.startswith("+++") and not line.startswith("---"):
                if "last_success_time" not in line:
                    content_changed = True
                    break

        if content_changed:
            print(f"偵測到【{region_name}】商品內容有實質變更！發送 Email 通知並同步至 Git...")
            
            # 組合信件內容，順便附上詳細的 git diff 異動清單
            subject = f"🚨 【Bandai 追蹤】{region_name} 地區商品有更新！"
            body = f"偵測到 Bandai {region_name} 地區有新商品上架或狀態變更。\n\n詳細異動內容：\n{diff_content[:2000]}" # 限制字數避免過長
            
            send_email_alert(subject, body)
        else:
            print(f"【{region_name}】僅有時間戳記 (last_success_time) 改變，商品內容無實質變動，不發送 Email。")
        
        # 無論是否有新商品，只要歷史檔案更新了，就順便 commit 並 push 保持 Git 同步
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
    check_and_track("美國 (US)", "us")