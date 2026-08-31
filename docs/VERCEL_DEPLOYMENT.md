# 🌐 VayuSutra APIx — Vercel Serverless Deployment Guide
### Fast, Zero-Config Serverless Deployment for FastAPI & Bento Command Center
*Smart India Hackathon 2026 (Problem Statement SIH26056)*  
*Target Beneficiaries:* **MoSPI / NSO**, **RBI Monetary Policy Committee**, **DGCA**

---

## 📋 1. Required Files Checklist for Vercel

The following files are configured and ready in the repository for Vercel:

| File Path | Purpose in Vercel | Status |
| :--- | :--- | :--- |
| `vercel.json` | Vercel Serverless build matrix, routing rules (`@vercel/python`), and environment tags. | ✅ Ready |
| `api/index.py` | Primary Serverless Function entrypoint exporting the ASGI FastAPI `app`. | ✅ Ready |
| `.vercelignore` | Excludes test suites, Docker manifests, and caches to keep bundle under 50MB. | ✅ Ready |
| `requirements.txt` | Python packages automatically installed by Vercel's build container. | ✅ Ready |
| `vayusutra_apix/static/dashboard.html` | Self-contained, zero-CDN interactive command center. | ✅ Ready |

---

## ⚡ 2. Method 1: Deploy via Vercel Dashboard (1-Click GitHub Flow)

### Step 1: Push Repository to GitHub
Ensure all code and the `api/index.py` and `vercel.json` files are pushed to your GitHub repository:
```bash
git add .
git commit -m "feat: add Vercel serverless deployment configuration"
git push origin main
```

### Step 2: Import into Vercel
1. Log in to your [Vercel Dashboard](https://vercel.com).
2. Click **"Add New..."** &rarr; **"Project"**.
3. Select your GitHub repository (`vayusutra-apix`).
4. In **Project Configuration**:
   - **Framework Preset**: Select `Other` (or leave default).
   - **Root Directory**: `./` (Root directory).
   - **Build Command**: *(Leave empty)*.
   - **Output Directory**: *(Leave empty)*.

### Step 3: Add Environment Variables in Vercel
In the **Environment Variables** section of the Vercel project setup, add:

| Key | Recommended Value | Explanation |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `production` | Enables production mode |
| `PYTHONPATH` | `.` | Ensures Python imports resolve across root package |
| `AUTH_SECRET_KEY` | `VAYUSUTRA-APIX-SECRET-KEY-SIH26056-MOSPI-RBI-DGCA-2026` | Token signing key |
| `TOKEN_EXPIRY_SECONDS` | `604800` | 7-day token expiration |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |

### Step 4: Click "Deploy"
Vercel will automatically build the Python serverless environment and deploy the application in ~45 seconds.

---

## 💻 3. Method 2: Deploy via Vercel CLI (From Terminal)

If you prefer deploying directly from your local terminal:

### Step 1: Install Vercel CLI
```bash
npm install -g vercel
```

### Step 2: Authenticate Vercel CLI
```bash
vercel login
```

### Step 3: Deploy Preview Environment
```bash
# In the root folder of vayusutra_apix
vercel
```
Follow the interactive CLI prompts:
- *Set up and deploy?* &rarr; **`Y`**
- *Which scope?* &rarr; Select your account.
- *Link to existing project?* &rarr; **`N`**
- *What's your project's name?* &rarr; **`vayusutra-apix`**
- *In which directory is your code located?* &rarr; **`./`**

### Step 4: Deploy to Production
```bash
vercel --prod
```

You will receive an instant production URL (e.g. `https://vayusutra-apix.vercel.app`).

---

## ⚙️ 4. How Vercel Serverless Architecture Works with VayuSutra

```
[ Incoming Browser / API Request ]
                │
                ▼
      ┌──────────────────┐
      │  Vercel Edge CDN │
      └─────────┬────────┘
                │  (Rewrites: /(.*) ──► api/index.py)
                ▼
      ┌──────────────────────────────────────────────┐
      │  Vercel Python Serverless Function (Lambda)  │
      │  • Runtime: Python 3.11 / 3.12               │
      │  • Memory: 1024 MB                           │
      │  • Max Duration: 60s                         │
      │  • Handler: api/index.py ──► FastAPI (app)   │
      └──────────────────────┬───────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   [ Static HTML Dashboard ]        [ In-Memory / /tmp SQLite ]
   (Zero CDN, 100% Offline)         (Auto-copied to /tmp WAL)
```

### Database Persistence on Serverless
In Vercel Serverless Functions:
- The `/app` directory is read-only.
- VayuSutra APIx's `DatabaseManager` automatically detects the Vercel serverless environment (`os.getenv("VERCEL")`) and copies the pre-seeded `vayusutra_airfare.db` database into `/tmp/vayusutra_airfare.db`, where write operations and token sessions execute without restriction.
- For multi-instance shared state across high-traffic enterprise scaling, you can optionally set `DATABASE_PATH` to a remote SQLite/Postgres cloud service (e.g. Turso libSQL or Neon Serverless Postgres).

---

## 🌐 5. Adding a Custom Domain on Vercel

1. In your Vercel Project Dashboard, navigate to **Settings** &rarr; **Domains**.
2. Enter your custom domain (e.g., `vayusutra.gov.in` or `vayusutra.yourdomain.com`).
3. Add the DNS records provided by Vercel:
   - **Type**: `CNAME`
   - **Name**: `vayusutra`
   - **Value**: `cname.vercel-dns.com`
4. Vercel will automatically provision and renew an **SSL/TLS Certificate** via Let's Encrypt.

---

## ✅ 6. Post-Deployment Verification Checklist

Once deployed, run these quick sanity checks against your Vercel deployment URL:

```bash
export VERCEL_URL="https://your-project.vercel.app"

# 1. Verify Health Endpoint
curl -f "$VERCEL_URL/api/v1/health"

# 2. Verify 1-Click Demo Credentials
curl -f "$VERCEL_URL/api/v1/auth/demo-users"

# 3. Verify Realtime Index
curl -f "$VERCEL_URL/api/v1/index/realtime"

# 4. Verify AI Policy Analyst
curl -X POST "$VERCEL_URL/api/v1/ai/analyst" \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain CPI transmission from airfares."}'

# 5. Open Web Dashboard in Browser
open "$VERCEL_URL"
```

---

## ❓ 7. Troubleshooting & Common Questions

### Q: Why is my build failing on Vercel with `@vercel/python`?
**A**: Ensure `requirements.txt` is in the root directory and does not contain OS-specific binary packages. VayuSutra's `requirements.txt` is verified for clean serverless installation.

### Q: Does the web dashboard work without external CDNs on Vercel?
**A**: Yes! The Bento Command Center (`vayusutra_apix/static/dashboard.html`) is 100% self-contained using vanilla HTML5 Canvas, embedded SVGs, and system fonts. It works offline and within iframe sandboxes.

### Q: How do WebSocket live feeds work on Vercel?
**A**: Vercel Serverless Functions timeout after 60s. For environments where long-lived WebSockets are restricted by serverless runtimes, VayuSutra provides automatic fallback to **Server-Sent Events (`GET /api/v1/stream/events`)** and polling.
