#!/usr/bin/env python3
"""Bot tim khach can in 3D trong nhom Facebook -> gui tung link vao nhom Zalo.

    python3 main.py           chay bot (lan dau tu cai dat va hoi token/ID nhom)
    python3 main.py --help    xem tat ca lenh
"""
import argparse
import logging
import sys

from bot import __version__, install

log = logging.getLogger("bot")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Quet nhom Facebook, gui tung link bai can in 3D vao nhom Zalo. "
                    "Khong co lenh nao: chay lien tuc, tu quet theo interval_seconds.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--setup", action="store_true", help="Cai/cap nhat thu vien, Chromium, nhap token Zalo")
    modes.add_argument("--chat-id", action="store_true", help="Tim va luu ID nhom Zalo vao .env")
    modes.add_argument("--send-test", action="store_true", help="Gui tin thu vao nhom Zalo")
    modes.add_argument("--login", action="store_true", help="Mo trinh duyet de dang nhap Facebook thu cong")
    modes.add_argument("--inspect", action="store_true", help="Kiem tra bot doc bai dung chua")
    modes.add_argument("--dry-run", action="store_true", help="Quet mot lan, in ket qua, KHONG gui")
    modes.add_argument("--bootstrap", action="store_true",
                       help="Luu bai hien co lam moc, KHONG gui (tranh gui don bai cu lan dau)")
    modes.add_argument("--install-service", action="store_true", help="Cai service systemd chay 24/7")
    modes.add_argument("--remove-service", action="store_true", help="Go service systemd")
    parser.add_argument("--once", action="store_true", help="Quet va gui mot lan roi thoat")
    parser.add_argument("--group", help='Chi quet nhom co ten chua chuoi nay (vd: "Nghiện In 3D")')
    parser.add_argument("--hours", type=float, help="Chi lay bai trong so gio gan nhat (ghi de lookback_days)")
    parser.add_argument("--headed", action="store_true", help="Hien cua so trinh duyet")
    parser.add_argument("--recheck", action="store_true",
                        help="Gui lai bai da biet neu nay khop bo loc; chi dung cung --once")
    parser.add_argument("--debug", action="store_true",
                        help="In log chi tiet; luu anh chup Facebook vao logs/ khi doc nhom loi")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    if args.recheck and not args.once:
        parser.error("--recheck chi dung cung --once")
    if args.recheck and (args.dry_run or args.bootstrap):
        parser.error("--recheck chi dung o che do gui that")
    return args


def select_groups(config, name):
    from bot.lead_filter import normalize
    from bot.settings import ConfigError
    if not name:
        return config["groups"]
    groups = [g for g in config["groups"] if normalize(name) in normalize(g["name"])]
    if not groups:
        raise ConfigError(f"Khong co nhom nao ten chua '{name}' trong config.json")
    return groups


def cmd_send_test():
    from bot import zalo
    me = zalo.get_me() or {}
    print(f"Token hop le. Bot: {me.get('account_name') or me.get('display_name') or me}")
    zalo.send_text("🤖 Bot tìm khách in 3D: kết nối Zalo thành công.")
    print("Da gui tin thu vao nhom Zalo.")


def cmd_login(config):
    from bot import facebook
    with facebook.browser_page(headless=False) as page:
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        input("Dang nhap thu cong, hoan tat 2FA neu co; sau do Enter o terminal... ")
        for group in config["groups"]:
            page.goto(group["url"], wait_until="domcontentloaded")
            input(f"Nhom {group['name']}: chon Bai viet moi/New posts, sau do Enter... ")


def cmd_inspect(config, group):
    import json
    from bot import facebook
    with facebook.browser_page(headless=False) as page:
        page.goto(group["url"], wait_until="domcontentloaded")
        input("Chon Bai viet moi, mo Xem them cua mot so bai; Enter de xem ket qua... ")
        posts = facebook.extract_cards(facebook.read_cards(page, config, reveal_dates=True), group)
        for post in posts[:10]:
            print(json.dumps(post, ensure_ascii=False, indent=2))
        if not posts:
            print("Khong trich xuat duoc link bai. Chan doan DOM:")
            facebook.print_diagnostics(page, group, config)
        input("Neu ket qua rong/sai, kiem tra selector va group_keys. Enter de dong... ")


def cmd_scan(args, config, groups):
    from bot import facebook, zalo
    from bot.runner import Runner
    from bot.settings import DB_FILE, env
    from bot.storage import Store

    mode = "dry-run" if args.dry_run else "bootstrap" if args.bootstrap else "send"
    if mode == "send":
        install.ensure_zalo_ready()
    chat = env("ZALO_CHAT_ID")
    store = Store(DB_FILE, chat)
    open_page = lambda: facebook.browser_page(headless=not args.headed)  # noqa: E731
    try:
        runner = Runner(None, config, store, groups, mode, recheck=args.recheck, debug=args.debug)
        if mode != "send" or args.once:
            with open_page() as page:
                runner.page = page
                runner.scan_all()
            return
        listener = zalo.Listener(chat).start()
        try:
            every = format_duration(config["interval_seconds"] / 3600)
            window = format_duration(config["lookback_days"] * 24)
            zalo.send_text(f"🤖 Bot tìm khách in 3D đã bật: cứ {every} quét bài trong {window} qua, "
                           "chỉ gửi bài cần in MỚI (không gửi lại bài đã gửi). Nhắn \"scan\" để quét ngay.")
            log.info("Cu %s quet bai trong %s qua; nhan 'scan' trong nhom Zalo de quet ngay. Ctrl+C de dung.",
                     every, window)
            runner.run_forever(listener, open_page)
        finally:
            listener.stop()
    finally:
        store.close()


def format_duration(hours):
    return f"{hours:g} giờ" if hours >= 1 else f"{hours * 60:g} phút"


def run(args):
    from bot import settings

    if args.setup:
        install.setup()
        return
    if args.install_service:
        install.install_service()
        return
    if args.remove_service:
        install.remove_service()
        return
    if args.chat_id:
        install.choose_chat_id()
        return
    if args.send_test:
        cmd_send_test()
        return

    config = settings.load_config()
    if args.hours:
        config["lookback_days"] = max(1 / 24, args.hours / 24)
    groups = select_groups(config, args.group)
    if args.login:
        cmd_login(config)
    elif args.inspect:
        cmd_inspect(config, groups[0])
    else:
        cmd_scan(args, config, groups)


def main(argv=None):
    args = parse_args(argv)
    install.ensure_venv()  # co the chay lai main.py ben trong .venv

    from bot import facebook, settings, zalo
    settings.setup_logging(args.debug)
    settings.load_env()
    log.debug("Zalo bot %s, Python %s, thu muc %s", __version__, sys.version.split()[0], settings.ROOT)
    try:
        run(args)
    except KeyboardInterrupt:
        log.info("Da dung bot.")
    except facebook.SessionExpired as error:
        log.error("%s", error)
        try:
            zalo.send_text(f"⚠️ {error}")
        except zalo.ZaloError:
            pass
        return settings.EXIT_SESSION_EXPIRED
    except (settings.ConfigError, zalo.ZaloError) as error:
        log.error("%s", error)
        return 1
    except Exception as error:
        log.debug("Traceback:", exc_info=True)
        log.error("%s: %s  (chi tiet: %s)", type(error).__name__, error, settings.LOG_FILE)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
