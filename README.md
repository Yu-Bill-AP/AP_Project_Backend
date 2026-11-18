# AP Planner Backend

AP Planner 是一个纯登录制的 AP 升学规划 Web 应用，包含账号注册登录、个人资料完善、2026–27 AP 课程库、个性化课程权重、美国院校匹配、升学指南、DeepSeek AI 规划对话、规划历史和个人设置。

## 功能页面

- 登录页：`/login.html`
- 注册页：`/register.html`
- 仪表盘：`/dashboard.html`
- 个人信息完善：`/profile.html`
- AP课程库：`/courses.html`
- 院校匹配：`/match.html`
- 申请时间线：`/timeline.html`
- 背景库：`/portfolio.html`
- 升学指南：`/guide.html`
- AI规划：`/ai-plan.html`
- 我的规划：`/my-plans.html`
- 个人设置：`/settings.html`
- API 文档：`/docs`

## 本地启动

```bash
cd /Users/bill/Desktop/AP_Project_Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
venv/bin/python -m uvicorn app.main:app --reload
```

也可以直接运行 `./start.sh`，脚本会安装依赖、执行数据库迁移并启动开发服务。

打开：

```text
http://127.0.0.1:8000/login.html
```

## 公网部署

项目已提供 `render.yaml` Blueprint，会同时创建 Python Web Service 和持久化 PostgreSQL 数据库：

1. 将当前项目的最新修改 commit 并 push 到 GitHub，包含根目录的 `render.yaml`、前端、后端和数据库迁移。不要提交 `.env`、`venv/` 和本地 `*.db`。
2. 在 [Render Dashboard](https://dashboard.render.com/) 选择 **New → Blueprint**，连接仓库和部署分支，Blueprint Path 使用根目录的 `render.yaml`。该流程会同时创建 Web Service 和 PostgreSQL，并自动注入 `DATABASE_URL` 和 `SECRET_KEY`；[官方步骤](https://render.com/docs/infrastructure-as-code)。
3. 按提示填写 `DEEPSEEK_API_KEY`，核对资源方案与费用后点击 **Deploy Blueprint**。当前 YAML 未显式指定资源方案，不应假定它会创建免费实例。长期使用应选择可持续保留数据的 PostgreSQL。免费 Web 会在空闲 15 分钟后休眠，免费 PostgreSQL 在创建 30 天后到期；[免费方案限制](https://render.com/docs/free)。

以下构建和启动命令已写入 Blueprint，无需再次手填。Build Command：

```bash
pip install -r requirements.txt
```

每次实例启动会先执行迁移，再启动服务：

```bash
alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

AI 相关环境变量：

```env
DEEPSEEK_API_KEY=你的DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_SEARCH_MODEL=deepseek-v4-pro
```

`DATABASE_URL` 和 `SECRET_KEY` 由 Blueprint 自动生成/注入。生产环境关闭自动建表和演示账号，并使用 Secure、HttpOnly 登录 Cookie。

部署完成后，在 Web Service 页面找到 Render 提供的 `https://服务名.onrender.com`，访问并分享其 `/login.html` 页面即可。先用新账号检查注册、登录和资料保存，再把链接发给其他人；电脑关机后，云端服务仍可继续运行。云端使用新数据库，已有本地账号与资料需要另外迁移。自有域名可以之后再绑定。

## 环境变量

复制 `.env.example` 为 `.env`，再填写本地配置：

```bash
cp .env.example .env
```

`.env` 已加入 `.gitignore`，不要提交到 GitHub。

关键开关：

- `APP_ENV=production` 会强制要求至少 32 字节的 `SECRET_KEY`。
- `DATABASE_URL` 支持 SQLite、PostgreSQL 和 MySQL；生产环境推荐 PostgreSQL。
- `ALLOW_ORIGINS` 默认留空，因为前后端同源；分离部署时填写明确的逗号分隔域名。
- `CREATE_DEMO_USER=false` 默认不会创建公开测试账号。仅本地演示时可临时设为 `true`。
- `AUTO_CREATE_SCHEMA=true` 仅用于本地兼容；生产环境统一执行 Alembic 迁移。

## 本地测试

```bash
venv/bin/python test.py
```

测试脚本使用临时测试账号，覆盖安全响应头、注册去重、登录 Cookie/Bearer 鉴权、Profile、AP 规划、画像分析、AI 本地兜底、资料回写、历史记录、设置同步和退出登录。测试结束会删除测试数据。

GitHub Actions 也会在每次 push 和 Pull Request 时验证全新数据库迁移并运行冒烟测试。

## 可选演示账号

```env
CREATE_DEMO_USER=true
```

开启后才会创建 `student123 / 12345678`。不要在生产环境开启。

## 说明

AI 规划接口会先判断问题是否属于 AP/升学规划范围。明显无关问题会直接拒答；相关问题会调用 DeepSeek。如果 API 调用失败，会自动使用本地规则版规划建议兜底。

AI 规划页提供“联网搜索”开关。关闭时使用 `deepseek-flash` 普通对话；开启时使用 `deepseek-v4-pro` 的 Responses API，允许模型在思考过程中搜索网页，并流式显示“思考中 / 搜索中 / 生成回答”。开关开启不保证每次都搜索；接口最终事件的 `searched` 字段只有在 DeepSeek 报告成功搜索后才为 `true`。联网搜索及页面抓取会产生额外费用。开发环境可在 `.env` 设置 `DEEPSEEK_SEARCH_MODEL`；Render 使用 `render.yaml` 中的同名变量。

课程库以 `app/course_catalog.py` 为单一数据源，覆盖 40 门常规 AP 和 3 门 2026–27 Career Kickstart 试点课程。每门课都有先修建议、学习准备、2027 变化、能力组、学科族和系统强度层级。`GET /api/courses` 返回完整目录；`GET/POST/DELETE /api/course-preferences` 管理当前用户评价。

个人评价由主观难度、兴趣、信心和可选备注组成。推荐引擎会同时计算直接课程、同学科族、共享能力组和进阶链影响：基础课程适配度较低时，更高阶后续课程会承受更强降权；如果目标专业仍需要同类能力，系统会提高替代学科权重。`/api/planning/analysis` 和 `/api/ai-chat` 返回同一份 `personalization` / `rankedRecommendations` 数据，课程库、仪表盘和 AI 对话页据此同步显示。

`GET /api/timeline` 会根据年级、目标专业、GPA、语言状态、AP 组合和申请阶段生成 GPA、AP、英语、活动、标化、选校/材料六条执行轨道。`POST /api/timeline/progress` 保存任务状态、已完成子步骤和备注；完成度会自动降低该任务紧迫度并重新排序。时间线、仪表盘和个性化升学指南使用同一份数据。

美国院校规则存于 `app/university_requirements.json`，由 `app/university_catalog.py` 加载，当前包含 U.S. News 2026 National Universities top-60 研究范围内的 41 所学校。`GET /api/universities/us` 返回逐校官方来源、复核日期与待核验项；已登录用户可用 `GET /api/school-matches?entry_year=2027` 获得按入学年份处理的测试、英语、材料核验及专业准备度结果。可选或不纳入录取的 SAT/ACT 不因缺失扣分；英语最低分、建议分、考试版本和小分分别核对。GPA、SAT/ACT 与专业分数中的系统参考值不是校方 cut-off，也不是录取概率。

2026-11-18 已逐条复核 41 所学校，其中 40 所测试和英语核心政策已读；Columbia 的英语与材料页面访问受限，保留待核验。UNC 和 UF 的官方页面差异在页面中单列，UF 未核实的英语数值也不自动判定通过。详情见 [逐校复核记录](docs/university-requirements-review-2026-11-18.md)。运行 `venv/bin/python -m unittest test_university_requirements -v` 验证政策分流及接口契约。

业务读写统一以 `profiles.data` 为准；旧版 GPA/AP/标化/背景分表仅用于兼容历史账号。院校匹配页使用有限示例学校池和启发式准备度规则，只能作为校单讨论起点，不代表录取概率或保底承诺。
