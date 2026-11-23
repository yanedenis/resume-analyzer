import json
import os
import re
import uuid
from decimal import Decimal

import boto3
from botocore.config import Config

BUCKET = os.environ["BUCKET_NAME"]
TABLE = os.environ["DYNAMODB_TABLE_NAME"]
REGION = os.environ.get("AWS_REGION")

# SigV4 + regional endpoint, required for presigned URLs in newer regions (eu-north-1)
s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))
table = boto3.resource("dynamodb").Table(TABLE)

ID_RE = re.compile(r"^[0-9a-f]{32}\.pdf$")

def _default(o):
    # DynamoDB returns numbers as Decimal
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError(f"Not serializable: {type(o)}")

def respond(status, body):
    # CORS headers are added by the Lambda Function URL config, not here
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_default),
    }

def lambda_handler(event, context):
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method")
    path = event.get("rawPath", "")

    # POST /upload-url -> presigned PUT URL for a new resume
    if method == "POST" and path == "/upload-url":
        resume_id = f"{uuid.uuid4().hex}.pdf"
        key = f"uploads/{resume_id}"
        url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET, "Key": key, "ContentType": "application/pdf"},
            ExpiresIn=300,
            HttpMethod="PUT",
        )
        return respond(200, {"upload_url": url, "resume_id": resume_id})

    # GET /result?id=<resume_id> -> analysis status / result
    if method == "GET" and path == "/result":
        resume_id = (event.get("queryStringParameters") or {}).get("id", "")
        if not ID_RE.match(resume_id):
            return respond(400, {"error": "Invalid id"})
        item = table.get_item(Key={"resume_id": resume_id}).get("Item")
        if not item:
            return respond(200, {"status": "PROCESSING"})
        return respond(200, item)

    return respond(404, {"error": "Not found"})