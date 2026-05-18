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
@app.get("/api/dcinside")
async def get_dcinside():
    cached = get_cache("dcinside")
    if cached: return cached

    posts = []
    urls = [
        "https://gall.dcinside.com/board/lists/?id=humor",
        "https://gall.dcinside.com/mgallery/board/lists/?id=programming",
        "https://m.dcinside.com/board/humor"
    ]
    try:
        async with httpx.AsyncClient(
            headers={
                **HEADERS,
                "Cookie": "adult_join=1",
                "X-Requested-With": "XMLHttpRequest"
            },
            timeout=15,
            follow_redirects=True
        ) as client:
            for url in urls:
                try:
                    res = await client.get(url)
                    if res.status_code != 200:
                        continue
                    soup = BeautifulSoup(res.text, "html.parser")
                    rows = soup.select("tr.us-post, tr[data-no], .ub-content")
                    for row in rows[:20]:
                        title_el = row.select_one(".gall-tit a, .t-tcatls a, .subject a")
                        if not title_el: continue
                        title = title_el.get_text(strip=True)
                        if len(title) < 3 or "공지" in title: continue
                        href = title_el.get("href", "")
                        post_url = href if href.startswith("http") else f"https://gall.dcinside.com{href}"
                        views_el = row.select_one(".gall-count, .view-cnt")
                        views = views_el.get_text(strip=True) if views_el else "0"
                        recomm_el = row.select_one(".gall-recommend, .recommend")
                        recomm = recomm_el.get_text(strip=True) if recomm_el else "0"
                        posts.append({
                            "title": title,
                            "url": post_url,
                            "views": views,
                            "recomm": recomm,
                            "hot": int(views.replace(",","") or 0) > 3000
                        })
                    if posts:
                        break
                except Exception as e:
                    logger.error(f"디시 URL {url} 실패: {e}")
                    continue
        logger.info(f"디시 {len(posts)}개 수집")
    except Exception as e:
        logger.error(f"디시 수집 실패: {e}")

    result = {"site": "dcinside", "name": "디시인사이드", "posts": posts[:15]}
    set_cache("dcinside", result)
    return result


# ─── 보배드림 ───
@app.get("/api/bobae")
async def get_bobae():
    cached = get_cache("bobae")
    if cached: return cached

    posts = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            res = await client.get("https://www.bobaedream.co.kr/list?code=funny")
            soup = BeautifulSoup(res.text, "html.parser")
            rows = soup.select("tr.bbs-list")
            for row in rows[:20]:
                title_el = row.select_one("a.bTitle, td.title a")
                if not title_el: continue
                title = title_el.get_text(strip=True)
                if len(title) < 3: continue
                href = title_el.get("href", "")
                url = href if href.startswith("http") else f"https://www.bobaedream.co.kr{href}"
                count_el = row.select_one(".count, .view")
                views = count_el.get_text(strip=True) if count_el else "0"
                posts.append({
                    "title": title,
                    "url": url,
                    "views": views,
                    "recomm": "0",
                    "hot": int(views.replace(",","") or 0) > 1000
                })
        logger.info(f"보배 {len(posts)}개 수집")
    except Exception as e:
        logger.error(f"보배 수집 실패: {e}")

    result = {"site": "bobae", "name": "보배드림", "posts": posts[:15]}
    set_cache("bobae", result)
    return result


# ─── 이토랜드 ───
@app.get("/api/etoland")
async def get_etoland():
    cached = get_cache("etoland")
    if cached: return cached

    posts = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            res = await client.get("https://www.etoland.co.kr/plugin/sns/board.php?bo_table=etohumor01")
            soup = BeautifulSoup(res.text, "html.parser")
            items = soup.select("div.gall-item, li.item, .list-item, tr")
            for item in items[:30]:
                title_el = item.select_one("a.subject, .title a, td.title a, a")
                if not title_el: continue
                title = title_el.get_text(strip=True)
                if len(title) < 5 or "로그인" in title or "회원" in title: continue
                href = title_el.get("href", "")
                if not href or href == "#": continue
                url = href if href.startswith("http") else f"https://www.etoland.co.kr{href}"
                posts.append({
                    "title": title,
                    "url": url,
                    "views": "-",
                    "recomm": "0",
                    "hot": False
                })
                if len(posts) >= 15: break
        logger.info(f"이토 {len(posts)}개 수집")
    except Exception as e:
        logger.error(f"이토 수집 실패: {e}")

    result = {"site": "etoland", "name": "이토랜드", "posts": posts[:15]}
    set_cache("etoland", result)
    return result


# ─── 웃긴대학 ───
@app.get("/api/humoruniv")
async def get_humoruniv():
    cached = get_cache("humoruniv")
    if cached: return cached

    posts = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            res = await client.get("https://humoruniv.com/board/humor/list.html")
            soup = BeautifulSoup(res.text, "html.parser")
            rows = soup.select("li.li_post, tr.post, .post-item, table tr")
            for row in rows[:30]:
                title_el = row.select_one("a.pvi_title, .title a, td.title a")
                if not title_el: continue
                title = title_el.get_text(strip=True)
                if len(title) < 3 or "로그인" in title: continue
                href = title_el.get("href", "")
                url = href if href.startswith("http") else f"https://humoruniv.com{href}"
                view_el = row.select_one(".view_count, .count")
                views = view_el.get_text(strip=True) if view_el else "0"
                posts.append({
                    "title": title,
                    "url": url,
                    "views": views,
                    "recomm": "0",
                    "hot": int(views.replace(",","") or 0) > 1000
                })
                if len(posts) >= 15: break
        logger.info(f"웃대 {len(posts)}개 수집")
    except Exception as e:
        logger.error(f"웃대 수집 실패: {e}")

    result = {"site": "humoruniv", "name": "웃긴대학", "posts": posts[:15]}
    set_cache("humoruniv", result)
    return result


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
