"""
Fiş fotoğrafından ham metin çıkarma.
OCR.space servisini kullanır - kurulumu sadece tek bir API key gerektirir,
kredi kartı veya servis hesabı dosyası istemez.
Ücretsiz key almak için: https://ocr.space/ocrapi/freekey
"""
import os
import requests

OCR_SPACE_API_KEY = os.environ.get("OCR_SPACE_API_KEY", "")
OCR_SPACE_URL = "https://api.ocr.space/parse/image"


def extract_text_from_image(image_bytes: bytes) -> str:
    """Fotoğraftaki tüm metni satır satır döndürür."""
    if not OCR_SPACE_API_KEY:
        raise RuntimeError("OCR_SPACE_API_KEY ortam değişkeni ayarlanmamış")

    response = requests.post(
        OCR_SPACE_URL,
        files={"file": ("receipt.jpg", image_bytes, "image/jpeg")},
        data={
            "apikey": OCR_SPACE_API_KEY,
            "language": "tur",
            "OCREngine": 2,  # daha yüksek doğruluklu motor
        },
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()

    if result.get("IsErroredOnProcessing"):
        raise RuntimeError(f"OCR hatası: {result.get('ErrorMessage')}")

    parsed_results = result.get("ParsedResults") or []
    if not parsed_results:
        return ""

    return parsed_results[0].get("ParsedText", "")
