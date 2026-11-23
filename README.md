# Cloud-Native AI Resume Analyzer

A serverless web app that analyzes a resume (PDF) with Google Gemini and returns a match score, experience level, extracted skills and improvement tips. The whole backend runs on AWS and is provisioned with Terraform.

## How it works

1. The page asks the API Lambda for a presigned S3 upload URL.
2. The browser uploads the PDF directly to S3.
3. The upload triggers the analyzer Lambda.
4. The analyzer sends the PDF to Gemini and requests a strict JSON response.
5. The result (or a `FAILED` status with the error) is stored in DynamoDB.
6. The page polls the API until the result is ready and renders it.

If a Gemini model is overloaded or times out, the analyzer automatically tries the next model in its list.

## Tech stack

- **Frontend:** plain HTML + JavaScript, Tailwind CSS (CDN)
- **Backend:** AWS Lambda (Python 3.11), Lambda Function URL, S3, DynamoDB
- **AI:** Google Gemini API (`google-genai` SDK)
- **Infrastructure as code:** Terraform

## Project structure

```
.
├── frontend/
│   └── index.html              # UI: upload, progress, results
├── src/
│   ├── application-code/
│   │   └── handler.py          # Analyzer Lambda (S3 trigger → Gemini → DynamoDB)
│   └── api-code/
│       └── api_handler.py      # API Lambda (/upload-url, /result)
├── scripts/
│   └── build_layer.py          # Builds the Python dependency layer
├── terraform/
│   ├── main.tf                 # S3, DynamoDB, IAM, analyzer Lambda, layer, trigger
│   ├── api.tf                  # API Lambda + Function URL
│   ├── variables.tf
│   └── outputs.tf
├── requirements.txt            # Lambda dependencies (google-genai)
└── .gitignore
```

## Prerequisites

- An AWS account and the [AWS CLI](https://aws.amazon.com/cli/) configured (`aws configure`)
- [Terraform](https://developer.hashicorp.com/terraform/install)
- Python 3.11+ and `pip`
- A [Gemini API key](https://aistudio.google.com/apikey)

## Deployment

1. **Clone the repo**
   ```bash
   git clone [your-repo-url](https://github.com/yanedenis/resume-analyzer)
   cd resume-analyzer
   ```

2. **Add your Gemini API key.** Create `terraform/terraform.tfvars` (it is git-ignored):
   ```hcl
   gemini_api_key = "YOUR_GEMINI_API_KEY"
   ```
   Alternatively, set the `TF_VAR_gemini_api_key` environment variable.

3. **Build the dependency layer**
   ```bash
   python scripts/build_layer.py
   ```
   This downloads the packages from `requirements.txt` for Lambda's Linux runtime into `build/layer/` (git-ignored).

4. **Deploy**
   ```bash
   cd terraform
   terraform init
   terraform apply
   ```

5. **Connect the frontend.** Print the API address:
   ```bash
   terraform output api_url
   ```
   Paste it into the `API_URL` constant near the top of the `<script>` in `frontend/index.html`.

6. **Use it.** Open `frontend/index.html` in your browser, choose a PDF and click **Analyze Resume**. Results appear after roughly 10–30 seconds.

## Configuration

| Setting | Where | Default |
| --- | --- | --- |
| AWS region | `aws_region` in `terraform/variables.tf` | `eu-north-1` |
| Gemini models (tried in order) | `GEMINI_MODELS` in `terraform/main.tf` | `gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite` |
| Analyzer timeout / memory | `aws_lambda_function.analyzer_lambda` | 120 s / 512 MB |
| Max upload size (client-side check) | `MAX_MB` in `frontend/index.html` | 10 MB |
| Results wait time | `TIMEOUT_MS` in `frontend/index.html` | 180 s |

The S3 bucket name is `resume-analyzer-storage-<region>`. Bucket names are globally unique, so change it in `main.tf` if it is already taken.

## Updating

- Changed `handler.py`, `api_handler.py` or any `.tf` file → `terraform apply`
- Changed `requirements.txt` → `python scripts/build_layer.py`, then `terraform apply`

## Troubleshooting

View the logs of either Lambda:

```bash
aws logs tail /aws/lambda/ResumeAnalyzerFunction --since 15m --region eu-north-1   # analyzer
aws logs tail /aws/lambda/ResumeAnalyzerApi      --since 15m --region eu-north-1   # API
```

| Symptom | Likely cause |
| --- | --- |
| `Server error (502)` in the page | The API Lambda crashed. Check the `ResumeAnalyzerApi` log, and confirm `src/api-code/api_handler.py` exists before running `terraform apply`. |
| Page says "Timed out waiting for the analysis" | The analyzer didn't finish. Check the `ResumeAnalyzerFunction` log. |
| `No module named 'google'` | The dependency layer wasn't built. Run `python scripts/build_layer.py`, then `terraform apply`. |
| `404 NOT_FOUND` for a model | Google retired that model. Update `GEMINI_MODELS` using the [current model list](https://ai.google.dev/gemini-api/docs/models). |
| `503 UNAVAILABLE` from Gemini | The model is overloaded. The Lambda falls back to other models automatically; try again later if all of them are busy. |

## Security notes

- **Never commit** `terraform.tfvars`, `.env` or any `*.tfstate*` file. The Terraform state stores the Gemini key in plaintext. `.gitignore` already excludes these.
- The API Function URL is **public with no authentication**, and so is the S3 CORS policy (`*`). This is fine for a demo or coursework, but anyone who finds the URL can trigger analyses that use your Gemini quota. For anything beyond a demo, add authentication (for example, API Gateway with a Cognito authorizer), restrict CORS to your own domain, and store the API key in AWS Secrets Manager or SSM Parameter Store instead of an environment variable.
- Uploaded resumes contain personal data. Add an S3 lifecycle rule to delete files from `uploads/` after a short time if you deploy this for real use.

## Cleanup

Remove all AWS resources (the bucket is created with `force_destroy`, so uploads are deleted too):

```bash
cd terraform
terraform destroy
```
