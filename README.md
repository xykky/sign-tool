# Sign Tool

独立签到工具 - 库洛(鸣潮/战双) + 塔吉多(异环/幻塔)

一个不依赖 gsuid_core 的独立签到工具，支持 Web 界面、定时签到、推送通知。

## 功能

- 支持库洛平台（鸣潮、战双）游戏签到和 BBS 社区任务
- 支持塔吉多平台（异环、幻塔）游戏签到和社区任务
- Web 管理界面，支持手机访问
- 手机号 + 验证码登录（库洛支持 Geetest 人机验证）
- 定时自动签到
- 签到结果推送（Server酱、Telegram Bot）
- CLI 命令行模式

## 截图

![Web UI](docs/screenshot.png)

## 快速开始

### 本地运行

```bash
# 克隆项目
git clone https://github.com/你的用户名/sign-tool.git
cd sign-tool

# 安装依赖
pip install -e .

# 复制配置文件
cp config.toml.example config.toml

# 启动 Web 服务
sign-tool web

# 访问 http://127.0.0.1:8080
```

### 服务器部署

```bash
# 克隆项目
git clone https://github.com/你的用户名/sign-tool.git
cd sign-tool

# 运行一键安装脚本
chmod +x install.sh
sudo bash install.sh sign.yourdomain.com

# 编辑配置文件
nano /opt/sign-tool/config.toml

# 重启服务
systemctl restart sign-tool
```

## 命令行用法

```bash
# 启动 Web 界面
sign-tool web
sign-tool web --host 0.0.0.0 --port 8080

# 执行签到
sign-tool run
sign-tool run --platform kuro
sign-tool run --platform tajiduo

# 查看签到状态
sign-tool status
sign-tool status --date 2026-06-01

# 登录
sign-tool login kuro --phone 13800138000 --code 123456 --game waves
sign-tool login tajiduo --phone 13800138000 --code 123456

# 发送验证码（仅塔吉多）
sign-tool send-code tajiduo --phone 13800138000

# 定时签到（前台运行）
sign-tool schedule

# 清理旧记录
sign-tool purge --days 30
```

## 配置说明

配置文件 `config.toml`：

```toml
[general]
concurrency = 3            # 最大并发数
delay = [1.0, 3.0]         # 账号间随机延迟 (秒)
log_level = "INFO"         # 日志级别
db_path = "sign.db"        # 数据库路径

# 库洛账号（通过 Web 界面或命令行登录后自动添加）
# [[kuro.accounts]]
# cookie = ""
# uid = ""
# game = "waves"

# 塔吉多账号
# [[tajiduo.accounts]]
# refresh_token = ""
# center_uid = ""

# 库洛 BBS 任务
[kuro.bbs]
enabled = ["sign", "detail", "like", "share"]

# 塔吉多社区任务
[tajiduo.tasks]
enabled = ["browse_post_c", "like_post_c", "share"]
action_delay = [0.5, 1.5]
max_failures = 3

# 定时签到
[schedule]
enabled = false
time = "06:00"

# 推送通知
[notify]
enabled = false

[notify.serverchan]
sckey = ""

[notify.telegram]
bot_token = ""
chat_id = ""
```

## Web 界面

启动后访问 `http://localhost:8080`（默认端口）。

功能：
- 登录：支持库洛和塔吉多平台，库洛支持 Geetest 人机验证
- 账号管理：查看、删除已登录账号
- 签到状态：查看今日签到记录
- 手动签到：点击按钮执行签到，实时显示进度
- 定时签到：配置自动签到时间
- 推送通知：配置 Server酱 或 Telegram Bot 推送

## 推送通知

### Server酱（微信推送）

1. 访问 https://sct.ftqq.com/ 获取 SCKEY
2. 在 Web 界面或配置文件中填入 SCKEY
3. 点击"测试推送"验证

### Telegram Bot

1. 在 Telegram 中找 @BotFather 创建 Bot，获取 Token
2. 找 @userinfobot 获取你的 Chat ID
3. 在 Web 界面或配置文件中填入 Token 和 Chat ID
4. 点击"测试推送"验证

## 服务器部署

### 依赖

- Python 3.8+
- Nginx

### 一键安装

```bash
sudo bash install.sh sign.yourdomain.com
```

安装脚本会：
1. 安装系统依赖 (python3, nginx)
2. 复制项目到 `/opt/sign-tool`
3. 创建 Python 虚拟环境
4. 安装 systemd 服务
5. 配置 Nginx 反向代理

### 手动部署

```bash
# 1. 安装依赖
apt install python3 python3-pip python3-venv nginx

# 2. 创建目录
mkdir -p /opt/sign-tool
cp -r ./* /opt/sign-tool/
cd /opt/sign-tool

# 3. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 4. 配置
cp config.toml.example config.toml
nano config.toml

# 5. 安装服务
cp sign-tool.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable sign-tool
systemctl start sign-tool

# 6. 配置 Nginx
cp nginx-sign-tool.conf /etc/nginx/sites-available/sign-tool
ln -sf /etc/nginx/sites-available/sign-tool /etc/nginx/sites-enabled/
systemctl reload nginx
```

### 常用命令

```bash
# 查看服务状态
systemctl status sign-tool

# 查看日志
journalctl -u sign-tool -f

# 重启服务
systemctl restart sign-tool

# 编辑配置
nano /opt/sign-tool/config.toml
```

### Cloudflare 配置（可选）

1. 添加域名到 Cloudflare
2. DNS 添加 A 记录指向服务器 IP，开启橙色云朵
3. SSL/TLS 设置为 Full
4. 访问 `https://sign.yourdomain.com`

## 项目结构

```
sign-tool/
├── sign_tool/                  # 主程序
│   ├── __init__.py
│   ├── __main__.py             # python -m sign_tool
│   ├── cli.py                  # CLI 入口
│   ├── config.py               # 配置管理
│   ├── db.py                   # SQLite 数据库
│   ├── log.py                  # 日志
│   ├── runner.py               # 签到执行器
│   ├── kuro/                   # 库洛平台
│   │   ├── api.py              # HTTP 客户端
│   │   ├── constants.py        # 常量
│   │   ├── login.py            # 登录
│   │   └── sign.py             # 签到逻辑
│   ├── tajiduo/                # 塔吉多平台
│   │   ├── api.py              # HTTP 客户端
│   │   ├── constants.py        # 常量
│   │   ├── laohu.py            # 老虎 SMS 登录
│   │   ├── login.py            # 登录
│   │   └── sign.py             # 签到逻辑
│   ├── notify/                 # 推送通知
│   │   ├── notify.py           # 统一接口
│   │   ├── serverchan.py       # Server酱
│   │   └── telegram.py         # Telegram Bot
│   └── web/                    # Web 界面
│       ├── app.py              # FastAPI 应用
│       └── static/
│           └── index.html      # 单页 UI
├── pyproject.toml               # 项目配置
├── config.toml.example          # 配置示例
├── install.sh                   # 一键安装脚本
├── sign-tool.service            # systemd 服务
└── nginx-sign-tool.conf         # Nginx 配置
```

## 技术栈

- Python 3.8+
- FastAPI + Uvicorn (Web 框架)
- httpx (HTTP 客户端)
- aiosqlite (异步 SQLite)
- pycryptodome (AES 加密)
- Geetest v4 (人机验证)

## 平台支持

| 平台 | 游戏 | 功能 |
|------|------|------|
| 库洛 | 鸣潮 | 游戏签到、BBS 签到、浏览/点赞/分享帖子 |
| 库洛 | 战双 | 游戏签到 |
| 塔吉多 | 异环 | App 签到、游戏签到、社区任务 |
| 塔吉多 | 幻塔 | 游戏签到 |

## 注意事项

- `config.toml` 包含账号凭据，不会被推送到 GitHub
- 签到记录存储在 `sign.db`（SQLite 数据库）
- 库洛登录需要通过 Geetest 人机验证
- 塔吉多登录会自动获取并刷新 token
- 定时签到通过系统 cron 或内置定时器实现

## 许可证

MIT License

## 致谢

- [gsuid_core](https://github.com/Genshin-bots/gsuid_core) - 原始插件框架
- [Geetest](https://www.geetest.com/) - 人机验证服务
