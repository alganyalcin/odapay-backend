"""
Fiş fotoğrafından ürün + fiyat çıkarma - Google Gemini (ücretsiz katman) kullanır.
Klasik OCR + regex yerine, görüntüyü bağlamıyla birlikte anlayan bir yapay zeka
modeli kullanıyoruz; kırışık/bulanık fişlerde çok daha isabetli sonuç verir.

Ücretsiz API anahtarı (kredi kartı istemez): https://aistudio.google.com/apikey

Dayanıklılık: Google bir modeli geçici olarak meşgul (503) ya da limitli (429)
döndürürse, otomatik olarak sıradaki modele geçilir. Ücretsiz katmanda limitler
model başına ayrı işlediği için bu, hatayı büyük ölçüde azaltır.
"""
import os
import json
import time
import base64
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Sırayla denenecek modeller. İlki asıl model, diğerleri yedek.
# Son eleman tekrar başa dönülerek bir kez daha denenir (toplam 4 deneme).
GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
]

# Bu durum kodlarında "tekrar dene / başka modele geç" mantıklı.
# 404: model adı bulunamadı (kaldırılmış olabilir), sıradakine geçeriz.
RETRYABLE_STATUS = {404, 429, 500, 502, 503, 504}

REQUEST_TIMEOUT = 30  # saniye, deneme başına

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


def _model_url(model: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _clean_json_text(text: str) -> str:
    """Bazen model JSON'u ```json ... ``` bloğu içine sarabiliyor, temizler."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    return cleaned


def _call_gemini(image_bytes: bytes, model: str) -> list[dict]:
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
        _model_url(model),
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Yapay zeka cevabı beklenmeyen formatta: {e}")

    cleaned = _clean_json_text(text)
    items = json.loads(cleaned)  # hata olursa çağıran taraf yakalayıp başka modelle dener
    if not isinstance(items, list):
        raise RuntimeError("Yapay zeka beklenmeyen bir format döndürdü")
    return items


def extract_items_from_image(image_bytes: bytes) -> list[dict]:
    """Fiş fotoğrafını Gemini'ye gönderir, ürün adı + fiyat listesini döndürür.

    Geçici hatalarda (503 meşgul, 429 limit, zaman aşımı, bozuk JSON) sıradaki
    modele geçerek yeniden dener. Kalıcı hatalarda (yanlış API anahtarı gibi)
    boşuna beklemeden hemen hata verir.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY ortam değişkeni ayarlanmamış")

    attempt_models = GEMINI_MODELS + [GEMINI_MODELS[0]]
    last_error: Exception | None = None

    for model in attempt_models:
        try:
            return _call_gemini(image_bytes, model)
        except requests.exceptions.HTTPError as e:
            last_error = e
            status = e.response.status_code if e.response is not None else None
            if status in RETRYABLE_STATUS:
                time.sleep(1.5)
                continue
            # 400/401/403 gibi kalıcı hatalar: tekrar denemenin anlamı yok
            raise RuntimeError(f"Yapay zeka servisi hata döndürdü ({status}): {e}")
        except (json.JSONDecodeError, RuntimeError, requests.exceptions.RequestException) as e:
            last_error = e
            time.sleep(1)
            continue

    raise RuntimeError(
        f"Yapay zeka cevabı alınamadı ({len(attempt_models)} denemeden sonra): {last_error}"
    )
