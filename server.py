import os
import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="트렌딩 허브 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 환경변수에서 유튜브 API 키 로드
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/"
}

# ─── 캐시 ───
cache = {}
CACHE_TTL = 300  # 5분

def get_cache(key):
    if key in cache:
        data, ts = cache[key]
        if (datetime.now() - ts).seconds < CACHE_TTL:
            return data
    return None

def set_cache(key, data):
    cache[key] = (data, datetime.now())


# ─── 헬스체크 ───
@app.get("/")
async def root():
    return {"status": "ok", "message": "트렌딩 허브 API 정상 작동 중"}


# ─── 디시인사이드 ───
# ─── 한국 뉴스 RSS ───
@app.get("/api/dcinside")
async def get_dcinside():
    return await get_naver_news()

@app.get("/api/bobae")
async def get_bobae():
    return await get_daum_news()

@app.get("/api/etoland")
async def get_etoland():
    return await get_yonhap_news()

@app.get("/api/humoruniv")
async def get_humoruniv():
    return await get_yna_entertainment()

async def parse_rss(url: str, site: str, name: str):
    cached = get_cache(site)
    if cached: return cached
    posts = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            res = await client.get(url)
            soup = BeautifulSoup(res.text, "xml")
            items = soup.find_all("item")[:15]
            for item in items:
                title = item.find("title")
                link = item.find("link")
                desc = item.find("description")
                pub = item.find("pubDate")
                if not title or not link: continue
                title_txt = title.get_text(strip=True)
                link_txt = link.get_text(strip=True) if link.get_text(strip=True) else (link.next_sibling or "")
                if len(title_txt) < 3: continue
                posts.append({
                    "title": title_txt,
                    "url": str(link_txt).strip(),
                    "views": pub.get_text(strip=True)[:16] if pub else "",
                    "recomm": "",
                    "hot": False
                })
    except Exception as e:
        logger.error(f"{site} RSS 실패: {e}")
    result = {"site": site, "name": name, "posts": posts}
    set_cache(site, result)
    return result

async def get_naver_news():
    return await parse_rss(
        "https://feeds.feedburner.com/yonhapnews_headline",
        "naver", "연합뉴스 헤드라인"
    )

async def get_daum_news():
    return await parse_rss(
        "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml",
        "daum", "조선일보"
    )

async def get_yonhap_news():
    return await parse_rss(
        "https://www.yna.co.kr/rss/news.xml",
        "yonhap", "연합뉴스"
    )

async def get_yna_entertainment():
    return await parse_rss(
        "https://www.yna.co.kr/rss/entertainment.xml",
        "yna_ent", "연합뉴스 연예"
    )


# ─── Hacker News ───
@app.get("/api/hackernews")
async def get_hackernews():
    cached = get_cache("hackernews")
    if cached: return cached

    posts = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            ids = res.json()[:15]
            tasks = [client.get(f"https://hacker-news.firebaseio.com/v0/item/{id}.json") for id in ids]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for r in responses:
                if isinstance(r, Exception): continue
                s = r.json()
                if not s or not s.get("title"): continue
                posts.append({
                    "title": s["title"],
                    "url": s.get("url") or f"https://news.ycombinator.com/item?id={s['id']}",
                    "views": str(s.get("score", 0)),
                    "recomm": str(s.get("descendants", 0)),
                    "hot": s.get("score", 0) > 200
                })
        logger.info(f"HN {len(posts)}개 수집")
    except Exception as e:
        logger.error(f"HN 수집 실패: {e}")

    result = {"site": "hackernews", "name": "Hacker News", "posts": posts}
    set_cache("hackernews", result)
    return result


# ─── 유튜브 숏츠 ───
@app.get("/api/shorts")
async def get_shorts():
    cached = get_cache("shorts")
    if cached: return cached

    if not YOUTUBE_API_KEY:
        return {"shorts": [], "error": "API 키 없음"}

    videos = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "snippet,statistics,contentDetails",
                    "chart": "mostPopular",
                    "regionCode": "KR",
                    "maxResults": 20,
                    "key": YOUTUBE_API_KEY
                }
            )
            data = res.json()
            for item in data.get("items", []):
                vid = item["id"]
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                duration = item.get("contentDetails", {}).get("duration", "")
                views = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                comments = int(stats.get("commentCount", 0))
                if views < 100000: continue
                videos.append({
                    "id": vid,
                    "title": snippet.get("title", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    "duration": duration
                })
        logger.info(f"유튜브 숏츠 {len(videos)}개 수집")
    except Exception as e:
        logger.error(f"유튜브 수집 실패: {e}")

    result = {"shorts": videos[:15]}
    set_cache("shorts", result)
    return result


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
