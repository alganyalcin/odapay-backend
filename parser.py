"""
Türk market fişlerinin farklı biçimlerini ayrıştırır. İki kalıbı destekler:
1) Aynı satırda: "SUT 1LT PINAR          *45,50"
2) Ayrı satırlarda: önce ürün adı satırı, hemen altında sadece fiyat
   (veya "2 X 1,75" gibi adet x birim fiyat) satırı.
Marketten markete format farklılık gösterebileceğinden, gerçek fişlerle
test edilip genişletilmelidir.
"""
import re
from models import ReceiptItem

# Satır sonunda fiyat: "*45,50" veya "45.50" gibi kalıpları yakalar
PRICE_PATTERN = re.compile(r"[*]?(\d+[.,]\d{2})\s*$")

# Sadece fiyattan ibaret bir satır: "45,50" veya "*45,50"
STANDALONE_PRICE_PATTERN = re.compile(r"^[*]?(\d+[.,]\d{2})$")

# "3 X 1,00" gibi adet x birim fiyat satırları
QTY_PRICE_PATTERN = re.compile(r"^(\d+)\s*[xX]\s*(\d+[.,]\d{2})$")

# Fiş üzerinde geçen ama ürün olmayan satırları eleriz
NOISE_KEYWORDS = ("toplam", "kdv", "nakit", "kredi", "para üstü", "fiş no", "tarih", "kart")


def parse_receipt_text(raw_text: str) -> list[ReceiptItem]:
    items: list[ReceiptItem] = []
    pending_name: str | None = None  # henüz fiyatı gelmemiş, bekleyen ürün adı

    for line in raw_text.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue

        if any(keyword in clean_line.lower() for keyword in NOISE_KEYWORDS):
            pending_name = None
            continue

        # Kalıp: TAB ile ayrılmış sütunlar -> "PAT.CIPSI PATITO \t %08 \t *3,25"
        # isTable=true ile OCR bu şekilde döndürüyorsa en güvenilir kalıp budur.
        if "\t" in line:
            columns = [c.strip() for c in line.split("\t") if c.strip()]
            if len(columns) >= 2:
                last_col_match = STANDALONE_PRICE_PATTERN.match(columns[-1])
                if last_col_match:
                    price = float(last_col_match.group(1).replace(",", "."))
                    name = columns[0]
                    if name and not name.replace(".", "").isdigit():
                        items.append(ReceiptItem(item_name=name, total_price=price))
                        pending_name = None
                        continue

        # Kalıp: "3 X 1,00" -> bir önceki ürün adına adet + birim fiyat uygula
        qty_match = QTY_PRICE_PATTERN.match(clean_line)
        if qty_match and pending_name:
            quantity = float(qty_match.group(1))
            unit_price = float(qty_match.group(2).replace(",", "."))
            items.append(
                ReceiptItem(
                    item_name=pending_name,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=round(quantity * unit_price, 2),
                )
            )
            pending_name = None
            continue

        # Kalıp: aynı satırda hem ürün adı hem fiyat
        inline_match = PRICE_PATTERN.search(clean_line)
        if inline_match and not STANDALONE_PRICE_PATTERN.match(clean_line):
            price_str = inline_match.group(1).replace(",", ".")
            name = clean_line[: inline_match.start()].strip(" *")
            if name:
                items.append(ReceiptItem(item_name=name, total_price=float(price_str)))
                pending_name = None
                continue

        # Kalıp: satır sadece fiyattan ibaret -> bir önceki ürün adına ait
        standalone_match = STANDALONE_PRICE_PATTERN.match(clean_line)
        if standalone_match and pending_name:
            price = float(standalone_match.group(1).replace(",", "."))
            items.append(ReceiptItem(item_name=pending_name, total_price=price))
            pending_name = None
            continue

        # Fiyat içermeyen, sayı olmayan bir satır -> muhtemel ürün adı, bir sonraki
        # satırda fiyat gelirse eşleştirmek üzere beklet
        if not clean_line.isdigit():
            pending_name = clean_line

    return items


def calculate_total(items: list[ReceiptItem]) -> float:
    return round(sum(item.total_price for item in items), 2)
