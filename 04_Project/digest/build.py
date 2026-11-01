"""构建：把候选池装配成「一期」，再把所有期次渲染成静态站。

关键约束：**摘要可以缺失**。整条管线在 content/summaries/ 为空时
必须依然产出一份完整可读的页面（见 ADR 0001）。
"""

import json
import shutil
import sys
from datetime import datetime

from paths import ISSUES_DIR, SITE_OUT, SITE_SRC, SUMMARIES_DIR

EMBED_RECENT = 14  # 内嵌最近 14 期；前端期次按钮数也从 data.js 读这个值，不再各写一份


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _read_json(path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_summaries(date_str: str) -> dict:
    """AI 层产出的摘要。缺失返回空字典——这是正常状态，不是错误。"""
    payload = _read_json(SUMMARIES_DIR / f"{date_str}.json", {}) or {}
    return payload.get("items", {})


def _merge(rendered, summaries):
    """把摘要盖到已渲染条目上并重排。build_issue 与 apply_summaries 共用这一份。"""
    for item in rendered:
        extra = summaries.get(item["id"])
        if not extra:
            continue
        item["title_zh"] = extra.get("title_zh") or item.get("title_zh", "")
        item["summary"] = extra.get("summary") or item.get("summary", "")
        item["category"] = extra.get("category") or item["category"]
        item["rank_hint"] = extra.get("rank", item.get("rank_hint", 0))

    if any(item.get("rank_hint") for item in rendered):
        rendered.sort(key=lambda r: (r.get("rank_hint") or 999, -r.get("score", 0)))
    return rendered


def build_issue(candidates, date_str: str, now: datetime,
                limit: int = 15, dropped: int = 0) -> dict:
    """candidates 是完整候选池（可 50 条），本函数负责选出最终的 limit 条。

    AI 层可以给任意候选打 rank 把它提上来——但只能从池内提，不能捞池外的
    （见 docs/ranking.md §6）。
    """
    summaries = load_summaries(date_str)
    pool_ids = {c["id"] for c in candidates}

    stray = [key for key in summaries if key not in pool_ids]
    if stray:
        _log(f"  ⚠ {len(stray)} 条摘要的 id 不在候选池里（多半是池被换过），已忽略："
             f"{', '.join(stray[:5])}")

    rendered = [
        {
            "id": item["id"],
            "title_zh": "",
            "title_orig": item["title"],
            "summary": "",
            "url": item["url"],
            "source": item["source"],
            "published": item["published"].isoformat(),
            "category": item["category"],
            "score": item["score"],
            "rank_hint": 0,
        }
        for item in candidates
    ]

    rendered = _merge(rendered, summaries)[:limit]

    if summaries:
        missing = [r["id"] for r in rendered if not r["summary"]]
        if missing:
            _log(f"  ⚠ {len(missing)}/{len(rendered)} 条没匹配上摘要，将显示原文标题："
                 f"{', '.join(missing)}")

    return {
        "id": date_str,
        "date": date_str,
        "generated_at": now.isoformat(),
        "count": len(rendered),
        "dropped": dropped,
        "has_ai_summary": any(r["summary"] for r in rendered),
        "items": rendered,
    }


def save_issue(issue: dict) -> None:
    _write_json(ISSUES_DIR / f"{issue['id']}.json", issue)


def apply_summaries(issue: dict) -> dict:
    """把已落盘的摘要盖回一期并重排（不重新抓取、不重新选条目）。"""
    summaries = load_summaries(issue["date"])
    if not summaries:
        return issue

    issue["items"] = _merge(issue["items"], summaries)
    issue["has_ai_summary"] = any(item.get("summary") for item in issue["items"])

    missing = [item["id"] for item in issue["items"] if not item["summary"]]
    if missing:
        _log(f"  ⚠ {issue['id']}：{len(missing)}/{len(issue['items'])} 条没有摘要，"
             f"将显示原文标题：{', '.join(missing)}")
    return issue


def rerender_all() -> dict:
    """重算所有期次（套用摘要）后重建站点。返回统计。"""
    touched = 0
    for path in sorted(ISSUES_DIR.glob("*.json")):
        issue = _read_json(path, {})
        if not issue:
            continue
        before = json.dumps(issue, ensure_ascii=False, sort_keys=True)
        issue = apply_summaries(issue)
        if json.dumps(issue, ensure_ascii=False, sort_keys=True) != before:
            save_issue(issue)
            touched += 1
    stats = render_site()
    stats["touched"] = touched
    return stats


def list_issues():
    """按时间倒序返回所有期次的摘要信息。"""
    entries = []
    for path in sorted(ISSUES_DIR.glob("*.json")):
        data = _read_json(path, {})
        if not data.get("id"):
            continue
        entries.append(
            {
                "id": data["id"],
                "date": data["date"],
                "count": data.get("count", 0),
                "has_ai_summary": data.get("has_ai_summary", False),
            }
        )
    entries.sort(key=lambda e: e["id"], reverse=True)
    return entries


def render_site() -> dict:
    """把 site/ 模板与全部期次渲染成成品目录。返回构建摘要。

    **先整目录清空再写**：否则上一版删掉的期次会留在 data/issues/ 里，
    拿本地产物一发布就把死数据推上线了。
    """
    if SITE_OUT.exists():
        shutil.rmtree(SITE_OUT)
    SITE_OUT.mkdir(parents=True, exist_ok=True)

    for asset in SITE_SRC.iterdir():
        if asset.is_file():
            shutil.copy2(asset, SITE_OUT / asset.name)

    entries = list_issues()
    embed = {entry["id"] for entry in entries[:EMBED_RECENT]}

    issues = {}
    data_dir = SITE_OUT / "data" / "issues"
    data_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        payload = _read_json(ISSUES_DIR / f"{entry['id']}.json")
        if not payload:
            continue
        _write_json(data_dir / f"{entry['id']}.json", payload)
        if entry["id"] in embed:
            issues[entry["id"]] = payload

    bundle = {
        "generatedAt": datetime.now().astimezone().isoformat(),
        "embedLimit": EMBED_RECENT,
        "index": entries,
        "issues": issues,
    }
    (SITE_OUT / "data.js").write_text(
        "window.DIGEST = " + json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )

    # GitHub Pages 默认跑 Jekyll，会把某些文件吃掉；一个空文件就能关掉
    (SITE_OUT / ".nojekyll").write_text("", encoding="utf-8")

    return {"issues": len(entries), "embedded": len(issues), "out": str(SITE_OUT)}


def export_markdown(issue: dict, out_path) -> None:
    """把一期导成可读的 markdown。与站点用同一份数据，保证两边一致。"""
    lines = [
        f"# AI 日报 · {issue['date']}",
        "",
        f"共 {issue['count']} 条，按重要度排序。摘要由 AI 改写，点链接核对原文。",
        "",
    ]
    for n, item in enumerate(issue["items"], 1):
        lines.append(f"## {n}. {item['title_zh'] or item['title_orig']}")
        lines.append(f"{item['category']} · {item['source']} · {item['published'][11:16]}")
        lines.append("")
        if item["summary"]:
            lines.append(item["summary"])
            lines.append("")
        lines.append(f"[原文]({item['url']})")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
