"""
Fiş fotoğrafından ürün + fiyat çıkarma - Google Gemini (ücretsiz katman) kullanır.
Klasik OCR + regex yerine, görüntüyü bağlamıyla birlikte anlayan bir yapay zeka
modeli kullanıyoruz; kırışık/bulanık fişlerde çok daha isabetli sonuç verir.

Ücretsiz API anahtarı (kredi kartı istemez): https://aistudio.google.com/apikey
"""
import os
import json
import base64
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

PROMPT = """Bu bir market fişi fotoğrafı. Fişteki her ürünü ve o ürünün toplam fiyatını (TL) çıkar.

Kurallar:
- Sadece gerçek ürün satırlarını al; başlık, KDV, toplam, kart bilgisi gibi satırları alma.
- Fiyatları ondalık sayı (nokta ile) olarak ver, örn: 3.25
- Emin olamadığın bir ürünü de en iyi tahminle dahil et, atlama.
- Sadece aşağıdaki JSON formatında cevap ver, başka hiçbir metin ekleme:
[{"item_name": "...", "total_price": 0.00}, ...]
"""


def extract_items_from_image(image_bytes: bytes) -> list[dict]:
    """Fiş fotoğrafını Gemini'ye gönderir, ürün adı + fiyat listesini döndürür."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY ortam değişkeni ayarlanmamış")

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
        "generationConfig": {"response_mime_type": "application/json"},
    }

    response = requests.post(
        GEMINI_URL,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        items = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Yapay zeka cevabı ayrıştırılamadı: {e}")

    if not isinstance(items, list):
        raise RuntimeError("Yapay zeka beklenmeyen bir format döndürdü")

    return items
