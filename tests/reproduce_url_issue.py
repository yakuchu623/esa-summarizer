import re

def clean_slack_url(url: str) -> str:
    """<https://...|title> 形式の余分な記号を除去"""
    url = url.split('|', 1)[0]
    return url.strip('<>').rstrip(')')

def is_esa_post_url(url: str) -> bool:
    """esaの投稿URLか簡易判定"""
    return bool(re.search(r'https?://[^/\s]+\.esa\.io/posts/\d+', url))

def test_url_normalization():
    url1 = "https://transmediatechlab.esa.io/posts/241/revisions/79/diff"
    url2 = "https://transmediatechlab.esa.io/posts/241"
    
    # Current logic simulation
    urls = set()
    
    # Process url1
    clean1 = clean_slack_url(url1)
    if is_esa_post_url(clean1):
        # Simulate new normalization logic
        match = re.search(r'(https?://[^/\s]+\.esa\.io/posts/\d+)', clean1)
        normalized1 = match.group(1) if match else clean1
        urls.add(normalized1)
        
    # Process url2
    clean2 = clean_slack_url(url2)
    if is_esa_post_url(clean2):
        match = re.search(r'(https?://[^/\s]+\.esa\.io/posts/\d+)', clean2)
        normalized2 = match.group(1) if match else clean2
        urls.add(normalized2)
        
    print(f"URL1 processed: {clean1}")
    print(f"URL2 processed: {clean2}")
    print(f"Set size: {len(urls)}")
    print(f"Set content: {urls}")
    
    if len(urls) > 1:
        print("ISSUE REPRODUCED: Different URLs for same post.")
    else:
        print("Issue NOT reproduced.")

if __name__ == "__main__":
    test_url_normalization()
