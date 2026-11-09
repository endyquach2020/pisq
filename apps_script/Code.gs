const DEFAULT_DRIVE_FOLDER_ID = '1n4KAU_hVz-0TrhFBY_1BHU7qrsQsJ701';

function doPost(event) {
  try {
    const request = JSON.parse(event.postData.contents || '{}');
    const properties = PropertiesService.getScriptProperties();
    const expectedToken = properties.getProperty('UPLOAD_TOKEN');

    if (!expectedToken || request.token !== expectedToken) {
      return jsonResponse({ status: 'error', message: 'Mã xác thực không hợp lệ.' });
    }

    if (typeof request.fileName !== 'string' || typeof request.fileData !== 'string') {
      return jsonResponse({ status: 'error', message: 'Thiếu tên file hoặc dữ liệu PDF.' });
    }

    const fileData = Utilities.base64Decode(request.fileData);
    const pdfHeader = String.fromCharCode.apply(null, fileData.slice(0, 5));
    if (pdfHeader !== '%PDF-') {
      return jsonResponse({ status: 'error', message: 'Dữ liệu gửi lên không phải file PDF.' });
    }

    const folderId = request.folderId ||
      properties.getProperty('DRIVE_FOLDER_ID') ||
      DEFAULT_DRIVE_FOLDER_ID;
    const folder = DriveApp.getFolderById(folderId);
    const safeFileName = request.fileName
      .replace(/[\\/:*?"<>|]/g, '_')
      .replace(/[\r\n]/g, '_');
    const blob = Utilities.newBlob(fileData, 'application/pdf', safeFileName);
    const file = folder.createFile(blob);

    return jsonResponse({
      status: 'success',
      file: {
        id: file.getId(),
        name: file.getName(),
        webViewLink: file.getUrl()
      }
    });
  } catch (error) {
    console.error(error);
    return jsonResponse({
      status: 'error',
      message: 'Không thể lưu PDF lên Google Drive. Kiểm tra quyền thư mục và cấu hình Apps Script.'
    });
  }
}

function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
