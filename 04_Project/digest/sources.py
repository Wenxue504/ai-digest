"""源清单。

只收实测可用的源。已淘汰的写在文件末尾的 EXCLUDED 里，附淘汰原因——
免得半年后又有人把它加回来重踩一遍。

改这里之后要同步 03_OutputFiles/reports/ 里的源可达性表。
"""

SOURCES = [
    {
        "id": "qbitai",
        "name": "量子位",
        "url": "https://www.qbitai.com/feed",
        "weight": 1.0,
        "lang": "zh",
    },
    {
        "id": "deepmind",
        "name": "DeepMind",
        "url": "https://deepmind.google/blog/rss.xml",
        "weight": 1.0,
        "lang": "en",
    },
    {
        "id": "googleai",
        "name": "Google AI",
        "url": "https://blog.google/technology/ai/rss/",
        "weight": 1.0,
        "lang": "en",
    },
    {
        "id": "infoq",
        "name": "InfoQ 中文",
        "url": "https://www.infoq.cn/feed",
        "weight": 0.9,
        "lang": "zh",
    },
    {
        "id": "mittr",
        "name": "MIT 科技评论",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
        "weight": 0.9,
        "lang": "en",
    },
    {
        "id": "techcrunch",
        "name": "TechCrunch",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "weight": 0.9,
        "lang": "en",
    },
    {
        "id": "verge",
        "name": "The Verge",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "weight": 0.8,
        "lang": "en",
    },
    {
        "id": "hn",
        "name": "Hacker News",
        "url": "https://hnrss.org/frontpage",
        "weight": 0.55,
        "lang": "en",
    },
    {
        "id": "ars",
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "weight": 0.5,
        "lang": "en",
    },
]

# 抓不到 / 已死的源。别删，删了下次还会有人加。
EXCLUDED = {
    "jiqizhixin": "https://www.jiqizhixin.com/rss —— 返回 HTML（数据服务页），RSS 已失效",
    "36kr": "https://36kr.com/feed —— 火山引擎 WAF 的 JS 挑战，curl 拿不到",
    "openai": "https://openai.com/blog/rss.xml —— TCP 直连超时，本机无代理可绕",
    "huggingface": "https://huggingface.co/blog/feed.xml —— 同上",
    "arxiv": "http://export.arxiv.org/rss/cs.AI —— 有效但周末 skipDays 为空，工作日再评估接入",
    "venturebeat": "https://venturebeat.com/category/ai/feed/ —— 最新条目停在 2026-08-27，已停更",
}
