# Gmail API Setup — Drafter & Follow Upper

One-time setup to connect the platform to your Gmail (gavin@ignitethelabel.com).

## Step 1: Enable Gmail API

1. Go to: https://console.cloud.google.com/apis/library/gmail.googleapis.com
2. Make sure project is `crypto-shore-499107-n4`
3. Click **ENABLE**

## Step 2: Create OAuth Credentials

1. Go to: https://console.cloud.google.com/apis/credentials
2. Click **+ CREATE CREDENTIALS** → **OAuth client ID**
3. If prompted for consent screen:
   - User type: **Internal** (since you're on Workspace)
   - App name: `IGNITE Virtual Scout`
   - Support email: `gavin@ignitethelabel.com`
   - Scopes: add `https://www.googleapis.com/auth/gmail.compose`
   - Save
4. Back to Create OAuth client:
   - Application type: **Desktop app**
   - Name: `IGNITE Scout`
   - Click **CREATE**
5. Click **DOWNLOAD JSON**
6. Rename the downloaded file to `credentials.json`

## Step 3: Place the file

Move `credentials.json` to your catalogs folder:

```bash
mv ~/Downloads/credentials.json ~/Documents/catalogs/credentials.json
```

## Step 4: Authorize (first time only)

Start the platform:
```bash
cd ~/Documents/catalogs
python3 run.py
```

Then go to **Drafter** tool and click **RUN**. A browser window opens asking you to authorize Gmail access. Sign in with `gavin@ignitethelabel.com` and allow.

After this, a `data/gmail_token.json` is saved and you won't be asked again.

## What it does

- **Drafter**: Creates one Gmail DRAFT per artist (never sends automatically)
- **Follow Upper**: Creates reply DRAFTS on labeled threads (never sends)
- Both tools only create drafts — you review and send manually from Gmail

## Security

- `credentials.json` = your app identity (keep private, don't commit to git)
- `data/gmail_token.json` = your authorized session (auto-refreshes)
- Scope is `gmail.compose` only (create drafts) — cannot read emails or send
- Revoke anytime: https://myaccount.google.com/permissions
