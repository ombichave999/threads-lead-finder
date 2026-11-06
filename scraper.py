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
LEADS_JSON = "leads.json"
GOOGLE_SHEET_WEBHOOK = os.environ.get("GOOGLE_SHEET_WEBHOOK", "").strip()

# Target high-intent queries
SEARCH_QUERIES = [
    'site:threads.net "looking for a website designer"',
    'site:threads.net "looking for a web developer"',
    'site:threads.net "need a website designer"',
    'site:threads.net "hire a web developer"',
    'site:threads.net "redesign our website"',
    'site:threads.net "looking for a shopify developer"',
    'site:threads.net "looking for a wordpress developer"',
    'site:threads.net "need a freelancer for website"'
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

def get_cutoff_date():
    """Returns midnight of yesterday as a datetime object."""
    now = datetime.datetime.now()
    yesterday = now - datetime.timedelta(days=1)
    return yesterday.replace(hour=0, minute=0, second=0, microsecond=0)

def is_recent(snippet):
    """
    Enforces 'yesterday to future' filter.
    Rejects any snippet indicating older dates.
    """
    snippet_lower = snippet.lower()
    
    # Old years check (e.g. 2020-2025 if current is 2026)
    current_year = datetime.datetime.now().year
    for past_year in range(2020, current_year):
        if str(past_year) in snippet:
            return False
            
    # Obvious old indicators
    old_patterns = [
        r'\b\d+\s+(weeks?|months?|years?)\s+ago\b',
        r'\b2\s+days?\s+ago\b',
        r'\b[3-9]\s+days?\s+ago\b'
    ]
    for p in old_patterns:
        if re.search(p, snippet_lower):
            return False

    return True

def load_existing_leads():
    leads = []
    seen_urls = set()
    if os.path.exists(LEADS_FILE):
        try:
            with open(LEADS_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get("Post URL", "").strip()
                    if url and url not in seen_urls:
                        leads.append(row)
                        seen_urls.add(url)
        except Exception as e:
            print(f"[!] Warning reading existing leads: {e}")
    return leads, seen_urls

def search_ddg_lite(query, time_range="d"):
    """
    Queries DuckDuckGo Lite with time filter.
    df='d' (past 24h), df='w' (past week)
    """
    leads = []
    try:
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({"q": query, "df": time_range}).encode("utf-8")
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
            matches = re.findall(r'<a[^>]+href="(https://(?:www\.)?threads\.net/@[^/]+/post/[^"?#]+)"[^>]*>(.*?)</a>', html)
            for link, snippet_html in matches:
                clean_snippet = re.sub(r'<[^>]+>', '', snippet_html).strip()
                if not is_recent(clean_snippet):
                    continue
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
    elif "react" in text_lower or "next" in text_lower:
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
        print(f"[!] Failed to push to Google Sheet: {e}")
        return False

def main():
    now = datetime.datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    cutoff = get_cutoff_date()
    print(f"[{now.isoformat()}] Starting Fresh Lead Finder (Filter: >= {cutoff.strftime('%Y-%m-%d')})...")
    
    all_leads, seen_urls = load_existing_leads()
    print(f"[*] Loaded {len(all_leads)} existing leads.")

    new_count = 0

    # Search past day (df='d') first, then past week (df='w')
    for time_filter in ["d", "w"]:
        for query in SEARCH_QUERIES:
            print(f"[*] Searching ({time_filter}): {query}")
            results = search_ddg_lite(query, time_range=time_filter)
            for res in results:
                url = res["url"]
                if url in seen_urls:
                    continue
                
                new_lead = {
                    "Date found": now_str,
                    "Posted date": "Yesterday - Today",
                    "Platform/source": detect_platform(res["snippet"]),
                    "Author/handle": res["author"],
                    "What they need": res["snippet"][:150],
                    "Post URL": url,
                    "Public contact": "Public Threads Post",
                    "Budget": "Discuss / Inquire",
                    "Location": "Remote",
                    "Deadline": "ASAP",
                    "Notes": "Fresh Lead (Filtered from yesterday onwards)"
                }
                all_leads.append(new_lead)
                seen_urls.add(url)
                new_count += 1
                
                if GOOGLE_SHEET_WEBHOOK:
                    push_to_google_sheet(new_lead)
            
            time.sleep(random.uniform(1.5, 3.0))

    # SORT: Newest found date first
    all_leads.sort(key=lambda x: x.get("Date found", ""), reverse=True)

    fieldnames = [
        "Date found", "Posted date", "Platform/source", "Author/handle",
        "What they need", "Post URL", "Public contact", "Budget",
        "Location", "Deadline", "Notes"
    ]

    # Save sorted leads to CSV
    with open(LEADS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for l in all_leads:
            writer.writerow(l)

    # Also save sorted leads to JSON for easy dashboard consumption
    with open(LEADS_JSON, "w", encoding="utf-8") as f:
        json.dump(all_leads, f, indent=2)

    print(f"[✓] Complete! {new_count} new fresh leads added. Total leads in ledger: {len(all_leads)} (Sorted newest first).")

if __name__ == "__main__":
    main()
