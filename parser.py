"""
Türk market fişlerinin tipik satır biçimini (ürün adı ... fiyat) ayrıştırır.
Örnek satır: "SUT 1LT PINAR          *45,50"
Bu bölüm markete göre farklılık gösterebileceğinden, gerçek fişlerle
test edilip regex desenleri zamanla genişletilmelidir.
"""
import re
from models import ReceiptItem

# Satır sonunda fiyat: "*45,50" veya "45.50" gibi kalıpları yakalar
PRICE_PATTERN = re.compile(r"[*]?(\d+[.,]\d{2})\s*$")

# Fiş üzerinde geçen ama ürün olmayan satırları eleriz
NOISE_KEYWORDS = ("toplam", "kdv", "nakit", "kredi", "para üstü", "fiş no", "tarih")


def parse_receipt_text(raw_text: str) -> list[ReceiptItem]:
    items: list[ReceiptItem] = []

    for line in raw_text.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue
        if any(keyword in clean_line.lower() for keyword in NOISE_KEYWORDS):
            continue

        match = PRICE_PATTERN.search(clean_line)
        if not match:
            continue

        price_str = match.group(1).replace(",", ".")
        try:
            price = float(price_str)
        except ValueError:
            continue

        name = clean_line[: match.start()].strip(" *")
        if not name:
            continue

        items.append(
            ReceiptItem(item_name=name, quantity=1, total_price=price)
        )

    return items


def calculate_total(items: list[ReceiptItem]) -> float:
    return round(sum(item.total_price for item in items), 2)
