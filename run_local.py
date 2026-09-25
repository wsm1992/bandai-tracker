import asyncio
import subprocess
import requests
import ollama

# 你的 Bark 專屬 Key
BARK_KEY = "qNRxAfYURwGKQbBTjvdnee"

def send_bark_notification(title, body):
    """使用 POST 方式發送 Bark 手機即時推播，穩定支援長篇內容與特殊字元"""
    try:
        url = f"https://api.day.app/{BARK_KEY}"
        payload = {
            "title": title,
            "body": body,
            "group": "BandaiMonitor",
            "ttl": 600
        }
        response = requests.post(url, data=payload)
        
        if response.status_code == 200:
            print("[通知] Bark 推播發送成功！")
        else:
            print(f"[通知警告] Bark 推播失敗，狀態碼：{response.status_code}")
    except Exception as e:
        print(f"[通知錯誤] 無法發送 Bark 推播：{e}")

async def run_tracker_for_region(region_name, region_arg):
    print(f"--- 開始執行 Bandai 追蹤任務 ({region_name}) ---")
    
    command = ["python3", "bandai_tracker.py", region_arg]
    process = subprocess.run(command, capture_output=True, text=True)
    
    tracker_output = process.stdout
    if process.returncode != 0:
        print(f"[{region_name}] 執行時有警告或錯誤：\n{process.stderr}")
    
    print(f"({region_name}) 追蹤完成，正在交由本地 Qwen2.5:14b 分析...")
    
    response = ollama.chat(model='qwen2.5:14b', messages=[
        {
            'role': 'user', 
            'content': f'''以下是 Bandai 追蹤腳本抓回來的【{region_name}】地區資料。
請幫我判斷：是否有新商品上架、或是商品狀態變成「可預購/有庫存」？
如果「沒有」重要變更或全都是舊資料，請回覆「無變動」。
如果「有」新商品或可預購，請用繁體中文列出重點商品與狀態：\n\n{tracker_output}'''
        }
    ])
    
    analysis_result = response['message']['content']
    return analysis_result

async def main():
    hk_result = await run_tracker_for_region("香港 (HK)", "hk")
    us_result = await run_tracker_for_region("美國 (US)", "us")
    
    full_report = f"=== HK 地區 ===\n{hk_result}\n\n=== US 地區 ===\n{us_result}"
    print("\n" + full_report)
    
    with open("tracker_report.log", "w", encoding="utf-8") as f:
        f.write(full_report)

    # 只要有任何一地不是「無變動」，就直接把 AI 分析的完整內容推送到手機上！
    if "無變動" not in hk_result or "無變動" not in us_result:
        print("[通知] 偵測到商品狀態變更或新商品，正在發送手機推播...")
        send_bark_notification("🚨 Bandai 監控通知", full_report)
    else:
        print("[通知] 目前兩地皆無新商品或狀態變更，不發送推播。")

if __name__ == '__main__':
    asyncio.run(main())