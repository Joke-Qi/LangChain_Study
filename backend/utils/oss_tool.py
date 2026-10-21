import os
import uuid
import oss2
from dotenv import load_dotenv

load_dotenv()

_endpoint = os.getenv("OSS_ENDPOINT")
_bucket_name = os.getenv("OSS_BUCKET_NAME")
_access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
_access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
_expire = int(os.getenv("OSS_URL_EXPIRE", "3600"))

_auth = oss2.Auth(_access_key_id, _access_key_secret)
_bucket = oss2.Bucket(_auth, _endpoint, _bucket_name)


def upload_bytes(data: bytes, ext: str = ".jpg", prefix: str = "chat-images/") -> str:
    """上传字节流到 OSS，返回可访问 URL（私有 bucket 返回签名 URL）。"""
    key = f"{prefix}{uuid.uuid4()}{ext}"
    _bucket.put_object(key, data)
    return get_url(key)


def get_url(key: str) -> str:
    """公有读 bucket 直接拼接；私有 bucket 用签名 URL。"""
    # 公有读：
    return f"https://{_bucket_name}.{_endpoint}/{key}"
    # 私有读（推荐，带过期时间）：
    # return _bucket.sign_url("GET", key, _expire, slash_safe=True)


def delete_object(key_or_url: str):
    """删除 OSS 对象（删除会话时可清理）。"""
    key = extract_key(key_or_url)
    if key:
        _bucket.delete_object(key)


def extract_key(url: str) -> str | None:
    """从 URL 里反推 object key（按你实际 URL 格式调整）。"""
    if not url:
        return None
    marker = ".aliyuncs.com/"
    if marker in url:
        return url.split(marker, 1)[1].split("?", 1)[0]
    return None