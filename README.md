# Bot tìm khách cần in 3D trên Facebook → gửi link vào nhóm Zalo

Bot đọc bài trong các nhóm Facebook mà tài khoản của bạn đã tham gia (Python + Playwright). Bài nào có người cần thuê/nhờ in 3D thì bot gửi **mỗi bài một tin** vào **nhóm Zalo**, kèm trích đoạn, thời gian đăng và link bài gốc.

- Chạy `python3 main.py` là bot chạy liên tục: **cứ 2 giờ quét lại các bài đăng trong 24 giờ qua**, có bài cần in mới thì gửi, không có thì thôi.
- Chống gửi trùng: mỗi link chỉ gửi một lần; bài cùng nội dung đăng ở nhiều nhóm (hoặc đăng lại) cũng chỉ gửi một lần.
- Nhắn **`scan`** (hoặc `quét`, `@TênBot scan`) trong nhóm Zalo để quét ngay.
- Dùng Zalo Bot Platform chính thức, **không cần** webhook hay tên miền.

**Chỉ có một lệnh: `python3 main.py`.** Lần đầu chạy, bot tự tạo `.venv`, cài thư viện, hỏi token và tìm ID nhóm Zalo.

## Lưu ý

- Meta không cho phép thu thập dữ liệu tự động khi chưa được họ đồng ý. Bot không tự đăng nhập, không vượt CAPTCHA, không dùng API nội bộ.
- Facebook đổi giao diện thường xuyên. Kiểm tra bằng `--inspect` và `--dry-run` trước khi chạy thật.
- Bot lọc theo từ khóa, không dùng AI; quảng cáo "nhận in 3D" vẫn có thể lọt.
- Zalo Bot giới hạn số tin theo gói. Khi hết quota (lỗi 429), bài được giữ lại và gửi ở lượt sau.

## Bắt đầu

1. Vào https://bot.zaloplatforms.com, tạo bot, copy **Bot Token**. Trong app Zalo, thêm bot vào nhóm muốn nhận link.
2. Cài đặt và nhập token:
   ```bash
   python3 main.py --setup
   ```
3. Lấy ID nhóm Zalo: chạy lệnh dưới, rồi trong vòng 2 phút gửi một tin **có nhắc tên bot** (`@TênBot hello`) vào nhóm.
   ```bash
   python3 main.py --chat-id
   ```
4. Đăng nhập Facebook và kiểm tra:
   ```bash
   python3 main.py --login        # đăng nhập, chọn "Bài viết mới" cho từng nhóm
   python3 main.py --send-test    # gửi tin thử vào nhóm Zalo
   python3 main.py --dry-run      # quét thử, in kết quả, KHÔNG gửi
   ```
5. (Tùy chọn) Không muốn nhận dồn bài cũ ở lần chạy đầu: `python3 main.py --bootstrap`
6. Chạy bot: `python3 main.py` (Ctrl+C để dừng).

## Các lệnh

| Lệnh | Tác dụng |
|---|---|
| `python3 main.py` | Chạy bot liên tục, gửi từng link vào nhóm |
| `--once` | Quét và gửi một lượt rồi thoát |
| `--dry-run` | Quét một lượt, in từng bài kèm lý do giữ/bỏ, không gửi |
| `--bootstrap` | Đánh dấu bài hiện có là đã xem, không gửi |
| `--setup` | Cài/cập nhật thư viện, Chromium, nhập token |
| `--chat-id` | Tìm và lưu ID nhóm Zalo |
| `--send-test` | Gửi tin thử |
| `--login` | Đăng nhập Facebook |
| `--inspect` | Kiểm tra bot đọc bài có đúng không |
| `--install-service` / `--remove-service` | Cài/gỡ service chạy 24/7 |

Tùy chọn thêm: `--group "Tên nhóm"` (chỉ quét một nhóm), `--hours 24` (chỉ lấy bài trong N giờ), `--headed` (hiện trình duyệt), `--debug` (log chi tiết), `--recheck` (cùng `--once`: gửi lại bài cũ nếu nay khớp bộ lọc). Xem đủ: `python3 main.py --help`.

## Cấu hình

`config.json`:

- `groups`: danh sách nhóm. `group_keys` là phần sau `/groups/` trong link. Nếu link nhóm dùng tên nhưng link bài dùng ID số, thêm cả hai: `["tennhom", "123456789"]`. Nhóm không chuyên in 3D thì thêm `"is_3d_group": false` để lọc chặt hơn.
- `interval_seconds`: khoảng cách giữa hai lần quét, tính từ lúc bắt đầu lượt trước (mặc định 7200 = 2 giờ, tối thiểu 60). Mỗi lượt mở trình duyệt, quét xong thì đóng.
- `lookback_days`: chỉ lấy bài trong N ngày gần nhất (1 = 24 giờ). Bot dừng cuộn khi gặp 3 bài cũ hơn mốc này liên tiếp.
- `max_posts_per_group`, `max_scroll_rounds`: giới hạn an toàn mỗi lượt.
- `article_selector`, `expand_labels`: selector/nhãn nút "Xem thêm" của Facebook; chỉ sửa khi `--inspect` báo sai.

`.env`: `ZALO_BOT_TOKEN` (token bot) và `ZALO_CHAT_ID` (do `--chat-id` tự điền).

Bộ lọc khách cần in nằm trong `bot/lead_filter.py`.

## Gỡ lỗi

- **Log:** màn hình hiện mức INFO; file `logs/bot.log` luôn ghi chi tiết (DEBUG) kèm traceback đầy đủ, tự xoay vòng.
- **`--debug`:** in log từng vòng cuộn, lý do bỏ từng bài trong hàng đợi, và khi đọc nhóm lỗi thì lưu ảnh chụp + HTML trang Facebook vào `logs/`.
- **`--dry-run`:** mỗi bài in một dòng `[CẦN IN 3D] ...` hoặc `[bo qua: lý do] ...`, giúp chỉnh bộ lọc.
- **`Zalo ... loi 401`:** token sai/bị thu hồi, sửa `ZALO_BOT_TOKEN` trong `.env`.
- **`loi 403`/`404`:** bot bị xóa khỏi nhóm hoặc `ZALO_CHAT_ID` sai, chạy lại `--chat-id`.
- **`loi 429`:** hết quota gói Zalo Bot; tin được gửi ở lượt sau. Có thể tăng `interval_seconds`.
- **Không gửi link nào:** chạy `--dry-run --headed --debug` xem bot có đọc được bài và ngày đăng không.
- **Facebook bắt đăng nhập lại:** bot báo vào nhóm Zalo rồi thoát với mã 42 (service không tự khởi động lại). Chạy `--login` rồi chạy lại bot.

## Chạy 24/7 (Ubuntu)

Nên để code trong thư mục nhà, vì ổ gắn ngoài có thể chưa được gắn lúc khởi động:

```bash
mv "/run/media/bee/New Volume/zalo-bot" ~/zalo-bot && cd ~/zalo-bot
rm -rf .venv && python3 main.py --setup
python3 main.py --install-service
journalctl --user -u zalo-bot -f        # xem log
```

Sửa `config.json`/`.env` xong: `systemctl --user restart zalo-bot`. Không chạy `python3 main.py` cùng lúc với service (dùng chung `browser-profile`).

Tắt chế độ ngủ: `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`. Laptop muốn gập máy vẫn chạy: đặt `HandleLidSwitch=ignore` trong `/etc/systemd/logind.conf`.

## Cấu trúc

```
main.py              điểm chạy duy nhất (lệnh, cài đặt lần đầu)
config.json          nhóm Facebook và tham số quét
bot/settings.py      đường dẫn, đọc config/.env, logging
bot/install.py       .venv, token, ID nhóm, service systemd
bot/facebook.py      đọc bài Facebook (ngày đăng, link, cuộn trang)
bot/lead_filter.py   bộ lọc "khách cần in 3D"
bot/storage.py       SQLite: bài đã đọc, hàng đợi, link đã gửi
bot/runner.py        vòng quét và gửi Zalo
bot/zalo.py          Zalo Bot API
```

Dữ liệu (không chia sẻ): `browser-profile/` (phiên Facebook), `posts.sqlite3` (chống gửi trùng, giữ khi cập nhật code), `.env` (token), `logs/`.
