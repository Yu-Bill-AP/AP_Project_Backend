# AP Planner Backend

AP Planner 是一个纯登录制的 AP 升学规划 Web 应用，包含账号注册登录、个人资料完善、AP 课程库、升学指南、DeepSeek AI 规划对话、规划历史和个人设置。

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
venv/bin/python -m uvicorn app.main:app --reload
```

打开：

```text
http://127.0.0.1:8000/login.html
```

## 环境变量

在项目根目录创建 `.env`：

```env
DEEPSEEK_API_KEY=你的DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
SECRET_KEY=请替换为至少32字节的随机密钥
```

`.env` 已加入 `.gitignore`，不要提交到 GitHub。

## 本地测试

```bash
venv/bin/python test.py
```

测试脚本会验证健康检查、测试账号登录、用户信息和 AP 规划接口是否可用。

## 测试账号

```text
用户名：student123
密码：12345678
```

## 说明

AI 规划接口会先判断问题是否属于 AP/升学规划范围。明显无关问题会直接拒答；相关问题会调用 DeepSeek。如果 API 调用失败，会自动使用本地规则版规划建议兜底。
