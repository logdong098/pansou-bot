import asyncio
import re
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup

from config import PROXY, MONITORED_CHANNELS, CRAWL_PAGES_PER_CHANNEL, DB_PATH, PAN_TYPES
from parser import parse_message
from database import save_resources

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

def clean_html_to_text(element) -> str:
    """
    Converts BeautifulSoup message HTML into plain text preserving newlines.
    """
    # Replace <br> and <br/> with newline
    for br in element.find_all(["br", "p"]):
        br.replace_with("\n" + br.text)
    return element.get_text()

class TelegramWebCrawler:
    def __init__(self, proxy: Optional[str] = PROXY, db_path: str = DB_PATH):
        self.proxy = proxy
        self.db_path = db_path

    def _get_client(self) -> httpx.AsyncClient:
        kwargs: Dict[str, Any] = {
            "headers": HEADERS,
            "timeout": 20.0,
            "follow_redirects": True,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        return httpx.AsyncClient(**kwargs)

    async def crawl_channel_page(
        self, client: httpx.AsyncClient, channel: str, before: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Crawls a single page of https://t.me/s/{channel}
        """
        url = f"https://t.me/s/{channel}"
        if before:
            url += f"?before={before}"

        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                print(f"[{channel}] HTTP {resp.status_code} on {url}")
                return {"messages": [], "min_id": None}

            soup = BeautifulSoup(resp.text, "html.parser")
            message_wraps = soup.find_all("div", class_="tgme_widget_message_wrap")

            parsed_resources: List[Dict[str, Any]] = []
            msg_ids = []

            for wrap in message_wraps:
                msg_div = wrap.find("div", class_="tgme_widget_message")
                if not msg_div:
                    continue

                # Extract message id from data-post (e.g. 'channel_name/1234')
                data_post = msg_div.get("data-post", "")
                msg_id = 0
                if "/" in data_post:
                    try:
                        msg_id = int(data_post.split("/")[-1])
                        msg_ids.append(msg_id)
                    except ValueError:
                        pass

                text_div = wrap.find("div", class_="tgme_widget_message_text")
                if not text_div:
                    continue

                raw_text = clean_html_to_text(text_div)
                extracted = parse_message(raw_text, channel=channel, message_id=msg_id)
                # Keep only the requested cloud-drive types. The default
                # deployment is quark-only; this prevents Aliyun/Baidu/etc.
                # links from entering the search database.
                if PAN_TYPES:
                    extracted = [r for r in extracted if r.get("pan_type", "").lower() in PAN_TYPES]
                if extracted:
                    parsed_resources.extend(extracted)

            min_id = min(msg_ids) if msg_ids else None
            return {"resources": parsed_resources, "min_id": min_id, "count": len(message_wraps)}

        except Exception as e:
            print(f"[{channel}] Fetch error: {e}")
            return {"resources": [], "min_id": None, "count": 0}

    async def crawl_channel(self, channel: str, max_pages: int = CRAWL_PAGES_PER_CHANNEL) -> Dict[str, int]:
        """
        Crawls multiple pages backwards for a single channel.
        """
        channel = channel.strip().lstrip("@")
        print(f"\n🚀 开始采集频道: @{channel} (最多 {max_pages} 页)...")

        total_scanned = 0
        total_found = 0
        total_inserted = 0
        total_duplicates = 0
        before: Optional[int] = None

        async with self._get_client() as client:
            for page in range(1, max_pages + 1):
                res = await self.crawl_channel_page(client, channel, before=before)
                found = res.get("resources", [])
                scanned = res.get("count", 0)
                min_id = res.get("min_id")

                total_scanned += scanned
                total_found += len(found)

                if found:
                    ins, dup = save_resources(found, db_path=self.db_path)
                    total_inserted += ins
                    total_duplicates += dup
                    print(f"  └ 📄 第 {page} 页: 扫描 {scanned} 条消息, 提取 {len(found)} 个网盘链接 (新增: {ins}, 重复: {dup})")
                else:
                    print(f"  └ 📄 第 {page} 页: 扫描 {scanned} 条消息, 未发现新资源")

                if not min_id or min_id <= 1:
                    break

                # The next page should be before the earliest message id on this page
                before = min_id
                await asyncio.sleep(1.5)  # Polite delay

        print(f"✅ 频道 @{channel} 采集完成! 扫描: {total_scanned} 条 | 提取: {total_found} 个 | 新增: {total_inserted} | 重复: {total_duplicates}")
        return {
            "scanned": total_scanned,
            "found": total_found,
            "inserted": total_inserted,
            "duplicate": total_duplicates,
        }

    async def crawl_all(self, channels: Optional[List[str]] = None, max_pages: int = CRAWL_PAGES_PER_CHANNEL):
        """
        Crawls all configured channels.
        """
        targets = channels or MONITORED_CHANNELS
        print(f"\n{'='*50}")
        print(f"📦 开始全量采集: 共 {len(targets)} 个频道")
        print(f"{'='*50}")

        summary = {"scanned": 0, "found": 0, "inserted": 0, "duplicate": 0}
        for ch in targets:
            stats = await self.crawl_channel(ch, max_pages=max_pages)
            for k in summary:
                summary[k] += stats.get(k, 0)
            await asyncio.sleep(2.0)

        print(f"\n🎉 全部采集结束!")
        print(f"📊 汇总数据: 总扫描: {summary['scanned']} | 提取资源: {summary['found']} | 成功入库: {summary['inserted']} | 重复过滤: {summary['duplicate']}")
        return summary

if __name__ == "__main__":
    from database import init_db
    init_db()
    crawler = TelegramWebCrawler()
    asyncio.run(crawler.crawl_all(max_pages=2))
