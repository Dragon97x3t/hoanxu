# Hoàn Xu — Lõi ứng dụng (MVP)

Đây là phần "lõi" của website hoàn tiền: tài khoản người dùng thật, ví tiền hoàn thật (lưu
trong cơ sở dữ liệu), link giới thiệu, và trang quản trị để cộng tiền hoàn dựa trên báo cáo
hoa hồng bạn xuất từ Shopee Affiliate Center. Giao diện hiện đang rất đơn giản — phần đẹp sẽ
làm sau khi bạn xác nhận lõi chạy đúng ý.

## 1. Nó hoạt động ra sao

1. Người dùng đăng ký → được cấp một **mã giới thiệu** riêng (ví dụ `8XQHDHJ`) và một ví 0đ.
2. Người dùng dán link sản phẩm Shopee vào trang "Ví của tôi" → hệ thống tạo ra một **link chia sẻ**
   dạng `.../go/8XQHDHJ?url=<link-shopee>`. Người dùng gửi link này cho bạn bè/khách.
3. Khi có người bấm vào, hệ thống ghi log rồi chuyển hướng sang Shopee theo một **mẫu link** mà
   *bạn* cấu hình trong phần Cài đặt (xem mục 4 — đây là phần cần bạn cung cấp thêm).
4. Định kỳ, bạn vào Shopee Affiliate Center, xuất báo cáo đơn hàng/hoa hồng, lưu thành CSV theo
   đúng cột hệ thống yêu cầu, rồi tải lên trang **Quản trị → Nhập báo cáo hoa hồng**. Hệ thống tự
   khớp theo mã giới thiệu và cộng tiền vào đúng ví từng người dùng (theo % bạn cấu hình).
5. Khi ví có số dư khả dụng, người dùng bấm **Rút tiền**; bạn (admin) vào trang Quản trị để đánh
   dấu "Đã trả" sau khi chuyển khoản thủ công.

## 2. Chạy thử ngay trên máy (không cần hiểu code)

Cần có Python 3 đã cài sẵn trên máy (Mac/Windows đều có thể cài từ python.org nếu chưa có).

```
pip install -r requirements.txt
python3 app.py
```

Sau đó mở trình duyệt vào `http://localhost:5000`.

Tài khoản quản trị mặc định được tạo tự động lần chạy đầu tiên:
- Email: `admin@hoanxu.local`
- Mật khẩu: `admin123`

**Hãy đăng nhập bằng tài khoản này và tự tạo một tài khoản người dùng thường khác để test** (vì
hiện chưa có trang đổi mật khẩu — nếu cần mình sẽ bổ sung).

## 3. Đưa lên một đường link online để dùng thử (không cần cài gì trên máy)

Cách dễ nhất cho người không rành kỹ thuật là dùng dịch vụ **Render.com** (có gói miễn phí):

1. Bạn cần một tài khoản GitHub (miễn phí) để chứa code, và một tài khoản Render.com (đăng ký
   bằng GitHub luôn cho nhanh).
2. Trong ứng dụng Claude, bạn có thể vào phần **kết nối (connectors)** và bật kết nối tới
   **Render** (hoặc Netlify/Vercel) — sau khi bạn bật, hãy báo mình, mình sẽ dùng kết nối đó để
   tự động triển khai (deploy) code này lên và gửi lại link cho bạn.
3. Nếu bạn muốn tự làm: tạo repo GitHub mới, đẩy toàn bộ thư mục này lên, vào Render → New →
   Web Service → chọn repo đó. Render sẽ tự nhận `requirements.txt` và `Procfile` để chạy.
   Nhớ vào mục "Environment" của Render, thêm biến `SECRET_KEY` với một chuỗi ký tự ngẫu nhiên
   dài (bảo mật phiên đăng nhập).

## 4. Việc bạn cần cung cấp thêm để phần "hoàn tiền thật" hoạt động

**a) Mẫu link Shopee Affiliate có gắn mã giới thiệu (sub_id).**
Shopee không có API công khai để tạo link kèm sub_id tự động bằng code — bạn cần tạo link qua
ứng dụng/portal Affiliate của Shopee (mục thường gọi là "Sub ID" khi tạo link, cho phép gắn tối
đa vài mã theo dõi). Sau khi có định dạng link thật, vào **Quản trị → Cài đặt** và điền vào ô
"Mẫu link chuyển hướng sang Shopee", dùng `{sub_id}` và `{target_url}` làm chỗ trống.

**b) Định dạng file báo cáo hoa hồng thật từ Shopee.**
Mình chưa có mẫu file thật Shopee xuất ra, nên trang Nhập báo cáo hiện yêu cầu đúng 6 cột:
`sub_id, shopee_order_id, product_name, order_amount, commission_amount, status` (xem file
`sample_report.csv` đính kèm làm ví dụ). Nếu file thật của Shopee có tên cột hoặc giá trị trạng
thái khác, bạn có thể tự đổi tên cột trong Excel trước khi tải lên, hoặc gửi cho mình một file
mẫu (đã ẩn thông tin nhạy cảm) để mình chỉnh code khớp tự động, đỡ phải sửa tay mỗi lần.

## 5. Vì sao chưa làm "tự động đồng bộ bằng cookie" như bạn đề xuất

Bạn có đề cập muốn nhập cookie phiên đăng nhập + ID Shopee để hệ thống tự lấy đơn hàng/hoa hồng
mà không cần xuất CSV thủ công. Mình chưa làm theo hướng đó ở bản lõi này vì hai lý do:

- **Bảo mật:** cookie phiên đăng nhập gần như tương đương mật khẩu tài khoản Shopee của bạn. Nếu
  lưu trong một web app rồi đưa lên một đường link công khai, một khi có sự cố bảo mật (dù nhỏ),
  người khác có thể chiếm được quyền truy cập tài khoản Shopee thật của bạn.
- **Điều khoản dịch vụ:** Shopee không cung cấp API affiliate công khai; việc dùng cookie để tự
  động truy cập trang nội bộ (Affiliate Center) giống hành vi tự động hoá/scraping mà điều khoản
  của nhiều sàn thương mại điện tử (bao gồm khả năng cao là Shopee) không cho phép, kể cả khi đó
  là tài khoản của chính bạn — có rủi ro tài khoản affiliate bị khoá.

Cách nhập CSV thủ công (định kỳ vài ngày/lần) an toàn hơn nhiều và vẫn dùng thử được ngay. Nếu
sau này bạn vẫn muốn thử hướng tự động, mình có thể cùng bạn xem xét kỹ hơn (ví dụ dùng trình
duyệt Claude in Chrome để thao tác trực tiếp trong phiên đăng nhập của bạn thay vì lưu cookie
trong hệ thống) — nhưng nên cân nhắc kỹ rủi ro trước.

## 6. Việc tiếp theo có thể làm

- Trang đổi mật khẩu, quên mật khẩu.
- Làm đẹp giao diện theo đúng phong cách bạn muốn (bạn nói giao diện bản demo trước chưa thuận
  mắt — mình sẽ làm lại sau khi lõi này ổn).
- Xác thực email khi đăng ký.
- Giới hạn/khoá tài khoản nghi ngờ gian lận (tự bấm vào link của chính mình).
