"""入口：抓取 → 排序 → 装配当天一期 → 渲染静态站。

一天只有一期（12:00）。18:00 的增量档已于 2026-11-01 移除，
理由：欧美白天新闻在中午那期已经落地，晚间增量太薄，不值得再跑一次。

**候选池只由云端产生，并随 content/pools/ 进 git。** 本机（AI 层）只读那份池、
只写 summaries/，不再自己抓一遍——否则同一期有两个生产者，内容不可复现
（见 01_Requirements/review_2026-11-01.md §7）。

用法：
    python 04_Project/digest/run.py                # 抓取并生成今天这一期（云端用）
    python 04_Project/digest/run.py --dry-run      # 只抓、不写任何文件，看候选池
    python 04_Project/digest/run.py --refresh      # 读已落盘候选池 + 摘要重建（AI 层用）
    python 04_Project/digest/run.py --rerender     # 只把摘要盖回已有期次
    python 04_Project/digest/run.py --export-md    # 额外导出 markdown 报表
"""

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paths import POOLS_DIR, RAW_DIR, REPORTS  # noqa: E402

from digest import build, rank  # noqa: E402
from digest.fetch import fetch_source, log  # noqa: E402
from digest.sources import SOURCES  # noqa: E402

CST = timezone(timedelta(hours=8))
LIMIT = 15
POOL_FOR_AI = 50     # 候选池上限：再多就是在烧额度（见 ADR 0003）
FETCH_DEADLINE = 30  # 整轮抓取墙钟上限（秒），与 AGENTS §4 的承诺一致


def collect(now: datetime):
    """并发抓全部源，返回 (标准化条目, 失败的源名)。

    用**守护线程**而不是 ThreadPoolExecutor：后者的线程是非守护的，
    解释器退出时会 join 它们，所以「墙钟上限」其实封不住——实测 main
    0.2 秒返回、进程 3.3 秒才退。守护线程超时后随进程一起消失，才是真封顶。
    """
    results = {}
    lock = threading.Lock()

    def worker(source):
        items, error = fetch_source(source)
        with lock:
            results[source["id"]] = (items, error)

    threads = []
    for source in SOURCES:
        thread = threading.Thread(
            target=worker, args=(source,), daemon=True, name=f"fetch-{source['id']}"
        )
        thread.start()
        threads.append(thread)

    deadline = time.monotonic() + FETCH_DEADLINE
    for thread in threads:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        thread.join(remaining)

    normalized = []
    failed = []
    for source in SOURCES:
        entry = results.get(source["id"])
        if entry is None:
            log(f"  SLOW {source['name']:<12s} 超过 {FETCH_DEADLINE}s 未返回，跳过")
            failed.append(source["name"])
            continue
        items, error = entry
        status = "OK" if items else "FAIL"
        log(f"  {status:4s} {source['name']:<12s} {len(items or [])} 条"
            + (f"  ({error})" if error else ""))
        if not items:
            failed.append(source["name"])
            continue
        for raw in items:
            normalized.append(
                {
                    "id": rank.item_id(raw["link"]),
                    "title": raw["title"],
                    "url": raw["link"],
                    "summary": raw["summary"],
                    "published": raw["published"],
                    "source": source["name"],
                    "source_id": source["id"],
                    "weight": source["weight"],
                }
            )

    # 有些源会给出「计划发布时间」（实测 InfoQ 会有），不夹住会让它排到未来
    for item in normalized:
        if item["published"] and item["published"] > now:
            item["published"] = now
    return normalized, failed


def pool_path(date_str: str) -> Path:
    return POOLS_DIR / f"{date_str}.json"


def write_pool(items, date_str: str, now: datetime, dropped: int) -> Path:
    """候选池。进 git 的另一半原因：AI 层读的就是这一份（见模块 docstring）。"""
    payload = {
        "date": date_str,
        "generated_at": now.isoformat(),
        "dropped": dropped,
        "candidates": [
            {
                "id": item["id"],
                "title": item["title"],
                "source": item["source"],
                "published": item["published"].isoformat(),
                "category_guess": item.get("category", ""),
                "excerpt": item["summary"][:160],
                "score": item.get("score", 0),
                "url": item["url"],
            }
            for item in items[:POOL_FOR_AI]
        ],
    }
    path = pool_path(date_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_pool(path: Path):
    """读已落盘的候选池，返回 (条目, 淘汰数)。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = [
        {
            "id": candidate["id"],
            "title": candidate["title"],
            "url": candidate["url"],
            "summary": candidate.get("excerpt", ""),
            "published": datetime.fromisoformat(candidate["published"]),
            "source": candidate["source"],
            "source_id": "",
            "weight": 1.0,
            "category": candidate.get("category_guess") or "产品",
            "score": candidate.get("score", 0),
        }
        for candidate in payload.get("candidates", [])
    ]
    return items, payload.get("dropped", 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 AI 行业新闻并生成当天一期报表")
    parser.add_argument("--date", default="", help="默认今天（北京时间）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只抓取并打印候选池，不写任何文件、不生成页面")
    parser.add_argument("--save-raw", action="store_true", help="另存一份候选到 05_Datas/raw/")
    parser.add_argument("--refresh", action="store_true",
                        help="不抓取，读 content/pools/<date>.json + 摘要重建（AI 层用）")
    parser.add_argument("--rerender", action="store_true",
                        help="不抓取，把摘要盖回全部已有期次并重建站点")
    parser.add_argument("--export-md", action="store_true",
                        help="同时导出一份 markdown 报表到 03_OutputFiles/reports/")
    args = parser.parse_args()

    if args.rerender:
        stats = build.rerender_all()
        log(f"[rerender] 更新 {stats['touched']} 期；站点共 {stats['issues']} 期，"
            f"内嵌 {stats['embedded']} 期 → {stats['out']}")
        if args.export_md:
            for entry in build.list_issues():
                issue = json.loads(
                    (build.ISSUES_DIR / f"{entry['id']}.json").read_text(encoding="utf-8")
                )
                md_path = REPORTS / f"digest_{entry['id']}.md"
                build.export_markdown(issue, md_path)
                log(f"  markdown → {md_path.name}")
        return 0

    now = datetime.now(CST)
    date_str = args.date or now.strftime("%Y-%m-%d")

    if args.refresh:
        path = pool_path(date_str)
        if not path.exists():
            log(f"找不到候选池 {path}")
            log("候选池由云端 12:00 生成并提交；先 git pull 一次再重试。")
            return 1
        pool, dropped = load_pool(path)
        log(f"[refresh] 用 {path.name} 重建 {date_str}，候选 {len(pool)} 条")
    else:
        log(f"[{now:%Y-%m-%d %H:%M}] 开始抓取 {date_str}")
        items, failed = collect(now)
        log(f"  合计 {len(items)} 条原始条目"
            + (f"；失败源：{', '.join(failed)}" if failed else "；全部源正常"))
        if not items:
            log("没有任何条目，放弃本次构建（不生成空壳）")
            return 1

        pool, dropped = rank.rank(items, now, POOL_FOR_AI)
        log(f"  候选池 {len(pool)} 条（最终入选上限 {LIMIT}），淘汰 {dropped} 条")

        if args.dry_run:
            for n, item in enumerate(pool[:LIMIT], 1):
                log(f"  {n:2d}. [{item['score']:>4}] [{item['category']}] {item['title'][:60]}")
            log("  （--dry-run：未写入任何文件）")
            return 0

        path = write_pool(pool, date_str, now, dropped)
        log(f"  候选池 → {path}")

        if args.save_raw:
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            (RAW_DIR / f"selected_{date_str}.json").write_text(
                json.dumps(
                    [{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in i.items()}
                     for i in pool],
                    ensure_ascii=False, indent=2,
                ), encoding="utf-8",
            )

    issue = build.build_issue(pool, date_str, now, limit=LIMIT, dropped=dropped)
    build.save_issue(issue)
    summary = build.render_site()

    if args.export_md:
        md_path = REPORTS / f"digest_{date_str}.md"
        build.export_markdown(issue, md_path)
        log(f"  markdown → {md_path}")

    log(f"  已生成 {issue['id']}（{issue['count']} 条，AI 摘要："
        f"{'有' if issue['has_ai_summary'] else '无'}）")
    log(f"  站点 {summary['issues']} 期，内嵌 {summary['embedded']} 期 → {summary['out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
