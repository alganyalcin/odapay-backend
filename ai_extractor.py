"""
Fiş fotoğrafından ürün + fiyat çıkarma - Google Gemini (ücretsiz katman) kullanır.
Klasik OCR + regex yerine, görüntüyü bağlamıyla birlikte anlayan bir yapay zeka
modeli kullanıyoruz; kırışık/bulanık fişlerde çok daha isabetli sonuç verir.

Ücretsiz API anahtarı (kredi kartı istemez): https://aistudio.google.com/apikey
"""
import os
import json
import time
import base64
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.5-flash:generateContent"
)

PROMPT = """Bu bir market fişi fotoğrafı. Fişteki her ürünü ve o ürünün toplam fiyatını (TL) çıkar.

Kurallar:
- Sadece gerçek ürün satırlarını al; başlık, KDV, toplam, kart bilgisi gibi satırları alma.
- Fiyatları ondalık sayı olarak ver (nokta ile, örn: 3.25), asla metin/kesir olarak yazma.
- Ürün adında çift tırnak (") karakteri kullanma.
- Emin olamadığın bir ürünü de en iyi tahminle dahil et, atlama.
"""

# Gemini'nin dönmesi gereken KESİN yapı - modelin serbest metin yazıp
# bozuk JSON üretmesini büyük ölçüde engelliyor.
RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "item_name": {"type": "STRING"},
            "total_price": {"type": "NUMBER"},
        },
        "required": ["item_name", "total_price"],
    },
}


def _clean_json_text(text: str) -> str:
    """Bazen model JSON'u ```json ... ``` bloğu içine sarabiliyor, temizler."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    return cleaned


def _call_gemini(image_bytes: bytes) -> list[dict]:
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT},
                    {"inline_data": {"mime_type": "image/jpeg", "data": encoded_image}},
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            "temperature": 0,  # tutarlılık için rastgeleliği kapat
            "maxOutputTokens": 4096,
        },
    }

    response = requests.post(
        GEMINI_URL,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=55,  # Gemini bazen yoğunlukta yavaş cevap verebiliyor, pay bırakıyoruz
    )
    response.raise_for_status()
    result = response.json()

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Yapay zeka cevabı beklenmeyen formatta: {e}")

    cleaned = _clean_json_text(text)
    items = json.loads(cleaned)  # burada hata olursa çağıran taraf yakalayıp tekrar dener

    if not isinstance(items, list):
        raise RuntimeError("Yapay zeka beklenmeyen bir format döndürdü")

    return items


def extract_items_from_image(image_bytes: bytes) -> list[dict]:
    """Fiş fotoğrafını Gemini'ye gönderir, ürün adı + fiyat listesini döndürür.

    Ara sıra model geçersiz JSON üretebiliyor, ya da Google'ın sunucusu
    yoğunlukta geç/zaman aşımına uğrayan bir cevap verebiliyor (nadir ama
    olabiliyor); böyle durumlarda otomatik olarak bir kez daha deniyoruz.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY ortam değişkeni ayarlanmamış")

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return _call_gemini(image_bytes)
        except (json.JSONDecodeError, RuntimeError, requests.exceptions.RequestException) as e:
            last_error = e
            time.sleep(1)
            continue

    raise RuntimeError(f"Yapay zeka cevabı alınamadı (3 denemeden sonra): {last_error}")
