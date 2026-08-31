# VayuSutra APIx: Enterprise Production Deployment Guide
### National Airfare Intelligence & Inflation Decision Platform (SIH26056)
*Commissioned for:* **Ministry of Statistics and Programme Implementation (MoSPI / NSO)**, **Reserve Bank of India (RBI) Monetary Policy Committee**, and **Directorate General of Civil Aviation (DGCA)**

---

## 🚀 1. Deployment Topology & Methods Overview

VayuSutra APIx supports four primary deployment methods:

| Method | Target Environment | Scale & High Availability | Setup Time |
| :--- | :--- | :--- | :--- |
| 🐳 **Docker Compose** | Single Node VPS / Dedicated Server (AWS EC2, DigitalOcean, Hetzner) | Multi-worker + Nginx Gateway + Persistent Volumes | **2 Minutes** |
| ☸️ **Kubernetes (K8s)** | Enterprise Cloud Clusters (AWS EKS, GCP GKE, Azure AKS, GovCloud) | HPA Autoscaling (2–10 Pods), Ingress TLS, Zero-Downtime Rolling Updates | **5 Minutes** |
| ⚡ **Bare-Metal / Systemd** | Ubuntu / Debian / RHEL Government Datacenter Servers | Systemd daemon service + Uvicorn/Gunicorn workers | **3 Minutes** |
| ☁️ **Serverless / PaaS** | Render, Railway, Fly.io, Google Cloud Run | Containerized stateless execution with volume mount | **1-Click** |

---

## 🐳 2. Quickstart with Docker Compose (Recommended)

### Prerequisites
- Docker Engine 24.0+
- Docker Compose v2.20+

### Step 1: Clone and Configure Environment
```bash
git clone https://github.com/vayusutra/vayusutra-apix.git
cd vayusutra-apix

# Create production environment file from template
cp .env.example .env
```

### Step 2: Launch Multi-Container Production Stack
```bash
docker-compose up -d --build
```

### Step 3: Verify Deployment
```bash
# Check container status
docker-compose ps

# Probe system health
curl -f http://localhost:80/api/v1/health
```

The stack provisions:
- **`vayusutra_apix_app`**: FastAPI production application running on internal port `8000`.
- **`vayusutra_apix_gateway`**: High-performance Nginx reverse proxy with rate-limiting, security headers, and WebSocket support on ports `80` & `443`.
- **`apix_data`**: Persistent volume mounting `/app/vayusutra_apix/data` for SQLite WAL database retention.

---

## ☸️ 3. Kubernetes (K8s) Cluster Deployment

All production Kubernetes manifests are pre-configured in `deploy/k8s/`:

```bash
# 1. Create dedicated namespace
kubectl apply -f deploy/k8s/namespace.yaml

# 2. Apply ConfigMap and Secrets
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secret.yaml

# 3. Provision Persistent Storage (PVC)
kubectl apply -f deploy/k8s/secret.yaml

# 4. Deploy Application Workloads & Services
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml

# 5. Apply Ingress with Automatic TLS
kubectl apply -f deploy/k8s/ingress.yaml

# 6. Apply Horizontal Pod Autoscaler (HPA)
kubectl apply -f deploy/k8s/hpa.yaml
```

### Checking Cluster Rollout
```bash
kubectl get pods -n vayusutra-system -w
kubectl get hpa -n vayusutra-system
```

---

## ⚡ 4. Bare-Metal & Systemd Service Deployment

For deployment directly on Ubuntu/Debian/RHEL servers:

### Step 1: Install Dependencies & Setup User
```bash
sudo useradd -r -s /bin/false -d /opt/vayusutra_apix mospi
sudo mkdir -p /opt/vayusutra_apix
sudo cp -r . /opt/vayusutra_apix/
cd /opt/vayusutra_apix

python3 -m pip install -r requirements.txt
sudo chown -R mospi:mospi /opt/vayusutra_apix
```

### Step 2: Install Systemd Service
```bash
sudo cp deploy/systemd/vayusutra-apix.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vayusutra-apix
sudo systemctl start vayusutra-apix
```

### Step 3: Monitor Service Logs
```bash
sudo journalctl -u vayusutra-apix -f
```

---

## ☁️ 5. Cloud Platform 1-Click Recipes

### A. Google Cloud Run
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/vayusutra-apix:2.0.0
gcloud run deploy vayusutra-apix \
  --image gcr.io/YOUR_PROJECT_ID/vayusutra-apix:2.0.0 \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --port 8000 \
  --memory 2Gi \
  --cpu 2
```

### B. AWS Elastic Container Service (ECS Fargate)
1. Push image to Amazon Elastic Container Registry (ECR).
2. Create Task Definition with 2 vCPUs, 4GB RAM, and mount Amazon EFS for `/app/vayusutra_apix/data`.
3. Attach Application Load Balancer (ALB) pointing to container port `8000`.

### C. Render / Railway / Fly.io
1. Connect GitHub repository.
2. Select **Docker** environment.
3. Add persistent volume mounted at `/app/vayusutra_apix/data`.
4. Set environment variable `PORT=8000`.

---

## 🔒 6. Security Hardening & Secret Rotation

1. **Authentication Secret**:
   Generate a 64-character high-entropy secret for token signing:
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```
   Set as `AUTH_SECRET_KEY` in `.env` or Kubernetes secret.
2. **Database Permissions**:
   Ensure SQLite database directory permissions are restricted to the runtime user:
   ```bash
   chmod 700 /app/vayusutra_apix/data
   chmod 600 /app/vayusutra_apix/data/vayusutra_airfare.db*
   ```
3. **CORS Configuration**:
   In production, restrict `CORS_ORIGINS` from `*` to the official domain, e.g. `https://vayusutra.mospi.gov.in`.

---

## 📊 7. Observability, Prometheus & Health Checks

- **Health Endpoint**: `GET /api/v1/health` (Returns JSON subsystem status and quote telemetry).
- **OpenMetrics / Prometheus Endpoint**: `GET /metrics` (Exposes scraper request rates, calculation latency, and CPI transmission metrics).
- **WebSocket Feed**: `WS /ws/live-feed` (Real-time live streaming of price ticks and alerts).

---

## 🛠️ 8. Backup, WAL Checkpointing & Disaster Recovery

### Manual SQLite WAL Checkpoint & Backup
```bash
# Checkpoint WAL logs into primary database file
sqlite3 /app/vayusutra_apix/data/vayusutra_airfare.db "PRAGMA wal_checkpoint(FULL);"

# Perform safe live backup
sqlite3 /app/vayusutra_apix/data/vayusutra_airfare.db ".backup /backups/vayusutra_airfare_backup_$(date +%Y%m%d).db"
```
