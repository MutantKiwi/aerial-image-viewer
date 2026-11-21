"""Shorten a project link for imagery.mutant.kiwi.

The viewer POSTs {"v":1,"d":"<its own packed payload>"} and gets back an id,
which it shares as https://imagery.mutant.kiwi/#s=<id>.

The payload is opaque here and stored verbatim, so the viewer can change its
own encoding without this function being redeployed.

Reads never reach this function. The object is written under p/ in the bucket
CloudFront already serves, so the viewer fetches
https://imagery.mutant.kiwi/p/<id>.json same-origin: no CORS, no per-read
Lambda cost, and the id is the hash of the body so the object can be cached
forever.
"""
import base64
import hashlib
import json
import os

import boto3
from botocore.exceptions import ClientError

BUCKET = os.environ.get("BUCKET", "gbf.nz.imagery")
PREFIX = os.environ.get("PREFIX", "p/")
MAX_BODY = int(os.environ.get("MAX_BODY", "4096"))

s3 = boto3.client("s3")


def _resp(code, obj):
    return {
        "statusCode": code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(obj, separators=(",", ":")),
    }


def handler(event, context):
    method = (
        ((event.get("requestContext") or {}).get("http") or {}).get("method") or ""
    ).upper()

    # Function URL CORS answers the real preflight; this is just a safety net.
    if method == "OPTIONS":
        return {"statusCode": 204, "body": ""}
    if method != "POST":
        return _resp(405, {"error": "POST only"})

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except Exception:
            return _resp(400, {"error": "bad body encoding"})

    # This endpoint is unauthenticated, so the size cap is the main guard
    # against someone filling the bucket. A real project is well under 1 KB.
    raw_len = len(body.encode("utf-8"))
    if raw_len > MAX_BODY:
        return _resp(413, {"error": "payload too large", "max": MAX_BODY, "got": raw_len})

    try:
        doc = json.loads(body)
    except Exception:
        return _resp(400, {"error": "body must be JSON"})

    if (
        not isinstance(doc, dict)
        or not isinstance(doc.get("v"), int)
        or not isinstance(doc.get("d"), str)
        or not doc["d"]
    ):
        return _resp(400, {"error": 'expected {"v":<int>,"d":"<payload>"}'})

    # Keep only the two fields we promise to store, so a caller cannot smuggle
    # extra data in, and reordering keys cannot change the digest.
    stored = json.dumps({"v": doc["v"], "d": doc["d"]}, separators=(",", ":")).encode()
    digest = hashlib.sha256(stored).digest()
    b64 = base64.urlsafe_b64encode(digest).decode().rstrip("=")

    # Content-addressed, so saving the same project twice yields the same link
    # and costs one PUT rather than two. Eight base64url characters is 48 bits;
    # comparing the stored bytes on a hit makes a collision impossible rather
    # than merely unlikely, and a longer id is the fallback if one happens.
    for n in (8, 12, 22):
        sid = b64[:n]
        key = PREFIX + sid + ".json"
        try:
            existing = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        except ClientError as err:
            code = err.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchKey", "NotFound"):
                raise
            existing = None

        if existing is None:
            s3.put_object(
                Bucket=BUCKET,
                Key=key,
                Body=stored,
                ContentType="application/json",
                CacheControl="public, max-age=31536000, immutable",
            )
            return _resp(201, {"id": sid, "bytes": len(stored), "new": True})

        if existing == stored:
            return _resp(200, {"id": sid, "bytes": len(stored), "new": False})
        # Same prefix, different content: fall through to a longer id.

    return _resp(500, {"error": "could not allocate an id"})
