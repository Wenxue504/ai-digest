"""构建：把入选条目装配成「一期」，再把所有期次渲染成静态站。

关键约束：**摘要可以缺失**。整条管线在 content/summaries/ 为空时
必须依然产出一份完整可读的页面（见 ADR 0001）。
"""

import json
import shutil
from datetime import datetime

from paths import ISSUES_DIR, SITE_OUT, SITE_SRC, SUMMARIES_DIR

CATEGORY_ORDER = ("模型", "产品", "资本", "研究", "政策", "硬件")
EMBED_RECENT = 14  # 页面内嵌最近 14 期（约一周），更早的按需 fetch


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


def build_issue(candidates, slot: int, date_str: str, now: datetime, kind: str,
                limit: int = 15, cutoff_iso: str = "", dropped: int = 0) -> dict:
    """candidates 是完整候选池（可 50 条），本函数负责选出最终的 limit 条。

    AI 层可以给任意候选打 rank 把它提上来——但只能从池内提，不能捞池外的
    （见 docs/ranking.md §6）。
    """
    issue_id = f"{date_str}-{slot:02d}"
    summaries = load_summaries(date_str)

    rendered = []
    for item in candidates:
        extra = summaries.get(item["id"], {})
        rendered.append(
            {
                "id": item["id"],
                "title_zh": extra.get("title_zh") or "",
                "title_orig": item["title"],
                "summary": extra.get("summary") or "",
                "url": item["url"],
                "source": item["source"],
                "published": item["published"].isoformat(),
                "category": extra.get("category") or item["category"],
                "score": item["score"],
                "rank_hint": extra.get("rank", 0),
            }
        )

    # AI 若给了 rank，就按 rank 重排；没给就保持脚本的分数序
    if any(r["rank_hint"] for r in rendered):
        rendered.sort(key=lambda r: (r["rank_hint"] or 999, -r["score"]))

    rendered = rendered[:limit]

    return {
        "id": issue_id,
        "date": date_str,
        "slot": slot,
        "kind": kind,
        "generated_at": now.isoformat(),
        "cutoff": cutoff_iso,
        "count": len(rendered),
        "dropped": dropped,
        "has_ai_summary": any(r["summary"] for r in rendered),
        "items": rendered,
    }


def save_issue(issue: dict) -> None:
    _write_json(ISSUES_DIR / f"{issue['id']}.json", issue)


def apply_summaries(issue: dict) -> dict:
    """把已落盘的摘要盖回一期，并按其 rank 重排。

    这是「AI 层写完摘要之后」唯一需要的动作：不用重新抓取，
    因此云端可以只凭 content/ 里的东西重建出最终页面。
    """
    summaries = load_summaries(issue["date"])
    if not summaries:
        return issue

    for item in issue["items"]:
        extra = summaries.get(item["id"])
        if not extra:
            continue
        item["title_zh"] = extra.get("title_zh") or item.get("title_zh", "")
        item["summary"] = extra.get("summary") or item.get("summary", "")
        item["category"] = extra.get("category") or item["category"]
        item["rank_hint"] = extra.get("rank", item.get("rank_hint", 0))

    if any(i.get("rank_hint") for i in issue["items"]):
        issue["items"].sort(key=lambda r: (r.get("rank_hint") or 999, -r.get("score", 0)))

    issue["has_ai_summary"] = any(i.get("summary") for i in issue["items"])
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
                "slot": data["slot"],
                "kind": data.get("kind", "full"),
                "count": data.get("count", 0),
                "has_ai_summary": data.get("has_ai_summary", False),
            }
        )
    entries.sort(key=lambda e: e["id"], reverse=True)
    return entries


def render_site() -> dict:
    """把 site/ 模板与全部期次渲染成成品目录。返回构建摘要。"""
    SITE_OUT.mkdir(parents=True, exist_ok=True)
    for asset in SITE_SRC.iterdir():
        if asset.is_file():
            shutil.copy2(asset, SITE_OUT / asset.name)

    entries = list_issues()
    embed = entries[:EMBED_RECENT]

    issues = {}
    data_dir = SITE_OUT / "data" / "issues"
    data_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        payload = _read_json(ISSUES_DIR / f"{entry['id']}.json")
        if not payload:
            continue
        _write_json(data_dir / f"{entry['id']}.json", payload)
        if entry["id"] in {e["id"] for e in embed}:
            issues[entry["id"]] = payload

    bundle = {
        "generatedAt": datetime.now().astimezone().isoformat(),
        "index": entries,
        "issues": issues,
        "embedded": len(issues),
    }
    (SITE_OUT / "data.js").write_text(
        "window.DIGEST = " + json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    _write_json(SITE_OUT / "data" / "index.json", {"index": entries})

    # GitHub Pages 默认跑 Jekyll，会把某些文件吃掉；一个空文件就能关掉
    (SITE_OUT / ".nojekyll").write_text("", encoding="utf-8")

    return {"issues": len(entries), "embedded": len(issues), "out": str(SITE_OUT)}
