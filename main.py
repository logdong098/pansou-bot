import argparse
import asyncio
import sys
from config import BOT_TOKEN, PROXY, MONITORED_CHANNELS, CRAWL_INTERVAL_MINUTES, DB_PATH
from database import init_db, search, get_stats
from crawler import TelegramWebCrawler
from bot import PansouTelegramBot

def print_stats():
    stats = get_stats()
    print("\n" + "=" * 45)
    print("📊 网盘资源数据库概览")
    print("=" * 45)
    print(f"📦 收录有效资源总量: {stats['total']} 条")
    print("\n📁 各网盘类型统计:")
    for pan, count in stats["by_type"].items():
        print(f"  • {pan:10s}: {count:6d} 条")
    print("\n📢 前 10 热门来源频道:")
    for ch, count in stats["by_channel"].items():
        print(f"  • @{ch:18s}: {count:6d} 条")
    if stats.get("latest"):
        latest = stats["latest"]
        print(f"\n🕒 最近收录: [{latest.get('pan_name')}] {latest.get('title')} ({latest.get('created_at')})")
    print("=" * 45 + "\n")

def run_cli_search(query: str):
    print(f"\n🔍 正在检索: 「{query}」...")
    results, total = search(query, limit=10, offset=0)
    print(f"📊 匹配到 {total} 条结果 (展示前 10 条):\n")
    if not results:
        print("  未找到相关资源，可尝试更换或缩短关键词。")
        return

    for i, item in enumerate(results, 1):
        icon = item.get("pan_icon") or "📁"
        pan_name = item.get("pan_name") or item.get("pan_type", "").upper()
        title = item["title"]
        url = item["url"]
        code = item.get("code")
        channel = item.get("channel", "")

        print(f"{i:2d}. {icon} [{pan_name}] {title}")
        print(f"    🔗 链接: {url}")
        if code:
            print(f"    🔑 提取码: {code}")
        if channel:
            print(f"    📢 来源: @{channel}")
        print()

async def scheduled_crawler(crawler: TelegramWebCrawler, interval_minutes: int):
    """
    Periodic background crawler loop.
    """
    while True:
        try:
            print(f"\n⏰ [定时任务] 触发频道轮询采集 (周期: {interval_minutes} 分钟)...")
            await crawler.crawl_all(max_pages=2)
        except Exception as e:
            print(f"[Scheduled Crawler Error] {e}")
        await asyncio.sleep(interval_minutes * 60)

async def run_all():
    """
    Runs both the Telegram Bot and background periodic crawler.
    """
    init_db()
    crawler = TelegramWebCrawler()
    bot = PansouTelegramBot()

    print("\n🌟 启动全套服务: Telegram Bot + 后台定时爬虫...")
    await asyncio.gather(
        bot.run(),
        scheduled_crawler(crawler, CRAWL_INTERVAL_MINUTES)
    )

def main():
    parser = argparse.ArgumentParser(description="PanSou 网盘资源检索与 Telegram Bot 系统")
    subparsers = parser.add_subparsers(dest="command", help="可用子命令")

    # Command: init
    subparsers.add_parser("init", help="初始化数据库表结构")

    # Command: crawl
    crawl_parser = subparsers.add_parser("crawl", help="手动运行爬虫采集公开 TG 频道")
    crawl_parser.add_argument("--channel", "-c", type=str, help="指定单个频道抓取，例如: yunpanpan")
    crawl_parser.add_argument("--pages", "-p", type=int, default=3, help="每个频道回溯抓取的页数 (默认 3)")

    # Command: bot
    subparsers.add_parser("bot", help="启动 Telegram Bot 搜索交互服务")

    # Command: run (both bot and periodic crawler)
    subparsers.add_parser("run", help="同时启动 Bot 与后台定时爬虫任务")

    # Command: search
    search_parser = subparsers.add_parser("search", help="直接在终端命令行搜索资源")
    search_parser.add_argument("query", type=str, help="搜索关键词，例如: 庆余年")

    # Command: stats
    subparsers.add_parser("stats", help="查看数据库统计信息")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    init_db()

    if args.command == "init":
        print("✅ 数据库与 FTS5 全文索引初始化成功！")
    elif args.command == "stats":
        print_stats()
    elif args.command == "search":
        run_cli_search(args.query)
    elif args.command == "crawl":
        crawler = TelegramWebCrawler()
        if args.channel:
            asyncio.run(crawler.crawl_channel(args.channel, max_pages=args.pages))
        else:
            asyncio.run(crawler.crawl_all(max_pages=args.pages))
    elif args.command == "bot":
        bot = PansouTelegramBot()
        asyncio.run(bot.run())
    elif args.command == "run":
        asyncio.run(run_all())

if __name__ == "__main__":
    main()
