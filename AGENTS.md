# 本工程规则（2026-11-ai-digest）

> 通用规则见总工作区 `E:\WorkBuddy Project\AGENTS.md`，此处只写**本工程特有**的部分。

---

## 1. 这是什么

一个纯静态的 AI 行业日报站。每天 12:00 出一期（15 条）。

**红线：不付费、不注册第三方服务、不填 key、无后端、无数据库。** 任何方案若需要申请凭证，直接否决。

## 2. 三层结构（改动前必须理解）

| 层 | 跑在哪 | 依赖 | 挂了会怎样 |
| --- | --- | --- | --- |
| **地基层** 抓取/排序/构页 | GitHub Actions 云端 | 只要 GitHub | 网站停止更新 |
| **增强层** 中文摘要 | 本机 WorkBuddy 12:15 | 客户端在跑 | 页面照常，摘要回落原文标题 |
| **阅读层** 静态页 | GitHub Pages | 只要浏览器 | — |

**铁律：地基层不得依赖增强层。** 任何时候把 `04_Project/content/summaries/` 清空，站点都必须能完整构建出来。这条破了，整套设计就退化成「客户端不开就没内容」。

## 3. 目录约定（在总规则的六区之内再细分）

```
04_Project/
├── paths.py          # 路径常量，向上找含 04_Project 的目录 = 工程根
├── digest/           # 抓取/排序/构建，纯标准库
├── site/             # 前端模板（index.html / app.js / style.css）
├── content/          # ★ 内容真值，进 git
│   ├── issues/       #   每期一条 JSON：2026-11-01-12.json
│   └── summaries/    #   AI 摘要：2026-11-01.json（可缺失）
└── docs/             # 技术文档 + adr/

03_OutputFiles/deliverables/site/   # 构建产物，不进 git，由 CI 或本地构建生成
05_Datas/raw/                       # 原始 RSS 落盘（调试用），不进 git
```

**已知偏差（有意为之）**：总规则说 `03_OutputFiles/` 不进 git，此处 `content/` 是例外——它是**构建输入**而非产物，必须版本化才能让云端每次构建都读到全部历史期次。站点本身仍不进 git。

## 4. 代码约定

- **只用 Python 标准库**。不引 feedparser、不用第三方包——云端 runner 和本机都不需要 `pip install`，这是「接手测试」的一部分。
- 网络请求一律带 `Accept-Encoding: identity`（避免 gzip 解压分支）与 `User-Agent`（部分源无 UA 直接 403）。
- 任何源失败**不得中断整轮构建**：捕获 → 记 warning → 跳过。禁止 `except: pass`，至少记日志。
- 抓取超时 **20 秒**，单轮总耗时目标 < 30 秒。
- 排序/去重逻辑改动必须同时更新 `docs/ranking.md`（同一提交内）。

## 5. 内容约定

- 每条必须有：`id / title_zh / title_orig / url / source / published / category`
- `title_zh` 缺失时前端回落显示 `title_orig`，**不允许出现空白标题**
- 篇幅上限 **15 条**，超了按分数截断，不硬凑
- 分类只有六个值：`模型 / 产品 / 资本 / 研究 / 政策 / 硬件`，不接受第七个
- 摘要两句话：第一句事实，第二句「为什么值得关心」。**不写推断，不写「据报道」以外的猜测**

## 6. 部署

- 发布分支 `gh-pages`（内容 = 构建产物根目录），主分支 `main` 保持六区干净
- 仓库名 `ai-digest`，公开（免费账户 Pages 不支持私有仓），站址 `https://wenxue504.github.io/ai-digest/`
- **禁止**在仓库中出现任何 token / key；提交走 `api.github.com`（本机 `github.com` 不可达）

## 7. 时间与调度

- Actions cron 用 **UTC**：`0 4 * * *` = 北京 12:00。**一天只有这一期**，18:00 档已于 2026-11-01 取消
- WorkBuddy 定时任务设在 **12:15**，比云端晚 15 分钟——等云端先把候选池与页面生成出来
- cron 有 5–20 分钟延迟，**不要**依赖「12:00 整」这个时间点做逻辑判断
- 期次 id 就是日期（`2026-11-01`），不带档位

## 8. 已知偏差（如实记，不抹平）

总规则说工程根只放 `AGENTS.md` / `README.md` / `GLOSSARY.md` / 六区，本工程多了三个：

| 偏差 | 为什么 |
| --- | --- |
| `GLOSSARY.md` 放在工程根 | 本工程术语密度高（期次/档位/候选池/降级），且只有本工程用，不往总工作区塞 |
| `.github/workflows/` 放在工程根 | GitHub 只认仓库根的 `.github`，挪位置 Actions 就找不到 |
| `.gitignore` 放在工程根 | 同上，git 只认仓库根 |

另有一处**有意违反**：`04_Project/content/` 进 git。总规则说产物与数据不入库，但 `content/` 是**构建输入**（云端每次构建都要读全部历史期次），不版本化就跑不通。站点产物 `03_OutputFiles/deliverables/site/` 仍然不入库。

