# Bot tìm khách cần in 3D trên Facebook → Zalo + bình luận AI local

Bot đọc bài trong các nhóm Facebook mà tài khoản của bạn đã tham gia:

1. **Lọc bài bằng từ khóa**: chỉ giữ bài người đăng cần thuê/nhờ in 3D. Bỏ quảng cáo, mua bán máy, tuyển dụng và các bài có từ khóa loại trừ (`HN`, `Hà Nội`, `in resin`, `pass máy in`...).
2. **Gửi link vào nhóm Zalo**: mỗi bài một tin, kèm trích đoạn, giờ đăng và link.
3. **AI bình luận chào khách**: model **Gemma 4 (`gemma4:e2b`) chạy local bằng Ollama**, không cần API key, không mất phí. AI đóng vai sales: trả lời đúng thứ khách cần, nói bên mình nhận làm, rồi mời vào **infinitemakerspace.com**. Mỗi bình luận 1-2 câu, dưới 180 ký tự.

Chạy `python3 main.py` thì bot chạy liên tục: **cứ 2 giờ quét bài trong 24 giờ qua**. Mỗi link chỉ gửi và bình luận một lần, kể cả khi cùng nội dung được đăng ở nhiều nhóm. Nhắn **`scan`** trong nhóm Zalo để quét ngay.

## Cài đặt

```bash
python3 main.py --setup        # thư viện, Chromium, Ollama + model gemma4:e2b (~4.6GB), token Zalo
python3 main.py --chat-id      # lấy ID nhóm Zalo (gửi "@TênBot hello" vào nhóm trong 2 phút)
python3 main.py --login        # đăng nhập Facebook, chọn "Bài viết mới" cho từng nhóm
python3 main.py --send-test    # gửi tin thử vào Zalo
python3 main.py                # chạy bot
```

Đã cài Ollama bằng `curl -fsSL https://ollama.com/install.sh | sh` (service hệ thống) thì `--setup` dùng luôn bản đó. Chưa có thì `--setup` cài vào `~/.local/ollama` (không cần sudo). Chỉ giữ **một** bản Ollama, hai bản sẽ tranh cổng 11434 và RAM. Máy chỉ có CPU vẫn chạy được: lần đầu nạp model mất khoảng 40 giây, sau đó mỗi bài mất khoảng 5-10 giây.

## Thử trước khi chạy thật

```bash
python3 main.py --dry-run                                   # xem bài nào được giữ/bỏ và lý do, không gửi
python3 main.py --ai-test --text "Cần in 20 móc khóa logo"  # thử AI với một nội dung, không mở Facebook
python3 main.py --ai-test --group "Nghiện In 3D" --hours 12 # quét thật, CHỈ IN bình luận ra màn hình
python3 main.py --comment-test --headed                     # gặp ĐÚNG 1 bài cần in là bình luận thật, gửi link vào Zalo
```

## Các lệnh

| Lệnh | Tác dụng |
|---|---|
| `python3 main.py` | Chạy liên tục: gửi link Zalo và bình luận thật |
| `--once` | Quét và gửi một lượt rồi thoát |
| `--dry-run` | Quét một lượt, in kết quả lọc, không gửi |
| `--ai-test` | Quét một lượt, in bình luận AI sẽ viết, không đăng (`--text "..."` / `--text -` để thử nội dung tự nhập) |
| `--comment-test` | Quét tới khi gặp **đúng 1** bài cần in mà AI chịu trả lời thì dừng cuộn, bình luận **thật** ngay, in link tới bình luận ra terminal và gửi vào nhóm Zalo, rồi thoát. Bỏ qua giờ/giãn cách/bài quá mới. Thêm `--headed` để xem trình duyệt gõ |
| `--bootstrap` | Đánh dấu bài hiện có là đã xem (chỉ dùng khi cài mới) |
| `--setup` / `--chat-id` / `--send-test` / `--login` / `--inspect` | Cài đặt và kiểm tra |
| `--install-service` / `--remove-service` | Cài/gỡ service chạy 24/7 |

Tùy chọn: `--group "Tên"`, `--hours N`, `--headed` (hiện trình duyệt), `--debug`.

## Cấu hình (`config.json`)

- `groups`: danh sách nhóm. `group_keys` là phần sau `/groups/` trong link (thêm cả tên và ID số nếu nhóm dùng cả hai). Nhóm không chuyên in 3D thì thêm `"is_3d_group": false`; nhóm cấm quảng cáo thì thêm `"ai_comment": false`.
- `exclude_keywords`: **bài chứa một trong các từ này thì bỏ hẳn** (không gửi Zalo, không bình luận). Không phân biệt hoa thường hay có dấu: `"Hà Nội"` khớp cả `ha noi`. Khớp nguyên từ, nên `"HN"` không khớp `JOHN`. Muốn chặn thêm thì thêm từ vào danh sách.
- `interval_seconds` (7200 = 2 giờ), `lookback_days` (1 = 24 giờ), `max_posts_per_group`, `max_scroll_rounds`.
- `ai`:

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `enabled` | `true` | `false` = chỉ gửi link Zalo, không bình luận |
| `model` | `gemma4:e2b` | Model Ollama. Máy mạnh hơn có thể dùng `gemma4:e4b` (chạy `ollama pull gemma4:e4b` trước) |
| `website` | `infinitemakerspace.com` | Luôn gắn cuối bình luận |
| `facebook_page` | `facebook.com/infinitestudiomakerspace` | Fanpage, gắn cuối bình luận trước website (`""` = không gắn) |
| `facebook_page_name` | `Infinite Makerspace` | Tên Trang trong gợi ý @ của Facebook. Bot gõ `@infinitestudiomakerspace` rồi chọn gợi ý này để tag thật; không thấy gợi ý thì dùng link fanpage. `""` = chỉ gắn link |
| `temperature` | `0.8` | Cao hơn thì bình luận sáng tạo, đa dạng hơn; thấp hơn thì đều và an toàn hơn |
| `business_file` | `makerspace.md` | Thông tin dịch vụ cho AI. AI chỉ được nói điều có trong file này |
| `max_comment_chars` | `220` | Độ dài tối đa phần AI viết (chưa tính link ở cuối) |
| `max_posts_per_run` | `20` | Số bài AI đọc mỗi lượt |
| `max_comments_per_run` / `_per_day` / `_per_group_per_day` | `3` / `8` / `3` | Giới hạn bình luận. Tuần đầu nên để `_per_day` ở 2-3 |
| `comment_gap_seconds` | `[480, 1200]` | Nghỉ 8-20 phút giữa hai bình luận |
| `active_hours` | `[8, 22]` | Chỉ bình luận từ 8:00 đến trước 22:00 |
| `min_post_age_minutes` | `10` | Không trả lời bài vừa đăng |
| `blocked_cooldown_hours` | `72` | Facebook báo giới hạn thì ngừng bình luận |
| `notify_zalo` | `true` | Báo vào Zalo mỗi bình luận đã đăng, kèm link để kiểm tra |

Muốn đổi giọng văn hoặc cách chốt khách thì sửa `PROMPT` trong `bot/commenter.py`. Mỗi bài, bot chọn ngẫu nhiên cách kết `CTA_ON` (rủ ib/ghé trang) hoặc `CTA_OFF` (kết bằng mẹo/câu hỏi lại), tỉ lệ `CTA_CHANCE`, và đưa 5 bình luận gần nhất cho AI để tránh lặp. AI trả về `quang_cao` (bên bán tự chào hàng: không bình luận, không gửi Zalo) và `reply` (có bình luận không). Vì vậy khi bình luận AI đang bật, link khách được gửi vào Zalo sau khi AI đọc xong bài. Bình luận xong, bot gửi vào Zalo nội dung bài, câu AI đã bình luận, link bài và link bình luận.

Trước khi đăng, bình luận được kiểm tra: có `@`, số điện thoại hoặc link lạ thì bỏ; quá dài thì cắt theo câu; link fanpage và website do code tự gắn ở cuối. Bình luận giống một bình luận gần đây cũng bị bỏ để tránh bị coi là spam.

`.env`: `ZALO_BOT_TOKEN`, `ZALO_CHAT_ID`, và tùy chọn `OLLAMA_HOST`.

## Lưu ý

- Tự động bình luận vi phạm điều khoản Facebook; tài khoản có thể bị giới hạn. Bot đã giới hạn số bình luận, giãn cách, và tự dừng 72 giờ khi Facebook cảnh báo.
- Facebook đổi giao diện thường xuyên: dùng `--inspect` và `--dry-run --headed --debug` để kiểm tra.
- Bot không tự đăng nhập Facebook và không vượt CAPTCHA. Khi Facebook bắt đăng nhập lại, bot báo vào Zalo rồi thoát với mã 42. Chạy `--login` rồi chạy lại bot.

## Gỡ lỗi

- Log chỉ in ra màn hình (không lưu file): mức INFO, thêm `--debug` để xem chi tiết kèm traceback. Chạy service thì xem bằng `journalctl --user -u zalo-bot -f`.
- **`Khong ket noi duoc Ollama`**: `sudo systemctl start ollama` (bản cài bằng sudo) hoặc `systemctl --user start ollama` (bản trong `~/.local`); xem lỗi bằng `journalctl -u ollama -n 50` (thêm `--user` với bản `~/.local`).
- **Ollama bị kill / `RemoteDisconnected`**: hết RAM (`journalctl -k | grep -i oom`). Đóng bớt ứng dụng hoặc dùng model nhỏ hơn.
- **`Chua tai model`**: `python3 main.py --setup` (hoặc `ollama pull gemma4:e2b`).
- **Zalo `401`**: token sai. **`403`/`404`**: bot bị xóa khỏi nhóm, chạy lại `--chat-id`. **`429`**: hết quota, tin được gửi ở lượt sau.

## Chạy 24/7 (Ubuntu)

```bash
mv "/run/media/bee/New Volume/zalo-bot" ~/zalo-bot && cd ~/zalo-bot   # ổ ngoài có thể chưa gắn lúc khởi động
rm -rf .venv && python3 main.py --setup
python3 main.py --install-service
journalctl --user -u zalo-bot -f
```

Sửa `config.json` hoặc `.env` xong thì chạy `systemctl --user restart zalo-bot`.

## Cấu trúc

```
main.py              điểm chạy duy nhất
config.json          nhóm Facebook, từ khóa loại trừ, cấu hình AI
makerspace.md        thông tin dịch vụ cho AI
bot/lead_filter.py   bộ lọc từ khóa "khách cần in 3D"
bot/facebook.py      đọc bài Facebook, đăng bình luận
bot/ollama.py        gọi AI local (Ollama REST, thư viện chuẩn)
bot/commenter.py     prompt sales + viết/kiểm tra/đăng bình luận
bot/runner.py        vòng quét, gửi Zalo
bot/zalo.py          Zalo Bot API
bot/storage.py       SQLite chống gửi trùng/bình luận trùng
bot/install.py       .venv, Ollama, token, service systemd
bot/settings.py      đường dẫn, config, .env, logging
```
