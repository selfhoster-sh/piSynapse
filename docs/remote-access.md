# Remote access & voice input

Two things break over plain HTTP, and both have the same fix (HTTPS):

1. **API key exposure** — every request carries `X-API-Key` in plaintext.
2. **Voice input** — browsers only give microphone access in a [secure context](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts)
   (`https://` or `http://localhost`). Over `http://<lan-ip>:8765` the mic
   button explains itself (`Microphone requires HTTPS. Use HTTPS or
   localhost.`) and stays off. The native phone app is unaffected (its
   WebView origin is a secure context).

## Multi-user access

Every person (and ideally every device) gets their **own API key**: register
once per device at `POST /users/register` (or via the login screen), and
never share keys. Per-user rate limits, memories, sessions, settings and
summaries all key off it — a shared key merges everyone's data and quota.
Admins manage users at `GET /users`; close open registration
(`REGISTRATION_OPEN=off`) once the household is onboarded.

## Tier 1 — Same Wi-Fi, plain HTTP (easiest, limited)

Open `http://<your-pi-ip>:8765`. Fine on a trusted home LAN for chat.
Browser microphone will NOT work here; use the phone app or move up a tier
for voice. Never expose this port to the internet as-is.

## Tier 2 — Tailscale (recommended for most)

Install Tailscale on the Pi and your devices, then open
`https://<pi-name>.<tailnet>.ts.net:8765`. You get TLS automatically
(including microphone access) with no ports, domains, or certificates to
manage. Two settings to check:

- Bind: keep the default (`0.0.0.0:8765`) or bind the tailnet IP.
- `TRUSTED_HOSTS`: add the tailnet hostname (e.g.
  `TRUSTED_HOSTS=<pi-name>.<tailnet>.ts.net`), otherwise requests are
  rejected with 403 — Host-header checking does not know about your VPN.

## Tier 3 — Own domain + reverse proxy (power users)

Terminate TLS on a reverse proxy (nginx/Caddy on a VPS or on the Pi) and
forward to the Pi over a WireGuard tunnel (e.g. AmneziaWG):

```nginx
server {
    listen 443 ssl;
    server_name pi.example.com;
    ssl_certificate     /etc/letsencrypt/live/pi.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pi.example.com/privkey.pem;
    location / {
        proxy_pass http://<pi-wireguard-ip>:8765;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";  # SSE streaming
        proxy_read_timeout 600s;
    }
}
```

Add the public domain to `TRUSTED_HOSTS`. The proxy-to-Pi leg stays inside
the encrypted tunnel; do not publish `:8765` itself. Note the SSE details:
HTTP/1.1 + Upgrade headers + a long read timeout, or streams will stall.

## Voice matrix

| Access | Chat | Browser mic | Phone-app mic |
|---|---|---|---|
| `http://localhost:8765` (on the Pi) | ✓ | ✓ | n/a |
| `http://<lan-ip>:8765` | ✓ | ✗ (toast explains) | ✓ |
| `https://…` (Tailscale / domain) | ✓ | ✓ | ✓ |
