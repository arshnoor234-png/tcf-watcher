#!/usr/bin/env python3
"""Watch Ashton Testing's TCF Canada page and push a phone alert (ntfy) when session dates change."""
import html, json, os, re, subprocess, sys, time

URL = "https://ashtontesting.ca/tcf-canada-test/"
TOPIC = os.environ.get("NTFY_TOPIC", "")
DIR = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(DIR, "state.json")
LOG = os.path.join(DIR, "watch.log")

def log(msg):
    with open(LOG, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")

def fetch():
    out = subprocess.run(["curl", "-sL", "--max-time", "30", "-A", "Mozilla/5.0", URL],
                         capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout:
        raise RuntimeError(f"fetch failed (curl exit {out.returncode})")
    return out.stdout

def parse(page):
    t = re.sub(r"(?s)<(script|style).*?</\1>", "", page)
    t = re.sub(r"(?s)<!--.*?-->", "", t)
    t = re.sub(r"<[^>]+>", "\n", t)
    lines = [l.strip() for l in html.unescape(t).splitlines() if l.strip()]
    sessions, notices = [], []
    try:
        i = lines.index("Date of the session")
        for l in lines[i + 1:]:
            if l.startswith("TCF Exam Registration Agreement"):
                break
            sessions.append(l)
    except ValueError:
        pass
    for l in lines:
        if re.search(r"(new|additional).*(dates?).*(release|soon)", l, re.I):
            notices.append(l)
    return sessions, notices

def push(title, body, priority="urgent"):
    subprocess.run(["curl", "-s", "--max-time", "20",
                    "-H", f"Title: {title}", "-H", f"Priority: {priority}",
                    "-H", "Tags: rotating_light", "-H", f"Click: {URL}",
                    "-d", body, f"https://ntfy.sh/{TOPIC}"], capture_output=True)

def main():
    try:
        sessions, notices = parse(fetch())
    except Exception as e:
        log(f"error: {e}")
        return
    if not sessions:
        log("warning: no sessions parsed (page layout may have changed)")
        return
    cur = {"sessions": sessions, "notices": notices}
    prev = None
    if os.path.exists(STATE):
        with open(STATE) as f:
            prev = json.load(f)
    if prev is None:
        log(f"baseline: {sessions} | {notices}")
    elif prev != cur:
        added = [s for s in sessions if s not in prev["sessions"]]
        removed = [s for s in prev["sessions"] if s not in sessions]
        parts = []
        if added: parts.append("NEW/CHANGED: " + "; ".join(added))
        if removed: parts.append("Gone: " + "; ".join(removed))
        if notices != prev["notices"]: parts.append("Notice now: " + (" | ".join(notices) or "(removed)"))
        open_ = [s for s in sessions if "FULL" not in s.upper()]
        title = "TCF dates OPEN at Ashton!" if open_ else "TCF page changed"
        body = "\n".join(parts) + "\n\nCurrent: " + "; ".join(sessions)
        push(title, body, "urgent" if open_ else "high")
        log(f"ALERT sent: {title} | {body!r}")
    with open(STATE, "w") as f:
        json.dump(cur, f)

if __name__ == "__main__":
    if "--test" in sys.argv:
        push("TCF watcher test", "If you see this, alerts are working.", "default")
    else:
        main()
