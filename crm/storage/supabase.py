import json
import mimetypes
import ssl
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import certifi
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


def _abrir_url(request):
    contexto = ssl.create_default_context(cafile=certifi.where())
    return urlopen(request, context=contexto)


@deconstructible
class SupabaseStorage(Storage):
    def __init__(self, bucket=None, base_url=None, api_key=None):
        self.bucket = bucket or settings.SUPABASE_STORAGE_BUCKET
        self.base_url = (base_url or settings.SUPABASE_URL).rstrip("/")
        self.api_key = api_key or settings.SUPABASE_SECRET_KEY

    def _normalize_name(self, name):
        return name.replace("\\", "/").lstrip("/")

    def _object_path(self, name):
        return quote(self._normalize_name(name), safe="/")

    def _api_url(self, name):
        return f"{self.base_url}/storage/v1/object/{self.bucket}/{self._object_path(name)}"

    def _public_url(self, name):
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/{self._object_path(name)}"

    def _request(self, url, method="GET", data=None, headers=None):
        req_headers = {"apikey": self.api_key}
        if headers:
            req_headers.update(headers)
        request = Request(url, data=data, method=method, headers=req_headers)
        return _abrir_url(request)

    def _save(self, name, content):
        name = self._normalize_name(name)
        data = content.read()
        content_type = getattr(content, "content_type", None) or mimetypes.guess_type(name)[0] or "application/octet-stream"
        self._request(
            self._api_url(name),
            method="POST",
            data=data,
            headers={
                "Content-Type": content_type,
                "x-upsert": "true",
            },
        )
        return name

    def delete(self, name):
        name = self._normalize_name(name)
        try:
            self._request(self._api_url(name), method="DELETE")
        except HTTPError:
            return

    def exists(self, name):
        name = self._normalize_name(name)
        try:
            with self._request(self._api_url(name), method="GET"):
                return True
        except HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def url(self, name):
        return self._public_url(self._normalize_name(name))

    def size(self, name):
        with self._request(self._api_url(self._normalize_name(name)), method="GET") as response:
            return int(response.headers.get("Content-Length", 0))

    def _open(self, name, mode="rb"):
        if "b" not in mode:
            raise ValueError("SupabaseStorage suporta apenas modo binario.")
        with self._request(self._api_url(self._normalize_name(name)), method="GET") as response:
            return ContentFile(response.read())

    def get_available_name(self, name, max_length=None):
        return self._normalize_name(name)


def criar_bucket_supabase(bucket=None, public=True):
    bucket = bucket or settings.SUPABASE_STORAGE_BUCKET
    body = json.dumps({"id": bucket, "name": bucket, "public": public}).encode("utf-8")
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/bucket"
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "apikey": settings.SUPABASE_SECRET_KEY,
            "Content-Type": "application/json",
        },
    )
    try:
        with _abrir_url(request) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
