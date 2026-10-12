#!/usr/bin/env python3
"""Bot tim khach can in 3D trong nhom Facebook -> gui tung link vao nhom Zalo,
va binh luan chao khach bang AI chay local (Ollama + Gemma), moi vao website.

    python3 main.py                      chay bot (lan dau tu cai dat va hoi token/ID nhom)
    python3 main.py --ai-test            quet mot lan, CHI IN binh luan AI se viet, khong dang
    python3 main.py --ai-test --text -   thu AI voi noi dung dan vao (khong mo Facebook)
    python3 main.py --comment-test       quet toi khi gap DUNG 1 bai can in, binh luan that ngay,
                                         in link binh luan ra terminal va gui vao nhom Zalo
    python3 main.py --help               xem tat ca lenh
"""
import argparse
import logging
import sys

from bot import __version__, install

log = logging.getLogger("bot")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Quet nhom Facebook, gui tung link bai can in 3D vao nhom Zalo va binh luan chao khach "
                    "bang AI local (Ollama). Khong co lenh nao: chay lien tuc, tu quet theo interval_seconds.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--setup", action="store_true",
                       help="Cai/cap nhat thu vien, Chromium, Ollama + model AI, nhap token Zalo")
    modes.add_argument("--chat-id", action="store_true", help="Tim va luu ID nhom Zalo vao .env")
    modes.add_argument("--send-test", action="store_true", help="Gui tin thu vao nhom Zalo")
    modes.add_argument("--login", action="store_true", help="Mo trinh duyet de dang nhap Facebook thu cong")
    modes.add_argument("--inspect", action="store_true", help="Kiem tra bot doc bai dung chua")
    modes.add_argument("--dry-run", action="store_true", help="Quet mot lan, in ket qua loc, KHONG gui")
    modes.add_argument("--ai-test", action="store_true",
                       help="Quet mot lan, AI doc bai can in va viet binh luan, CHI IN ra man hinh")
    modes.add_argument("--comment-test", action="store_true",
                       help="Quet toi khi gap DUNG 1 bai can in AI chiu tra loi, binh luan THAT ngay, "
                            "in link binh luan ra terminal va gui vao nhom Zalo, roi thoat")
    modes.add_argument("--bootstrap", action="store_true",
                       help="Luu bai hien co lam moc, KHONG gui (tranh gui don bai cu lan dau)")
    modes.add_argument("--install-service", action="store_true", help="Cai service systemd chay 24/7")
    modes.add_argument("--remove-service", action="store_true", help="Go service systemd")
    parser.add_argument("--once", action="store_true", help="Quet va gui mot lan roi thoat")
    parser.add_argument("--group", help='Chi quet nhom co ten chua chuoi nay (vd: "Nghiện In 3D")')
    parser.add_argument("--hours", type=float, help="Chi lay bai trong so gio gan nhat (ghi de lookback_days)")
    parser.add_argument("--headed", action="store_true", help="Hien cua so trinh duyet")
    parser.add_argument("--debug", action="store_true",
                        help="In log chi tiet ra man hinh (kem traceback khi loi)")
    parser.add_argument("--text", metavar="NOI_DUNG",
                        help='Cung --ai-test: thu voi noi dung bai nay, khong mo Facebook ("-" = doc tu ban phim)')
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    if args.text is not None and not args.ai_test:
        parser.error("--text chi dung cung --ai-test")
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


def cmd_setup():
    from bot import settings
    try:
        model = settings.load_config()["ai"]["model"]
    except settings.ConfigError:
        model = settings.AI_DEFAULTS["model"]
    install.setup(model)


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
        cards = facebook.read_cards(page, config, reveal_dates=True)
        posts = facebook.extract_cards(cards, group, config["exclude_re"])
        for post in posts[:10]:
            print(json.dumps(post, ensure_ascii=False, indent=2))
        if not posts:
            print("Khong trich xuat duoc link bai. Chan doan DOM:")
            facebook.print_diagnostics(page, group, config)
        input("Neu ket qua rong/sai, kiem tra selector va group_keys. Enter de dong... ")


def cmd_ai_text(config, text):
    from bot.commenter import Commenter
    if text == "-":
        print("Dan noi dung bai Facebook, xong nhan Ctrl+D (dong moi) de chay:")
        text = sys.stdin.read()
    if not text.strip():
        print("Noi dung trong.")
        return
    install.ensure_model(config["ai"]["model"])
    Commenter(config, None, "test").review_text(text)


def make_commenter(config, store, mode):
    """Commenter cho che do quet, hoac None neu khong binh luan AI."""
    from bot.commenter import Commenter
    if mode == "ai-test":
        install.ensure_model(config["ai"]["model"])
        return Commenter(config, store, "test")
    if mode == "dry-run" or not config["ai"]["enabled"]:
        return None
    if mode == "bootstrap":
        return Commenter(config, store, "bootstrap")
    install.ensure_model(config["ai"]["model"])
    return Commenter(config, store, "live")


def cmd_comment_test(args, config, groups):
    """Quet tung nhom; gap bai can in dau tien ma AI viet duoc binh luan thi dung cuon, dang ngay."""
    from bot import facebook
    from bot.commenter import Commenter
    from bot.runner import short_error
    from bot.settings import DB_FILE, env
    from bot.storage import Store

    install.ensure_model(config["ai"]["model"])
    if not (env("ZALO_BOT_TOKEN") and env("ZALO_CHAT_ID")):
        log.warning("Chua cai Zalo: chi in link binh luan ra terminal")
    store = Store(DB_FILE, env("ZALO_CHAT_ID"))
    try:
        commenter = Commenter(config, store, "try")
        if commenter.halted:
            print(f"Khong binh luan: {commenter.halted}")
            return
        with facebook.browser_page(headless=not args.headed) as page:
            for group in groups:
                if group.get("ai_comment") is False:
                    continue

                def on_post(post, group=group):
                    log.info("Bai can in: %s, cho AI doc...", post["url"])
                    commenter.process(page, group, [post])
                    return bool(commenter.jobs)  # True: du 1 bai, dung cuon

                try:
                    facebook.scan_group(page, group, config, on_post=on_post)
                except facebook.SessionExpired:
                    raise
                except Exception as error:
                    log.error("Loi nhom %s: %s", group["name"], short_error(error))
                if commenter.jobs or commenter.ai_halted:
                    break
            if not commenter.jobs:
                print("\nKhong tim thay bai can in nao de binh luan thu "
                      "(chua binh luan, AI chiu tra loi) trong khung thoi gian.")
            commenter.finish_run(page)
    finally:
        store.close()


def cmd_scan(args, config, groups):
    from bot import facebook, zalo
    from bot.runner import Runner
    from bot.settings import DB_FILE, env
    from bot.storage import Store

    mode = ("dry-run" if args.dry_run else "bootstrap" if args.bootstrap else
            "ai-test" if args.ai_test else "send")
    if mode == "send":
        install.ensure_zalo_ready()
    chat = env("ZALO_CHAT_ID")
    store = Store(DB_FILE, chat)
    open_page = lambda: facebook.browser_page(headless=not args.headed)  # noqa: E731
    try:
        commenter = make_commenter(config, store, mode)
        runner = Runner(None, config, store, groups, mode, debug=args.debug, commenter=commenter)
        if mode != "send" or args.once:
            with open_page() as page:
                runner.page = page
                runner.scan_all()
            return
        listener = zalo.Listener(chat).start()
        try:
            every = format_duration(config["interval_seconds"] / 3600)
            window = format_duration(config["lookback_days"] * 24)
            ai = config["ai"]
            ai_note = (f" Bình luận AI ({ai['model']}): bật, tối đa {ai['max_comments_per_day']}/ngày, "
                       f"{ai['active_hours'][0]}h-{ai['active_hours'][1]}h." if commenter else "")
            zalo.send_text(f"🤖 Bot tìm khách in 3D đã bật: cứ {every} quét bài trong {window} qua, "
                           "chỉ gửi bài cần in MỚI (không gửi lại bài đã gửi). Nhắn \"scan\" để quét ngay."
                           + ai_note)
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

    simple = {"setup": cmd_setup, "install_service": install.install_service,
              "remove_service": install.remove_service, "chat_id": install.choose_chat_id,
              "send_test": cmd_send_test}
    for flag, command in simple.items():
        if getattr(args, flag):
            command()
            return

    config = settings.load_config()
    if args.hours:
        config["lookback_days"] = max(1 / 24, args.hours / 24)
    if args.ai_test and args.text is not None:
        cmd_ai_text(config, args.text)
        return
    groups = select_groups(config, args.group)
    if args.login:
        cmd_login(config)
    elif args.inspect:
        cmd_inspect(config, groups[0])
    elif args.comment_test:
        cmd_comment_test(args, config, groups)
    else:
        cmd_scan(args, config, groups)


def main(argv=None):
    args = parse_args(argv)
    install.ensure_venv()  # co the chay lai main.py ben trong .venv

    from bot import facebook, ollama, settings, zalo
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
    except (settings.ConfigError, zalo.ZaloError, ollama.OllamaError) as error:
        log.error("%s", error)
        return 1
    except Exception as error:
        log.debug("Traceback:", exc_info=True)
        log.error("%s: %s  (chay lai voi --debug de xem chi tiet)", type(error).__name__, error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
