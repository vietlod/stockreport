"""Quick API test for server endpoints."""
import requests

BASE = "http://localhost:8000"

def test(name, url):
    try:
        r = requests.get(url, timeout=5)
        d = r.json()
        print(f"✔ {name}: {r.status_code}")
        return d
    except Exception as e:
        print(f"✖ {name}: {e}")
        return None

# Test stock-data
d = test("GET /api/stock-data", f"{BASE}/api/stock-data")
if d:
    print(f"  Exchanges: {len(d['exchanges'])}, Industries: {len(d['industries'])}, Indexes: {len(d['indexes'])}")

# Test tickers
d = test("GET /api/tickers?search=FPT", f"{BASE}/api/tickers?search=FPT")
if d:
    print(f"  Found: {d['count']} tickers")
    for t in d["tickers"][:2]:
        print(f"    {t['ticker']}: {t['exchange']} | ICB:{t['icb_code']} | {t['indexes']}")

# Test stats
d = test("GET /api/stats", f"{BASE}/api/stats")
if d:
    print(f"  Summary: {d['summary']}")
    print(f"  By exchange: {len(d['by_exchange'])} groups")
    print(f"  By industry: {len(d['by_industry'])} groups")

# Test history
d = test("GET /api/history?limit=3", f"{BASE}/api/history?limit=3")
if d:
    print(f"  Total: {d['total']} records")
    for r in d["records"][:2]:
        print(f"    {r['filename']} | ICB:{r.get('icb_code','-')} | {r.get('exchange','-')}")

# Test HTML page
r = requests.get(f"{BASE}/", timeout=5)
print(f"\n✔ GET /: {r.status_code}, Content-Type: {r.headers.get('content-type','?')}, Length: {len(r.text)}")
