import asyncio
import json
from typing import Optional, Dict, Any, List, Tuple
import httpx

from config import BOT_TOKEN, PROXY, DB_PATH, ADMIN_USER_IDS
from database import search, get_stats
from crawler import TelegramWebCrawler

PAGE_SIZE = 5

class PansouTelegramBot:
    def __init__(self, token: str = BOT_TOKEN, proxy: Optional[str] = PROXY, db_path: str = DB_PATH):
        if not token:
            raise ValueError("BOT_TOKEN 未配置！请在 .env 文件中填入从 @BotFather 获取的 token。")
        self.token = token
        self.api_base = f"https://api.telegram.org/bot{self.token}"
        self.proxy = proxy
        self.db_path = db_path
        self.crawler = TelegramWebCrawler(proxy=proxy, db_path=db_path)
        self.is_crawling = False

    def _get_client(self) -> httpx.AsyncClient:
        kwargs: Dict[str, Any] = {
            "timeout": 45.0,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        return httpx.AsyncClient(**kwargs)

    async def api_call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        url = f"{self.api_base}/{method}"
        async with self._get_client() as client:
            try:
                resp = await client.post(url, json=params or {})
                data = resp.json()
                if not data.get("ok"):
                    print(f"[Bot API Error] {method}: {data.get('description')}")
                    return None
                return data.get("result")
            except Exception as e:
                print(f"[Bot Network Error] {method}: {e}")
                return None

    def format_search_results(self, query: str, results: List[Dict[str, Any]], total: int, page: int) -> Tuple[str, Dict[str, Any]]:
        """
        Formats search results into Telegram HTML message and inline keyboard.
        """
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        if total == 0:
            text = (
                f"🔍 搜索关键词：<b>{query}</b>\n\n"
                f"抱歉，没有找到匹配的网盘资源。\n"
                f"💡 建议：\n"
                f"• 尝试缩短关键词（如搜索「三体」而非「三体第一集」）\n"
                f"• 稍后再试，爬虫正在持续收录最新资源中"
            )
            return text, {"inline_keyboard": []}

        lines = [
            f"🔍 关键词：<b>{query}</b>",
            f"📊 找到 <b>{total}</b> 条资源 (第 {page}/{total_pages} 页)",
            "━" * 22,
        ]

        for i, item in enumerate(results, 1):
            idx = (page - 1) * PAGE_SIZE + i
            icon = item.get("pan_icon") or "📁"
            pan_name = item.get("pan_name") or item.get("pan_type", "").upper()
            title = item["title"]
            url = item["url"]
            code = item.get("code", "")
            channel = item.get("channel", "")

            entry = [f"<b>{idx}. {icon} [{pan_name}] {title}</b>"]
            link_line = f"👉 <a href=\"{url}\">点击转存/打开链接</a>"
            if code:
                link_line += f" | 🔑 提取码: <code>{code}</code>"
            entry.append(link_line)
            if channel:
                entry.append(f"<i>来源: @{channel}</i>")

            lines.append("\n".join(entry))

        lines.append("━" * 22)
        lines.append("💡 发送任意新关键词可直接发起搜索")
        text = "\n\n".join(lines)

        # Pagination inline buttons
        buttons = []
        row = []
        if page > 1:
            row.append({"text": "⬅️ 上一页", "callback_data": f"p:{page-1}:{query[:25]}"})
        row.append({"text": f"{page} / {total_pages}", "callback_data": "noop"})
        if page < total_pages:
            row.append({"text": "下一页 ➡️", "callback_data": f"p:{page+1}:{query[:25]}"})

        if row:
            buttons.append(row)

        return text, {"inline_keyboard": buttons}

    async def handle_start(self, chat_id: int):
        text = (
            "🤖 <b>欢迎使用 网盘资源搜索机器人 (PanSou)</b>\n\n"
            "✨ <b>功能与使用指南：</b>\n"
            "• <b>直接搜索</b>：无需任何前缀，直接把想找的电影、剧集、书籍名发给我，例如：\n"
            "  <code>庆余年</code>、<code>黑神话</code>、<code>考研数学</code>\n"
            "• <b>/stats</b>：查看当前收录的资源量及各网盘分布\n"
            "• <b>/crawl</b>：手动触发最新资源抓取（限管理员）\n"
            "• <b>/help</b>：查看本帮助信息\n\n"
            "⚡ 资源持续从 Telegram 多个热门频道自动收录，自动去重与分类！"
        )
        await self.api_call("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        })

    async def handle_stats(self, chat_id: int):
        stats = get_stats(self.db_path)
        total = stats.get("total", 0)
        by_type = stats.get("by_type", {})
        by_channel = stats.get("by_channel", {})
        latest = stats.get("latest")

        lines = [
            "📊 <b>网盘资源库统计</b>",
            "━" * 20,
            f"📦 <b>已收录有效资源总量</b>: <code>{total}</code> 条",
            "",
            "<b>📁 各网盘类型分布:</b>"
        ]
        if by_type:
            for pan, count in by_type.items():
                pct = f"{(count / total * 100):.1f}%" if total > 0 else "0%"
                lines.append(f"  • {pan}: <code>{count}</code> 条 ({pct})")
        else:
            lines.append("  (暂无数据，请先运行爬虫)")

        if by_channel:
            lines.append("\n<b>📢 热门来源频道:</b>")
            for ch, count in by_channel.items():
                lines.append(f"  • @{ch}: <code>{count}</code> 条")

        if latest:
            lines.append(f"\n🕒 <b>最新收录</b>: {latest.get('title')} ({latest.get('created_at')})")

        lines.append("━" * 20)
        await self.api_call("sendMessage", {
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "parse_mode": "HTML"
        })

    async def handle_search(self, chat_id: int, query: str, page: int = 1, message_id: Optional[int] = None):
        offset = (page - 1) * PAGE_SIZE
        results, total = search(query, limit=PAGE_SIZE, offset=offset, db_path=self.db_path)
        text, reply_markup = self.format_search_results(query, results, total, page)

        if message_id:
            # Edit existing message (for pagination)
            await self.api_call("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_web_page_preview": True
            })
        else:
            await self.api_call("sendMessage", {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_web_page_preview": True
            })

    async def handle_crawl_trigger(self, chat_id: int, user_id: int):
        if ADMIN_USER_IDS and user_id not in ADMIN_USER_IDS:
            await self.api_call("sendMessage", {
                "chat_id": chat_id,
                "text": "❌ 您没有权限触发全量抓取任务。"
            })
            return

        if self.is_crawling:
            await self.api_call("sendMessage", {
                "chat_id": chat_id,
                "text": "⏳ 爬虫任务正在后台运行中，请勿重复触发。"
            })
            return

        self.is_crawling = True
        await self.api_call("sendMessage", {
            "chat_id": chat_id,
            "text": "🚀 已启动后台频道抓取任务，抓取完成后将通知您..."
        })

        async def run_crawler_bg():
            try:
                summary = await self.crawler.crawl_all(max_pages=2)
                self.is_crawling = False
                report = (
                    "✅ <b>后台爬虫抓取完成！</b>\n"
                    f"• 扫描消息：<code>{summary['scanned']}</code> 条\n"
                    f"• 提取链接：<code>{summary['found']}</code> 个\n"
                    f"• 成功入库：<code>{summary['inserted']}</code> 个\n"
                    f"• 重复过滤：<code>{summary['duplicate']}</code> 个"
                )
                await self.api_call("sendMessage", {
                    "chat_id": chat_id,
                    "text": report,
                    "parse_mode": "HTML"
                })
            except Exception as e:
                self.is_crawling = False
                await self.api_call("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"❌ 抓取任务异常: {e}"
                })

        asyncio.create_task(run_crawler_bg())

    async def process_update(self, update: Dict[str, Any]):
        # Handle button callback queries
        if "callback_query" in update:
            cb = update["callback_query"]
            cb_id = cb["id"]
            data = cb.get("data", "")
            msg = cb.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            message_id = msg.get("message_id")

            await self.api_call("answerCallbackQuery", {"callback_query_id": cb_id})

            if data == "noop":
                return
            if data.startswith("p:"):
                parts = data.split(":", 2)
                if len(parts) == 3:
                    try:
                        page = int(parts[1])
                        query = parts[2]
                        await self.handle_search(chat_id, query, page=page, message_id=message_id)
                    except Exception as e:
                        print(f"Pagination error: {e}")
            return

        # Handle regular messages
        if "message" in update:
            msg = update["message"]
            chat_id = msg.get("chat", {}).get("id")
            user_id = msg.get("from", {}).get("id")
            text = (msg.get("text") or "").strip()

            if not text:
                return

            if text in {"/start", "/help"}:
                await self.handle_start(chat_id)
            elif text == "/stats":
                await self.handle_stats(chat_id)
            elif text == "/crawl":
                await self.handle_crawl_trigger(chat_id, user_id)
            elif text.startswith("/search"):
                parts = text.split(maxsplit=1)
                if len(parts) > 1:
                    await self.handle_search(chat_id, parts[1].strip())
                else:
                    await self.api_call("sendMessage", {
                        "chat_id": chat_id,
                        "text": "💡 请输入要搜索的关键词，例如：<code>/search 庆余年</code>",
                        "parse_mode": "HTML"
                    })
            else:
                # Any plain text is treated as a search query!
                await self.handle_search(chat_id, text)

    async def run(self):
        """
        Starts the Telegram Bot long polling loop.
        """
        print("🤖 正在连接 Telegram Bot 服务...")
        me = await self.api_call("getMe")
        if not me:
            print("❌ 无法连接 Telegram Bot API，请检查：")
            print("  1. BOT_TOKEN 是否正确配置在 .env 文件中")
            print("  2. 如果你在国内，是否在 .env 中配置了有效的 PROXY（如 PROXY=http://127.0.0.1:7890）")
            return

        bot_name = me.get("first_name", "Bot")
        username = me.get("username", "")
        print(f"✅ Bot 登录成功: {bot_name} (@{username})")
        print("⚡ Bot 正在监听消息中... (按 Ctrl+C 停止)")

        offset = 0
        while True:
            try:
                updates = await self.api_call("getUpdates", {
                    "offset": offset,
                    "timeout": 30,
                    "allowed_updates": ["message", "callback_query"]
                })
                if updates:
                    for update in updates:
                        offset = max(offset, update["update_id"] + 1)
                        await self.process_update(update)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Polling Exception] {e}")
                await asyncio.sleep(3)

if __name__ == "__main__":
    from database import init_db
    init_db()
    bot = PansouTelegramBot()
    asyncio.run(bot.run())
