# S3 Member Onboarding

This guide explains how a project member configures local AWS access for the
shared S3 source store. It does not contain real access keys, passwords, bucket
administration steps, or admin-only cleanup instructions.

> Scope: this document covers **AWS S3 + Qdrant access only**. The application
> also needs LLM, embedding, rerank, and (optionally) RAGFlow credentials to run
> — see "Application Secrets Beyond AWS" near the end before running the app.

## Prerequisites

Install these before starting:

- **AWS CLI v2** — see "Installing the AWS CLI v2" below.
- **Python 3.12+** — the project sets `requires-python = ">=3.12"`.
- **uv** — used to run the backend (`uv run ...`).

### Installing the AWS CLI v2

First check whether it is already installed and is **version 2.x**:

```bash
aws --version
```

If the command is not found (or shows a 1.x version), install v2 using the steps
for your operating system. These are the official AWS installers; for the latest
details see
<https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html>.

**macOS**

Homebrew (simplest):

```bash
brew install awscli
```

Or the official package installer:

```bash
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /
```

**Linux (x86_64 / Intel/AMD)**

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

**Linux (ARM / aarch64)**

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

> If `unzip` is missing, install it first (`sudo apt install unzip` on
> Debian/Ubuntu, `sudo dnf install unzip` on Fedora/RHEL). To upgrade an
> existing v2 install, append `--update`: `sudo ./aws/install --update`.

**Windows**

PowerShell or Command Prompt (downloads and runs the MSI):

```powershell
msiexec.exe /i https://awscli.amazonaws.com/AWSCLIV2.msi
```

Or download and double-click the installer:
<https://awscli.amazonaws.com/AWSCLIV2.msi>

**Verify the install** (re-open the terminal first so `PATH` updates):

```bash
aws --version
```

You should see output beginning with `aws-cli/2.` — then continue to
"Configure Your Local AWS Profile" below.

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
rag-s3-<member>
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
Default region name: ap-southeast-2
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
arn:aws:iam::<account-id>:user/<your-iam-username>
```

`<your-iam-username>` is the IAM user the admin created for you. It is assigned
by the admin and **may differ from your local profile alias** (`AWS_PROFILE`).
For example, the local profile `rag-s3-natus` may map to an IAM user named
`agentic-rag-local`. Confirm the expected username with the admin.

The command should succeed and return a user ARN. If it returns
`InvalidClientTokenId`, the profile holds a key that was deleted or rotated —
reconfigure it with your current key. If it returns a *different* username than
the admin told you to expect, the profile was configured with the wrong key.

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
AWS_DEFAULT_REGION=ap-southeast-2
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
| `InvalidClientTokenId` on any command | Profile holds a deleted or rotated access key | Ask the admin for your current key and reconfigure the profile |
| `AccessDenied` on `aws s3 ls` | IAM user is missing S3 access or the prefix is wrong | Ask the admin to check group membership and policy |
| `sts get-caller-identity` shows the wrong user | Profile has the wrong access key | Reconfigure the profile with your own key |
| App health shows `s3_bucket_configured=false` | Missing `AWS_S3_BUCKET` | Set the bucket in `.env` |
| App can upload but search fails | Qdrant configuration is missing or wrong | Check `VECTOR_STORE_PROVIDER`, `VECTOR_STORE_URL`, `VECTOR_STORE_API_KEY`, and collection name |
| Delete fails in S3 mode | Expected safety behavior | Ask the admin to perform cleanup outside the normal app |

## Application Secrets Beyond AWS

S3 + Qdrant access is not enough to run the full app. The application also needs
the following, supplied privately by the admin and placed in your local `.env`
(see `.env.example` for the complete list):

- LLM credentials: `LLM_PROVIDER`, `LLM_API_BASE`, `LLM_API_KEY`, and the
  per-stage keys (`QUERY_REWRITE_LLM_API_KEY`, `QUERY_TRANSFORM_LLM_API_KEY`,
  `GENERATION_LLM_API_KEY`, `INGESTION_LLM_API_KEY`, `EVALUATION_LLM_API_KEY`).
- Embedding credentials: `EMBEDDING_PROVIDER`, `EMBEDDING_API_BASE`,
  `EMBEDDING_API_KEY`.
- Rerank credentials: `RERANK_API_KEY` (only if using a hosted reranker; the
  default `sentence-transformers` reranker runs locally and needs no key).
- RAGFlow credentials (optional): `RAGFLOW_BASE_URL`, `RAGFLOW_API_KEY`,
  `RAGFLOW_DATASET_ID`.

Unlike AWS access keys, these belong in `.env` (which is git-ignored). Never
commit them.

## For Admins: Provisioning A Member

When creating and delivering a member's key:

1. Create the IAM user / access key (AWS Console or CLI). The secret access key
   is shown **once** — capture it immediately.
2. Deliver the access key ID and secret to the member over a **secure channel**:
   a password manager secure-share or a one-time self-destructing secret link.
   **Never** send keys over email, Slack, chat, or screenshots.
3. **Delete the downloaded `*_accessKeys.csv` immediately after delivery.** Do
   not leave it in `~/Downloads` or any unencrypted location.
4. Tell the member their IAM username and the bucket/prefix/region values.
5. To rotate a member's key: create the new key, deliver it, confirm the member
   has switched, then deactivate and delete the old key.

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
