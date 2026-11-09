import base64
import json
import os
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


DEFAULT_DRIVE_FOLDER_ID = "1n4KAU_hVz-0TrhFBY_1BHU7qrsQsJ701"


class DriveConfigurationError(Exception):
    pass


class DriveUploadError(Exception):
    pass


def upload_pdf_to_drive(pdf_bytes: bytes, file_name: str) -> Dict[str, Any]:
    script_url = os.getenv("GOOGLE_APPS_SCRIPT_URL", "").strip()
    upload_token = os.getenv("GOOGLE_APPS_SCRIPT_TOKEN", "").strip()
    if not script_url:
        raise DriveConfigurationError(
            "Chưa cấu hình GOOGLE_APPS_SCRIPT_URL là URL Web App của Google Apps Script."
        )
    if not upload_token:
        raise DriveConfigurationError(
            "Chưa cấu hình GOOGLE_APPS_SCRIPT_TOKEN để xác thực với Google Apps Script."
        )
    parsed_url = urlsplit(script_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "script.google.com"
        or not parsed_url.path.startswith("/macros/s/")
        or not parsed_url.path.endswith("/exec")
    ):
        raise DriveConfigurationError(
            "GOOGLE_APPS_SCRIPT_URL phải là URL Web App HTTPS kết thúc bằng /exec."
        )

    payload = json.dumps({
        "token": upload_token,
        "fileName": file_name,
        "fileData": base64.b64encode(pdf_bytes).decode("ascii"),
        "folderId": os.getenv("GOOGLE_DRIVE_FOLDER_ID", DEFAULT_DRIVE_FOLDER_ID),
    }).encode("utf-8")
    request = Request(
        script_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            response_body = response.read()
    except HTTPError as exc:
        raise DriveUploadError(
            f"Google Apps Script từ chối yêu cầu (HTTP {exc.code}). "
            "Kiểm tra quyền truy cập của Web App."
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DriveUploadError(
            "Không thể kết nối tới Google Apps Script. Kiểm tra Internet và URL Web App."
        ) from exc

    try:
        result = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DriveUploadError(
            "Google Apps Script trả về phản hồi không hợp lệ. Kiểm tra URL triển khai Web App."
        ) from exc

    if not isinstance(result, dict):
        raise DriveUploadError("Google Apps Script trả về phản hồi không hợp lệ.")

    if result.get("status") != "success":
        detail = result.get("message")
        if not isinstance(detail, str) or not detail:
            detail = "Google Apps Script không lưu được file PDF."
        raise DriveUploadError(detail)

    uploaded_file = result.get("file")
    if (
        not isinstance(uploaded_file, dict)
        or not isinstance(uploaded_file.get("id"), str)
        or not uploaded_file["id"]
    ):
        raise DriveUploadError("Google Apps Script không trả về thông tin file đã lưu.")

    file_id = uploaded_file["id"]
    return {
        "id": file_id,
        "name": uploaded_file.get("name", file_name),
        "web_view_link": uploaded_file.get(
            "webViewLink",
            f"https://drive.google.com/file/d/{file_id}/view",
        ),
    }
