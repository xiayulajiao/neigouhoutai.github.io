# WorkTex 6535 工装面料大宗出口销售情报 MVP

> AI-readable project brief: this block is intentionally structured so an AI assistant can understand the project before reading implementation files.

```yaml
project_name: WorkTex AI Sales Intelligence MVP
project_type: static_web_demo_and_data_pipeline
industry: textile_fabric_b2b_export
primary_users: [owner, export_sales]
primary_goal: turn compliant public signals into explainable sales follow-up actions
product_scope: [65/35 twill workwear fabric, 65/35 poplin fabric]
core_workflow: [discover, verify_company, score_signal, match_product, prepare_followup, human_approve, record_crm_action]
automation_method: knowledge_base_plus_layered_skills
frontend_entrypoints: [index.html, portfolio.html, sales-intel-demo.html]
backend_demo: [worktex_pipeline.py, worktex_pipeline.db]
data_status: public_company_samples_and_synthetic_demo_cases
truth_boundary: public_company_profile_is_not_proof_of_active_buying_intent
automation_boundary: never_guess_personal_email_or_send_message_automatically
human_gate: required_before_contact_or_quote
success_metrics: [research_time, first_followup_time, evidence_completeness, human_review_rate, qualified_reply_rate]
deployment_target: GitHub Pages
```

机器可读版本见 `project_manifest.json`；人类阅读时可直接从“项目目标”“HTML演示操作”和“当前行业假设”开始。

## 在线访问

- GitHub Pages：<https://xiayulajiao.github.io/>
- GitHub 源码：<https://github.com/xiayulajiao/neigouhoutai.github.io>
- 交互页面：<https://xiayulajiao.github.io/sales-intel-demo.html>

如果访问首页出现 404，请在 GitHub 仓库中打开 `Settings → Pages`，将 `Build and deployment` 设置为 `Deploy from a branch`，分支选择 `main`，目录选择 `/ (root)`，保存后等待一两分钟。该仓库已加入 `.nojekyll`，用于保持静态 HTML 原样发布。

这是一个本地、可复现的测试版本，验证第一阶段的核心流程：

`证据记录 → 公司去重 → 需求信号评分 → 证据置信度 → 合规硬门槛 → A/B/C分级 → 人工复核队列`

当前版本刻意不做以下事情：

- 不抓取LinkedIn、招聘网站或其他需要登录的平台；
- 不猜测个人邮箱；
- 不自动发送邮件、私信或表单；
- 不把网页里的指令当作系统指令；
- 不把AI推断冒充为事实。

## 运行

```bash
python3 sales_intel_mvp.py sample_leads.json --json-out report.json --csv-out report.csv
```

用于案例展示的包装机械合成、人工标注数据可以这样运行：

```bash
python3 sales_intel_mvp.py demo_annotated_leads.json --json-out demo_report.json --csv-out demo_report.csv
```

`demo_annotated_leads.json` 中的记录均带有 `synthetic_demo: true`，用于模拟“人工已经看过并标注”的效果，不应被当作真实企业资料。

当前 HTML 演示已进一步收窄为一家只卖两款产品的虚拟公司 WorkTex：主产品是 65/35 涤棉 2/1 斜纹工装面料，辅产品是 65/35 涤棉平纹府绸。公司假设在 `worktex_company_profile.json`，线索在 `demo_textile_leads.json`，每日采集排程在 `worktex_collection_schedule.json`，合规采集来源在 `worktex_data_sources.json`，Skills 的输入、输出和权限边界在 `demo_skill_catalog.json`。

知识库演示数据位于 `demo_knowledge_base.json`。HTML页面内嵌了这组核心知识及少量地区案例的离线快照，用于展示检索命中、Skill编排和人工审批，不需要联网即可演示。

第一批公开公司级目标账户已整理在 `worktex_real_leads_seed.json` 和 `worktex_real_leads_seed.csv`，共 8 条，来源是公司官网公开页面，均标记为“待人工核验”，不代表已经存在真实采购需求。`worktex_real_leads_report.json` 和 `worktex_real_leads_report.csv` 是用当前严格规则跑出的复核结果。

本地持久化流水由 `worktex_pipeline.py` 提供，已生成 `worktex_pipeline.db` 和 `worktex_pipeline_export.json`。重新导入一批数据可运行：

```bash
python3 worktex_pipeline.py ingest worktex_real_leads_seed.json --db worktex_pipeline.db
python3 worktex_pipeline.py export --db worktex_pipeline.db --json-out worktex_pipeline_export.json
```

SQLite 中会保存线索、证据、每个子 Skill 的运行状态和自动化事件，方便后续替换成真实 API、任务队列或 CRM 连接器。

## HTML演示操作

作品展示首页是 `portfolio.html`（发布到静态托管后也可直接访问根目录 `index.html`）。它把行业背景、业务闭环、知识库 + 分层 Skill 方法、老板可见的增长证据和演示边界放在一个页面里，适合直接作为面试作品入口；页面中的“进入交互 Demo”会打开 `sales-intel-demo.html`。

如果上传平台要求填写“文本 + 超链接”，建议：

- 文本填写作品名称和一句话价值说明；
- 超链接填写部署后的 `portfolio.html` 公网地址；
- `sales-intel-demo.html` 作为作品首页中的二级入口，不要只把本地文件路径粘贴到超链接里；
- 如果平台允许补充材料，再附 1 张流程截图或 2 分钟操作录屏。

本地双击 HTML 可以预览，但 `/Users/...` 本地路径只有自己的电脑能打开，不能作为面试官可访问的作品链接。

打开 `sales-intel-demo.html` 后可以选择两个演示账号：

- 销售员工账号：查看今日线索、日期排表、我的跟进、上传名片和资料查询；点击日历中的某一天会回到该日期的线索列表。
- 老板账号：查看增长总览、后台自动处理中心、合规采集中心、线索来源效果、团队效率、自媒体线索和系统配置。

首页五个指标、日期按钮、采集按钮、资料按钮和名片按钮都有可见反馈。名片页支持演示名片，也支持读取简单 CSV/VCF 字段；XLSX 在本地演示中按文件名创建待核验线索，不连接真实后台。

分层 Skill 的架构定义在 `worktex_skill_hierarchy.json`：一个“销售情报总控”负责安排顺序，下面分为线索处理、商务准备、客户跟进和安全审批模块；每个模块再调用只负责单一动作的子 Skill。老板端的“后台自动处理中心”按这套流程生成每条线索的处理记录，展示已完成、等待人工确认、需要补资料和已拦截等状态。演示流程定义另见 `worktex_automation_blueprint.json`。

老板端的“企业自媒体线索”页现在明确展示了绑定链路：自有账号授权/官网表单 → 保存内容和评论/私信原文 → 匹配公司并核验 → 进入线索评分和人工确认。演示按钮会把一条合成互动真正加入线索池。团队效率页也解释了“单条线索研究耗时”和“首次跟进用时”的口径，并对应展示减少查资料、自动分配、提醒和回复分类等提效动作。

运行后会生成：

- `report.json`：完整证据、评分、失败硬门槛和人工复核队列；
- `report.csv`：适合在表格中查看的摘要。
- `demo_report.json`：包含模型分级与模拟人工标注的差异，适合做复盘演示。

## 测试

```bash
python3 -m unittest -v
```

## 当前行业假设

- 服务对象：WorkTex 这类只深耕一两个面料产品的 B2B 出口企业；
- 海外买家：工作服品牌、制服/校服工厂、工业洗涤服务商、工装面料进口商和区域经销商；
- 核心产品：WT-6535-TWILL、WT-6535-POPLIN；
- 首批数据为演示记录，不代表真实公司；
- 后续接入数据源前，必须为每个来源建立条款、频率、字段和合规审查表。

## 复盘重点

运行测试后重点观察：

1. A级是否同时满足商业价值、采购时点和证据可信度；
2. 只有一个信号的公司是否被正确降为B级；
3. 过期信息、排除对象和重复域名是否被拦截；
4. 高分但联系路径不合规的记录是否进入人工而非发送队列；
5. 缺少公司域名、目标克重、门幅、年度用量、目的港或日期证据时，系统是否明确指出缺口。
