import os
import csv
import re
import json
import time
import random
import datetime
import subprocess
import shutil

LEADS_FILE = "leads.csv"
LEADS_JSON = "leads.json"
GOOGLE_SHEET_WEBHOOK = os.environ.get("GOOGLE_SHEET_WEBHOOK", "").strip()

SEARCH_QUERIES = [
    "looking for website designer",
    "need website designer",
    "looking for web developer",
    "need web developer",
    "hire a web developer",
    "need freelance web developer",
    "redesign our website",
    "looking for shopify developer",
    "looking for wordpress developer"
]

def get_browser_bin():
    """Finds available Chrome/Brave/Chromium executable."""
    candidates = [
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium"
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    for b in ["google-chrome", "google-chrome-stable", "chromium", "brave-browser"]:
        which = shutil.which(b)
        if which:
            return which
    return None

def get_cutoff_timestamp():
    """Returns UNIX timestamp of midnight of yesterday."""
    now = datetime.datetime.now()
    yesterday = now - datetime.timedelta(days=1)
    midnight_yesterday = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_yesterday.timestamp()

def extract_posts_from_dom(html):
    scripts = re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html)
    posts = []
    
    def search_nodes(obj):
        if isinstance(obj, dict):
            if "code" in obj and "caption" in obj and isinstance(obj["caption"], dict) and "user" in obj and isinstance(obj["user"], dict):
                username = obj["user"].get("username")
                code = obj.get("code")
                caption_text = obj["caption"].get("text", "")
                taken_at = obj.get("taken_at")
                if username and code and caption_text:
                    posts.append({
                        "username": username,
                        "code": code,
                        "caption": caption_text,
                        "taken_at": taken_at
                    })
            for v in obj.values():
                search_nodes(v)
        elif isinstance(obj, list):
            for item in obj:
                search_nodes(item)

    for s in scripts:
        if '"caption":' in s and '"username":' in s:
            try:
                data = json.loads(s)
                search_nodes(data)
            except:
                pass
    return posts

def fetch_threads_posts(query, browser_bin):
    url = f"https://www.threads.net/search?q={query.replace(' ', '+')}&serp_type=default"
    cmd = [
        browser_bin,
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--virtual-time-budget=6000",
        "--dump-dom",
        url
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=25, text=True, errors="ignore")
        if proc.stdout:
            return extract_posts_from_dom(proc.stdout)
    except Exception as e:
        print(f"[!] Browser fetch error for '{query}': {e}")
    return []

def detect_platform(text):
    text_lower = text.lower()
    if "shopify" in text_lower:
        return "Shopify"
    elif "wordpress" in text_lower:
        return "WordPress"
    elif "webflow" in text_lower:
        return "Webflow"
    elif "react" in text_lower or "next" in text_lower:
        return "React / Next.js"
    return "Website / Custom"

def extract_budget(text):
    match = re.search(r'(\$\d+[\d,]*|\b\d+\s*(?:k|usd|eur|inr|gbp)\b|budget[^\n,.]+)', text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return "Negotiable / Discuss"

def load_existing_leads():
    leads = []
    seen_codes = set()
    if os.path.exists(LEADS_FILE):
        try:
            with open(LEADS_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get("Post URL", "")
                    code_match = re.search(r'/post/([A-Za-z0-9_-]+)', url)
                    if code_match:
                        seen_codes.add(code_match.group(1))
                    leads.append(row)
        except Exception as e:
            print(f"[!] Warning reading existing leads: {e}")
    return leads, seen_codes

def push_to_google_sheet(lead):
    if not GOOGLE_SHEET_WEBHOOK:
        return False
    try:
        import urllib.request
        payload = json.dumps(lead).encode("utf-8")
        req = urllib.request.Request(
            GOOGLE_SHEET_WEBHOOK,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[!] Failed to push to Google Sheet: {e}")
        return False

def main():
    browser_bin = get_browser_bin()
    if not browser_bin:
        print("[!] Error: No Chrome/Brave/Chromium browser found on system.")
        return

    cutoff_ts = get_cutoff_timestamp()
    cutoff_dt = datetime.datetime.fromtimestamp(cutoff_ts)
    print(f"[{datetime.datetime.now().isoformat()}] Starting Fast Lead Finder (Cutoff: >= {cutoff_dt.strftime('%Y-%m-%d')})...")
    print(f"[*] Using browser binary: {browser_bin}")

    all_leads, seen_codes = load_existing_leads()
    print(f"[*] Loaded {len(all_leads)} existing leads in ledger.")

    new_count = 0

    for query in SEARCH_QUERIES:
        print(f"[*] Scanning Threads: '{query}'")
        raw_posts = fetch_threads_posts(query, browser_bin)
        
        for p in raw_posts:
            code = p.get("code")
            if not code or code in seen_codes:
                continue

            taken_at = p.get("taken_at")
            if taken_at and taken_at < cutoff_ts:
                # Exclude leads older than yesterday
                continue

            posted_date_str = (
                datetime.datetime.fromtimestamp(taken_at).strftime("%Y-%m-%d")
                if taken_at else datetime.datetime.now().strftime("%Y-%m-%d")
            )

            caption = p.get("caption", "").strip()
            caption_lower = caption.lower()
            
            # Rule 6 Filter: Ignore competitors, job seekers, pure mobile apps, and spam
            if any(k in caption_lower for k in [
                'am a web developer', 'i am a developer', 'web developer from',
                'looking for work:', 'hire me', 'open to work', 'beauty contest',
                'graphic designer', 'create content for instagram', 'dr cardin is hiring'
            ]):
                continue
            if 'mobile app' in caption_lower and 'website' not in caption_lower and 'web' not in caption_lower:
                continue

            username = p.get("username", "unknown")
            post_url = f"https://www.threads.net/@{username}/post/{code}"

            lead = {
                "Date found": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Posted date": posted_date_str,
                "Platform/source": detect_platform(caption),
                "Author/handle": f"@{username}",
                "What they need": caption.replace("\n", " ")[:160],
                "Post URL": post_url,
                "Public contact": "Threads DM",
                "Budget": extract_budget(caption),
                "Location": "Remote",
                "Deadline": "Immediate / ASAP",
                "Notes": "Fresh Lead (Yesterday to Future)"
            }

            all_leads.append(lead)
            seen_codes.add(code)
            new_count += 1

            if GOOGLE_SHEET_WEBHOOK:
                push_to_google_sheet(lead)

        time.sleep(random.uniform(1.0, 2.0))

    # Sort strictly newest first
    all_leads.sort(key=lambda x: (x.get("Posted date", ""), x.get("Date found", "")), reverse=True)

    fieldnames = [
        "Date found", "Posted date", "Platform/source", "Author/handle",
        "What they need", "Post URL", "Public contact", "Budget",
        "Location", "Deadline", "Notes"
    ]

    with open(LEADS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for l in all_leads:
            writer.writerow(l)

    with open(LEADS_JSON, "w", encoding="utf-8") as f:
        json.dump(all_leads, f, indent=2)

    print(f"[✓] Complete! {new_count} fresh leads added. Total leads in ledger: {len(all_leads)}.")

if __name__ == "__main__":
    main()
