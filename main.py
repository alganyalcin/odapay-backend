"""
OdaPay API - Fiş işleme ve harcama bölüştürme servisi

Uçlar:
  POST /receipts/process   -> fiş fotoğrafını OCR'dan geçirir, kalemleri döndürür
  POST /expenses/split     -> işlenmiş fişi ev arkadaşları arasında bölüştürür

Çalıştırma:
  uvicorn main:app --reload
"""
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from models import ReceiptItem, ReceiptProcessResult, SplitRequest, SplitResult
from ai_extractor import extract_items_from_image
from splitter import split_equal, split_by_item

app = FastAPI(title="OdaPay API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def health_check():
    """Render'ın sunucunun ayakta olduğunu anlaması için basit kontrol noktası."""
    return {"status": "ok", "service": "OdaPay API"}


@app.get("/confirmed", response_class=HTMLResponse)
async def confirmed_page():
    """
    E-posta onayı / şifre sıfırlama sonrası kullanıcıya gösterilen sayfa.
    Onay işleminin kendisi bu sayfaya gelmeden ÖNCE Supabase tarafında zaten
    tamamlanmış olur - bu sadece kullanıcıya "başarılı" demek için var.
    """
    return """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>OdaPay</title>
      <style>
        body {
          font-family: -apple-system, Segoe UI, Roboto, sans-serif;
          background: linear-gradient(135deg, #8FE3C0, #3FB8A6, #6C8EF5);
          height: 100vh; margin: 0;
          display: flex; align-items: center; justify-content: center;
          color: white; text-align: center;
        }
        .card { padding: 40px; }
        h1 { font-size: 28px; margin-bottom: 8px; }
        p { opacity: 0.9; }
      </style>
    </head>
    <body>
      <div class="card">
        <h1>✓ Onaylandı</h1>
        <p>Artık OdaPay uygulamasına dönüp giriş yapabilirsin.</p>
      </div>
    </body>
    </html>
    """

# NOT: Demo amaçlı bellek-içi depolama. Gerçek ortamda schema.sql'deki
# receipts / receipt_items tablolarına yazılmalı (asyncpg ile).
_processed_receipts: dict[str, ReceiptProcessResult] = {}


@app.post("/receipts/process", response_model=ReceiptProcessResult)
async def process_receipt(file: UploadFile = File(...)):
    """Market fişi fotoğrafını alır, OCR uygular ve kalemlere ayırır."""
    # Android/iOS kameraları content_type'ı bazen boş veya farklı formatta gönderebiliyor,
    # bu yüzden sadece açıkça 'image/' ile başlamayan durumları reddediyoruz
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(400, "Sadece resim dosyaları kabul edilir")

    image_bytes = await file.read()

    try:
        raw_items = extract_items_from_image(image_bytes)
    except Exception as e:
        raise HTTPException(502, f"Yapay zeka servisi başarısız oldu: {e}")

    items = [
        ReceiptItem(
            item_name=str(entry.get("item_name", "")).strip(),
            total_price=float(entry.get("total_price", 0) or 0),
        )
        for entry in raw_items
        if str(entry.get("item_name", "")).strip()
    ]
    total = round(sum(item.total_price for item in items), 2)

    result = ReceiptProcessResult(
        receipt_id=str(uuid.uuid4()),
        raw_text="",  # artık kullanılmıyor, yapay zeka doğrudan yapılandırılmış veri döndürüyor
        items=items,
        total_amount=total,
        status="processed" if items else "needs_review",
    )

    _processed_receipts[result.receipt_id] = result
    return result


@app.post("/expenses/split", response_model=SplitResult)
async def split_expense(request: SplitRequest):
    """İşlenmiş bir fişi ev arkadaşları arasında bölüştürüp harcama kaydı oluşturur."""
    receipt = _processed_receipts.get(request.receipt_id)
    if not receipt:
        raise HTTPException(404, "Fiş bulunamadı, önce /receipts/process çağırın")

    if request.split_mode == "by_item":
        shares = split_by_item(receipt.items, request.member_user_ids)
    else:
        shares = split_equal(receipt.total_amount, request.member_user_ids)

    # Gerçek ortamda burada expenses + expense_shares tablolarına INSERT yapılır
    expense_id = str(uuid.uuid4())

    return SplitResult(
        expense_id=expense_id,
        total_amount=receipt.total_amount,
        shares=shares,
    )
