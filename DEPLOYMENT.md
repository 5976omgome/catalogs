# IGNITE Virtual Scout — Cloud Deployment Plan

## Recommended Stack (All Google)

| Service | Purpose | Cost |
|---------|---------|------|
| **Google Cloud Run** | Host the Flask app (serverless, auto-scale) | Free tier: 2M requests/month |
| **Cloud SQL (SQLite mode)** or **Firestore** | Persistent database | $0 for small usage |
| **Google Drive API** | Backup/sync artist data to your Workspace Drive | Free (unlimited storage with Workspace) |
| **Google Identity Platform** | Optional — OAuth login via Google account | Free tier |
| **Artifact Registry** | Store Docker images | Free tier: 500MB |

## Deployment Steps

### 1. Setup Google Cloud Project

```bash
# Install gcloud CLI: https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud projects create ignite-virtual-scout
gcloud config set project ignite-virtual-scout
gcloud services enable run.googleapis.com artifactregistry.googleapis.com drive.googleapis.com
```

### 2. Create Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN cd frontend && npm install && npm run build
ENV PORT=8080
CMD ["python", "run.py"]
```

### 3. Deploy to Cloud Run

```bash
gcloud run deploy ignite-scout \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SECRET_KEY=your-production-secret
```

### 4. Google Drive Sync (for artist data backup)

1. Create a Service Account in GCP Console
2. Share a Drive folder with the service account email
3. Add `GOOGLE_DRIVE_FOLDER_ID` env var to Cloud Run
4. The app will auto-backup the SQLite DB daily to Drive

### 5. Custom Domain

```bash
gcloud run domain-mappings create --service ignite-scout --domain scout.ignitethelabel.com
```

## Two-Factor Authentication (Already Implemented)

- Uses PyOTP + Google Authenticator
- Setup: Settings page → Enable 2FA → Scan QR → Enter code
- Login: email + password + 6-digit code from Authenticator app
- Can be disabled per-user

## Security

- Passwords: bcrypt with salt (cost factor 12)
- Sessions: HTTP-only secure cookies, 30-day expiry
- 2FA: TOTP (RFC 6238), 30-second codes, 1-window tolerance
- HTTPS: enforced by Cloud Run (free TLS cert)
- CORS: same-origin only
- Rate limiting: add via Cloud Armor or nginx (TODO)

## Google Drive Integration (TODO — requires GCP setup)

Once deployed, the platform can:
1. Auto-export artist library to a Google Sheet in your Drive (daily)
2. Backup the SQLite database to Drive as a .db file
3. Sync import files from a designated Drive folder

Requires: `google-api-python-client`, `google-auth` packages + service account credentials.

## Quick Local Run (current)

```bash
cd ~/Desktop/catalogs
pip install -r requirements.txt
rm -f data/ignite.db
python3 run.py
```
