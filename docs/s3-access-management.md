# S3 Member Onboarding

This guide explains how a project member configures local AWS access for the
shared S3 source store. It does not contain real access keys, passwords, bucket
administration steps, or admin-only cleanup instructions.

## What You Need From The Admin

Ask the project admin for:

- Your personal AWS access key ID.
- Your personal AWS secret access key.
- Your IAM username and temporary Console password if Console access is enabled.
- The shared S3 bucket name.
- The shared S3 prefix.
- The AWS region.
- The Qdrant URL, API key, and collection name if cloud retrieval is enabled.

Do not paste credentials into the repository, `.env.example`, shared chat,
screenshots, or documentation.

## Profile Naming

Each member should use a local AWS profile name like:

```text
rag-s3-<member>
```

Example:

```text
rag-s3-natus
```

`AWS_PROFILE` is only a local alias. The access key stored inside that profile
determines the actual IAM user AWS sees.

## Optional AWS Console Access

Use AWS Console only if the admin has enabled Console login for your IAM user.
Console login uses your IAM username and Console password. It does not use the
access key configured in `AWS_PROFILE`.

Sign in at:

```text
https://271030593001.signin.aws.amazon.com/console
```

Use the IAM username provided by the admin, for example:

```text
rag-s3-<member>-user
```

If the admin gives you a temporary Console password, change it at first sign-in.
Enable or complete MFA setup if prompted.

Do not paste Console passwords, MFA recovery codes, or screenshots containing
account details into the repository, shared chat, or documentation.

## 1. Configure Your Local AWS Profile

Run:

```bash
aws configure --profile rag-s3-<member>
```

Enter the values provided privately by the admin:

```text
AWS Access Key ID: <your-access-key-id>
AWS Secret Access Key: <your-secret-access-key>
Default region name: ap-southeast-1
Default output format: json
```

This stores credentials locally in `~/.aws/credentials`. Treat that machine as
trusted.

## 2. Verify Your IAM Identity

Run:

```bash
aws sts get-caller-identity --profile rag-s3-<member>
```

Expected ARN shape:

```text
arn:aws:iam::<account-id>:user/rag-s3-<member>-user
```

If the ARN shows another IAM user, the profile was configured with the wrong
access key.

## 3. Verify S3 Access

Run:

```bash
aws s3 ls s3://<bucket-name>/<prefix>/ --profile rag-s3-<member>
```

Example:

```bash
aws s3 ls s3://my-rag-bucket/agentic-rag/sources/ --profile rag-s3-natus
```

Expected result:

- Success with an object listing, or an empty listing if the prefix has no
  objects.
- `AccessDenied` means the IAM permission, bucket policy, or prefix is wrong.
- `Unable to locate credentials` means the profile was not configured locally.

## 4. Configure The App `.env`

Each member uses the same bucket settings but their own local profile:

```env
EVIDENCE_PROVIDER=local_pdf
LOCAL_SOURCE_STORE=s3
AWS_DEFAULT_REGION=ap-southeast-1
AWS_S3_BUCKET=<bucket-name>
AWS_S3_PREFIX=agentic-rag/sources
AWS_PROFILE=rag-s3-<member>

VECTOR_STORE_PROVIDER=qdrant
VECTOR_STORE_URL=<qdrant-url>
VECTOR_STORE_API_KEY=<qdrant-api-key>
VECTOR_STORE_COLLECTION=agentic_rag_chunks
```

Do not add these variables to `.env`:

```env
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

## 5. Smoke Test The App

Start the backend:

```bash
uv run uvicorn agentic_rag.api:api --reload
```

Check health:

```bash
curl http://127.0.0.1:8000/health
```

Expected S3-related fields:

```json
{
  "source_store": "s3",
  "s3_bucket_configured": "true",
  "s3_prefix": "agentic-rag/sources"
}
```

Then upload one small document through the app or API and confirm it appears in
the source list. In S3 mode, normal delete controls are disabled for shared
storage safety.

## Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `Unable to locate credentials` | `AWS_PROFILE` does not exist locally | Run `aws configure --profile rag-s3-<member>` |
| `AccessDenied` on `aws s3 ls` | IAM user is missing S3 access or the prefix is wrong | Ask the admin to check group membership and policy |
| `sts get-caller-identity` shows the wrong user | Profile has the wrong access key | Reconfigure the profile with your own key |
| App health shows `s3_bucket_configured=false` | Missing `AWS_S3_BUCKET` | Set the bucket in `.env` |
| App can upload but search fails | Qdrant configuration is missing or wrong | Check `VECTOR_STORE_PROVIDER`, `VECTOR_STORE_URL`, `VECTOR_STORE_API_KEY`, and collection name |
| Delete fails in S3 mode | Expected safety behavior | Ask the admin to perform cleanup outside the normal app |

## Security Rules

- Do not commit access keys, secrets, `.env`, or screenshots containing secrets.
- Do not use another member's AWS profile or access key.
- Store access keys only in your local AWS CLI credentials file or an approved
  password manager.
- Tell the admin immediately if a key is exposed or a machine with credentials
  is lost.

## References

- [Manage access keys for IAM users](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html)
- [AWS CLI configuration and named profiles](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
