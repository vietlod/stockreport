"""
Find the IformationDisclosure JS module and its API endpoint.
"""
import re
from playwright.sync_api import sync_playwright

URL = "https://cafef.vn/du-lieu/cong-bo-thong-tin.chn"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = context.new_page()
    
    # Capture JS files that contain IformationDisclosure
    def on_response(response):
        url = response.url
        if response.status == 200:
            ct = response.headers.get("content-type", "")
            if "javascript" in ct or url.endswith(".js"):
                try:
                    body = response.text()
                    if "IformationDisclosure" in body or "informationdisclosure" in body.lower():
                        print(f"\n✅ Found IformationDisclosure in: {url}")
                        # Save the JS file
                        safe_name = re.sub(r'[^\w]', '_', url.split('/')[-1].split('?')[0])[:50]
                        with open(f"pdf/_js_{safe_name}.js", "w", encoding="utf-8") as f:
                            f.write(body)
                        print(f"   Saved to pdf/_js_{safe_name}.js")
                        
                        # Find the API URL pattern
                        api_patterns = re.findall(r'(https?://[^\s"\'<>]+(?:ashx|aspx|chn|api|ajax)[^\s"\'<>]*)', body)
                        if api_patterns:
                            print(f"   API URLs found:")
                            for u in set(api_patterns):
                                print(f"     {u}")
                        
                        # Find handleChangePage function
                        hcp_match = re.search(r'handleChangePage[^}]+\{[^}]+\}', body)
                        if hcp_match:
                            print(f"   handleChangePage: {hcp_match.group()[:300]}")
                except:
                    pass
    
    page.on("response", on_response)
    
    print("🌐 Loading page...")
    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)
    
    # Try to evaluate JS in page context
    print("\n📋 Evaluating IformationDisclosure in page context...")
    try:
        result = page.evaluate("""() => {
            if (typeof IformationDisclosure !== 'undefined') {
                return {
                    exists: true,
                    keys: Object.keys(IformationDisclosure),
                    pageIndex: IformationDisclosure.pageIndex,
                    pageSize: IformationDisclosure.pageSize,
                    totalPage: IformationDisclosure.totalPage,
                    // Try to get the source code of key methods
                    loadDataStr: IformationDisclosure.loadData ? IformationDisclosure.loadData.toString().substring(0, 500) : null,
                    handleChangePageStr: IformationDisclosure.handleChangePage ? IformationDisclosure.handleChangePage.toString() : null,
                };
            }
            return { exists: false };
        }""")
        print(f"   Result: {result}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Also try to get the pagination container
    print("\n📋 Looking for pagination elements...")
    pag_elements = page.query_selector_all("[onclick*='handleChangePage']")
    print(f"   Found {len(pag_elements)} pagination buttons")
    for pe in pag_elements[:10]:
        onclick = pe.get_attribute("onclick") or ""
        text = pe.inner_text()
        tag = pe.evaluate("el => el.tagName")
        cls = pe.get_attribute("class") or ""
        print(f"   <{tag} class='{cls}' onclick='{onclick}'>{text}</{tag}>")
    
    # Find the parent container of pagination
    if pag_elements:
        parent = pag_elements[0].evaluate("el => el.closest('.paging, .pagination, div')?.outerHTML?.substring(0, 500)")
        print(f"\n   Parent container: {parent}")
    
    browser.close()
