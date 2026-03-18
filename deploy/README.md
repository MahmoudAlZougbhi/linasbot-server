# Deployment

## Nginx config for linasaibot.com

The host nginx must proxy `/api/*` and `/webhook` to the backend (port 8003) for login, API calls, and WhatsApp webhooks (MontyMobile) to work.

### Option A: Full config (fresh install)

Use `nginx-linasaibot.conf` as your site config:

```bash
sudo cp deploy/nginx-linasaibot.conf /etc/nginx/sites-available/linasaibot
sudo ln -sf /etc/nginx/sites-available/linasaibot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### Option B: Add to existing config (you already have SSL/custom config)

Add the contents of `nginx-api-include.conf` inside your existing `server { ... }` block for linasaibot.com, **before** the `location /` block.

Or include the snippet:

```nginx
server {
    server_name linasaibot.com www.linasaibot.com;
    # ... your existing config ...
    
    include /etc/nginx/snippets/linasbot-api.conf;
    
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Copy the snippet:

```bash
sudo mkdir -p /etc/nginx/snippets
sudo cp deploy/nginx-api-include.conf /etc/nginx/snippets/linasbot-api.conf
# Then add the include line to your server block
```
