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

from models import ReceiptProcessResult, SplitRequest, SplitResult
from ocr import extract_text_from_image
from parser import parse_receipt_text, calculate_total
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

# NOT: Demo amaçlı bellek-içi depolama. Gerçek ortamda schema.sql'deki
# receipts / receipt_items tablolarına yazılmalı (asyncpg ile).
_processed_receipts: dict[str, ReceiptProcessResult] = {}


@app.post("/receipts/process", response_model=ReceiptProcessResult)
async def process_receipt(file: UploadFile = File(...)):
    """Market fişi fotoğrafını alır, OCR uygular ve kalemlere ayırır."""
    if file.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(400, "Sadece JPEG veya PNG kabul edilir")

    image_bytes = await file.read()

    try:
        raw_text = extract_text_from_image(image_bytes)
    except Exception as e:
        raise HTTPException(502, f"OCR servisi başarısız oldu: {e}")

    items = parse_receipt_text(raw_text)
    total = calculate_total(items)

    result = ReceiptProcessResult(
        receipt_id=str(uuid.uuid4()),
        raw_text=raw_text,
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
