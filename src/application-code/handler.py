import json
import os
import time
import boto3
import urllib.parse
from google import genai
from google.genai import errors, types

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'ResumeAnalysisResults')
table = dynamodb.Table(table_name)

# Models are tried in order, then round-robin, until the Lambda runs low on time
MODELS = [
    m.strip()
    for m in os.environ.get(
        'GEMINI_MODELS', 'gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite'
    ).split(',')
    if m.strip()
]
ATTEMPT_TIMEOUT_MS = 20000  # one hung request must not eat the whole Lambda run

# Initialize Gemini Client
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))


RETRY_CODES = {429, 500, 502, 503, 504}


def generate_with_fallback(context, **kwargs):
    """Call Gemini; on overload/timeouts try the next model until time runs low."""
    last_error = None
    i = 0
    while context.get_remaining_time_in_millis() > 30000:
        model = MODELS[i % len(MODELS)]
        i += 1
        try:
            return client.models.generate_content(model=model, **kwargs)
        except Exception as e:
            # Real errors (bad key, bad request...) fail immediately
            if isinstance(e, errors.APIError) and e.code not in RETRY_CODES:
                raise
            last_error = e
            print(f"{model} failed ({type(e).__name__}: {str(e)[:120]}), trying next")
            time.sleep(2)
    raise last_error or TimeoutError("Ran out of time before Gemini answered")


def lambda_handler(event, context):
    resume_id = None
    uploaded_file = None
    try:
        # Get S3 bucket and object key from the event notification
        record = event['Records'][0]
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'], encoding='utf-8')

        resume_id = key.split('/')[-1]

        # Download PDF file from S3 to local Lambda temp storage
        local_file_path = f"/tmp/{resume_id}"
        s3_client.download_file(bucket, key, local_file_path)

        # Upload file to Gemini File API for document processing
        print(f"Analyzing resume: {resume_id}")
        uploaded_file = client.files.upload(file=local_file_path)

        # Prompt Gemini to analyze resume and return strict JSON
        prompt = """
        Analyze this resume against modern software engineering standards.
        Provide a match score out of 100, extracted skills, experience level,
        and 3 concise constructive improvement tips.
        """

        response = generate_with_fallback(
            context,
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                http_options=types.HttpOptions(timeout=ATTEMPT_TIMEOUT_MS),
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "match_score": {"type": "INTEGER"},
                        "experience_level": {"type": "STRING"},
                        "skills": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"}
                        },
                        "improvement_tips": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"}
                        }
                    },
                    "required": ["match_score", "experience_level", "skills", "improvement_tips"]
                },
            ),
        )

        analysis_data = json.loads(response.text)

        # Save analysis output to DynamoDB
        table.put_item(
            Item={
                'resume_id': resume_id,
                'status': 'COMPLETED',
                'analysis': analysis_data
            }
        )

        print(f"Successfully processed resume: {resume_id}")
        return {'statusCode': 200, 'body': 'Analysis complete'}

    except Exception as e:
        print(f"Error processing resume: {str(e)}")
        # Record the failure so the frontend can stop waiting
        if resume_id:
            try:
                table.put_item(
                    Item={
                        'resume_id': resume_id,
                        'status': 'FAILED',
                        'error': str(e)[:500]
                    }
                )
            except Exception as db_err:
                print(f"Could not record failure: {db_err}")
        return {'statusCode': 500, 'body': str(e)}

    finally:
        # Clean up the copy stored in the Gemini File API
        if uploaded_file is not None:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass