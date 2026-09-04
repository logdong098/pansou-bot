# PanSou 网盘资源检索与 Telegram Bot 系统

基于 **Telegram 公开频道免登录网页爬虫** + **SQLite FTS5 中文全文检索** + **Telegram Bot** 构建的个人私有网盘资源搜索引擎。

---

## 🌟 系统特色

1. **无需 Telegram API ID & Hash**：
   - 采用 Telegram 官方公开网页预览（`https://t.me/s/频道名`）机制，无需个人账号登录，无封号风险。
2. **极轻量数据存储与高效检索**：
   - 使用 **SQLite + FTS5** 虚拟表与 **Jieba 中文分词**，毫秒级 BM25 检索。
   - **URL 唯一索引去重**：自动过滤多频道转发的重复链接，10 万条资源仅占约 80MB 磁盘。
3. **多网盘协议智能识别**：
   - 自动识别夸克网盘、百度网盘、阿里云盘、UC网盘、迅雷云盘、115网盘、天翼云盘、PikPak。
   - 自动近邻匹配提取码/访问码。
4. **全功能 Telegram Bot**：
   - 支持自然语言直接搜索、翻页按钮切换、资源分类徽标、数据库统计等。
   - 提供命令行（CLI）调试与搜索功能，脱离 Bot 也能本地检索。

---

## 📁 目录结构

```
pansou/
├── .env                  # 运行配置文件（Bot Token、代理、频道列表）
├── .env.example          # 配置模板
├── requirements.txt      # 依赖包列表
├── config.py             # 配置加载模块
├── database.py           # SQLite + FTS5 中文分词与检索
├── parser.py             # 消息解析与网盘链接/提取码提取
├── crawler.py            # Telegram 公开频道异步爬虫
├── bot.py                # Telegram 交互机器人
├── main.py               # CLI 统一管理入口
└── README.md             # 说明文档
```
---

## 🚀 快速上手

### 1. 安装依赖

本项目已在本地预装好所需依赖，如需手动安装：
```bash
pip install -r requirements.txt
```

### 2. 申请 Telegram Bot Token（1 分钟搞定）

1. 打开 Telegram，搜索官方机器人：[@BotFather](https://t.me/BotFather)
2. 发送 `/newbot`，按照提示输入：
   - 机器人昵称（例如：`我的网盘搜索`）
   - 机器人用户名（必须以 `bot` 结尾，例如：`my_pansou_bot`）
3. 复制获得的 **HTTP API Token**（格式如：`123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`）。

### 3. 配置 `.env` 文件

编辑当前目录下的 `.env`：
```bash
# 必填：填入刚申请的 Bot Token
BOT_TOKEN=your_telegram_bot_token

# 选填：国内网络环境下如果无法直连 Telegram，请配置本地代理（支持 HTTP 或 SOCKS5）
# PROXY=http://127.0.0.1:7890

# 监控的频道（无需 @，英文逗号分隔）
CHANNELS=yunpanpan,ucpanpan,yppshare,hao1234cn,Quark_Share_Group,alyp_4K_remux,shareAliyun
```

---

## 🛠️ 常用运行命令

### 1. 命令行直接搜索（无需启动 Bot）
在终端中随时测试搜索：
```bash
python3 main.py search 庆余年
python3 main.py search 黑神话
```

### 2. 查看数据库统计
```bash
python3 main.py stats
```

### 3. 手动运行爬虫采集频道
采集配置中的所有频道：
```bash
python3 main.py crawl --pages 3
```
或者单独抓取某一个指定频道：
```bash
python3 main.py crawl --channel yunpanpan --pages 5
```

### 4. 启动 Telegram 搜索机器人
```bash
python3 main.py bot
```
启动后，打开 Telegram 找到你的 Bot，发送任意关键词即可搜索：
- 直接输入电影/剧集/资料名（如：`庆余年`）
- 发送 `/stats` 查看收录统计
- 发送 `/help` 查看指令帮助

### 5. 一键同时运行 Bot 与后台定时爬虫
如果你在本地直接运行：
```bash
python3 main.py run
```
系统会启动 Telegram Bot，并在后台每隔指定周期（默认 60 分钟）自动增量抓取最新资源。

---

## 🐳 Docker Compose 容器化部署（推荐）

本项目已完整支持 Docker 与 Docker Compose 部署，数据自动持久化在 `./data` 目录。

### 1. 配置环境变量
确保已在 `.env` 中填写了你的 `BOT_TOKEN`：
```bash
cp .env.example .env
vim .env
```
> **提示（代理设置）**：如果你的 Docker 容器需要通过宿主机科学上网代理连接 Telegram：
> - 代理地址请填写：`PROXY=http://host.docker.internal:7890`（已在 `docker-compose.yml` 中配置好 host 映射）
> - 如果部署在境外 VPS 上，则无需设置 `PROXY`。

### 2. 一键构建与启动
```bash
docker compose up -d --build
```

### 3. 查看运行日志
```bash
docker compose logs -f
```

### 4. 停止与重启
```bash
# 停止容器
docker compose down

# 重启容器
docker compose restart
```

---

## 💡 进阶维护与建议

- **数据持久化**：SQLite 数据库存放在宿主机的 `./data/pansou.db` 中，容器重建或升级代码数据不会丢失。
- **添加更多资源频道**：在 `.env` 的 `CHANNELS` 后面追加高质量公开频道用户名即可。
- **在容器中手动触发全量爬虫**：
  ```bash
  docker compose exec pansou python main.py crawl --pages 5
  ```
- **在容器中查看统计**：
  ```bash
  docker compose exec pansou python main.py stats
  ```
