"""Loc bai Facebook: nguoi dang CAN THUE / NHO IN 3D (khach hang), khong phai
ben ban dich vu, hoi loi may, mua ban may/nhua hay in an 2D.

Cach lam:
1. Chuan hoa: bo dau, viet thuong, doi teencode (mk -> minh, ib -> inbox, ...).
2. Loai ngay: bai co tu khoa loai tru (config.json "exclude_keywords": HN, in resin, pass may...),
   quang cao dich vu, tuyen dung, in an 2D khong lien quan 3D.
3. Tim y dinh "nho/thue/tim cho in" (manh) va "can/muon in" (yeu).
4. Y dinh yeu bi chan neu bai la hoi ky thuat / mua ban may.
"""
import re
import unicodedata


def normalize(text):
    text = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


# Teencode / viet tat thuong gap trong nhom Facebook Viet Nam.
_SLANG = [
    (r"\bin\s*3\s*d\b", "in 3d"),
    (r"\b3\s*d\b", "3d"),
    (r"\b(?:mk|mik|mjk|mjnh|mh|mnh)\b", "minh"),
    (r"\b(?:e)\b", "em"),
    (r"\b(?:t|tui|to)\b(?=\s+(?:can|muon|dang|co|nho))", "toi"),
    (r"\b(?:ng|ngta|nguoj)\b", "nguoi"),
    (r"\b(?:k|ko|kh|kg|hok|hong|khong)\b", "khong"),
    (r"\b(?:dc|duoc|dk|đc)\b", "duoc"),
    (r"\b(?:ae|ace|ac|a/c|anh chi em)\b", "anh em"),
    (r"\b(?:mn|mng|mog)\b", "moi nguoi"),
    (r"\b(?:bac|cac bac|cac anh)\b", "bac"),
    (r"\b(?:ib|inb|ibx|nt|nhan tin)\b", "inbox"),
    (r"\b(?:dum|gium|giup do)\b", "giup"),
    (r"\b(?:bnhieu|bnh|bn tien|bao nhieu tien)\b", "bao nhieu"),
    (r"\b(?:lh)\b", "lien he"),
    (r"\b(?:sdt|zl)\b", "zalo"),
    (r"\b(?:sp)\b", "san pham"),
    (r"\b(?:file\s+)?(?:\.?stl|\.?obj|\.?3mf|\.?step|\.?stp)\b", "file stl"),
]


def exclude_pattern(words):
    """Regex khop bat ky tu khoa nao (bo dau, nguyen tu: "hn" khong khop "john"); None neu rong."""
    parts = [r"\s+".join(map(re.escape, normalize(word).split())) for word in words or []]
    parts = [part for part in parts if part]
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])") if parts else None


def prepare(text):
    value = normalize(text)
    for pattern, repl in _SLANG:
        value = re.sub(pattern, repl, value)
    return re.sub(r"\s+", " ", value)


# Doi tuong in 3D: dung de xac nhan bai noi ve in 3D (bat buoc o nhom khong chuyen 3D).
SUBJECT = re.compile(
    r"\b(?:in 3d|3d|resin|fdm|sla|file stl|mo hinh|figure|figurine|sa ban|filament"
    r"|nhua (?:pla|petg|abs|tpu|asa|pa|nylon|resin)|pla|petg|abs|tpu"
    r"|chi tiet|linh kien|vo hop|vo may|hop dung|khuon|prototype|mau thu|mockup"
    r"|cosplay|mat na|tuong|banh rang|gia do|moc khoa|cup|ky niem chuong"
    r"|do choi|nhan vat|dong co|phu kien|thay the|logo noi)\b"
)

# Y dinh MANH: chac chan la nguoi can tim ben in.
STRONG = [
    # thue / nho in
    r"\b(?:can|muon|tim)?\s*thue\s+(?:nguoi\s+|ben\s+|xuong\s+|ai\s+|cho\s+)?(?:in|gia cong|lam|thiet ke|ve|scan|dung)\b",
    r"\b(?:minh|em|toi|can|muon|cho|xin|dinh)\s+nho\b.{0,40}\b(?:in|gia cong|lam|thiet ke|scan)\b",
    r"\bnho\s+(?:ai|ban|bac|anh chi|anh em|moi nguoi|cac ban|cao nhan)\b.{0,40}\b(?:in|gia cong|lam|thiet ke|scan)\b",
    # tim nguoi / cho / xuong in
    r"\b(?:tim|kiem|can tim|dang tim|tim giup|can)\s+(?:1\s+|mot\s+)?(?:nguoi|tho|cho|noi|ben|xuong|don vi|dich vu|co so|shop|cua hang|ai|ban|bac|anh em)\b.{0,40}\b(?:in|gia cong|lam mo hinh|thiet ke|scan)\b",
    # ai / bac nao ... in duoc / nhan in / in giup
    r"\b(?:co\s+)?(?:ai|bac nao|ban nao|anh chi nao|anh em nao|moi nguoi ai|cao nhan nao|xuong nao|ben nao|shop nao|cho nao|noi nao|don vi nao)\b"
    r".{0,40}\b(?:nhan\s+(?:in|gia cong|lam|thiet ke|order|scan|duoc|khong|ho|giup)|in\s+(?:duoc(?!.{0,40}\bchua\b)|giup|ho|thue|cho\s+(?:minh|em|toi))|lam\s+duoc(?!.{0,40}\bchua\b)|co the in|gia cong)\b",
    # in ho / giup + nguoi
    r"\bin\s+(?:giup|ho|thue|gia cong)\s+(?:minh|em|toi|chau|con|anh|chi|ban than)\b",
    r"\bin\s+(?:giup|ho)\b.{0,30}\b(?:voi|nhe|duoc khong|khong a|a\b)",
    # hoi gia / bao gia
    r"\b(?:xin|cho\s+(?:minh|em|toi)\s+xin|hoi|can|nho)\s+(?:bao\s+)?gia\b.{0,80}\b(?:in|3d|mo hinh|file|chi tiet|san pham)\b",
    r"\b(?:bao gia|bao gia giup|bao gia cho)\s+(?:giup\s+)?(?:minh|em|toi)\b",
    r"\b(?:in|lam|gia cong)\b.{0,60}\b(?:het|tam|khoang|mat|gia)\s+(?:bao nhieu|bn)\b(?!\s*(?:nhua|gram|gam|g\b|gr\b|gio|tieng|phut|thoi gian|lop|layer|ml|resin|cuon))",
    r"\b(?:in|lam)\b.{0,60}\b(?:bao nhieu tien|chi phi bao nhieu|gia the nao|gia sao|ton bao nhieu)\b",
    # dat in / order
    r"\b(?:can|muon|dinh|xin)\s+(?:dat|order)\s+(?:in|lam|gia cong)\b",
    r"\b(?:can|muon|dinh)\s+gia cong\b",
    # o dau / cho nao in
    r"\b(?:o dau|cho nao|noi nao|ben nao)\b.{0,30}\b(?:nhan\s+)?(?:in|gia cong)\b.{0,40}\b(?:3d|resin|mo hinh|file|chi tiet|duoc|uy tin|tot|re)\b",
    r"\bin\s+(?:3d\s+|resin\s+|mo hinh\s+)?o\s+dau\b",
    r"\b(?:co ai|ai)\s+o\s+(?:khu vuc\s+)?[a-z ]{2,25}\b.{0,30}\b(?:in|co may in)\b",
    # co file can in
    r"\b(?:co|minh co|em co|toi co)\s+(?:san\s+)?(?:file stl|file|ban ve)\b.{0,60}\b(?:can|muon|nho|ai)\b.{0,20}\bin\b",
    # tieng Anh
    r"\b(?:need|looking for|anyone|someone|who can)\b.{0,40}\b(?:print|printing service|3d print)\b",
]

# Y dinh YEU: co nhu cau in nhung chua chac la thue (co the la tu in).
WEAK = [
    r"\b(?:minh|em|toi|chau|con|anh|chi|ben minh|cong ty)\s+(?:dang\s+)?(?:can|muon|dinh)\b.{0,60}\b(?:in|lam)\b",
    r"\b(?:can|muon)\s+(?:gap\s+)?(?:in|lam)\b(?!\s+(?:may|thu|nghiem))",
    r"\b(?:can|muon)\b.{0,40}\b(?:mo hinh|sa ban|figure|vo hop|chi tiet|linh kien|moc khoa|cosplay|mat na|cup|banh rang)\b",
    r"\bco ai\b.{0,40}\b(?:may in|in 3d|resin)\b",
]

# Ben BAN dich vu (quang cao) -> loai.
SELLER = [
    r"^(?:\W*)(?:nhan|chuyen nhan|chuyen|xuong|dich vu|cung cap|thanh ly|pass)\s+(?:in|gia cong|thiet ke|scan|ban|cac loai)\b",
    r"\b(?:ben minh|ben em|ben toi|chung toi|chung em|shop|xuong minh|xuong em|cong ty minh|cong ty em|minh chuyen|em chuyen)\b"
    r".{0,60}\b(?:nhan|chuyen|cung cap|co dich vu|nhan order|nhan don|san sang)\b",
    r"\b(?:ai|anh chi|anh em|khach|cac ban|ban nao|moi nguoi|bac nao|quy khach|ai do)\s+(?:nao\s+)?(?:dang\s+|co\s+)?(?:can|co nhu cau|muon)\s+(?:in|gia cong|thiet ke|lam|scan|dat)\b",
    r"\b(?:nhan in|nhan gia cong)\b.{0,30}\b(?:theo yeu cau|moi chat lieu|so luong lon|gia re|gia tot|lay lien|lay nhanh|toan quoc)\b",
    r"\b(?:in 3d|dich vu in)\s+(?:gia re|gia tot|uy tin|chat luong|theo yeu cau)\b",
    r"\b(?:ung ho|support)\s+(?:minh|em|shop)\b",
    # "CAN IN 3D? CO NGAY! 500d/g": tieu de cau khach cua ben ban
    r"\b(?:can|muon)?\s*in\s*(?:3d|resin|fdm)\b.{0,40}\b(?:co ngay|lay ngay|lay lien|co lien|gia chi)\b",
    # gia theo gram + moi lien he
    r"\d+\s*(?:k|d|vnd|dong)\s*/\s*(?:g|gr|gram|gam)\b.{0,150}\b(?:inbox|lien he|bao gia|zalo|hotline)\b",
    r"\b(?:minh|em|ben minh|ben em|shop)\s+(?:se\s+)?(?:tu van|bao gia)\b(?!\s+(?:giup|dum|duoc|voi|cho minh|cho em))",
    r"\bgui\s+(?:mau|file|hinh|anh)\s+qua\s+inbox\b",
]
AD_SIGNALS = [
    r"\bgia (?:re|tot|uu dai|hat de|canh tranh|chi tu)\b", r"\bchi tu\s*\d", r"\buy tin\b",
    r"\bchat luong cao\b", r"\bnhanh chong\b", r"\bfreeship|mien phi van chuyen\b",
    r"\bship (?:cod|toan quoc)|\btoan quoc\b", r"\bhotline\b", r"\blien he\b",
    r"\bnhan don\b", r"\bnhan order\b", r"\bkhuyen mai|giam gia|uu dai\b",
    r"\d+\s*(?:k|d|vnd|dong)\s*/\s*(?:g|gr|gram|gam|cm)\b", r"\b0\d{2,3}[ .-]?\d{3}[ .-]?\d{3,4}\b",
    r"\b(?:co|xuat|da gom)\s+vat\b|\bhoa don\b", r"\bson\s+(?:mo hinh|hoan thien)\b",
    r"\b(?:co ngay|lay ngay|lay lien)\b", r"\b(?:tu van|bao gia)\s*(?:&|va)\s*(?:tu van|bao gia)\b",
    r"\bwebsite|fanpage|www\.", r"\bcam ket\b", r"\bbao hanh\b",
]

# Khong phai khach thue in.
SELLING_GEAR = (r"\b(?:can ban|muon ban|ban lai|thanh ly|pass lai|pass|de lai|gom|ban gap)\s+(?:\d+\s+)?"
                r"(?:may|bo|cuon|lo|chai|nhua|filament|resin|bambu|creality|elegoo|anycubic|prusa|ender|a1|p1s|x1c|k1)\b")
HIRING = r"\b(?:tuyen dung|tuyen nhan vien|tuyen tho|tuyen ctv|tuyen cong tac vien|viec lam|can tuyen|tim viec)\b"
TRADE = (r"\b(?:can mua|muon mua|tim mua|dinh mua|nen mua|mua may|mua nhua|thanh ly|pass lai|pass may|can ban|ban may|"
         r"de lai|gom may|san may)\b|\b(?:mua|ban)\b.{0,30}\b(?:may in|may|nhua|filament|resin|bambu|creality|elegoo|"
         r"anycubic|prusa|ender|a1 mini|a1 combo|p1s|p1p|x1c|k1|saturn|mars|photon)\b")
TECH = (r"\b(?:loi|bi loi|bi hong|warp|cong venh|kep nhua|ket nhua|tac|nghet|nozzle|dau phun|ban nhiet|bed|"
        r"slicer|cura|orca|prusaslicer|bambu studio|chitubox|lychee|setting|thong so|cai dat|firmware|calib|"
        r"layer|bong|khong dinh|dinh ban|xin kinh nghiem|kinh nghiem|tu van|nen chon|co nen|so sanh|"
        r"review|khoe|thanh qua|chia se|share file|tang file|free file|huong dan|lam sao|lam the nao|"
        r"the nao|nhu the nao|cach nao|tai sao|vi sao|nguyen nhan|giai phap)\b")
PRINT_2D = (r"\bin\s+(?:an|decal|to roi|bat|offset|tem|nhan dan|hoa don|giay|ao|lua|uv|chuyen nhiet|canvas|"
            r"name card|card visit|danh thiep|lich|phun|laser|mau sac|hop giay|catalogue|catalog|brochure|bang ron|"
            r"standee|backdrop|the nhua|ly|coc)\b")

_QUESTION_BEFORE = re.compile(
    r"\b(?:ai|nao|co ai|tim|can|cho|o dau|nguoi|nho|thue|xin|hoi|biet|gioi thieu)\b")


def _seller_by_nhan(value):
    """'nhan in' sau cau hoi (ai nhan in?) la khach; dung dau/ben minh nhan in la ben ban."""
    for match in re.finditer(r"\b(?:chuyen\s+)?nhan\s+(?:in|gia cong|thiet ke|scan|order)\b", value):
        before = value[max(0, match.start() - 35):match.start()]
        if _QUESTION_BEFORE.search(before):
            continue
        return True
    return False


def _find(patterns, value):
    return [m.group(0).strip() for p in patterns if (m := re.search(p, value))]


def analyze(text, printing_group=True, exclude=None):
    """Tra ve dict: category ('' neu khong phai khach), score, reasons, keywords.

    printing_group=False: nhom khong chuyen in 3D, bai phai nhac doi tuong in 3D.
    exclude: regex tu exclude_pattern(); bai khop thi bo luon.
    """
    value = prepare(text)
    result = {"category": "", "score": 0, "reasons": [], "keywords": []}
    if not value:
        return result
    if exclude and (hit := exclude.search(normalize(text))):
        result["reasons"].append("tu khoa loai tru: " + hit.group(0))
        return result

    strong = _find(STRONG, value)
    weak = _find(WEAK, value)
    subjects = list(dict.fromkeys(m.group(0) for m in SUBJECT.finditer(value)))
    seller = _find(SELLER, value)
    ads = sum(bool(re.search(p, value)) for p in AD_SIGNALS)
    first_person = re.search(r"\b(?:minh|em|toi|chau|con)\s+(?:dang\s+)?(?:can|muon|nho|tim|co file|dinh)\b", value)

    def reject(reason):
        result["reasons"].append(reason)
        return result

    if re.search(SELLING_GEAR, value):
        return reject("ban may/nhua")
    if re.search(HIRING, value):
        return reject("tuyen dung")
    if seller and not first_person:
        return reject("quang cao dich vu: " + seller[0])
    if _seller_by_nhan(value) and not strong:
        return reject("ben nhan in")
    if ads >= 3 or (ads >= 2 and not (strong or first_person)):
        return reject(f"nhieu dau hieu quang cao ({ads})")
    if re.search(PRINT_2D, value) and not subjects:
        return reject("in an 2D")
    if not printing_group and not subjects:
        return reject("khong noi ve in 3D")

    score = 3 * len(strong) + len(weak) + min(len(subjects), 2) - ads
    tech = re.search(TECH, value)
    trade = re.search(TRADE, value)
    if not strong:
        if trade:
            return reject("mua ban may/nhua")
        if tech:
            return reject("hoi ky thuat: " + tech.group(0))
        if not weak:
            return reject("khong co y dinh can in")
        if not subjects:
            return reject("y dinh yeu, khong ro doi tuong in 3D")

    result["score"] = score
    result["category"] = "CẦN IN 3D" if strong else "CÓ THỂ CẦN IN 3D"
    result["keywords"] = list(dict.fromkeys(strong + weak + subjects))[:8]
    return result
