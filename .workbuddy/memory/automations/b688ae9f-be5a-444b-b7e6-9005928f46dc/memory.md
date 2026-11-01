# 自动化执行记录：AI 日报中文摘要 + 发布

## 2026-11-01 13:22（首次记录）

- 抓取：`run.py --dry-run` 正常，9 源全部 OK，230 条原始 → 候选池 50 条（`05_Datas/interim/pool_2026-11-01_12.json`）。
- 摘要：重写 `04_Project/content/summaries/2026-11-01.json`，15 条，rank 1–15，五类分布 资本3/产品6/政策2/研究3/硬件1。
  - 覆盖了仓库初始提交里那版占位摘要（其中含推断性表述、以及来源仅一条推文的弱条目，已剔除）。
- 重建：`run.py --refresh` → 期次 `2026-11-01-12` 15 条 has_ai_summary=true，站点 2 期。
- 发布：commit `5c5f8c6`，`git pull --rebase` 显示 up to date，`git push` 一次成功（本次 github.com 通）。

### 踩过的坑（下次直接用）

- `--dry-run` 生成的候选池路径用「北京时间日期」，与本机时区一致。
- `git pull --rebase` 前必须先把工作区改动 commit，否则报 `cannot pull with rebase: You have unstaged changes`；
  另外用 `cmd | tail` 判断成功会误判（管道返回 tail 的退出码），要 `out=$(cmd)` 再取 `$?`。
- 仓库里已存在 `issues/2026-11-01-18.json`（云端 18 点档占位，仅 1 条），属正常，不必清理。
