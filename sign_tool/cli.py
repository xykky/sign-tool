from __future__ import annotations

import sys
import asyncio
import argparse
from datetime import datetime, timedelta

from .log import setup_logger
from .config import load_config
from . import db


async def _run(args, config):
    await db.init_db(config.db_path)
    try:
        from .runner import run_all
        await run_all(config, platform=getattr(args, 'platform', None))
    finally:
        await db.close_db()


async def _status(args, config):
    await db.init_db(config.db_path)
    try:
        d = getattr(args, 'date', None)
        records = await db.get_today_records(d)
        if not records:
            date_str = d or datetime.now().strftime("%Y-%m-%d")
            print(f"{date_str} 无签到记录")
            return

        date_str = d or datetime.now().strftime("%Y-%m-%d")
        print(f"{date_str} 签到记录:")
        print("-" * 40)
        for r in records:
            print(f"  {r['ref_id']} / {r['kind']}")
    finally:
        await db.close_db()


async def _purge(args, config):
    await db.init_db(config.db_path)
    try:
        days = getattr(args, 'days', 30)
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        deleted = await db.purge_before(cutoff)
        print(f"已清理 {deleted} 条 {cutoff} 之前的记录")
    finally:
        await db.close_db()


async def _login_kuro(args, config):
    from .kuro.login import login_kuro
    mobile = getattr(args, 'phone', '')
    code = getattr(args, 'code', '')
    game = getattr(args, 'game', 'waves')
    if not mobile or not code:
        print("请提供手机号和验证码: sign-tool login kuro --phone 13800138000 --code 123456")
        return
    try:
        account = await login_kuro(mobile, code, game, config)
        print(f"登录成功!")
        print(f"  UID: {account.uid}")
        print(f"  游戏: {account.game}")
        print(f"  凭据已保存到配置文件")
    except Exception as e:
        print(f"登录失败: {e}")
        sys.exit(1)


async def _login_tajiduo(args, config):
    from .tajiduo.login import login_tajiduo
    mobile = getattr(args, 'phone', '')
    code = getattr(args, 'code', '')
    if not mobile or not code:
        print("请提供手机号和验证码: sign-tool login tajiduo --phone 13800138000 --code 123456")
        return
    try:
        account = await login_tajiduo(mobile, code, config)
        print(f"登录成功!")
        print(f"  中心UID: {account.center_uid}")
        print(f"  凭据已保存到配置文件")
    except Exception as e:
        print(f"登录失败: {e}")
        sys.exit(1)


async def _send_code(args, config):
    platform = getattr(args, 'platform', '')
    phone = getattr(args, 'phone', '')
    if not phone:
        print("请提供手机号: sign-tool send-code <platform> --phone 13800138000")
        return

    if platform == "tajiduo":
        from .tajiduo.laohu import LaohuClient, LaohuDevice
        device = LaohuDevice()
        client = LaohuClient(device=device)
        try:
            await client.send_sms_code(phone)
            print(f"验证码已发送至 {phone}")
        except Exception as e:
            print(f"发送失败: {e}")
            sys.exit(1)
    elif platform == "kuro":
        print("库洛平台验证码需要通过库洛App获取，暂不支持短信发送")
        print("请在库洛App中获取验证码后使用: sign-tool login kuro --phone <phone> --code <code>")
    else:
        print(f"不支持的平台: {platform}")
        print("支持的平台: kuro, tajiduo")


def _schedule_loop(config):
    """Run the scheduler loop."""
    import time as time_mod

    sched = config.schedule
    parts = sched.time.split(":")
    hour, minute = int(parts[0]), int(parts[1])

    print(f"定时签到已启动: 每天 {hour:02d}:{minute:02d}")
    if sched.repeat:
        print("  模式: 重复签到 (5次/天)")

    def _run_once():
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run(argparse.Namespace(platform=None), config))
        finally:
            loop.close()

    # Calculate schedule times
    times = [(hour, minute)]
    if sched.repeat:
        times.extend([
            ((hour + 9) % 24, minute),
            ((hour + 12) % 24, minute),
            ((hour + 13) % 24, minute),
            ((hour + 14) % 24, minute),
        ])

    while True:
        now = datetime.now()
        current_hm = (now.hour, now.minute)

        # Find next scheduled time
        next_time = None
        for h, m in sorted(times):
            if (h, m) > current_hm:
                next_time = (h, m)
                break
        if next_time is None:
            next_time = times[0]
            # Tomorrow
            wait_seconds = ((24 - now.hour + next_time[0]) * 3600
                          + (next_time[1] - now.minute) * 60
                          - now.second)
        else:
            wait_seconds = ((next_time[0] - now.hour) * 3600
                          + (next_time[1] - now.minute) * 60
                          - now.second)

        if wait_seconds < 0:
            wait_seconds += 86400

        print(f"下次签到: {next_time[0]:02d}:{next_time[1]:02d} ({wait_seconds // 3600}小时{(wait_seconds % 3600) // 60}分钟后)")
        time_mod.sleep(wait_seconds)
        _run_once()


def _start_web(args, config):
    """Start the web server."""
    import uvicorn
    host = getattr(args, 'host', '127.0.0.1')
    port = getattr(args, 'port', 8080)
    print(f"启动 Web 界面: http://{host}:{port}")
    print(f"按 Ctrl+C 停止")
    uvicorn.run(
        "sign_tool.web.app:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


def main():
    parser = argparse.ArgumentParser(
        description="独立签到工具 - 库洛(鸣潮/战双) + 塔吉多(异环/幻塔)",
        prog="sign-tool",
    )
    parser.add_argument("--config", default="config.toml", help="配置文件路径")
    parser.add_argument("--db", default=None, help="数据库文件路径 (覆盖配置)")

    subparsers = parser.add_subparsers(dest="command")

    # run
    run_parser = subparsers.add_parser("run", help="执行签到")
    run_parser.add_argument("--platform", choices=["kuro", "tajiduo"], help="仅签到指定平台")

    # status
    status_parser = subparsers.add_parser("status", help="查看签到状态")
    status_parser.add_argument("--date", default=None, help="日期 (YYYY-MM-DD)")

    # purge
    purge_parser = subparsers.add_parser("purge", help="清理旧记录")
    purge_parser.add_argument("--days", type=int, default=30, help="保留天数 (默认30)")

    # login
    login_parser = subparsers.add_parser("login", help="登录账号")
    login_sub = login_parser.add_subparsers(dest="platform")

    # login kuro
    kuro_login = login_sub.add_parser("kuro", help="库洛登录")
    kuro_login.add_argument("--phone", required=True, help="手机号")
    kuro_login.add_argument("--code", required=True, help="验证码")
    kuro_login.add_argument("--game", default="waves", choices=["waves", "pgr"], help="游戏 (默认waves)")

    # login tajiduo
    tajiduo_login = login_sub.add_parser("tajiduo", help="塔吉多登录")
    tajiduo_login.add_argument("--phone", required=True, help="手机号")
    tajiduo_login.add_argument("--code", required=True, help="验证码")

    # send-code
    send_code_parser = subparsers.add_parser("send-code", help="发送验证码")
    send_code_parser.add_argument("platform", choices=["kuro", "tajiduo"], help="平台")
    send_code_parser.add_argument("--phone", required=True, help="手机号")

    # schedule
    schedule_parser = subparsers.add_parser("schedule", help="定时签到 (前台运行)")

    # web
    web_parser = subparsers.add_parser("web", help="启动 Web 界面")
    web_parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认127.0.0.1)")
    web_parser.add_argument("--port", type=int, default=8080, help="监听端口 (默认8080)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Load config
    config = load_config(args.config)
    if args.db:
        config.db_path = args.db

    setup_logger(config.log_level)

    # Route commands
    if args.command == "run":
        asyncio.run(_run(args, config))
    elif args.command == "status":
        asyncio.run(_status(args, config))
    elif args.command == "purge":
        asyncio.run(_purge(args, config))
    elif args.command == "login":
        if args.platform == "kuro":
            asyncio.run(_login_kuro(args, config))
        elif args.platform == "tajiduo":
            asyncio.run(_login_tajiduo(args, config))
        else:
            login_parser.print_help()
    elif args.command == "send-code":
        asyncio.run(_send_code(args, config))
    elif args.command == "schedule":
        _schedule_loop(config)
    elif args.command == "web":
        _start_web(args, config)


if __name__ == "__main__":
    main()
