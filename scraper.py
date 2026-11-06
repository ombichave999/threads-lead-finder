import os
import csv
import re
import json
import time
import random
import datetime
import urllib.parse
import urllib.request

LEADS_FILE = "leads.csv"
GOOGLE_SHEET_WEBHOOK = os.environ.get("GOOGLE_SHEET_WEBHOOK", "").strip()

SEARCH_QUERIES = [
    'site:threads.net "looking for a website designer"',
    'site:threads.net "looking for a web developer"',
    'site:threads.net "need a website designer"',
    'site:threads.net "hire a web developer"',
    'site:threads.net "redesign our website"',
    'site:threads.net "looking for a shopify developer"'
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

def load_existing_urls():
    existing = set()
    if os.path.exists(LEADS_FILE):
        try:
            with open(LEADS_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get("Post URL", "").strip()
                    if url:
                        existing.add(url)
        except Exception as e:
            print(f"[!] Warning reading existing leads: {e}")
    return existing

def search_ddg_lite(query):
    leads = []
    try:
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": random.choice(USER_AGENTS),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            
            # Extract threads post links and snippets
            matches = re.findall(r'<a[^>]+href="(https://(?:www\.)?threads\.net/@[^/]+/post/[^"?#]+)"[^>]*>(.*?)</a>', html)
            for link, snippet_html in matches:
                clean_snippet = re.sub(r'<[^>]+>', '', snippet_html).strip()
                author_match = re.search(r'threads\.net/@([^/]+)', link)
                author = f"@{author_match.group(1)}" if author_match else "Unknown"
                leads.append({
                    "url": link,
                    "author": author,
                    "snippet": clean_snippet or "Looking for web developer/designer"
                })
    except Exception as e:
        print(f"[!] Search error for '{query}': {e}")
    return leads

def detect_platform(text):
    text_lower = text.lower()
    if "shopify" in text_lower:
        return "Shopify"
    elif "wordpress" in text_lower:
        return "WordPress"
    elif "webflow" in text_lower:
        return "Webflow"
    elif "react" in text_lower or "nextjs" in text_lower or "next.js" in text_lower:
        return "React / Next.js"
    return "Website / Custom"

def push_to_google_sheet(lead):
    if not GOOGLE_SHEET_WEBHOOK:
        return False
    try:
        payload = json.dumps(lead).encode("utf-8")
        req = urllib.request.Request(
            GOOGLE_SHEET_WEBHOOK,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[!] Failed to push to Google Sheet webhook: {e}")
        return False

def main():
    print(f"[{datetime.datetime.utcnow().isoformat()}] Starting 24/7 Cloud Lead Finder...")
    existing_urls = load_existing_urls()
    print(f"[*] Loaded {len(existing_urls)} existing leads.")

    new_leads = []
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    for query in SEARCH_QUERIES:
        print(f"[*] Querying: {query}")
        results = search_ddg_lite(query)
        for res in results:
            url = res["url"]
            if url in existing_urls:
                continue
            
            # New lead found!
            lead = {
                "Date found": now_str,
                "Posted date": "Recent",
                "Platform/source": detect_platform(res["snippet"]),
                "Author/handle": res["author"],
                "What they need": res["snippet"][:150],
                "Post URL": url,
                "Public contact": "Public Threads Post",
                "Budget": "Discuss / Inquire",
                "Location": "Remote",
                "Deadline": "ASAP",
                "Notes": "Auto-discovered by 24/7 Cloud Runner"
            }
            new_leads.append(lead)
            existing_urls.add(url)
        
        # Polite jitter delay between queries
        time.sleep(random.uniform(2.0, 4.0))

    if not new_leads:
        print("[✓] Scan complete: No new leads found on this run.")
        return

    print(f"[✓] Found {len(new_leads)} new leads! Appending to {LEADS_FILE}...")
    
    file_exists = os.path.exists(LEADS_FILE)
    with open(LEADS_FILE, "a", newline="", encoding="utf-8") as f:
        fieldnames = [
            "Date found", "Posted date", "Platform/source", "Author/handle",
            "What they need", "Post URL", "Public contact", "Budget",
            "Location", "Deadline", "Notes"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists or os.path.getsize(LEADS_FILE) == 0:
            writer.writeheader()
        for lead in new_leads:
            writer.writerow(lead)
            if GOOGLE_SHEET_WEBHOOK:
                push_to_google_sheet(lead)

    print(f"[✓] Successfully recorded {len(new_leads)} new leads.")

if __name__ == "__main__":
    main()
