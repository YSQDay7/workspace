# 杭州智游助手 使用说明

杭州智游助手是一个面向杭州全市多景区的智能问答与行程规划系统，覆盖西湖、灵隐寺、西溪湿地、良渚古城遗址、宋城、运河等 15 个热门景区。

你可以用它查询景点知识、票价、开放时间、天气，生成单景区或跨景区路线，也可以在遇到问题时一键转人工客服。

## 环境要求

- Windows / macOS / Linux
- Python 3.10+
- Node.js 18+
- MySQL 8.0（本地运行）
- Redis 7（本地运行）
- Milvus（Docker，端口 19530）
- 可选：Docker + Docker Compose（一键部署）

## 快速开始（本地运行）

### 1. 复制并填写配置

```powershell
Copy-Item backend\.env.example backend\.env
```

打开 `backend/.env`，填写：

- `DEEPSEEK_API_KEY`：DeepSeek 对话模型密钥
- `SILICONFLOW_API_KEY`：bge-m3 向量模型密钥
- `DINGTALK_WEBHOOK`：钉钉群机器人 webhook（可选，不填则转人工降级为站内通知）
- `MYSQL_PASSWORD`：你的 MySQL 密码
- `JWT_SECRET`：改成一段随机字符串

### 2. 启动 MySQL、Redis、Milvus

如果你已经用 Docker 启动过相关容器：

```powershell
docker start redis-standalone milvus-standalone
```

MySQL 使用你本机已安装的 MySQL 8.0 服务。

### 3. 安装后端依赖并初始化

```powershell
pip install -r backend\requirements.txt
python backend\scripts\ingest.py --force
python backend\scripts\reset_demo.py
```

### 4. 安装前端依赖

```powershell
cd frontend
npm install
cd ..
```

### 5. 启动服务

```powershell
.\start.ps1
```

启动后打开：

- 游客端：http://127.0.0.1:5173
- 客服工作台：http://127.0.0.1:5173/agent
- API 文档：http://127.0.0.1:8000/docs

停止服务：

```powershell
.\stop.ps1
```

## Docker Compose 部署

### 1. 复制生产环境配置

```powershell
Copy-Item .env.production.example .env.production
```

填写 `.env.production` 中的密钥和密码。

### 2. 启动全部服务

```powershell
docker compose --env-file .env.production up -d --build
```

### 3. 初始化知识库和账号

```powershell
python backend\scripts\ingest.py --force
python backend\scripts\reset_demo.py
```

## 默认账号

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 管理员 | root | 123456 |

> 仅用于演示，正式使用前请修改密码。

## 使用方法

### 游客端

- 直接提问，例如：“杭州一日游怎么安排？”、“灵隐寺门票多少钱？”、“明天西湖天气怎么样？”
- 追问时可以直接说：“第二天呢”、“那晚上呢”，系统会结合上一轮问题继续回答。
- 右侧面板可以查看地图、行程时间表和回答来源。
- 全城路线只显示关键节点，单景区问题会展示景区内小景点。

### 客服工作台

- 访问 http://127.0.0.1:5173/agent
- 使用客服或管理员账号登录。
- 客服可以查看待办、回复用户、转回机器人、结束会话。
- 管理员可以创建账号、分配工单、查看绩效。

### 转人工

- 游客端聊天窗口点击“转人工”。
- 或发送“我要投诉”等消息，系统会自动创建工单。
- 分配成功后，客服会在工作台收到任务。

## 常见问题

### 页面显示“服务暂时开小差了”

先确认后端是否启动，并检查 `backend/.env` 中的 MySQL、Redis 配置是否正确。

### 天气显示为“预报数据”

说明 Open-Meteo 请求失败，系统自动使用了兜底模拟数据，不影响其他功能。

### 钉钉收不到转人工消息

检查 `backend/.env` 中 `DINGTALK_WEBHOOK` 是否已配置，并确认钉钉机器人安全设置允许该消息。

### 想清空所有测试数据

```powershell
python backend\scripts\reset_demo.py
```

## 安全提示

- `backend/.env` 和 `.env.production` 不要提交到 GitHub。
- 密钥通过环境变量注入，仓库只保留 `.env.example` 和 `.env.production.example` 占位模板。
- 正式环境请修改默认密码，并使用强密码。
