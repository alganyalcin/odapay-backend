"""OdaPay API - istek/yanıt veri modelleri"""
from pydantic import BaseModel
from typing import Optional


class ReceiptItem(BaseModel):
    item_name: str
    quantity: float = 1
    unit_price: Optional[float] = None
    total_price: float
    assigned_to_user_id: Optional[str] = None  # None = ortak harcama


class ReceiptProcessResult(BaseModel):
    receipt_id: str
    raw_text: str
    items: list[ReceiptItem]
    total_amount: float
    status: str  # "processed" | "needs_review" | "failed"


class SplitRequest(BaseModel):
    """Fiş işlendikten sonra harcamanın nasıl bölüşüleceğini belirten istek"""
    receipt_id: str
    household_id: str
    paid_by_user_id: str
    member_user_ids: list[str]      # eve dahil olup ortak paya girecek kişiler
    split_mode: str = "equal"       # "equal" | "by_item"


class SplitResult(BaseModel):
    expense_id: str
    total_amount: float
    shares: dict[str, float]        # user_id -> tutar
