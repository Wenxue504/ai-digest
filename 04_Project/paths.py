"""路径常量。

向上找「含 04_Project 的目录」= 工程根；找不到就抛异常。
不写固定深度兜底——路径错了必须立刻炸，不能静默指到别处。
"""

from pathlib import Path


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "04_Project").is_dir():
            return candidate
    raise RuntimeError(
        f"找不到工程根：从 {start} 向上没有含 04_Project 的目录。"
        "是不是把脚本挪出工程了？"
    )


ROOT = _find_project_root(Path(__file__).resolve().parent)

PROJECT = ROOT / "04_Project"
CONTENT = PROJECT / "content"
ISSUES_DIR = CONTENT / "issues"
SUMMARIES_DIR = CONTENT / "summaries"
SITE_SRC = PROJECT / "site"
DOCS_DIR = PROJECT / "docs"

SITE_OUT = ROOT / "03_OutputFiles" / "deliverables" / "site"
REPORTS = ROOT / "03_OutputFiles" / "reports"
WORK = ROOT / "03_OutputFiles" / "work"

RAW_DIR = ROOT / "05_Datas" / "raw"
INTERIM_DIR = ROOT / "05_Datas" / "interim"
