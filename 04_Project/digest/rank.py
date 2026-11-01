"""去重、打分、分类。

规则与 docs/ranking.md 一一对应。改这里必须同一次提交里改那份文档。

⚠️ 匹配规则：ASCII 词必须按「词边界」匹配。
   早期版本用 `"ai" in text`，结果 `explained` / `available` / `said` 全部命中，
   一堆非 AI 的 HN 帖子涌进候选池（Show HN: 8-bit computer 排到第一名）。
"""

import hashlib
import re
from difflib import SequenceMatcher

CLS_ACCEPT = ("模型", "产品", "资本", "研究", "政策", "硬件")

# 泛科技源（不专做 AI），必须过相关性闸门
GENERIC_SOURCES = {"hn", "ars", "infoq"}

AI_TERMS = (
    "ai", "a.i.", "artificial intelligence", "llm", "gpt", "chatgpt", "openai",
    "anthropic", "claude", "gemini", "deepseek", "qwen", "llama", "mistral",
    "agent", "agents", "transformer", "diffusion", "rag", "embedding", "copilot",
    "gpu", "nvidia", "tpu", "machine learning", "deep learning", "neural",
    "model", "models", "prompt", "fine-tuning", "inference",
    "人工智能", "大模型", "模型", "智能体", "机器学习", "深度学习", "神经网络",
    "生成式", "文生图", "文生视频", "多模态", "推理", "训练", "算力", "通义",
    "豆包", "aigc",
)

CATEGORY_RULES = [
    ("资本", ("融资", "收购", "估值", "ipo", "并购", "上市", "亿元", "轮融资",
              "funding", "fundraise", "acquire", "acquisition", "valuation",
              "series a", "series b", "raises")),
    ("政策", ("监管", "法案", "合规", "诉讼", "禁令", "版权", "反垄断", "备案",
              "法院", "裁定", "判决", "裁决", "侵权", "处罚", "罚款",
              "regulation", "regulator", "lawsuit", "ban", "policy", "antitrust",
              "copyright", "court", "ruling", "fine")),
    ("硬件", ("芯片", "算力", "数据中心", "晶圆", "台积电", "英伟达",
              "chip", "chips", "datacenter", "data center", "semiconductor",
              "nvidia", "tsmc", "wafer")),
    ("研究", ("论文", "arxiv", "基准", "数据集", "实验室", "顶会", "研究",
              "paper", "benchmark", "dataset", "research", "study", "researchers")),
    ("模型", ("发布", "开源", "参数", "推理", "训练", "上下文", "模型",
              "model", "release", "released", "open-source", "open source",
              "training", "inference", "context window", "parameters")),
]

# (加分, 关键词组) —— 每组最多命中一次
BOOST_RULES = [
    (1.5, ("发布", "开源", "上线", "release", "released", "launch", "launches",
           "open-source", "open source", "unveils")),
    (1.2, ("openai", "gpt", "gemini", "claude", "deepseek", "qwen", "通义",
           "豆包", "llama", "anthropic")),
    (1.0, ("融资", "收购", "估值", "ipo", "funding", "fundraise", "acquire",
           "valuation", "raises")),
    (1.0, ("芯片", "gpu", "算力", "数据中心", "tsmc", "nvidia", "chip")),
    (0.8, ("agent", "rag", "微调", "评测", "benchmark", "数据集", "论文",
           "fine-tuning", "dataset", "paper")),
]

NEGATIVE = ("招聘", "直播预告", "课程", "折扣", "广告", "促销", "抽奖",
            "sponsored", "webinar", "hiring", "coupon", "giveaway",
            "early bird", "register now", "tickets", "summit")

_DROP_RE = re.compile(r"[^\w\u4e00-\u9fff]+")
_POINTS_RE = re.compile(r"Points:\s*(\d+)")
_ASCII_RE = re.compile(r"[a-z0-9\.\- ]+")
_pattern_cache = {}


def _pattern(term: str) -> re.Pattern:
    cached = _pattern_cache.get(term)
    if cached is None:
        if _ASCII_RE.fullmatch(term):
            cached = re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])")
        else:
            cached = re.compile(re.escape(term))
        _pattern_cache[term] = cached
    return cached


def hits(haystack: str, terms) -> bool:
    """haystack 必须已转小写。"""
    return any(_pattern(t).search(haystack) for t in terms)


def normalize(text: str) -> str:
    return _DROP_RE.sub("", (text or "").lower())


def item_id(url: str) -> str:
    """稳定 id：同一链接在任何一次运行里都得到同一个 id。"""
    return hashlib.sha1(url.split("?")[0].strip().lower().encode()).hexdigest()[:12]


def is_ai_related(item) -> bool:
    if item["source_id"] not in GENERIC_SOURCES:
        return True
    haystack = (item["title"] + " " + item["summary"]).lower()
    return hits(haystack, AI_TERMS)


def classify(item) -> str:
    haystack = (item["title"] + " " + item["summary"]).lower()
    for name, keywords in CATEGORY_RULES:
        if hits(haystack, keywords):
            return name
    return "产品"


def hn_points(item) -> int:
    if item["source_id"] != "hn":
        return -1
    match = _POINTS_RE.search(item["summary"])
    return int(match.group(1)) if match else -1


def score(item, now) -> float:
    value = item["weight"]
    age_hours = (now - item["published"]).total_seconds() / 3600

    if age_hours <= 6:
        value += 2.0
    elif age_hours <= 12:
        value += 1.5
    elif age_hours <= 24:
        value += 1.0

    haystack = (item["title"] + " " + item["summary"]).lower()
    for bonus, keywords in BOOST_RULES:
        if hits(haystack, keywords):
            value += bonus

    # 泛科技源：标题里没有 AI 词、只在正文顺带提一句的，不算 AI 新闻。
    # 否则「Show HN: 8-bit computer」这种正文提到 Claude 的帖子会顶到第一。
    if item["source_id"] in GENERIC_SOURCES and not hits(item["title"].lower(), AI_TERMS):
        value -= 1.5

    if hits(haystack, NEGATIVE):
        value -= 3
    # 只罚「拿到了摘要但很短」；完全不提供摘要的源不该被罚——
    # InfoQ 只给一句「点击查看原文」，按长度扣分会把整个源挤到后面。
    if item["summary"] and len(item["summary"]) < 20:
        value -= 1
    points = hn_points(item)
    if points >= 0 and points < 100:
        value -= 2

    return round(value, 2)


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def dedupe(items):
    """同 URL 去重；标题相似度 ≥0.78 视为同一条，保留来源权重高的。"""
    items = sorted(items, key=lambda x: x["weight"], reverse=True)
    kept = []
    seen_urls = set()
    for item in items:
        url_key = item["url"].split("?")[0].rstrip("/").lower()
        if url_key in seen_urls:
            continue
        norm = normalize(item["title"])
        if any(_similar(norm, prior["_norm"]) >= 0.78 for prior in kept):
            continue
        item["_norm"] = norm
        seen_urls.add(url_key)
        kept.append(item)
    return kept


def rank(items, now, limit: int):
    """过滤 → 去重 → 打分 → 截断。返回 (候选池, 被丢弃数)。"""
    fresh = [
        i for i in items
        if i["published"] and (now - i["published"]).total_seconds() <= 48 * 3600
    ]
    relevant = [i for i in fresh if is_ai_related(i)]
    dropped = len(items) - len(relevant)

    unique = dedupe(relevant)
    dropped += len(relevant) - len(unique)

    for item in unique:
        item["score"] = score(item, now)
        item["category"] = classify(item)

    unique.sort(key=lambda x: x["score"], reverse=True)
    return unique[:limit], dropped
