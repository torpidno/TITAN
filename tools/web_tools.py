import re
import urllib.parse
import httpx
from typing import Dict, Any, List

async def search_web(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the web for up-to-date information or websites using DuckDuckGo.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
            res = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
            if res.status_code != 200:
                return {"status": "error", "message": f"Search returned status {res.status_code}"}
            
            html = res.text
            matches = re.findall(r'<a class="result__url"[^>]*href="([^"]*)"[^>]*>\s*(.*?)\s*</a>', html, re.DOTALL)
            snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
            
            results = []
            for i, (raw_url, raw_title) in enumerate(matches[:max_results]):
                clean_title = re.sub(r'<[^>]+>', '', raw_title).strip()
                clean_snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
                
                if "uddg=" in raw_url:
                    parsed_url = urllib.parse.unquote(raw_url.split("uddg=")[-1].split("&")[0])
                else:
                    parsed_url = raw_url if raw_url.startswith("http") else f"https://{raw_url}"
                
                results.append({
                    "title": clean_title,
                    "snippet": clean_snippet,
                    "url": parsed_url
                })

            if not results:
                return {"status": "success", "results": [], "message": "No direct search results found."}

            return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "message": f"Web search error: {str(e)}"}

async def fetch_webpage(url: str, max_length: int = 4000) -> Dict[str, Any]:
    """
    Fetch clean markdown/text content from a web URL.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
            res = await client.get(url)
            if res.status_code != 200:
                return {"status": "error", "message": f"HTTP status {res.status_code}"}
            
            html = res.text
            # Strip script and style tags
            clean = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r'<style.*?</style>', '', clean, flags=re.DOTALL | re.IGNORECASE)
            # Replace tags with whitespace
            text = re.sub(r'<[^>]+>', ' ', clean)
            # Normalize whitespace
            normalized_text = ' '.join(text.split())
            
            return {
                "status": "success",
                "url": url,
                "content": normalized_text[:max_length]
            }
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch webpage: {str(e)}"}
