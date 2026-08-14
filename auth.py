"""
Backend'e gelen isteklerin gerçekten giriş yapmış bir OdaPay kullanıcısından
geldiğini doğrular. Bu olmadan, adresi bilen HERKES (uygulamayı hiç
kullanmasa bile) doğrudan API'ye istek atıp ücretsiz yapay zeka kotamızı
tüketebilirdi.
"""
import os
import jwt
from fastapi import Header, HTTPException

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")


def verify_auth(authorization: str = Header(None)) -> str:
    """Geçerli bir giriş oturumu yoksa isteği reddeder, varsa kullanıcı id'sini döndürür."""
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(500, "Sunucu güvenlik ayarı eksik (SUPABASE_JWT_SECRET)")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bu işlem için giriş yapmış olman gerekiyor")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Geçersiz veya süresi dolmuş oturum: {e}")

    return payload.get("sub", "")
