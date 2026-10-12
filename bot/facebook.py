"""Doc bai trong nhom Facebook bang Playwright.

Phan 1 - ham thuan, khong can trinh duyet: doc ngay dang, nhan dien link bai, loc trung.
Phan 2 - dieu khien trinh duyet: mo nhom, cuon, bam "Xem them", doc khung bai.

Giao dien Facebook thay doi thuong xuyen: kiem tra bang `main.py --inspect`.
Khong tu dang nhap, khong vuot CAPTCHA, khong dung API noi bo.
"""
import base64
import json
import logging
import random
import re
import time
import unicodedata
import urllib.parse
from contextlib import contextmanager
from datetime import datetime, timedelta

from .lead_filter import analyze, normalize
from .settings import PROFILE_DIR

log = logging.getLogger(__name__)

EPOCH = r"\d{9,13}(?:\.\d+)?"
FACEBOOK_HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com"}
MONTHS = {name: index for index, name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"), start=1)}
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800,
                "second": 1, "sec": 1, "minute": 60, "min": 60,
                "hour": 3600, "hr": 3600, "day": 86400, "week": 604800,
                "phut": 60, "gio": 3600, "ngay": 86400, "tuan": 604800}

OLD_POSTS_TO_STOP = 3     # gap lien tiep N bai cu hon lookback -> dung cuon
EMPTY_ROUNDS_TO_STOP = 4  # N vong cuon khong co bai moi -> het feed
MAX_DATE_HOVERS = 30      # so lan re chuot doc tooltip ngay dang moi vong
SCROLL_PIXELS = 1300


class SessionExpired(RuntimeError):
    """Facebook bat dang nhap/xac minh lai."""


class ScanError(RuntimeError):
    """Khong doc duoc bai trong nhom (sai quyen, sai selector, doi giao dien...)."""


# =========================================================== 1. Ham thuan

def window_label(days):
    hours = days * 24
    return f"{hours:g} gio" if hours < 48 else f"{days:g} ngay"


def is_recent(post, days):
    stamp = post.get("published_at")
    now = time.time()
    # +5 phut: gio Facebook hien thi co the lech nhe so voi may.
    return stamp is not None and now - days * 86400 <= stamp <= now + 300


def parse_post_timestamp(value):
    """Epoch/ISO trong thuoc tinh HTML, hoac nhan hien thi ("3 gio", "12 thang 5 luc 10:00")."""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    if re.fullmatch(EPOCH, value):
        stamp = float(value)
        return stamp / 1000 if stamp > 100_000_000_000 else stamp
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed.timestamp()
    except ValueError:
        pass

    text = normalize(value)
    now = datetime.now().astimezone()

    # Ngay day du: "12 thang 5, 2025 luc 10:30" hoac "May 12, 2025 at 10:30 AM".
    vietnamese = re.search(
        r"(\d{1,2})\s+thang\s+(\d{1,2})(?:,?\s+(?:nam\s+)?(20\d{2}))?"
        r"(?:\s+(?:luc|at)\s+(\d{1,2}):(\d{2}))?", text)
    text = re.sub(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(20\d{2})\b", r"\2 \1, \3", text)
    english = re.search(
        r"(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:,?\s+(20\d{2}))?"
        r"(?:\s+at\s+(\d{1,2}):(\d{2})(?:\s*(am|pm))?)?", text)
    if vietnamese or english:
        match = vietnamese or english
        day = int(match[1] if vietnamese else match[2])
        month = int(match[2]) if vietnamese else MONTHS[match[1]]
        year = int(match[3] or now.year)
        hour, minute = int(match[4] or 0), int(match[5] or 0)
        if english and english[6]:
            hour = hour % 12 + (12 if english[6] == "pm" else 0)
        try:
            parsed = datetime(year, month, day, hour, minute).astimezone()
        except ValueError:
            return None
        if not match[3] and parsed > now:  # khong ghi nam -> nam ngoai
            parsed = parsed.replace(year=year - 1)
        return parsed.timestamp()

    # Thoi gian tuong doi.
    if text in {"just now", "vua xong", "vua moi"}:
        return now.timestamp()
    if "yesterday" in text or "hom qua" in text:
        return (now - timedelta(days=1)).timestamp()
    relative = re.search(
        r"\b(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w|phut|gio|ngay|tuan)\b",
        text)
    if relative:
        unit = relative.group(2)
        factor = UNIT_SECONDS.get(unit, UNIT_SECONDS.get(unit.rstrip("s")))
        if factor:
            return (now - timedelta(seconds=int(relative.group(1)) * factor)).timestamp()
    return None


def post_link_parts(href):
    """(group_key, post_id) neu href la link bai goc trong nhom; None neu khong phai."""
    parsed = urllib.parse.urlsplit(urllib.parse.urljoin("https://www.facebook.com/", href))
    if parsed.hostname not in FACEBOOK_HOSTS:
        return None
    query = urllib.parse.parse_qs(parsed.query)
    # Thoi gian cua binh luan khong phai thoi gian dang bai.
    if "comment_id" in query or "reply_comment_id" in query:
        return None
    if parsed.path in {"/story.php", "/permalink.php"}:
        post_ids, group_ids = query.get("story_fbid", []), query.get("id", [])
        if len(post_ids) == 1 and len(group_ids) == 1:
            key, post_id = group_ids[0], post_ids[0]
            if re.fullmatch(r"[A-Za-z0-9._-]+", key) and re.fullmatch(r"[A-Za-z0-9._-]+", post_id):
                return key, post_id
    # Chi nhan link bai trong nhom (ID so hoac pfbid...); bo trang thanh vien/ca nhan.
    match = re.fullmatch(r"/groups/([^/]+)/(?:posts|permalink)/([A-Za-z0-9._-]+)/?", parsed.path)
    return match.groups() if match else None


def canonical_link(href, group):
    """(post_id, permalink chuan) neu href la bai cua `group`."""
    parts = post_link_parts(href)
    if not parts or parts[0] not in group["group_keys"]:
        return None
    key, post_id = parts
    return post_id, f"https://www.facebook.com/groups/{key}/permalink/{post_id}/"


def link_key(url):
    """Khoa on dinh cho cung mot bai du URL khac nhau (dung de chong gui trung)."""
    parts = post_link_parts(url or "")
    if parts:
        return f"facebook:post:{parts[1]}"
    parsed = urllib.parse.urlsplit((url or "").strip())
    host, path = (parsed.hostname or "").lower(), parsed.path.rstrip("/")
    return f"{host}{path}" if host and path else (url or "").strip().lower()


def unique_posts(posts):
    """Giu bai dau tien cho moi permalink, giu nguyen thu tu."""
    result, seen = [], set()
    for post in posts:
        key = link_key(post.get("url", ""))
        if key and key not in seen:
            seen.add(key)
            result.append(post)
    return result


def extract_cards(raw_cards, group, exclude=None):
    """Khung bai tho (tu EXTRACT_JS) -> danh sach post da phan loai (exclude: regex tu khoa loai tru)."""
    posts = []
    for raw in raw_cards:
        candidates = {}
        for anchor in raw.get("post_links", []):
            value = canonical_link(anchor["url"], group)
            if value:
                candidates.setdefault(value[0], {"url": value[1], "dates": []})["dates"].extend(anchor["dates"])
        # Khong doan tu link thanh vien, link binh luan hay bai chia se mo ho.
        if len(candidates) != 1 or not raw["text"].strip():
            continue
        post_id, candidate = next(iter(candidates.items()))
        timestamp, label = None, ""
        for date in candidate["dates"]:
            timestamp = parse_post_timestamp(date)
            if timestamp is not None:
                # Chi giu nhan de doc (vd "3 gio"); bo epoch/ISO.
                label = "" if re.fullmatch(EPOCH, date) or re.match(r"\d{4}-\d{2}-\d{2}", date) else date
                break
        result = analyze(raw["text"], group.get("is_3d_group", True), exclude)
        posts.append({
            "id": post_id, "url": candidate["url"], "group": group["name"], "text": raw["text"],
            "category": result["category"], "candidate": bool(result["category"]),
            "matched": ", ".join(result["keywords"]), "reason": "; ".join(result["reasons"]),
            "published_at": timestamp, "published_label": label,
        })
    return posts


# =================================================== 2. Dieu khien trinh duyet

MESSAGE_SELECTOR = ('[data-ad-rendering-role="story_message"], '
                    '[data-ad-preview="message"], [data-ad-comet-preview="message"]')

# Danh dau moi khung bai (data-fb3d-post), tra ve noi dung + cac link kem ngay dang.
EXTRACT_JS = r"""({article, message: messageSelector}) => {
  const seen = new Set();
  return Array.from(document.querySelectorAll(messageSelector))
    .filter(message => !message.parentElement?.closest(messageSelector))
    .map(message => {
      const feed = message.closest('[role="feed"]');
      let node = message.closest(article);
      if (feed) {
        node = message;
        while (node.parentElement && node.parentElement !== feed) node = node.parentElement;
      }
      if (!node || seen.has(node) || /^(Comment|Reply|Bình luận|Phản hồi)\b/i.test(node.getAttribute('aria-label') || '')) return null;
      seen.add(node);
      node.setAttribute('data-fb3d-post', '1');
      const anchors = Array.from(node.querySelectorAll('a[href]')).filter(a =>
        !a.contains(message) && !a.closest('[aria-label^="Comment by"], [aria-label^="Reply by"]') &&
        Boolean(a.compareDocumentPosition(message) & Node.DOCUMENT_POSITION_FOLLOWING));
      const post_links = anchors.map(a => {
        const t = a.querySelector('time, abbr, [data-utime]');
        const url = new URL(a.href);
        const cached = a.getAttribute('data-fb3d-date-url') === url.pathname ? a.getAttribute('data-fb3d-date') : null;
        const dates = [t?.getAttribute('data-utime'), t?.getAttribute('datetime'),
          cached, t?.getAttribute('title'), a.getAttribute('aria-label'),
          a.getAttribute('title'), t?.textContent, a.textContent].filter(Boolean).map(s => s.trim()).filter(Boolean);
        // Link thoi gian luc dau co the chi tro ve nhom, chua co nhan.
        if (/^\/groups\/[^/]+(?:\/(?:posts|permalink)\/[^/]+)?\/?$/.test(url.pathname)
            || /\/(?:story|permalink)\.php$/.test(url.pathname)) {
          a.setAttribute('data-fb3d-time-link', '1');
        }
        return {url: a.href, dates};
      });
      return {text: message.innerText, links: anchors.map(a => a.href), post_links};
    }).filter(Boolean);
}"""


def chronological_url(url):
    """Mo nhom theo "Bai viet moi" de cuon tu moi den cu."""
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query))
    query.setdefault("sorting_setting", "CHRONOLOGICAL")
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


@contextmanager
def browser_page(headless=True):
    """Mo Chromium voi phien dang nhap luu trong browser-profile/."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                str(PROFILE_DIR), headless=headless, viewport={"width": 1280, "height": 900})
        except Exception as error:
            if "Executable doesn't exist" in str(error):
                raise RuntimeError("Chua cai Chromium cho Playwright: chay python3 main.py --setup") from None
            if "ProcessSingleton" in str(error) or "SingletonLock" in str(error):
                raise RuntimeError("browser-profile dang duoc dung boi bot/trinh duyet khac; tat no truoc") from None
            raise
        try:
            yield context.new_page()
        finally:
            try:
                context.close()
            except Exception as error:  # Ctrl+C/trinh duyet da tu dong: khong che loi goc
                log.debug("Dong trinh duyet: %s", str(error).splitlines()[0] if str(error) else error)


def check_access(page):
    path = urllib.parse.urlsplit(page.url).path
    if path.startswith(("/login", "/checkpoint", "/two_step_verification")):
        raise SessionExpired("Facebook yeu cau dang nhap/xac minh. Dung bot va chay: python3 main.py --login")


def read_cards(page, config, reveal_dates=False):
    selectors = {"article": config["article_selector"], "message": MESSAGE_SELECTOR}
    cards = page.evaluate(EXTRACT_JS, selectors)
    if reveal_dates:
        _reveal_dates(page, cards)
        cards = page.evaluate(EXTRACT_JS, selectors)
    return cards


def _reveal_dates(page, cards):
    """Re chuot vao link thoi gian chua co ngay de doc tooltip, luu vao thuoc tinh data-fb3d-date."""
    resolved = {a["url"] for card in cards for a in card["post_links"]
                if post_link_parts(a["url"]) and any(parse_post_timestamp(d) is not None for d in a["dates"])}
    anchors = page.locator('[data-fb3d-time-link="1"]')
    hovers = 0
    for index in range(anchors.count()):
        if hovers >= MAX_DATE_HOVERS:
            break
        anchor = anchors.nth(index)
        try:
            if not anchor.is_visible():
                continue
            if anchor.get_attribute("href") in resolved or anchor.evaluate("a => a.href") in resolved:
                continue
            if anchor.evaluate('a => a.getAttribute("data-fb3d-date-url") === new URL(a.href).pathname'):
                continue
            hovers += 1
            page.mouse.move(0, 0)
            tooltip = page.locator('[role="tooltip"]:visible').last
            tooltip.wait_for(state="hidden", timeout=1000)
            anchor.hover(timeout=1200)
            tooltip.wait_for(state="visible", timeout=1800)
            label = tooltip.inner_text(timeout=500)
            if parse_post_timestamp(label) is not None:
                anchor.evaluate('''(a, text) => {
                  a.setAttribute("data-fb3d-date", text);
                  a.setAttribute("data-fb3d-date-url", new URL(a.href).pathname);
                }''', label)
        except Exception as error:
            log.debug("Bo qua tooltip ngay dang: %s", str(error).splitlines()[0])


def _expand_posts(page, config):
    """Bam "Xem them" trong cac khung bai dang hien de doc du noi dung."""
    for label in config["expand_labels"]:
        buttons = page.locator('[data-fb3d-post="1"]').get_by_text(label, exact=True)
        for index in range(min(buttons.count(), 12)):
            try:
                button = buttons.nth(index)
                if button.is_visible():
                    button.click(timeout=1500)
            except Exception:
                pass


def scan_group(page, group, config, on_post=None):
    """Cuon nhom (bai moi truoc) den khi gap bai cu hon lookback_days thi dung.

    on_post(post) duoc goi NGAY khi thay mot bai can in trong khung thoi gian,
    de gui Zalo luon thay vi doi quet xong ca nhom.
    Tra ve cac bai trong khung thoi gian, bai can in xep truoc.
    """
    days = config["lookback_days"]
    window = window_label(days)
    log.info("Dang doc nhom: %s (bai trong %s)", group["name"], window)
    page.goto(chronological_url(group["url"]), wait_until="domcontentloaded", timeout=60000)
    check_access(page)
    try:
        page.locator(MESSAGE_SELECTOR).first.wait_for(timeout=30000)
    except Exception:
        check_access(page)
        raise ScanError("Khong thay bai nao: kiem tra quyen vao nhom va article_selector") from None

    posts = {}          # post_id -> post
    notified = set()
    old_streak = 0      # so bai cu (qua lookback) lien tiep o cuoi feed
    empty_rounds = 0    # so vong cuon khong them bai moi
    cards = read_cards(page, config)  # danh dau khung bai de _expand_posts tim duoc nut
    max_rounds = config["max_scroll_rounds"]
    for round_no in range(1, max_rounds + 1):
        check_access(page)
        _expand_posts(page, config)
        cards = read_cards(page, config, reveal_dates=True)
        added = 0
        for post in extract_cards(cards, group, config["exclude_re"]):
            previous = posts.get(post["id"])
            if previous is None:
                added += 1
                # Bai ghim cu o dau feed chi lam tang tam; gap bai moi se reset.
                if post["published_at"] is not None:
                    old_streak = 0 if is_recent(post, days) else old_streak + 1
            elif post["published_at"] is None:
                post["published_at"] = previous["published_at"]
                post["published_label"] = previous["published_label"]
            posts[post["id"]] = post
        empty_rounds = 0 if added else empty_rounds + 1

        recent = [post for post in posts.values() if is_recent(post, days)]
        stop = False
        if on_post:
            # Ngay dang co the doc duoc o vong sau, nen kiem tra lai moi vong.
            for post in recent:
                if post["candidate"] and post["id"] not in notified:
                    notified.add(post["id"])
                    if on_post(post) is True:  # nguoi goi da du bai (--comment-test)
                        stop = True
                        break
        if stop:
            log.info("Da du bai can, dung cuon o vong %d", round_no)
            return [post for post in unique_posts(posts.values()) if is_recent(post, days)]
        log.debug("Vong %d: %d khung, %d bai goc, %d trong %s, %d can in, %d bai cu lien tiep",
                  round_no, len(cards), len(posts), len(recent), window,
                  sum(p["candidate"] for p in recent), old_streak)

        if old_streak >= OLD_POSTS_TO_STOP:
            log.info("Da den bai cu hon %s sau %d vong; dung cuon", window, round_no)
            break
        if empty_rounds >= EMPTY_ROUNDS_TO_STOP:
            log.info("Het bai moi sau %d vong; dung cuon", round_no)
            break
        if len(recent) >= config["max_posts_per_group"]:
            log.info("Du %d bai (max_posts_per_group); dung cuon", len(recent))
            break
        if round_no < max_rounds:
            page.mouse.wheel(0, SCROLL_PIXELS)
            page.wait_for_timeout(2000)
    else:
        log.info("Het %d vong cuon (max_scroll_rounds)", max_rounds)

    if not posts:
        raise ScanError(f"Khong doc duoc link bai goc (khung bai: {len(cards)}). "
                        "Chay --inspect de kiem tra selector/group_keys.")
    dated = sum(post["published_at"] is not None for post in posts.values())
    if not dated:
        raise ScanError(f"Doc duoc {len(posts)} bai nhung khong doc duoc ngay dang; chua the loc {window}.")
    recent = [post for post in unique_posts(posts.values()) if is_recent(post, days)]
    candidates = sum(post["candidate"] for post in recent)
    log.info("%s: %d bai goc (%d co ngay), %d trong %s, %d can in",
             group["name"], len(posts), dated, len(recent), window, candidates)
    # Uu tien bai can in, khong de gioi han so bai cat mat khach.
    recent.sort(key=lambda post: not post["candidate"])
    return recent[:max(config["max_posts_per_group"], candidates)]


def print_diagnostics(page, group, config):
    """In 5 khung bai dau de xem vi sao khong nhan ra link bai (dung cho --inspect)."""
    raw_cards = read_cards(page, config, reveal_dates=True)
    print(f"Khung bai tim thay: {len(raw_cards)}")
    for index, raw in enumerate(raw_cards[:5], start=1):
        print(json.dumps({
            "card": index,
            "text_preview": raw["text"][:240],
            "post_links": raw.get("post_links", []),
            "links": raw["links"][:12],
            "recognized_post_links": [link for link in raw["links"] if canonical_link(link, group)],
        }, ensure_ascii=False, indent=2))


# ======================================================= 3. Binh luan vao bai

# O nhap binh luan cua bai (khong phai o tra loi binh luan, o dang bai nhom hay Messenger).
COMMENT_BOX_LABEL = re.compile(
    r"^(?:write a (?:public )?comment|comment as |write an answer|viết bình luận|bình luận dưới tên"
    r"|bình luận với tư cách|viết câu trả lời)", re.I)
COMMENT_BUTTON_LABELS = ("Viết bình luận", "Bình luận", "Leave a comment", "Comment")
JOIN_LABELS = ("Tham gia nhóm", "Join group")
BLOCK_TEXT = re.compile(
    r"we limit how often|can.t use this feature|going too fast|against our community standards"
    r"|temporarily blocked|misusing (?:this|a) feature"
    r"|chúng tôi giới hạn tần suất|tạm thời bị chặn|không thể dùng tính năng|tiêu chuẩn cộng đồng", re.I)
COMMENT_MUTATION = "CreateComment"  # useCometUFICreateCommentMutation


class CommentError(RuntimeError):
    """Chua bam gui (khong thay o binh luan, go sai chu...): co the thu lai luot sau."""


class CommentUncertain(RuntimeError):
    """Da bam gui nhung khong xac nhan duoc: KHONG thu lai (tranh binh luan hai lan)."""


class CommentBlocked(RuntimeError):
    """Facebook bao gioi han/chan binh luan: dung binh luan nhieu ngay.

    submitted=True: bao sau khi da bam Enter, binh luan co the da len (khong dang lai).
    """
    submitted = False


def _letters(text):
    """So sanh noi dung go vao: bo emoji, dau cau, khoang trang (Facebook doi emoji thanh anh)."""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFC", text or "").lower())


def _comment_scope(page):
    """Bai mo trong hop thoai thi chi tim trong hop thoai tren cung; khong thi trong vung chinh."""
    dialogs = page.locator('[role="dialog"]:visible')
    for index in range(dialogs.count() - 1, -1, -1):
        dialog = dialogs.nth(index)
        if dialog.locator('[role="textbox"][contenteditable="true"]').count():
            return dialog
    main = page.locator('[role="main"]')
    return main.first if main.count() else page.locator("body")


def _comment_boxes(scope):
    boxes = scope.locator('[role="textbox"][contenteditable="true"]:visible')
    found, labels = [], []
    for index in range(boxes.count()):
        box = boxes.nth(index)
        label = (box.get_attribute("aria-label") or box.get_attribute("aria-placeholder") or "").strip()
        labels.append(label)
        if COMMENT_BOX_LABEL.search(label):
            found.append(box)
    return found, labels


def _block_notice(page):
    """Noi dung thong bao gioi han/chan cua Facebook dang hien, hoac ""."""
    for selector in ('[role="dialog"]:visible', '[role="alert"]:visible'):
        notes = page.locator(selector)
        try:
            count = notes.count()
        except Exception:
            continue
        for index in range(count):
            note = notes.nth(index)
            try:
                # Hop thoai chua bai/binh luan la noi dung nguoi dung, khong phai thong bao cua Facebook.
                if note.locator(f'[role="article"], [role="textbox"], {MESSAGE_SELECTOR}').count():
                    continue
                text = note.inner_text(timeout=1000)
            except Exception:
                continue
            if BLOCK_TEXT.search(text):
                return "Facebook gioi han binh luan: " + " ".join(text.split())[:160]
    return ""


def _comment_link(url, created):
    """Link toi thang binh luan vua tao (url bai + ?comment_id=); khong doc duoc id thi tra ve url bai."""
    stack, ids = [created], []
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if key == "url" and isinstance(value, str) and "comment_id=" in value:
                    return value
                if key in ("legacy_fbid", "id") and isinstance(value, (str, int)):
                    ids.append(str(value))
                stack.append(value)
        elif isinstance(item, list):
            stack.extend(item)
    for value in ids:
        if not value.isdigit():  # id dang base64 "comment:<bai>_<binh luan>"
            try:
                value = base64.b64decode(value + "=" * (-len(value) % 4)).decode()
            except (ValueError, UnicodeDecodeError):
                continue
            value = value.rsplit("_", 1)[-1] if value.startswith("comment:") else ""
        if value.isdigit():
            return f"{url.split('?')[0]}?comment_id={value}"
    return url


def _comment_result(response):
    """dict comment_create neu Facebook tao binh luan; chuoi loi neu bi tu choi."""
    body = response.text()
    errors = []
    for chunk in body.removeprefix("for (;;);").splitlines():
        try:
            data = json.loads(chunk)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        created = (data.get("data") or {}).get("comment_create")
        if created:
            return created if isinstance(created, dict) else {"ok": created}
        for error in data.get("errors") or []:
            parts = [str(error.get(k) or "") for k in ("summary", "description", "message")] \
                if isinstance(error, dict) else []
            errors.append((" ".join(part for part in parts if part) or str(error))[:300])
    return "; ".join(errors) or "Facebook khong xac nhan"


def post_comment(page, url, text, before_submit=None):
    """Mo bai, go `text` (mot dong) vao o binh luan, bam Enter MOT lan, xac nhan qua phan hoi mang.

    before_submit(): goi ngay truoc khi bam Enter (ghi DB "da binh luan" de bi tat giua chung
    cung khong dang lai). Tra ve (canh_bao, link): canh_bao "" hoac noi dung neu da dang nhung
    Facebook bao gioi han ngay sau do; link toi binh luan (hoac link bai). Nem CommentError (loi truoc khi bam gui, ngoai le Playwright khac
    cung la truoc khi gui), CommentUncertain (da bam gui, khong ro ket qua: khong thu lai),
    CommentBlocked (Facebook chan), SessionExpired.
    """
    text = " ".join(text.split())  # \n trong press_sequentially = Enter = gui giua chung
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    check_access(page)
    page.wait_for_timeout(random.randint(3000, 5000))  # doc bai nhu nguoi that
    check_access(page)
    if notice := _block_notice(page):
        raise CommentBlocked(notice)

    scope = _comment_scope(page)
    boxes, labels = _comment_boxes(scope)
    if not boxes:
        for label in COMMENT_BUTTON_LABELS:  # bai nhieu binh luan: o nhap chi hien sau khi bam nut
            button = scope.locator(f'[role="button"][aria-label="{label}"]:visible')
            if button.count():
                button.first.click(timeout=3000)
                page.wait_for_timeout(1500)
                scope = _comment_scope(page)
                boxes, labels = _comment_boxes(scope)
                break
    if len(boxes) != 1:
        if not boxes and any(page.get_by_role("button", name=name).count() for name in JOIN_LABELS):
            raise CommentError("tai khoan chua la thanh vien nhom")
        raise CommentError(f"tim thay {len(boxes)} o binh luan (o nhap tren trang: {labels[:6]}); "
                           "bai tat binh luan hoac Facebook doi giao dien")
    box = boxes[0]
    label = box.get_attribute("aria-label") or ""
    if label.lower().startswith(("comment as", "bình luận dưới tên", "bình luận với tư cách")):
        log.info("O binh luan: %s", label)  # kiem tra dung tai khoan/Trang dang binh luan

    box.scroll_into_view_if_needed(timeout=5000)
    box.click(timeout=5000)
    if not box.evaluate("el => el === document.activeElement || el.contains(document.activeElement)"):
        raise CommentError("khong dat duoc con tro vao o binh luan")
    if box.inner_text().strip():  # ban nhap cu Facebook giu lai
        box.press("Control+a")
        box.press("Backspace")
        page.wait_for_timeout(400)
    page.wait_for_timeout(random.randint(1000, 3000))
    box.press_sequentially(text, delay=random.randint(25, 70))
    page.wait_for_timeout(random.randint(1500, 3000))  # cho xem truoc link

    def clear():
        box.press("Control+a")
        box.press("Backspace")

    if page.locator('[role="listbox"]:visible').count():
        clear()
        raise CommentError("Facebook mo goi y nhac ten/hashtag; huy de khong gan nham")
    typed = box.inner_text()
    if _letters(typed) != _letters(text):
        clear()
        raise CommentError(f"chu go vao khong khop: {' '.join(typed.split())[:80]!r}")

    def is_comment_request(response):
        request = response.request
        return (request.method == "POST" and "/api/graphql" in response.url
                and (COMMENT_MUTATION in request.headers.get("x-fb-friendly-name", "")
                     or COMMENT_MUTATION in (request.post_data or "")))

    if before_submit:
        before_submit()
    try:
        with page.expect_response(is_comment_request, timeout=25000) as info:
            box.press("Enter")
        result = _comment_result(info.value)
    except Exception as error:  # het thoi gian cho / khong doc duoc phan hoi / trang dong
        result = error
    # Da bam Enter: tu day moi loi deu la "khong ro", khong bao gio thu lai.
    try:
        page.wait_for_timeout(2000)
        notice = _block_notice(page)
    except Exception:
        notice = ""
    if isinstance(result, dict):
        return notice, _comment_link(url, result)
    if isinstance(result, str) and BLOCK_TEXT.search(result):
        raise CommentBlocked(f"Facebook gioi han binh luan: {result}")  # Facebook tu choi, chua dang
    if notice:
        error = CommentBlocked(notice)
        error.submitted = True
        raise error
    if isinstance(result, str):
        raise CommentUncertain(f"Facebook tra loi loi: {result}")
    try:
        cleared = not box.inner_text(timeout=2000).strip()
    except Exception:
        cleared = False
    raise CommentUncertain(("o binh luan da trong" if cleared else "o binh luan con chu")
                           + f" nhung khong thay phan hoi Facebook ({type(result).__name__})")
