# NVIDIA NIM 号池管理网关

统一管理多个 NVIDIA NIM API Key 的号池网关：轮询调度、限流自动冷却、OpenAI 兼容接口（含 SSE 流式），以及 Vue 3 管理控制台。

## 功能

- **Vue 管理控制台**：登录会话、独立业务路由、桌面与移动端响应式布局
- **号池管理**：多个 NIM API Key 统一接入，支持增删、启停和轮询调度
- **轮询调度 + 自动冷却**：单 KEY 遇到 429/5xx 自动进入冷却（默认 60 秒）并切换下一 KEY，冷却到期自动恢复
- **编辑器兼容**：支持 `/v1/chat/completions`、`/v1/responses`、`/v1/completions`、`/v1/embeddings` 和 `/v1/models`
- **高级能力透传**：保留图片消息、工具调用、结构化输出和 `reasoning_effort` 等上游参数
- **系统预设**：可完全透传、前置注入或替换编辑器发送的系统提示词
- **模型管理**：从 NVIDIA 同步模型目录、手动添加、启停和删除；禁用模型会在聊天入口返回 403
- **定时模型检测**：按配置周期对所有启用模型发送最小推理请求，记录可用性与延迟
- **网关令牌面板管理**：客户端调用令牌在面板中创建/启停/删除；表中一个令牌都没有时不校验、放行所有请求
- **在线配置**：管理上游地址、冷却时间、监听端口和控制台密码
- **实时面板**：总请求数、总/今日 Token、平均延迟、近 60 分钟消耗曲线、最近请求日志
- **接口文档**：控制台内置调用说明，FastAPI Swagger 位于 `/swagger`

## 快速开始

```bash
pip install -r requirements.txt
cp config.example.toml config.toml   # 修改 admin_password 等配置
uvicorn main:app --port 5010
```

- 管理控制台：<http://localhost:5010/>，使用 `config.toml` 中的 `admin_password` 登录
- 数据保存在 `data/gateway.db`（SQLite），首次启动自动建表
- 旧数据库会在启动时自动补充模型表和检测字段
- `config.toml` 不存在时会以默认值自动生成一份；该文件含密码，已被 `.gitignore` 忽略，请勿提交

仓库中已包含构建后的前端文件，部署运行时不需要 Node.js。修改 Vue 源码后重新构建：

```bash
cd frontend
npm install
npm run build
```

本地前端开发可运行 `npm run dev`，Vite 会把 `/admin` 和 `/v1` 代理到 `127.0.0.1:5010`。

## Docker 部署

首次运行先创建环境文件并修改管理密码：

```bash
cp .env.example .env
# 编辑 .env，设置一个强密码
docker compose up -d --build
```

打开 <http://localhost:5010/>。容器包含前端构建阶段，不需要在宿主机安装 Node.js 或 Python。

```bash
# 查看状态和日志
docker compose ps
docker compose logs -f gateway

# 更新代码后重建
docker compose up -d --build

# 停止服务
docker compose down
```

Compose 使用两个命名卷：

- `gateway_config`：保存可由控制台在线修改的 `config.toml`
- `gateway_data`：保存 SQLite 数据库

`NIM_GATEWAY_ADMIN_PASSWORD` 只在配置卷首次创建时作为初始密码；之后以持久化的 `config.toml` 为准。执行 `docker compose down -v` 会同时删除配置和数据库，请谨慎使用。

可用环境变量：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `NIM_GATEWAY_PORT` | `5010` | 映射到宿主机的端口 |
| `NIM_GATEWAY_ADMIN_PASSWORD` | `admin123` | 首次启动使用的管理密码，生产环境建议修改 |
| `NIM_GATEWAY_UPSTREAM_BASE_URL` | NVIDIA NIM 官方地址 | 首次启动使用的上游地址 |
| `NIM_GATEWAY_SYSTEM_PROMPT_MODE` | `passthrough` | 首次启动使用的系统预设策略 |
| `NIM_GATEWAY_SYSTEM_PROMPT` | 空 | 首次启动注入的系统提示词 |
| `NIM_GATEWAY_CONFIG` | `/config/config.toml` | 容器内配置路径 |
| `NIM_GATEWAY_DATA_DIR` | `/data` | 容器内数据库目录 |

## 配置文件（config.toml）

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `admin_password` | `admin123` | 管理面板密码（用户名固定 `admin`），**生产环境务必修改** |
| `listen_port` | `5010` | 监听端口（`python main.py` 时生效；用 uvicorn 命令行则以 `--port` 为准） |
| `cooldown_seconds` | `60` | KEY 触发限流后的冷却秒数 |
| `upstream_base_url` | `https://integrate.api.nvidia.com/v1` | 上游 NIM API 地址 |
| `model_check_enabled` | `false` | 是否启用后台定时模型检测 |
| `model_check_interval_minutes` | `60` | 定时模型检测间隔，范围 1 到 10080 分钟 |
| `system_prompt_mode` | `passthrough` | 系统预设策略：`passthrough`、`prepend`、`replace` |
| `system_prompt` | 空 | 注入 Chat Completions 和 Responses API 的系统提示词 |

控制台配置页保存后，上游地址、冷却时间和模型检测计划立即生效；监听端口需要重启服务。修改管理密码会让当前登录会话立即失效。

## 控制台路由

| 路由 | 页面 |
|---|---|
| `/overview` | 运行概览与最近请求 |
| `/checks` | 模型真实推理检测 |
| `/models` | 模型同步、启停和维护 |
| `/keys` | NVIDIA API Key 管理 |
| `/tokens` | 客户端访问令牌管理 |
| `/settings` | 网关配置与管理密码 |
| `/docs` | OpenAI 兼容接口文档 |
| `/swagger` | FastAPI Swagger UI |

## 客户端用法

先在管理面板的「网关令牌」区块创建一个令牌（可留空自动生成），然后：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:5010/v1",
    api_key="面板中创建的网关令牌",
)
resp = client.chat.completions.create(
    model="meta/llama-3.1-70b-instruct",
    messages=[{"role": "user", "content": "hi"}],
    stream=True,
)
```

**注意**：当没有任何启用状态的网关令牌时，网关不校验客户端令牌、放行所有请求（仅建议在本机或受信网络使用）；只要存在至少一个启用令牌，客户端就必须携带正确的 Bearer 令牌，否则返回 401。
