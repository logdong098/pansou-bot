import re
from typing import List, Dict, Any, Optional

# Supported cloud drive patterns: (pan_type, regex_pattern, display_name, icon)
PAN_RULES = [
    {
        "type": "quark",
        "name": "夸克网盘",
        "icon": "⚡",
        "pattern": re.compile(r"https?://pan\.quark\.cn/s/([a-zA-Z0-9]+)", re.IGNORECASE),
        "clean_url": lambda m: f"https://pan.quark.cn/s/{m.group(1)}",
    },
    {
        "type": "baidu",
        "name": "百度网盘",
        "icon": "☁️",
        "pattern": re.compile(r"https?://pan\.baidu\.com/s/([a-zA-Z0-9_-]+)", re.IGNORECASE),
        "clean_url": lambda m: f"https://pan.baidu.com/s/{m.group(1)}",
    },
    {
        "type": "aliyun",
        "name": "阿里云盘",
        "icon": "🚀",
        "pattern": re.compile(r"https?://(?:www\.)?(?:alipan\.com|aliyundrive\.com)/s/([a-zA-Z0-9]+)", re.IGNORECASE),
        "clean_url": lambda m: f"https://www.alipan.com/s/{m.group(1)}",
    },
    {
        "type": "uc",
        "name": "UC网盘",
        "icon": "🐿️",
        "pattern": re.compile(r"https?://(?:drive|fast)\.uc\.cn/s/([a-zA-Z0-9]+)", re.IGNORECASE),
        "clean_url": lambda m: f"https://drive.uc.cn/s/{m.group(1)}",
    },
    {
        "type": "xunlei",
        "name": "迅雷云盘",
        "icon": "⚡",
        "pattern": re.compile(r"https?://pan\.xunlei\.com/s/([a-zA-Z0-9_-]+)", re.IGNORECASE),
        "clean_url": lambda m: f"https://pan.xunlei.com/s/{m.group(1)}",
    },
    {
        "type": "115",
        "name": "115网盘",
        "icon": "📦",
        "pattern": re.compile(r"https?://(?:anxia\.com|115\.com)/s/([a-zA-Z0-9]+)", re.IGNORECASE),
        "clean_url": lambda m: f"https://115.com/s/{m.group(1)}",
    },
    {
        "type": "tianyi",
        "name": "天翼云盘",
        "icon": "翼",
        "pattern": re.compile(r"https?://cloud\.189\.cn/(?:t|web/share\?code=)/?([a-zA-Z0-9_-]+)", re.IGNORECASE),
        "clean_url": lambda m: f"https://cloud.189.cn/t/{m.group(1)}",
    },
    {
        "type": "pikpak",
        "name": "PikPak",
        "icon": "🅿️",
        "pattern": re.compile(r"https?://(?:mypikpak\.com|pikpak\.me)/s/([a-zA-Z0-9]+)", re.IGNORECASE),
        "clean_url": lambda m: f"https://mypikpak.com/s/{m.group(1)}",
    },
]

# Pattern to extract access/pwd code near a link
CODE_PATTERNS = [
    re.compile(r"(?:提取码|密码|访问码|pwd|code)[：:\s]*([a-zA-Z0-9]{4,6})", re.IGNORECASE),
    re.compile(r"码[：:\s]*([a-zA-Z0-9]{4,6})", re.IGNORECASE),
]

def extract_title(text: str) -> str:
    """
    Extracts a concise, representative title from the Telegram message text.
    Filters out common noise, bot promotions, tags, and URLs.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return "未命名资源"

    candidate = ""
    for line in lines:
        # Skip lines that are purely URLs
        if re.match(r"^https?://\S+$", line):
            continue
        # Skip pure hashtag or divider lines
        if re.match(r"^[#\-_*=\s\./]+$", line):
            continue
        # Remove common prefixes like '🎬 片名：', '【名称】', '◎译　　名'
        cleaned = re.sub(
            r"^(?:🎬|🎥|📺|📁|🍿|📖|🎮|📦)?\s*(?:片名|名称|书名|剧名|资源|影视|标题|◎译\s*名|◎片\s*名)[：:\s【\[]*",
            "",
            line,
        )
        cleaned = re.sub(r"[】\]]$", "", cleaned).strip()
        # Remove leading hashtags
        cleaned = re.sub(r"^#\S+\s*", "", cleaned).strip()
        if len(cleaned) >= 2:
            candidate = cleaned
            break

    if not candidate:
        candidate = lines[0]

    # Clean up trailing noise
    candidate = re.sub(r"https?://\S+", "", candidate).strip()
    # Limit length
    if len(candidate) > 120:
        candidate = candidate[:120] + "..."
    return candidate or "未命名资源"

def extract_code(text: str, link_pos: int, link_str: str = "") -> Optional[str]:
    """
    Looks for extraction code strictly associated with this link
    (on the same line, or next line if no subsequent link).
    """
    # Find line containing link
    lines = text.split("\n")
    cur_pos = 0
    target_line_idx = -1
    for idx, line in enumerate(lines):
        next_pos = cur_pos + len(line) + 1
        if cur_pos <= link_pos < next_pos:
            target_line_idx = idx
            break
        cur_pos = next_pos

    if target_line_idx == -1:
        return None

    # Check the same line first
    same_line = lines[target_line_idx]
    for pat in CODE_PATTERNS:
        m = pat.search(same_line)
        if m:
            code = m.group(1)
            if code.lower() not in {"1080", "2160", "720p", "4k", "mp4", "mkv"}:
                return code

    # Check next line if it doesn't have a new URL
    if target_line_idx + 1 < len(lines):
        next_line = lines[target_line_idx + 1]
        if "http://" not in next_line and "https://" not in next_line:
            for pat in CODE_PATTERNS:
                m = pat.search(next_line)
                if m:
                    code = m.group(1)
                    if code.lower() not in {"1080", "2160", "720p", "4k", "mp4", "mkv"}:
                        return code

    return None

def parse_message(
    text: str, channel: str = "", message_id: int = 0
) -> List[Dict[str, Any]]:
    """
    Parses a Telegram message, extracting all cloud drive links and metadata.
    Returns a list of resource dicts.
    """
    if not text:
        return []

    title = extract_title(text)
    resources = []
    seen_urls = set()

    for rule in PAN_RULES:
        for match in rule["pattern"].finditer(text):
            clean_url = rule["clean_url"](match)
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            code = extract_code(text, match.start())
            resources.append({
                "url": clean_url,
                "pan_type": rule["type"],
                "pan_name": rule["name"],
                "pan_icon": rule["icon"],
                "code": code or "",
                "title": title,
                "content": text[:800],  # Keep raw text excerpt for context
                "channel": channel,
                "message_id": message_id,
            })

    return resources
