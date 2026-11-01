# AI 行业日报

每天早上 12:00 一份完整版、下午 18:00 一份增量版，自动整理当天的 AI 行业消息，一屏读完。

**在线读**：<https://wenxue504.github.io/ai-digest/>

---

## 它是什么

一个纯静态的阅读页。没有登录、没有后端、没有数据库、不调用任何付费 API。

- **12:00 完整版**：15 条，按重要度排序，每条「中文标题 + 两句摘要 + 来源 + 时间 + 原文链接」
- **18:00 增量版**：只放中午之后新增的，最多 8 条；没有就明说「今天没有新动静」
- **已读标记**：点过的条目下次打开自动变灰沉下去（存在浏览器本地，不上传）
- **历史**：顶部可翻过去的期次

## 怎么跑

```bash
# 抓当天的（默认 12 点档）
python 04_Project/digest/run.py

# 指定档位
python 04_Project/digest/run.py --slot 18

# 只抓不建页，看候选池长什么样
python 04_Project/digest/run.py --dry-run
```

产物：`04_Project/content/issues/*.json`（内容真值）与 `03_OutputFiles/deliverables/site/`（可直接双击打开的静态站）。

**只用 Python 标准库，不需要 `pip install` 任何东西。**

## 自动更新怎么来的

```
GitHub Actions（云端，12:00 / 18:00 北京时间）
  ├─ 抓 RSS → 去重 → 打分 → 生成当期 JSON
  ├─ 构建静态站
  └─ 推到 gh-pages 分支 → Pages 自动发布
```

**跟你电脑开不开机无关。** 关一周，网站照样每天两更。

## 中文摘要是怎么加上的

云端只出「原文标题 + 来源 + 时间」的骨架。中文摘要由本机 WorkBuddy 每天 12:15 读候选池生成，提交 `04_Project/content/summaries/`，触发重新构建。

**没跑也不影响**：页面照常出，摘要位回落显示原文标题。这是刻意的降级设计，不是故障。

## 现在的状态

| 项 | 状态 |
| --- | --- |
| 抓取 / 排序 / 构建 | ✅ 已跑通，9 个源全部正常 |
| 站点前端 | ✅ 已可用，390px 下无溢出 |
| 中文摘要（首期） | ✅ 已写好 15 条 |
| Pages 发布 | ✅ 已上线 <https://wenxue504.github.io/ai-digest/> |
| Actions 定时 | ✅ 已生效：云端试跑 9 源全通（含国内源），每天 12:00 / 18:00 自动两更 |
| 12:15 AI 摘要自动化 | ✅ 已建 WorkBuddy 定时任务 |

云端抓取能力已实测（2026-11-01 手动试跑）：量子位、InfoQ 中文这两个国内源从 GitHub 服务器访问**全部正常**，230 条原始条目与本地一致。

手动补一期（不依赖云端）：

```bash
python 04_Project/digest/run.py            # 抓取并生成
python 04_Project/digest/run.py --rerender # 只套用摘要重建
```

## 文档

- 需求与验收：[`01_Requirements/requirements_2026-11-01.md`](01_Requirements/requirements_2026-11-01.md)
- 访谈报告（为什么这么做）：[`01_Requirements/grill_report_2026-11-01.md`](01_Requirements/grill_report_2026-11-01.md)
- 架构决策：[`04_Project/docs/adr/`](04_Project/docs/adr/)
- 排序规则：[`04_Project/docs/ranking.md`](04_Project/docs/ranking.md)
- 术语表：[`GLOSSARY.md`](GLOSSARY.md)
