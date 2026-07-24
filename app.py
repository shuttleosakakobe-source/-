function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    
    let reportDate = data.report_date || "";
    let customerName = data.customer_name || "";
    let branchName = data.branch_name || "";
    let amount = data.amount || "";
    let phone = data.phone || "";
    let address = data.address || "";
    let content = data.content || "";
    
    // 画像が送信されてきた場合はGoogle Drive標準OCRを実行
    if (data.image_base64) {
      const bytes = Utilities.base64Decode(data.image_base64);
      const mimeType = data.mime_type || "image/jpeg";
      const blob = Utilities.newBlob(bytes, mimeType, "ocr_temp_image");
      
      // Google Driveで画像から文字を読み取り（OCR）
      const ocrText = runGoogleDriveOcr(blob, mimeType);
      
      // 読み取った文字から詳細にセット
      if (!content) {
        content = ocrText;
      }
      
      // テキストから金額を自動抽出（数字+円のパターンなど）
      if (!amount) {
        const amountMatch = ocrText.match(/[¥￥\s]([0-9,]{3,})/);
        if (amountMatch) {
          amount = amountMatch[1].replace(/,/g, "");
        }
      }
    }
    
    // スプレッドシートに追記
    sheet.appendRow([
      new Date(),       // タイムスタンプ
      reportDate,       // 日付
      customerName,     // お客様名
      branchName,       // 店舗名
      amount,           // 金額
      phone,            // 電話番号
      address,          // 住所
      content           // 詳細内容（OCR抽出テキスト含む）
    ]);
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      message: "保存完了しました",
      extracted_text: content
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: error.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

// Google Driveの標準機能を使った無料OCR関数（エラー修正版）
function runGoogleDriveOcr(blob, mimeType) {
  // Drive API を使って画像からテキスト作成
  const file = DriveApp.createFile(blob);
  
  // OCR処理用にコピーしてテキスト抽出
  const docFile = Drive.Files.insert(
    { title: "OCR_Result", mimeType: "application/vnd.google-apps.document" },
    file,
    { ocr: true, ocrLanguage: "ja" }
  );
  
  const doc = DocumentApp.openById(docFile.id);
  const text = doc.getBody().getText();
  
  // 一時ファイルの削除
  file.setTrashed(true);
  DriveApp.getFileById(docFile.id).setTrashed(true);
  
  return text;
}
