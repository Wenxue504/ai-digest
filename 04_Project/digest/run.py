"""入口：抓取 → 排序 → 装配一期 → 渲染静态站。

用法：
    python 04_Project/digest/run.py                # 今天 12 点档
    python 04_Project/digest/run.py --slot 18      # 今天 18 点档（增量）
    python 04_Project/digest/run.py --dry-run      # 只抓不建页，看候选池
    python 04_Project/digest/run.py --date 2026-11-01 --slot 12
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paths import INTERIM_DIR, RAW_DIR  # noqa: E402

from digest import build, rank  # noqa: E402
from digest.fetch import fetch_source, log  # noqa: E402
from digest.sources import SOURCES  # noqa: E402

CST = timezone(timedelta(hours=8))
LIMIT_FULL = 15
LIMIT_INCREMENTAL = 8
POOL_FOR_AI = 50  # 候选池上限：再多就是在烧额度（见 ADR 0003）
FETCH_DEADLINE = 60  # 整轮抓取墙钟上限（秒）


def collect(now: datetime):
    """并发抓全部源，返回 (标准化条目, 每个源的成败记录)。

    用 wait(timeout=) 而不是 map：map 会一直等最慢的那个，
    任何一个源在云端挂起（实测出现过）都会把整轮拖死。
    """
    executor = ThreadPoolExecutor(max_workers=8)
    futures = {executor.submit(fetch_source, source): source for source in SOURCES}
    done, pending = futures_wait(futures, timeout=FETCH_DEADLINE)

    results = []
    for future in done:
        source = futures[future]
        try:
            items, error = future.result()
        except Exception as exc:  # 理论上不会到这里，兜一层
            items, error = None, f"{type(exc).__name__}: {exc}"
        status = "OK" if items else "FAIL"
        log(f"  {status:4s} {source['name']:<12s} {len(items or [])} 条"
            + (f"  ({error})" if error else ""))
        results.append((source, items, error))

    for future in pending:
        source = futures[future]
        log(f"  SLOW {source['name']:<12s} 超过 {FETCH_DEADLINE}s 未返回，跳过")
        results.append((source, None, "timeout"))
        future.cancel()

    executor.shutdown(wait=False, cancel_futures=True)

    normalized = []
    for source, items, _ in results:
        for raw in items or []:
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
    failed = [s["name"] for s, items, _ in results if not items]
    # 有些源会给出「计划发布时间」（实测 InfoQ 会有），不夹住会让它排到未来
    for item in normalized:
        if item["published"] and item["published"] > now:
            item["published"] = now
    return normalized, failed


def write_pool(items, date_str: str, slot: int, now: datetime) -> Path:
    """给 AI 层看的候选池。故意截断摘要——它不需要读全文（见 ADR 0003）。"""
    payload = {
        "date": date_str,
        "slot": slot,
        "generated_at": now.isoformat(),
        "candidates": [
            {
                "id": i["id"],
                "title": i["title"],
                "source": i["source"],
                "published": i["published"].isoformat(),
                "category_guess": i.get("category", ""),
                "excerpt": i["summary"][:160],
                "score": i.get("score", 0),
                "url": i["url"],
            }
            for i in items[:POOL_FOR_AI]
        ],
    }
    path = INTERIM_DIR / f"pool_{date_str}_{slot:02d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_pool(path: Path):
    """把落盘的候选池读回来，用于「摘要写好之后重建」这一步。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for candidate in payload.get("candidates", []):
        items.append(
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
        )
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 AI 行业新闻并生成一期报表")
    parser.add_argument("--slot", type=int, default=12, choices=[12, 18])
    parser.add_argument("--date", default="", help="默认今天（北京时间）")
    parser.add_argument("--dry-run", action="store_true", help="只抓取并打印候选池，不生成页面")
    parser.add_argument("--save-raw", action="store_true", help="把候选池另存到 05_Datas/raw/")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="不重新抓取，用已落盘的候选池 + 现有摘要重建这一期（AI 层写完后调用）",
    )
    parser.add_argument(
        "--rerender",
        action="store_true",
        help="重算全部期次套用摘要并重建站点（云端在 push 时用，不抓取）",
    )
    args = parser.parse_args()

    if args.rerender:
        stats = build.rerender_all()
        log(f"[rerender] 更新 {stats['touched']} 期；站点共 {stats['issues']} 期，"
            f"内嵌 {stats['embedded']} 期 → {stats['out']}")
        return 0

    now = datetime.now(CST)
    date_str = args.date or now.strftime("%Y-%m-%d")
    limit = LIMIT_INCREMENTAL if args.slot == 18 else LIMIT_FULL
    kind = "incremental" if args.slot == 18 else "full"

    if args.refresh:
        pool_path = INTERIM_DIR / f"pool_{date_str}_{args.slot:02d}.json"
        if not pool_path.exists():
            log(f"没有找到候选池 {pool_path}，先跑一次正常抓取")
            return 1
        pool = load_pool(pool_path)
        log(f"[refresh] 用 {pool_path.name} 重建 {date_str}-{args.slot:02d}，候选 {len(pool)} 条")
    else:
        log(f"[{now:%Y-%m-%d %H:%M}] 开始抓取，档位 {args.slot:02d}，日期 {date_str}")
        items, failed = collect(now)
        log(f"  合计 {len(items)} 条原始条目"
            + (f"；失败源：{', '.join(failed)}" if failed else "；全部源正常"))
        if not items:
            log("没有任何条目，放弃本次构建（不生成空壳）")
            return 1

        # 增量档：只保留上一期（同一天 12 点）之后发布的
        if args.slot == 18:
            previous = build._read_json(build.ISSUES_DIR / f"{date_str}-12.json", {})
            if previous.get("generated_at"):
                cutoff = datetime.fromisoformat(previous["generated_at"])
                items = [i for i in items if i["published"] and i["published"] > cutoff]
                log(f"  增量模式：只保留 {cutoff:%H:%M} 之后的，剩 {len(items)} 条")

        pool, dropped = rank.rank(items, now, POOL_FOR_AI)
        log(f"  候选池 {len(pool)} 条（最终入选上限 {limit}），淘汰 {dropped} 条")
        pool_path = write_pool(pool, date_str, args.slot, now)
        log(f"  候选池 → {pool_path}")

        if args.save_raw:
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            (RAW_DIR / f"selected_{date_str}_{args.slot:02d}.json").write_text(
                json.dumps(
                    [{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in i.items()}
                     for i in pool],
                    ensure_ascii=False, indent=2,
                ), encoding="utf-8",
            )

        if args.dry_run:
            for n, item in enumerate(pool[:limit], 1):
                log(f"  {n:2d}. [{item['score']:>4}] [{item['category']}] {item['title'][:60]}")
            return 0

    cutoff_iso = ""
    if args.slot == 18:
        previous = build._read_json(build.ISSUES_DIR / f"{date_str}-12.json", {})
        cutoff_iso = previous.get("generated_at", "")

    issue = build.build_issue(
        pool, args.slot, date_str, now, kind, limit=limit,
        cutoff_iso=cutoff_iso, dropped=len(pool),
    )
    build.save_issue(issue)
    summary = build.render_site()

    log(f"  已生成 {issue['id']}（{issue['count']} 条，AI 摘要：{'有' if issue['has_ai_summary'] else '无'}）")
    log(f"  站点 {summary['issues']} 期，内嵌 {summary['embedded']} 期 → {summary['out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
