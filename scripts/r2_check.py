#!/usr/bin/env python3
"""Verificación real de Cloudflare R2 y configuración CORS segura para Doppler.

- Lee credenciales desde `.env` (o entorno) SIN imprimir secretos ni URLs firmadas completas.
- Comprueba acceso al bucket privado (`HeadBucket`).
- Inspecciona CORS actual (`GetBucketCors`); con `--ensure-cors` añade o actualiza
  exclusivamente la regla para `APP_ORIGIN` conservando reglas ajenas existentes.
- Ejecuta el ciclo real sobre `R2_TEST_PREFIX`: presigned PUT, HeadObject, GetObject,
  comprobación SHA-256, expiración de presigned GET (TTL 2 s), y DeleteObject con limpieza.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret: str, datestamp: str, region: str, service: str = "s3") -> bytes:
    k_date = hmac_sha256(("AWS4" + secret).encode("utf-8"), datestamp)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    return hmac_sha256(k_service, "aws4_request")


class R2Client:
    def __init__(self) -> None:
        self.account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
        self.access_key = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
        self.secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
        self.bucket = os.environ.get("R2_BUCKET", "").strip()
        self.region = os.environ.get("R2_REGION", "auto").strip() or "auto"
        endpoint = os.environ.get("R2_ENDPOINT", "").strip()
        self.endpoint = (
            endpoint.rstrip("/")
            if endpoint
            else f"https://{self.account_id}.r2.cloudflarestorage.com"
        )
        self.host = urllib.parse.urlparse(self.endpoint).netloc
        self.app_origin = os.environ.get("APP_ORIGIN", "http://localhost:4321").strip()
        raw_test_prefix = os.environ.get("R2_TEST_PREFIX", "doppler/tests/").strip().lstrip("/")
        self.test_prefix = (
            raw_test_prefix if raw_test_prefix.endswith("/") else raw_test_prefix + "/"
        )

        missing = [
            k
            for k, v in [
                ("R2_ACCOUNT_ID", self.account_id),
                ("R2_ACCESS_KEY_ID", self.access_key),
                ("R2_SECRET_ACCESS_KEY", self.secret_key),
                ("R2_BUCKET", self.bucket),
            ]
            if not v or v.startswith("replace_with_")
        ]
        if missing:
            raise RuntimeError(f"Credenciales R2 incompletas: {', '.join(missing)}")

    def signed_request(
        self,
        method: str,
        path: str,
        query: dict[str, str] | None = None,
        body: bytes = b"",
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()

        canonical_uri = "/" + urllib.parse.quote(path.lstrip("/"), safe="/-_.~")
        query_items = sorted((query or {}).items())
        canonical_query = "&".join(
            f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
            for k, v in query_items
        )

        headers: dict[str, str] = {
            "host": self.host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if extra_headers:
            for k, v in extra_headers.items():
                headers[k.lower()] = v

        sorted_headers = sorted(headers.items())
        canonical_headers = "".join(f"{k}:{v.strip()}\n" for k, v in sorted_headers)
        signed_headers = ";".join(k for k, _ in sorted_headers)

        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        scope = f"{datestamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        sig = hmac.new(
            signing_key(self.secret_key, datestamp, self.region),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        auth = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={sig}"
        )

        url = f"{self.endpoint}{canonical_uri}"
        if canonical_query:
            url += f"?{canonical_query}"

        req_headers = {k: v for k, v in headers.items() if k != "host"}
        req_headers["Authorization"] = auth

        req = urllib.request.Request(url, data=body if body else None, method=method, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()

    def presign_url(
        self,
        method: str,
        key: str,
        expires: int,
        content_type: str | None = None,
    ) -> str:
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        scope = f"{datestamp}/{self.region}/s3/aws4_request"
        canonical_uri = "/" + urllib.parse.quote(f"{self.bucket}/{key.lstrip('/')}", safe="/-_.~")

        headers_to_sign = {"host": self.host}
        if content_type:
            headers_to_sign["content-type"] = content_type
        sorted_h = sorted(headers_to_sign.items())
        signed_headers = ";".join(k for k, _ in sorted_h)
        canonical_headers = "".join(f"{k}:{v}\n" for k, v in sorted_h)

        params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key}/{scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires),
            "X-Amz-SignedHeaders": signed_headers,
        }
        canonical_query = "&".join(
            f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
            for k, v in sorted(params.items())
        )
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_query,
                canonical_headers,
                signed_headers,
                "UNSIGNED-PAYLOAD",
            ]
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        sig = hmac.new(
            signing_key(self.secret_key, datestamp, self.region),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{self.endpoint}{canonical_uri}?{canonical_query}&X-Amz-Signature={sig}"

    def parse_cors_rules(self, xml_bytes: bytes) -> list[dict[str, object]]:
        root = ET.fromstring(xml_bytes)
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"
        rules: list[dict[str, object]] = []
        for rule_el in root.findall(f"{ns}CORSRule"):
            rule: dict[str, object] = {
                "AllowedOrigins": [e.text for e in rule_el.findall(f"{ns}AllowedOrigin") if e.text],
                "AllowedMethods": [e.text for e in rule_el.findall(f"{ns}AllowedMethod") if e.text],
                "AllowedHeaders": [e.text for e in rule_el.findall(f"{ns}AllowedHeader") if e.text],
                "ExposeHeaders": [e.text for e in rule_el.findall(f"{ns}ExposeHeader") if e.text],
            }
            max_age = rule_el.find(f"{ns}MaxAgeSeconds")
            if max_age is not None and max_age.text:
                rule["MaxAgeSeconds"] = int(max_age.text)
            rules.append(rule)
        return rules

    def build_cors_xml(self, rules: list[dict[str, object]]) -> bytes:
        root = ET.Element("CORSConfiguration")
        for r in rules:
            el = ET.SubElement(root, "CORSRule")
            for origin in r.get("AllowedOrigins", []):
                ET.SubElement(el, "AllowedOrigin").text = str(origin)
            for method in r.get("AllowedMethods", []):
                ET.SubElement(el, "AllowedMethod").text = str(method)
            for header in r.get("AllowedHeaders", []):
                ET.SubElement(el, "AllowedHeader").text = str(header)
            for expose in r.get("ExposeHeaders", []):
                ET.SubElement(el, "ExposeHeader").text = str(expose)
            if "MaxAgeSeconds" in r:
                ET.SubElement(el, "MaxAgeSeconds").text = str(r["MaxAgeSeconds"])
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def run_check(ensure_cors: bool, out_json: Path | None) -> int:
    load_dotenv(Path(".env"))
    client = R2Client()
    report: dict[str, object] = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bucket": client.bucket,
        "region": client.region,
        "app_origin": client.app_origin,
        "test_prefix": client.test_prefix,
        "checks": {},
    }
    checks: dict[str, object] = report["checks"]  # type: ignore[assignment]

    # 1. HeadBucket
    st, _, _ = client.signed_request("HEAD", f"/{client.bucket}")
    checks["head_bucket"] = {"status": st, "passed": st == 200}
    if st != 200:
        raise RuntimeError(f"HeadBucket falló con HTTP {st}")

    # 2. GetBucketCors + optional PutBucketCors (preservando reglas ajenas)
    st_cors, _, body_cors = client.signed_request("GET", f"/{client.bucket}", query={"cors": ""})
    existing_rules: list[dict[str, object]] = []
    if st_cors == 200 and body_cors:
        existing_rules = client.parse_cors_rules(body_cors)

    has_doppler_cors = any(
        client.app_origin in r.get("AllowedOrigins", [])
        and all(m in r.get("AllowedMethods", []) for m in ("PUT", "GET", "HEAD"))
        and "content-type" in [h.lower() for h in r.get("AllowedHeaders", [])]
        for r in existing_rules
    )

    cors_updated = False
    if ensure_cors and not has_doppler_cors:
        doppler_rule = {
            "AllowedOrigins": [client.app_origin],
            "AllowedMethods": ["PUT", "GET", "HEAD"],
            "AllowedHeaders": ["content-type"],
            "ExposeHeaders": ["etag"],
            "MaxAgeSeconds": 3000,
        }
        preserved = [
            r for r in existing_rules if client.app_origin not in r.get("AllowedOrigins", [])
        ]
        new_rules = preserved + [doppler_rule]
        xml_payload = client.build_cors_xml(new_rules)
        md5_b64 = base64.b64encode(hashlib.md5(xml_payload).digest()).decode("ascii")
        st_put, _, err_put = client.signed_request(
            "PUT",
            f"/{client.bucket}",
            query={"cors": ""},
            body=xml_payload,
            extra_headers={"content-type": "application/xml", "content-md5": md5_b64},
        )
        cors_updated = st_put in (200, 204)
        checks["put_bucket_cors"] = {
            "status": st_put,
            "passed": cors_updated,
            "preserved_other_rules": len(preserved),
            "detail": err_put.decode("utf-8", errors="ignore")[:200] if not cors_updated else "ok",
        }
        if cors_updated:
            has_doppler_cors = True

    checks["cors_ready_for_origin"] = {
        "passed": has_doppler_cors,
        "updated": cors_updated,
        "origin": client.app_origin,
    }

    # 3. Presigned PUT (con preflight OPTIONS + cabecera Origin), HeadObject, GetObject + SHA-256 + Expiry + Delete
    test_key = f"{client.test_prefix}r2_check_{uuid.uuid4().hex}.wav"
    payload = b"RIFF\x24\x00\x00\x00WAVEfmt " + os.urandom(2048)
    expected_sha256 = hashlib.sha256(payload).hexdigest()

    put_url = client.presign_url("PUT", test_key, expires=120, content_type="audio/wav")

    preflight_req = urllib.request.Request(
        put_url,
        method="OPTIONS",
        headers={
            "Origin": client.app_origin,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    preflight_status = 0
    preflight_acao = None
    preflight_methods = None
    try:
        with urllib.request.urlopen(preflight_req, timeout=20) as resp:
            preflight_status = resp.status
            preflight_acao = resp.headers.get("Access-Control-Allow-Origin")
            preflight_methods = resp.headers.get("Access-Control-Allow-Methods")
    except urllib.error.HTTPError as exc:
        preflight_status = exc.code
        preflight_acao = exc.headers.get("Access-Control-Allow-Origin")
        preflight_methods = exc.headers.get("Access-Control-Allow-Methods")

    preflight_ok = preflight_status in (200, 204) and preflight_acao == client.app_origin
    if preflight_ok:
        has_doppler_cors = True
        checks["cors_ready_for_origin"] = {
            "passed": True,
            "updated": cors_updated,
            "verified_via": "live_options_preflight",
            "preflight_status": preflight_status,
            "cors_allow_origin": preflight_acao,
            "cors_allow_methods": preflight_methods,
            "origin": client.app_origin,
        }
    else:
        checks["cors_ready_for_origin"] = {
            "passed": has_doppler_cors,
            "updated": cors_updated,
            "verified_via": "get_bucket_cors_or_preflight",
            "preflight_status": preflight_status,
            "cors_allow_origin": preflight_acao,
            "origin": client.app_origin,
        }

    put_req = urllib.request.Request(
        put_url,
        data=payload,
        method="PUT",
        headers={"Content-Type": "audio/wav", "Origin": client.app_origin},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(put_req, timeout=20) as resp:
        put_status = resp.status
        cors_acao = resp.headers.get("Access-Control-Allow-Origin")
    put_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    checks["presigned_put"] = {
        "status": put_status,
        "passed": put_status in (200, 204),
        "elapsed_ms": put_ms,
        "cors_allow_origin": cors_acao,
        "payload_bytes": len(payload),
    }

    # 4. HeadObject
    st_head, head_headers, _ = client.signed_request("HEAD", f"/{client.bucket}/{test_key}")
    head_len = int(head_headers.get("Content-Length") or head_headers.get("content-length") or 0)
    checks["head_object"] = {
        "status": st_head,
        "passed": st_head == 200 and head_len == len(payload),
        "content_length": head_len,
    }

    # 5. Presigned GET + SHA-256 verification
    get_url = client.presign_url("GET", test_key, expires=60)
    t1 = time.perf_counter()
    with urllib.request.urlopen(urllib.request.Request(get_url, method="GET"), timeout=20) as resp:
        downloaded = resp.read()
        get_status = resp.status
    get_ms = round((time.perf_counter() - t1) * 1000.0, 2)
    actual_sha256 = hashlib.sha256(downloaded).hexdigest()
    checks["presigned_get_and_sha256"] = {
        "status": get_status,
        "passed": get_status == 200 and actual_sha256 == expected_sha256,
        "elapsed_ms": get_ms,
        "sha256_match": actual_sha256 == expected_sha256,
        "sha256": actual_sha256,
    }

    # 6. Presigned GET expiration (TTL = 2s, wait 3.5s)
    short_get_url = client.presign_url("GET", test_key, expires=2)
    time.sleep(3.5)
    expired_status = 0
    try:
        with urllib.request.urlopen(urllib.request.Request(short_get_url, method="GET"), timeout=15) as resp:
            expired_status = resp.status
    except urllib.error.HTTPError as exc:
        expired_status = exc.code
    checks["presigned_get_expiration"] = {
        "status": expired_status,
        "passed": expired_status in (400, 403),
    }

    # 7. Cleanup DeleteObject + confirm 404
    st_del, _, _ = client.signed_request("DELETE", f"/{client.bucket}/{test_key}")
    st_after, _, _ = client.signed_request("HEAD", f"/{client.bucket}/{test_key}")
    checks["delete_and_cleanup"] = {
        "delete_status": st_del,
        "head_after_delete_status": st_after,
        "passed": st_del in (200, 204) and st_after == 404,
    }

    all_passed = all(
        bool(v.get("passed")) for v in checks.values() if isinstance(v, dict) and "passed" in v
    )
    report["all_passed"] = all_passed

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(rendered + "\n", encoding="utf-8")

    return 0 if all_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Comprobación real de Cloudflare R2 para Doppler")
    parser.add_argument(
        "--ensure-cors",
        action="store_true",
        help="Configura la regla CORS exacta para APP_ORIGIN conservando reglas ajenas",
    )
    parser.add_argument("--out", type=Path, default=None, help="Ruta opcional para guardar JSON sin secretos")
    args = parser.parse_args()
    try:
        return run_check(ensure_cors=args.ensure_cors, out_json=args.out)
    except Exception as exc:
        print(json.dumps({"all_passed": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
