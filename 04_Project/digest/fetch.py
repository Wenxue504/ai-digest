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
MAX_FEED_BYTES = 8 * 1024 * 1024  # 单个 feed 上限，防超大响应与 gzip 炸弹
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# 有些源不给摘要，只放一句「点击查看原文」。这类占位文本要当成空，
# 否则会被排序规则当成「信息量不足」扣分，系统性压低整个源。
_BOILERPLATE = re.compile(
    r"^(点击?查看原文|查看全文|阅读原文|详情请见原文|read more|continue reading|"
    r"read the full (story|article)|\.{3,}|…+)\s*[>»]*$",
    re.IGNORECASE,
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def clean_text(value: str, limit: int = 0) -> str:
    """去标签、解实体、压空白。占位文本归零。limit>0 时截断。"""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    if _BOILERPLATE.match(text):
        return ""
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
        raw = resp.read(MAX_FEED_BYTES + 1)
        if len(raw) > MAX_FEED_BYTES:
            raise ValueError(f"响应超过 {MAX_FEED_BYTES // 1024 // 1024} MB，放弃")
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

        title = link = desc = summary = content = date_text = ""
        for child in node:
            name = _localname(child.tag)
            text = "".join(child.itertext())
            if name == "link":
                href = child.get("href")
                if href and child.get("rel", "alternate") == "alternate" and not link:
                    link = href
                elif text.strip() and not link:
                    link = text.strip()
            elif name == "title":
                title = text
            elif name == "description":
                desc = text
            elif name == "summary":
                summary = text
            elif name in ("content", "encoded"):
                # 同时覆盖 Atom 的 <content> 与 RSS 的 <content:encoded>
                content = text
            elif name in ("pubdate", "published", "updated") and not date_text:
                date_text = text

        title = clean_text(title, 200)
        if not title or not link:
            continue

        out.append(
            {
                "title": title,
                "link": link,
                "summary": clean_text(desc or summary or content, 400),
                "published": parse_date(date_text),
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
