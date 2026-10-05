from dotenv import load_dotenv; load_dotenv(".env")
from haqdaar.audio.telephony import twilio
keep = ("sid","status","start_time","end_time","duration","direction","answered_by","price","queue_time")
for c in twilio.recent_calls(6):
    print({k: (str(c.get(k))[-34:] if k=="sid" else c.get(k)) for k in keep})
sid="CAc30f3e0585c7461f35e88f6833e0b2b5"
for path in (f"Calls/{sid}/Events.json", f"Calls/{sid}/Notifications.json"):
    try:
        d=twilio._api(path)
        rows=d.get("events") or d.get("notifications") or []
        print(path, len(rows))
        for r in rows[:12]:
            req=(r.get("request") or {}); resp=(r.get("response") or {})
            print("  ", (req.get("url") or r.get("message_text") or "")[:90], resp.get("response_code") or r.get("error_code"), str((req.get("parameters") or {}).get("call_status") or "")[:20], r.get("message_date") or "")
    except Exception as e:
        print(path, "failed:", repr(e)[:200])
