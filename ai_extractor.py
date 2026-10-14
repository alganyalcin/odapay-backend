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
# Hepsi sırayla denenir, sonra ilk ikisi bir kez daha (toplam 7 deneme).
GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",       # Google'ın o anki en yeni Flash modeline işaret eden takma ad
    "gemini-flash-lite-latest",  # daha hafif model, son çare yedek
]
# Not: Pro modeller (gemini-pro-latest vb.) Nisan 2026'dan beri ücretsiz katmanda yok,
# bu yüzden listeye eklenmedi.

REQUEST_TIMEOUT = 30  # saniye, deneme başına (en fazla)
TOTAL_DEADLINE = 80  # saniye, tüm denemeler için toplam üst sınır

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


def _call_gemini(image_bytes: bytes, model: str, timeout: float) -> list[dict]:
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
        timeout=timeout,
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
    modele geçerek yeniden dener (en fazla TOTAL_DEADLINE saniye). Aynı model
    ikinci kez denenecekse önce kısa bir süre beklenir.
    Her deneme loglanır.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY ortam değişkeni ayarlanmamış")

    attempt_models = GEMINI_MODELS + GEMINI_MODELS[:2]  # tüm modeller, sonra ilk ikisi bir kez daha
    last_error: Exception | None = None
    started = time.monotonic()
    attempts_made = 0

    tried: set[str] = set()

    for model in attempt_models:
        if model in tried:
            # Aynı modeli ikinci kez deniyoruz: Google'a biraz nefes aldır.
            time.sleep(3)
        tried.add(model)
        remaining = TOTAL_DEADLINE - (time.monotonic() - started)
        if remaining <= 5:
            break
        attempts_made += 1
        try:
            result = _call_gemini(image_bytes, model, min(REQUEST_TIMEOUT, remaining))
            print(f"[gemini] OK model={model} deneme={attempts_made}", flush=True)
            return result
        except requests.exceptions.HTTPError as e:
            last_error = e
            status = e.response.status_code if e.response is not None else None
            print(f"[gemini] HATA model={model} deneme={attempts_made} status={status}", flush=True)
            # Kapasite/limit model başına ayrı tutulduğu için, başka modele geçerken
            # beklemenin faydası yok; doğrudan sıradakini dene.
            continue
        except (json.JSONDecodeError, RuntimeError, requests.exceptions.RequestException) as e:
            last_error = e
            print(f"[gemini] HATA model={model} deneme={attempts_made} {type(e).__name__}", flush=True)
            time.sleep(1)
            continue

    raise RuntimeError(
        f"Yapay zeka cevabı alınamadı ({attempts_made} denemeden sonra): {last_error}"
    )
