import sqlite3
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import jieba

from config import DB_PATH

def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def tokenize_chinese(text: str) -> str:
    """
    Tokenizes text with jieba into space-separated words for FTS indexing and querying.
    """
    if not text:
        return ""
    # Filter out special punctuation to keep clean search tokens
    words = jieba.cut_for_search(text)
    clean_words = [w.strip() for w in words if len(w.strip()) > 0 and not re.match(r"^[\s\.,!?;:\"'()\[\]{}<>#@/\\|~`+=*&^%$]+$", w)]
    return " ".join(clean_words)

def init_db(db_path: str = DB_PATH):
    """
    Initializes the SQLite schema and FTS5 full-text search table.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Main resources table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            pan_type TEXT NOT NULL,
            pan_name TEXT NOT NULL,
            pan_icon TEXT NOT NULL,
            code TEXT DEFAULT '',
            title TEXT NOT NULL,
            content TEXT DEFAULT '',
            channel TEXT DEFAULT '',
            message_id INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_res_type ON resources(pan_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_res_channel ON resources(channel);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_res_created ON resources(created_at);")

        # FTS5 full-text virtual table
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(
            resource_id UNINDEXED,
            title,
            tokens,
            content
        );
        """)
        conn.commit()

def save_resources(resources: List[Dict[str, Any]], db_path: str = DB_PATH) -> Tuple[int, int]:
    """
    Batch saves resources with URL deduplication.
    Returns (inserted_count, duplicate_count).
    """
    if not resources:
        return 0, 0

    inserted = 0
    duplicate = 0

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for res in resources:
            try:
                cursor.execute("""
                INSERT INTO resources (url, pan_type, pan_name, pan_icon, code, title, content, channel, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    res["url"],
                    res["pan_type"],
                    res.get("pan_name", ""),
                    res.get("pan_icon", ""),
                    res.get("code", ""),
                    res["title"],
                    res.get("content", ""),
                    res.get("channel", ""),
                    res.get("message_id", 0)
                ))
                new_id = cursor.lastrowid

                # Tokenize title & content for FTS
                combined_text = f"{res['title']} {res.get('content', '')}"
                tokens = tokenize_chinese(combined_text)

                cursor.execute("""
                INSERT INTO resources_fts (resource_id, title, tokens, content)
                VALUES (?, ?, ?, ?)
                """, (new_id, res["title"], tokens, res.get("content", "")))

                inserted += 1
            except sqlite3.IntegrityError:
                # URL already exists -> duplicate!
                duplicate += 1
            except Exception as e:
                print(f"[DB Error] insert error: {e}")

        conn.commit()

    return inserted, duplicate

def search(
    query: str,
    pan_type: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    db_path: str = DB_PATH
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Full-text search on resources by keyword with optional pan_type filter.
    Returns (results, total_count).
    """
    clean_q = query.strip()
    if not clean_q:
        return [], 0

    # Tokenize search query with jieba
    tokens = tokenize_chinese(clean_q)
    token_list = tokens.split() if tokens else [clean_q]

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Try FTS5 search first
        fts_conditions = []
        for t in token_list:
            safe_t = t.replace('"', '""')
            fts_conditions.append(f'"{safe_t}"')
        fts_query = " AND ".join(fts_conditions)

        results = []
        total = 0

        if fts_query:
            sql_count = """
            SELECT COUNT(DISTINCT r.id) as total
            FROM resources r
            JOIN resources_fts f ON r.id = f.resource_id
            WHERE resources_fts MATCH ?
            """
            params_count: List[Any] = [fts_query]
            if pan_type:
                sql_count += " AND r.pan_type = ?"
                params_count.append(pan_type)

            try:
                cursor.execute(sql_count, params_count)
                row = cursor.fetchone()
                total = row["total"] if row else 0

                if total > 0:
                    sql_data = """
                    SELECT r.*, bm25(resources_fts) as rank
                    FROM resources r
                    JOIN resources_fts f ON r.id = f.resource_id
                    WHERE resources_fts MATCH ?
                    """
                    params_data: List[Any] = [fts_query]
                    if pan_type:
                        sql_data += " AND r.pan_type = ?"
                        params_data.append(pan_type)

                    sql_data += " ORDER BY rank ASC, r.id DESC LIMIT ? OFFSET ?"
                    params_data.extend([limit, offset])

                    cursor.execute(sql_data, params_data)
                    results = [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                print(f"[Search FTS5 Error] {e}")

        # 2. Fallback to LIKE if FTS5 returned 0 results
        if not results:
            like_pat = f"%{clean_q}%"
            sql_like_count = "SELECT COUNT(*) as total FROM resources WHERE (title LIKE ? OR content LIKE ?)"
            params_like_count: List[Any] = [like_pat, like_pat]
            if pan_type:
                sql_like_count += " AND pan_type = ?"
                params_like_count.append(pan_type)

            cursor.execute(sql_like_count, params_like_count)
            row = cursor.fetchone()
            total = row["total"] if row else 0

            if total > 0:
                sql_like_data = """
                SELECT * FROM resources
                WHERE (title LIKE ? OR content LIKE ?)
                """
                params_like_data: List[Any] = [like_pat, like_pat]
                if pan_type:
                    sql_like_data += " AND pan_type = ?"
                    params_like_data.append(pan_type)

                sql_like_data += " ORDER BY id DESC LIMIT ? OFFSET ?"
                params_like_data.extend([limit, offset])

                cursor.execute(sql_like_data, params_like_data)
                results = [dict(row) for row in cursor.fetchall()]

        return results, total

def get_stats(db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Returns statistics about indexed resources.
    """
    stats: Dict[str, Any] = {
        "total": 0,
        "by_type": {},
        "by_channel": {},
        "latest": None
    }
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        # Total
        cursor.execute("SELECT COUNT(*) as cnt FROM resources")
        row = cursor.fetchone()
        stats["total"] = row["cnt"] if row else 0

        # By type
        cursor.execute("SELECT pan_name, pan_type, COUNT(*) as cnt FROM resources GROUP BY pan_type ORDER BY cnt DESC")
        for r in cursor.fetchall():
            stats["by_type"][r["pan_name"] or r["pan_type"]] = r["cnt"]

        # By channel
        cursor.execute("SELECT channel, COUNT(*) as cnt FROM resources WHERE channel != '' GROUP BY channel ORDER BY cnt DESC LIMIT 10")
        for r in cursor.fetchall():
            stats["by_channel"][r["channel"]] = r["cnt"]

        # Latest
        cursor.execute("SELECT title, pan_name, created_at FROM resources ORDER BY id DESC LIMIT 1")
        latest_row = cursor.fetchone()
        if latest_row:
            stats["latest"] = dict(latest_row)

    return stats
