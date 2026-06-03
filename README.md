# Sign Tool

独立签到工具 - 库洛(鸣潮/战双) + 塔吉多(异环/幻塔)

不依赖 gsuid_core，支持 Web 界面、定时签到、推送通知。

## 功能

- 库洛（鸣潮、战双）游戏签到 + BBS 社区任务
- 塔吉多（异环、幻塔）游戏签到 + 社区任务
- Web 管理界面，支持手机访问
- 手机号 + 验证码登录（库洛支持 Geetest 人机验证）
- 定时自动签到
- 签到结果推送（Server酱、Telegram Bot）

## 快速开始

### 本地运行

```bash
git clone https://github.com/xykky/sign-tool.git
cd sign-tool
pip install -e .
cp config.toml.example config.toml
sign-tool web
# 访问 http://127.0.0.1:8080
```

### 服务器部署

```bash
git clone https://github.com/xykky/sign-tool.git
cd sign-tool
sudo bash install.sh sign.yourdomain.com
```

安装脚本会自动完成：
1. 安装系统依赖（python3、nginx、git）
2. 克隆项目到 `/opt/sign-tool`
3. 创建 Python 虚拟环境并安装依赖
4. 配置 systemd 服务
5. 配置 Nginx 反向代理

安装后编辑配置文件并填入账号信息：
```bash
nano /opt/sign-tool/config.toml
systemctl restart sign-tool
```

## 更新

```bash
cd /opt/sign-tool
sudo bash update.sh
```

## 卸载

```bash
# 完全卸载
sudo bash uninstall.sh

# 保留配置和数据库（方便以后重新部署）
sudo bash uninstall.sh --keep-data
```

## 命令行用法

```bash
sign-tool web                                    # 启动 Web 界面
sign-tool web --host 0.0.0.0 --port 8080        # 指定地址和端口
sign-tool run                                    # 执行所有签到
sign-tool run --platform kuro                    # 仅库洛
sign-tool run --platform tajiduo                 # 仅塔吉多
sign-tool status                                 # 查看今日签到状态
sign-tool status --date 2026-06-01               # 查看指定日期
sign-tool login kuro --phone 138x --code 123456 --game waves
sign-tool login tajiduo --phone 138x --code 123456
sign-tool send-code tajiduo --phone 138x         # 发送验证码（仅塔吉多）
sign-tool schedule                               # 前台定时签到
sign-tool purge --days 30                        # 清理旧记录
```

## 服务器管理

```bash
systemctl status sign-tool    # 查看状态
systemctl restart sign-tool   # 重启
journalctl -u sign-tool -f    # 查看日志
nano /opt/sign-tool/config.toml  # 编辑配置
```

## 配置说明

配置文件 `config.toml`：

```toml
[general]
concurrency = 3
delay = [1.0, 3.0]
log_level = "INFO"
db_path = "sign.db"

# 库洛账号（通过 Web 界面或命令行登录后自动添加）
# [[kuro.accounts]]
# cookie = ""
# uid = ""
# game = "waves"

# 塔吉多账号
# [[tajiduo.accounts]]
# refresh_token = ""
# center_uid = ""

[kuro.bbs]
enabled = ["sign", "detail", "like", "share"]

[tajiduo.tasks]
enabled = ["browse_post_c", "like_post_c", "share"]
action_delay = [0.5, 1.5]
max_failures = 3

[schedule]
enabled = false
time = "06:00"
repeat = false

[notify]
enabled = false

[notify.serverchan]
sckey = ""

[notify.telegram]
bot_token = ""
chat_id = ""
```

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

## Cloudflare 配置（可选）

1. 添加域名到 Cloudflare
2. DNS 添加 A 记录指向服务器 IP，开启橙色云朵
3. SSL/TLS 设置为 Full
4. 访问 `https://sign.yourdomain.com`

## 项目结构

```
sign-tool/
├── sign_tool/                  # 主程序
│   ├── __main__.py             # python -m sign_tool 入口
│   ├── cli.py                  # CLI 入口
│   ├── config.py               # 配置管理
│   ├── db.py                   # SQLite 数据库
│   ├── runner.py               # 签到执行器
│   ├── kuro/                   # 库洛平台
│   ├── tajiduo/                # 塔吉多平台
│   ├── notify/                 # 推送通知
│   └── web/                    # Web 界面
├── config.toml.example         # 配置示例
├── pyproject.toml              # 项目配置
├── install.sh                  # 一键安装
├── update.sh                   # 一键更新
├── uninstall.sh                # 卸载
├── sign-tool.service           # systemd 服务
└── nginx-sign-tool.conf        # Nginx 配置
```

## 技术栈

- Python 3.8+
- FastAPI + Uvicorn
- httpx
- aiosqlite
- pycryptodome

## 平台支持

| 平台 | 游戏 | 功能 |
|------|------|------|
| 库洛 | 鸣潮 | 游戏签到、BBS 签到、浏览/点赞/分享帖子 |
| 库洛 | 战双 | 游戏签到 |
| 塔吉多 | 异环 | App 签到、游戏签到、社区任务 |
| 塔吉多 | 幻塔 | 游戏签到 |

## 许可证

MIT License
