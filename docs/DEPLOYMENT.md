# Deployment Guide

This guide covers deploying Kavach to production environments.

## Prerequisites

- Python 3.11+
- PostgreSQL (optional, for persistent review logs)
- Redis (optional, for caching)
- Reverse proxy (nginx or similar)
- SSL certificate

## Environment Setup

### 1. Clone Repository

```bash
git clone https://github.com/AstroSaran/hackspire-2026-dinos.git
cd hackspire-2026-dinos
```

### 2. Create Production Environment File

```bash
cd backend
cp .env.example .env
```

Edit `.env` with production values:

```bash
# Weather Provider Configuration
WEATHER_PROVIDER=imd                    # imd | open_meteo | demo
WEATHER_ENABLE_FALLBACK=true
WEATHER_DEMO_FALLBACK=false             # NEVER true in production
WEATHER_CACHE_TTL_CURRENT_S=600
WEATHER_CACHE_TTL_FORECAST_S=3600
WEATHER_STALE_AFTER_S=1800

# IMD Configuration (requires whitelisting)
IMD_API_KEY=your_imd_api_key_if_required
IMD_BASE_URL=https://mausam.imd.gov.in/api

# Application
API_HOST=0.0.0.0
API_PORT=8000
WORKERS=4
LOG_LEVEL=info

# Security
API_KEY=generate_secure_random_key_here
ALLOWED_ORIGINS=https://yourdomain.com,https://dashboard.yourdomain.com
```

### 3. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# OR
.\venv\Scripts\Activate.ps1  # Windows

pip install -r requirements.txt
pip install gunicorn  # Production ASGI server
```

### 4. Generate Data & Train Model

```bash
python data/generate_dataset.py
python train_model.py
python export_snapshot.py
```

## Deployment Options

### Option 1: Traditional Server (Ubuntu/Debian)

#### Install System Dependencies

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv nginx certbot python3-certbot-nginx
```

#### Create Systemd Service

Create `/etc/systemd/system/kavach.service`:

```ini
[Unit]
Description=Kavach API Server
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/kavach/backend
Environment="PATH=/opt/kavach/backend/venv/bin"
ExecStart=/opt/kavach/backend/venv/bin/gunicorn app.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --access-logfile /var/log/kavach/access.log \
    --error-logfile /var/log/kavach/error.log

[Install]
WantedBy=multi-user.target
```

#### Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable kavach
sudo systemctl start kavach
sudo systemctl status kavach
```

#### Configure Nginx

Create `/etc/nginx/sites-available/kavach`:

```nginx
upstream kavach_backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    # API endpoints
    location /api/ {
        proxy_pass http://kavach_backend/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # CORS headers
        add_header Access-Control-Allow-Origin "https://yourdomain.com" always;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Content-Type, Authorization" always;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;
    limit_req zone=api_limit burst=20 nodelay;
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/kavach /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Setup SSL

```bash
sudo certbot --nginx -d api.yourdomain.com
```

---

### Option 2: Docker Deployment

#### Create Dockerfile

`backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application
COPY . .

# Generate data and train model
RUN python data/generate_dataset.py && \
    python train_model.py && \
    python export_snapshot.py

EXPOSE 8000

CMD ["gunicorn", "app.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000"]
```

#### Create docker-compose.yml

```yaml
version: '3.8'

services:
  kavach-api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - WEATHER_PROVIDER=imd
      - WEATHER_ENABLE_FALLBACK=true
      - WEATHER_DEMO_FALLBACK=false
    volumes:
      - ./backend/.env:/app/.env:ro
      - logs:/var/log/kavach
    restart: unless-stopped
    networks:
      - kavach-net

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - kavach-api
    restart: unless-stopped
    networks:
      - kavach-net

volumes:
  logs:

networks:
  kavach-net:
    driver: bridge
```

#### Deploy

```bash
docker-compose up -d
docker-compose logs -f kavach-api
```

---

### Option 3: Cloud Platforms

#### AWS Elastic Beanstalk

```bash
eb init -p python-3.11 kavach-api
eb create kavach-prod
eb deploy
```

#### Google Cloud Run

```bash
gcloud run deploy kavach-api \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated
```

#### Heroku

```bash
heroku create kavach-api
git push heroku main
```

---

## Production Checklist

### Security

- [ ] Set strong `API_KEY` in `.env`
- [ ] Configure `ALLOWED_ORIGINS` to specific domains
- [ ] Enable HTTPS/SSL
- [ ] Set up firewall rules
- [ ] Disable debug mode
- [ ] Remove `.env.example` and sensitive files
- [ ] Set `WEATHER_DEMO_FALLBACK=false`

### Performance

- [ ] Configure caching (Redis recommended)
- [ ] Set appropriate worker count (2-4 per CPU core)
- [ ] Enable gzip compression in nginx
- [ ] Set up CDN for static files (frontend)
- [ ] Configure database connection pooling

### Monitoring

- [ ] Set up application logging
- [ ] Configure error tracking (Sentry, Rollbar)
- [ ] Set up uptime monitoring
- [ ] Configure alerts for API failures
- [ ] Monitor weather provider health (`/data-health`)

### Data

- [ ] Configure automated backups for review logs
- [ ] Set up model retraining pipeline (when real data available)
- [ ] Archive historical snapshots
- [ ] Document data retention policy

### IMD Integration

For live IMD data:

1. Apply for IMD API access through proper channels
2. Complete IP whitelisting process with IMD nodal officer
3. Obtain actual IMD station/district IDs for West Bengal
4. Update `geography.py` with real IMD IDs
5. Test connection with IMD endpoints
6. Monitor via `/data-health` endpoint

### Testing

```bash
# Run full test suite
pytest tests/ -v

# Test specific endpoints
curl https://api.yourdomain.com/villages
curl https://api.yourdomain.com/data-health
```

### Scaling

For high traffic:

1. **Horizontal Scaling**: Deploy multiple API instances behind load balancer
2. **Database**: Move review logs to PostgreSQL
3. **Caching**: Use Redis for weather/village data
4. **CDN**: Serve frontend via CDN
5. **Async Workers**: Use Celery for background tasks

---

## Maintenance

### Update Application

```bash
cd /opt/kavach
git pull origin main
source backend/venv/bin/activate
pip install -r backend/requirements.txt
sudo systemctl restart kavach
```

### View Logs

```bash
sudo journalctl -u kavach -f
tail -f /var/log/kavach/error.log
```

### Backup

```bash
# Backup review logs
cp backend/review_log.jsonl backup/review_log_$(date +%Y%m%d).jsonl

# Backup model artifacts
tar -czf backup/model_$(date +%Y%m%d).tar.gz backend/model_artifacts/
```

---

## Troubleshooting

### API Not Starting

```bash
# Check logs
sudo journalctl -u kavach -n 50

# Check port
sudo netstat -tlnp | grep 8000

# Test manually
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

### Weather Provider Failures

Check `/data-health` endpoint and review:
- Network connectivity to IMD/Open-Meteo
- IP whitelisting status (for IMD)
- API credentials in `.env`
- Provider cache TTL settings

### High Memory Usage

- Reduce worker count
- Enable swap
- Optimize model loading (load once, share across workers)

---

## Support

For deployment issues, open an issue on GitHub: https://github.com/AstroSaran/hackspire-2026-dinos/issues
