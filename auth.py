"""
Backend'e gelen isteklerin gerçekten giriş yapmış bir OdaPay kullanıcısından
geldiğini doğrular. Bu olmadan, adresi bilen HERKES (uygulamayı hiç
kullanmasa bile) doğrudan API'ye istek atıp ücretsiz yapay zeka kotamızı
tüketebilirdi.

Supabase, token imzalamak için kendi anahtarlarını kullanıyor ve bu
anahtarlar zamanla değişebiliyor - bu yüzden sabit bir "şifre" yerine,
Supabase'in genel anahtarlarını (JWKS) canlı olarak kontrol ediyoruz.
Bu yöntem, Supabase anahtar değiştirse bile otomatik uyum sağlar.
"""
import os
import jwt
from fastapi import Header, HTTPException

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://nehliewzvnzynsjqzzvd.supabase.co")
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"

_jwks_client = jwt.PyJWKClient(JWKS_URL)


def verify_auth(authorization: str = Header(None)) -> str:
    """Geçerli bir giriş oturumu yoksa isteği reddeder, varsa kullanıcı id'sini döndürür."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bu işlem için giriş yapmış olman gerekiyor")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256", "HS256"],
            audience="authenticated",
        )
    except Exception as e:
        # Hata ayıklama için token'ın gerçekte hangi algoritmayı kullandığını da gösteriyoruz
        try:
            header = jwt.get_unverified_header(token)
        except Exception:
            header = {}
        raise HTTPException(401, f"Geçersiz veya süresi dolmuş oturum: {e} (token header: {header})")

    return payload.get("sub", "")
