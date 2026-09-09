"""Simple localization: supports vi/en, with a callback mechanism when the language changes."""

TRANSLATIONS = {
    "vi": {
        # Common
        "app_title": "Comic Download Tool",
        "paste": "Dán",
        "folder": "Thư mục",
        "settings": "Cài đặt",
        "mode": "Mode:",
        "mode_manual": "Thủ công",
        "mode_auto": "Tự động",
        "add_queue": "Thêm vào danh sách",
        "start": "Bắt đầu",
        "pause": "Tạm dừng",
        "resume": "Tiếp tục",
        "clear_done": "Xóa truyện tải xong",
        "queue": "Danh sách",
        "auto_queue": "Tự động thêm vào danh sách",
        "shutdown_after_done": "Tắt máy khi xong trong",
        "language": "EN",
        "language_tooltip": "Chuyển sang tiếng Anh",
        "language_label": "Ngôn ngữ",
        "lang_vi": "Tiếng Việt",
        "lang_en": "English",
        # Notifications
        "no_chapters": "Không tìm thấy chapter nào cho truyện này.",
        "network_error": "Không thể tải trang, vui lòng kiểm tra mạng",
        "extractor_error": "Không hỗ trợ website này",
        "load_chapters_error": "Không thể tải danh sách chapter",
        "clipboard_invalid": "Clipboard không chứa link hợp lệ",
        "already_running": "Truyện đang được tải.",
        "already_queued": "Truyện đã có trong danh sách.",
        "delete_failed": "Không thể xóa truyện khỏi danh sách.",
        "queue_empty": "Danh sách trống! Hãy thêm truyện vào danh sách trước khi bắt đầu.",
        "notify": "Thông báo",
        "error": "Lỗi",
        "path_warning_title": "Cảnh báo đường dẫn",
        "path_empty": "Chưa nhập đường dẫn lưu trữ! Vui lòng chọn thư mục trước khi bắt đầu.",
        "path_invalid_title": "Đường dẫn không hợp lệ",
        "path_invalid": "Đường dẫn lưu trữ phải là thư mục tuyệt đối",
        "path_not_found_title": "Thư mục không tồn tại",
        "path_not_found": "Đường dẫn lưu trữ không tồn tại",
        "pick_folder_title": "Chọn thư mục",
        "url_placeholder": "Dán link truyện cần tải...",
        "path_placeholder": "Đường dẫn lưu...",
        "file_placeholder": "Chọn file chứa danh sách link...",
        "file_pick": "Thư mục",
        "file_pick_title": "Chọn file chứa danh sách link",
        "file_empty": "Chưa chọn file! Vui lòng chọn file trước.",
        "file_no_links": "File không chứa link hợp lệ nào.",
        "all_files": "Tất cả tệp",
        "import_error_title": "Lỗi nhập tệp",
        "import_error_media": "Tệp bạn chọn là tệp ảnh/âm thanh/video, không phải danh sách liên kết.",
        "import_error_not_text": "Không thể đọc tệp này dưới dạng văn bản.",
        "import_error_read": "Không thể mở tệp đã chọn.",
        "import_error_empty": "Tệp không chứa liên kết nào hợp lệ.",
        "import_error_invalid": "Một số dòng trong tệp không phải là liên kết http(s) hợp lệ:",
        "import_error_too_large": "Tệp quá lớn (giới hạn 5MB) để là danh sách liên kết.",
        "import_error_binary": "Tệp này là tệp nhị phân (chương trình/lưu trữ/media...), không phải danh sách liên kết dạng văn bản.",
        "adding_jobs_title": "Đang thêm job",
        "adding_jobs_text": "Đang thêm job... {current}/{total}",
        "adding_jobs_done": "Đã thêm {added} job vào danh sách.",
        "close_confirm_title": "Xác nhận thoát",
        "close_confirm_running": "Tiến trình tải đang chạy. Bạn có chắc chắn muốn thoát ứng dụng không?",
        "close_confirm_idle": "Bạn có chắc chắn muốn thoát ứng dụng không?",
        "yes": "Có",
        "no": "Không",
        # Auto shutdown
        "shutdown_confirm_title": "Xác nhận tắt máy",
        "shutdown_confirm_text": "Tất cả truyện trong hàng đợi đã tải xong.",
        "shutdown_countdown": "Máy sẽ tắt sau",
        "shutdown_now": "Tắt ngay",
        "shutdown_failed": "Không thể tắt máy tự động.",
        "shutdown_seconds": "giây",
        "shutdown_delay_hint": "Số giây đếm ngược trước khi máy tự tắt sau khi tải xong (từ khi hộp thoại xác nhận hiện ra).",
        # Settings dialog
        "settings_title": "Cài đặt",
        "settings_help_title": "Chi tiết tùy chọn",
        "save": "Lưu",
        "apply": "Áp dụng",
        "cancel": "Hủy",
        "ok": "OK",
        "save_thumb": "Lưu thumbnail khi tải",
        "thumb_yes": "Có",
        "thumb_no": "Không",
        "save_error": "Không thể ghi config.json. Kiểm tra quyền thư mục.",
        # Settings fields (label, key, desc)
        "field_max_workers": "Số truyện tải song song (worker)",
        "field_max_workers_desc": "Số truyện được xử lý cùng lúc.\n\nKhuyến nghị: 5-10. Đặt quá cao (10+) khiến máy lag, chiếm nhiều RAM/CPU và dễ bị website chặn.",
        "field_max_concurrent": "Tổng số ảnh tải đồng thời",
        "field_max_concurrent_desc": "Số request tải ảnh tối đa cùng lúc trên toàn app (chia sẻ giữa mọi truyện đang tải).\n\nKhuyến nghị: 5-10. Quá cao làm nghẽn băng thông, ảnh lỗi nhiều và có thể bị chặn IP.",
        "field_download_retry": "Số lần thử lại khi tải ảnh lỗi",
        "field_download_retry_desc": "Khi tải 1 ảnh thất bại, tự động thử lại bao nhiêu lần.\n\nKhuyến nghị: 2-3. Quá cao làm chậm cả queue khi ảnh thực sự hỏng (thử lại vô ích).",
        "field_chapter_retry": "Số lần thử lại khi lấy danh sách chapter lỗi",
        "field_chapter_retry_desc": "Khi không tải được danh sách chapter (mạng chập chờn), thử lại bao nhiêu lần.\n\nKhuyến nghị: 2. Quá cao khiến chờ lâu trước khi báo lỗi.",
        "field_timeout": "Thời gian chờ tải trang (giây)",
        "field_timeout_desc": "Thời gian tối đa chờ trang web phản hồi trước khi báo lỗi.\n\nKhuyến nghị: 30. Quá thấp dễ báo lỗi khi mạng chậm, quá cao làm treo lâu khi trang không vào được.",
        "thumb_help_title": "Lưu thumbnail khi tải",
        "thumb_help_desc": "Có: lưu ảnh bìa (thumb.jpg) vào thư mục mỗi truyện khi tải.\n\nKhông: bỏ qua ảnh bìa, chỉ tải các chapter — tiết kiệm băng thông và 1 request ảnh mỗi truyện.\n\nKhuyến nghị: Có.",
        # Queue status
        "status_waiting": "Waiting",
        "status_paused": "Paused",
        "status_resume": "Resume",
        "status_done": "Done",
        "status_failed": "Failed",
        "status_done_with_missing": "Done with missing",
        # Auth / login
        "auth_missing_login_url": "thiếu login_url",
        "auth_login_failed": "Đăng nhập '{}' thất bại",
        "auth_login_failed_user": "Đăng nhập '{}' thất bại cho user '{}'",
        "auth_login_failed_status": "Đăng nhập '{}' thất bại (HTTP {})",
        "auth_login_no_token": "Đăng nhập '{}' thất bại: không nhận được token",
        "auth_config_error": "[auth] Lỗi cấu hình site '{}': {}",
        "login_title": "Đăng nhập",
        "login_site": "Trang:",
        "login_username": "Tài khoản:",
        "login_password": "Mật khẩu:",
        "login_required_fields": "Vui lòng nhập đầy đủ tài khoản và mật khẩu.",
        "login_failed_title": "Đăng nhập thất bại",
        "login_required_message": "cần đăng nhập vào {} để tiếp tục",
        "login_need_auth": "Cần đăng nhập",
    },
    "en": {
        # Common
        "app_title": "Comic Download Tool",
        "paste": "Paste",
        "folder": "Folder",
        "settings": "Settings",
        "mode": "Mode:",
        "mode_manual": "Manual",
        "mode_auto": "Auto",
        "add_queue": "Add Queue",
        "start": "Start",
        "pause": "Pause",
        "resume": "Resume",
        "clear_done": "Clear Done",
        "queue": "Queue",
        "auto_queue": "Automatically add to queue",
        "shutdown_after_done": "Shutdown when done in",
        "language": "VI",
        "language_tooltip": "Switch to Vietnamese",
        "language_label": "Language",
        "lang_vi": "Tiếng Việt",
        "lang_en": "English",
        # Notifications
        "no_chapters": "No chapters found for this comic.",
        "network_error": "Failed to load page, please check your network",
        "extractor_error": "This website is not supported",
        "load_chapters_error": "Failed to load chapter list",
        "clipboard_invalid": "Clipboard does not contain a valid URL",
        "already_running": "This comic is already downloading.",
        "already_queued": "This comic is already in the queue.",
        "delete_failed": "Failed to remove comic from the queue.",
        "queue_empty": "Queue is empty! Add a comic to the queue before starting.",
        "notify": "Notification",
        "error": "Error",
        "path_warning_title": "Save path warning",
        "path_empty": "No save path entered! Please choose a folder before starting.",
        "path_invalid_title": "Invalid path",
        "path_invalid": "Save path must be an absolute directory",
        "path_not_found_title": "Directory does not exist",
        "path_not_found": "Save path does not exist",
        "pick_folder_title": "Choose folder",
        "url_placeholder": "Paste comic link...",
        "path_placeholder": "Save path...",
        "file_placeholder": "Choose a file containing a list of links...",
        "file_pick": "Folder",
        "file_pick_title": "Choose a file containing a list of links",
        "file_empty": "No file selected! Please choose a file first.",
        "file_no_links": "The file does not contain any valid links.",
        "all_files": "All files",
        "import_error_title": "Import error",
        "import_error_media": "The selected file is an image/audio/video file, not a link list.",
        "import_error_not_text": "This file could not be read as text.",
        "import_error_read": "Could not open the selected file.",
        "import_error_empty": "The file does not contain any valid links.",
        "import_error_invalid": "Some lines in the file are not valid http(s) links:",
        "import_error_too_large": "The file is too large (5MB limit) to be a link list.",
        "import_error_binary": "This is a binary file (program/archive/media/...), not a plain-text link list.",
        "adding_jobs_title": "Adding jobs",
        "adding_jobs_text": "Adding jobs... {current}/{total}",
        "adding_jobs_done": "Added {added} job(s) to the queue.",
        "close_confirm_title": "Confirm exit",
        "close_confirm_running": "Download is in progress. Are you sure you want to exit?",
        "close_confirm_idle": "Are you sure you want to exit?",
        "yes": "Yes",
        "no": "No",
        # Auto shutdown
        "shutdown_confirm_title": "Confirm shutdown",
        "shutdown_confirm_text": "All queued downloads finished.",
        "shutdown_countdown": "Shutting down in",
        "shutdown_now": "Shut down now",
        "shutdown_failed": "Auto shutdown failed.",
        "shutdown_seconds": "sec",
        "shutdown_delay_hint": "Countdown in seconds before the machine shuts down after downloads finish (from when the confirmation dialog appears).",
        # Settings dialog
        "settings_title": "Settings",
        "settings_help_title": "Option details",
        "save": "Save",
        "apply": "Apply",
        "cancel": "Cancel",
        "ok": "OK",
        "save_thumb": "Download thumbnail",
        "thumb_yes": "Yes",
        "thumb_no": "No",
        "save_error": "Failed to write config.json. Check folder permissions.",
        # Settings fields
        "field_max_workers": "Parallel comics (workers)",
        "field_max_workers_desc": "How many comics are processed at the same time.\n\nRecommended: 5-10. Setting too high (10+) slows down the machine, uses more RAM/CPU and may get blocked by websites.",
        "field_max_concurrent": "Total concurrent image downloads",
        "field_max_concurrent_desc": "Maximum number of image requests at once across the whole app (shared between all downloading comics).\n\nRecommended: 5-10. Too high saturates bandwidth, causes more failed images and may get your IP blocked.",
        "field_download_retry": "Image download retries",
        "field_download_retry_desc": "How many times to retry when an image download fails.\n\nRecommended: 2-3. Too high slows the whole queue when an image is really broken (useless retries).",
        "field_chapter_retry": "Chapter list retries",
        "field_chapter_retry_desc": "How many times to retry when the chapter list cannot be loaded (flaky network).\n\nRecommended: 2. Too high means waiting long before showing an error.",
        "field_timeout": "Page load timeout (seconds)",
        "field_timeout_desc": "Maximum time to wait for a website response before showing an error.\n\nRecommended: 30. Too low errors out on slow networks, too high hangs for long when a page is unreachable.",
        "thumb_help_title": "Download thumbnail",
        "thumb_help_desc": "Yes: save the cover image (thumb.jpg) into each comic folder when downloading.\n\nNo: skip the cover, only download the chapters — saves bandwidth and one image request per comic.\n\nRecommended: Yes.",
        # Queue status
        "status_waiting": "Waiting",
        "status_paused": "Paused",
        "status_resume": "Resume",
        "status_done": "Done",
        "status_failed": "Failed",
        "status_done_with_missing": "Done with missing",
        # Auth / login
        "auth_missing_login_url": "missing login_url",
        "auth_login_failed": "Login '{}' failed",
        "auth_login_failed_user": "Login '{}' failed for user '{}'",
        "auth_login_failed_status": "Login '{}' failed (HTTP {})",
        "auth_login_no_token": "Login '{}' failed: no token received",
        "auth_config_error": "[auth] Config error for site '{}': {}",
        "login_title": "Login",
        "login_site": "Site:",
        "login_username": "Username:",
        "login_password": "Password:",
        "login_required_fields": "Please enter both username and password.",
        "login_failed_title": "Login failed",
        "login_required_message": "needs login to {} to continue",
        "login_need_auth": "Login required",
    },
}

# Current language
_lang = "vi"

# Listeners called when the language changes (so the UI can update itself)
_listeners = []


def tr(key: str) -> str:
    """Get the translated string for the current language."""
    return TRANSLATIONS.get(_lang, {}).get(key, key)


def get_lang() -> str:
    return _lang


def set_lang(lang: str):
    global _lang
    if lang not in TRANSLATIONS:
        lang = "vi"
    if lang == _lang:
        return
    _lang = lang
    for cb in list(_listeners):
        cb()


def add_listener(cb):
    _listeners.append(cb)


def remove_listener(cb):
    if cb in _listeners:
        _listeners.remove(cb)
