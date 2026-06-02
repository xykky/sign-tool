# Sign Tool - 独立签到工具

库洛(鸣潮/战双) + 塔吉多(异环/幻塔) 每日自动签到工具，带 Web 管理界面。

## 功能

- 库洛平台签到（鸣潮、战双游戏签到 + BBS 社区任务）
- 塔吉多平台签到（异环、幻塔游戏签到 + 社区任务）
- Web 管理界面（登录、签到、状态查看、定时配置）
- 短信验证码登录（库洛支持 Geetest 人机验证）
- 定时自动签到
- 签到结果推送（Server酱、Telegram Bot）
- Nginx 反向代理 + Linux 一键部署

## 快速开始

### 本地运行

```bash
# 克隆项目
git clone https://github.com/你的用户名/sign-tool.git
cd sign-tool

# 安装依赖
pip install -e .

# 启动 Web 服务
sign-tool web

# 访问 http://127.0.0.1:8080
```

### Linux 服务器部署（一键脚本）

```bash
# 克隆项目
git clone https://github.com/你的用户名/sign-tool.git
cd sign-tool

# 运行安装脚本（传入你的域名）
chmod +x install.sh
sudo ./install.sh sign.yourdomain.com

# 编辑配置文件
nano /opt/sign-tool/config.toml

# 重启服务
systemctl restart sign-tool

# 访问 http://sign.yourdomain.com
```

## 命令行使用

```bash
# 发送验证码（塔吉多）
sign-tool send-code tajiduo --phone 13800138000

# 登录
sign-tool login kuro --phone 13800138000 --code 123456
sign-tool login tajiduo --phone 13800138000 --code 123456

# 执行签到
sign-tool run                      # 全部签到
sign-tool run --platform kuro      # 仅库洛
sign-tool run --platform tajiduo   # 仅塔吉多

# 查看状态
sign-tool status

# 启动 Web 界面
sign-tool web                      # 默认 127.0.0.1:8080
sign-tool web --host 0.0.0.0       # 允许外部访问
sign-tool web --port 2087          # 自定义端口

# 定时签到（前台运行）
sign-tool schedule

# 清理旧记录
sign-tool purge --days 30
```

## Web 界面功能

| 功能 | 说明 |
|------|------|
| SMS 登录 | 输入手机号、验证码登录库洛/塔吉多 |
| 账号管理 | 查看已登录账号，支持删除 |
| 签到状态 | 显示今日各账号签到记录 |
| 手动签到 | 点击按钮执行签到，实时显示进度 |
| 定时签到 | 配置自动签到时间，支持开关 |
| 推送通知 | 配置 Server酱/Telegram 推送签到结果 |

## 配置说明

配置文件：`config.toml`

```toml
[general]
concurrency = 3            # 最大并发数
delay = [1.0, 3.0]         # 账号间随机延迟 (秒)
db_path = "sign.db"        # 数据库路径

# 库洛账号（登录后自动填充）
[[kuro.accounts]]
cookie = ""
uid = ""
game = "waves"             # waves=鸣潮, pgr=战双

# 塔吉多账号（登录后自动填充）
[[tajiduo.accounts]]
refresh_token = ""
center_uid = ""

# BBS 社区任务
[kuro.bbs]
enabled = ["sign", "detail", "like", "share"]

# 塔吉多社区任务
[tajiduo.tasks]
enabled = ["browse_post_c", "like_post_c", "share"]

# 定时签到
[schedule]
enabled = false
time = "06:00"             # 签到时间

# 推送通知
[notify]
enabled = false

[notify.serverchan]
sckey = ""                 # Server酱 SCKEY

[notify.telegram]
bot_token = ""             # Telegram Bot Token
chat_id = ""               # Telegram Chat ID
```

## 推送通知配置

### Server酱 (微信推送)

1. 访问 https://sct.ftqq.com/
2. 登录获取 SCKEY
3. 填入配置文件或 Web 界面

### Telegram Bot

1. 搜索 @BotFather，创建 Bot，获取 Token
2. 搜索 @userinfobot，获取你的 Chat ID
3. 填入配置文件或 Web 界面

## Nginx 配置

```nginx
server {
    listen 80;
    server_name sign.example.com;

    location / {
        proxy_pass http://127.0.0.1:2087;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 支持（签到进度实时推送）
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

## Cloudflare 配置（可选）

1. DNS 添加 A 记录指向服务器 IP
2. 开启橙色云朵 (Proxy)
3. SSL/TLS 设置为 Full
4. 访问 https://sign.yourdomain.com

## 系统服务管理

```bash
# 查看状态
systemctl status sign-tool

# 启动/停止/重启
systemctl start sign-tool
systemctl stop sign-tool
systemctl restart sign-tool

# 查看日志
journalctl -u sign-tool -f

# 开机自启
systemctl enable sign-tool
systemctl disable sign-tool
```

## 项目结构

```
sign-tool/
├── pyproject.toml              # 项目配置
├── config.toml.example         # 配置文件模板
├── install.sh                  # 一键部署脚本
├── sign-tool.service           # systemd 服务文件
├── nginx-sign-tool.conf        # Nginx 配置
├── sign_tool/
│   ├── __init__.py
│   ├── __main__.py             # python -m sign_tool
│   ├── cli.py                  # CLI 入口
│   ├── config.py               # 配置管理
│   ├── db.py                   # SQLite 数据库
│   ├── log.py                  # 日志
│   ├── runner.py               # 签到调度
│   ├── kuro/
│   │   ├── api.py              # 库洛 HTTP 客户端
│   │   ├── constants.py        # 常量
│   │   ├── login.py            # 库洛登录
│   │   └── sign.py             # 库洛签到
│   ├── tajiduo/
│   │   ├── api.py              # 塔吉多 HTTP 客户端
│   │   ├── constants.py        # 常量
│   │   ├── laohu.py            # 老虎 SMS 登录
│   │   ├── login.py            # 塔吉多登录
│   │   └── sign.py             # 塔吉多签到
│   ├── notify/
│   │   ├── serverchan.py       # Server酱推送
│   │   ├── telegram.py         # Telegram 推送
│   │   └── notify.py           # 统一推送接口
│   └── web/
│       ├── app.py              # FastAPI 应用
│       └── static/
│           └── index.html      # Web 界面
```

## 依赖

- Python >= 3.8
- httpx
- pydantic
- aiosqlite
- pycryptodome
- tomli (Python < 3.11)
- fastapi
- uvicorn

## 许可证

MIT License
