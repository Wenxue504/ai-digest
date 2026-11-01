"""抓取与解析 RSS / Atom。

只用标准库。任何源失败只记 warning 并跳过，绝不中断整轮。
"""

import gzip
import html
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

CST = timezone(timedelta(hours=8))
TIMEOUT = 20
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def clean_text(value: str, limit: int = 0) -> str:
    """去标签、解实体、压空白。limit>0 时截断并补省略号。"""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _localname(tag: str) -> str:
    return tag.split("}")[-1].lower()


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Encoding": "identity"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw


def parse_date(value: str):
    """RFC822（RSS）与 ISO8601（Atom）都吃。解析不了返回 None。"""
    if not value:
        return None
    value = value.strip()
    for parser in (
        lambda s: parsedate_to_datetime(s),
        lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")),
    ):
        try:
            dt = parser(value)
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CST)
    return None


def parse_feed(raw: bytes):
    """返回 [{'title','link','summary','published'}]，解析失败返回 []。"""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        log(f"    XML 解析失败：{exc}")
        return []

    out = []
    for node in root.iter():
        if _localname(node.tag) not in ("item", "entry"):
            continue

        fields = {}
        link = ""
        for child in node:
            name = _localname(child.tag)
            if name == "link":
                # Atom 用 href 属性，RSS 用文本
                href = child.get("href")
                rel = child.get("rel", "alternate")
                if href and rel == "alternate" and not link:
                    link = href
                elif (child.text or "").strip() and not link:
                    link = (child.text or "").strip()
            elif name in ("title", "description", "summary", "content",
                          "pubdate", "published", "updated"):
                # content 常含完整正文，只在没有 summary 时才用
                if name in fields and name == "content":
                    continue
                fields.setdefault(name, "" if name == "content" else "".join(child.itertext()))

        title = clean_text(fields.get("title", ""), 200)
        if not title or not link:
            continue

        excerpt = (
            fields.get("description")
            or fields.get("summary")
            or fields.get("content")
            or ""
        )
        out.append(
            {
                "title": title,
                "link": link,
                "summary": clean_text(excerpt, 400),
                "published": parse_date(
                    fields.get("pubdate")
                    or fields.get("published")
                    or fields.get("updated")
                    or ""
                ),
            }
        )
    return out


def fetch_source(source: dict):
    """抓一个源。失败返回 (None, 错误说明)，不抛给上层。"""
    try:
        raw = fetch_bytes(source["url"])
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, f"连接失败 {exc.reason}"
    except Exception as exc:  # 兜底：任何源异常都不许拖垮整轮
        return None, f"{type(exc).__name__}: {exc}"

    items = parse_feed(raw)
    if not items:
        return None, "解析出 0 条（可能是 HTML 或 WAF 页）"
    return items, None
