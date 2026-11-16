# HTTPS setup (microphone / secure context)

Browsers only expose `getUserMedia` (microphone) in a **secure context**:
localhost/127.0.0.1 or HTTPS. Plain-HTTP LAN access (`http://<pi-ip>:8765`)
therefore cannot use voice input. The UI shows an "HTTPS required" toast in
that case — this document is the real fix.

`piSynapse` itself stays on `0.0.0.0:8765` (LAN phone access is a deliberate
design choice, see A-Y2 in `NOTES.md`); TLS is terminated in front of it.

## Option A — VPS reverse proxy via NPM (recommended if you have a VPS)

You already run Nginx Proxy Manager on a VPS with a wildcard cert — reuse it.

1. In NPM: **Add Proxy Host**
   - Domain: `assistant.<your-domain>`
   - Forward: `<pi-vpn-ip>:8765` (the Pi's AWG/LAN address)
   - SSL tab: pick your existing `*.<your-domain>` cert, enable "Force SSL"
2. Phone/laptop opens `https://assistant.<your-domain>` → VPS 443 → tunnel → Pi.
3. Set `SESSION_COOKIE_SECURE=true` in `.env` (TLS is now the documented path) and restart.

Pros: zero extra config on the Pi, existing cert valid, works from anywhere.
Cons: all traffic crosses the VPS (~5-10 ms extra).

## Option B — Caddy automatic HTTPS on the Pi

```bash
sudo apt install caddy
# /etc/caddy/Caddyfile
assistant.<your-domain> {
    reverse_proxy localhost:8765
}
sudo systemctl reload caddy
```

Use a **DNS-01** challenge with your DNS provider API (Cloudflare etc.) so the
Pi can get a Let's Encrypt cert without exposing port 80. Point the domain's
DNS A record at the Pi's LAN IP (DNS-only / grey cloud — never proxied).

Pros: fully automatic Let's Encrypt, local HTTPS.
Cons: DNS must resolve to a LAN IP (public access unintended, LAN/VPN only).

## Option C — Self-signed cert + mkcert (fully local, no internet)

```bash
sudo apt install mkcert
mkcert -install                         # local CA
mkcert <pi-lan-ip> <pi-vpn-ip> localhost
# serve with caddy/nginx using the generated cert+key
```

Trust the CA's public key on each phone/laptop (iOS profile / Android CA
cert). Fully LAN-dependent, no internet needed; cost is manual trust per
device.

## Option D — NPM on the Pi itself

Install Docker + NPM on the Pi, serve HTTPS with a self-signed or DNS-01
Let's Encrypt cert through NPM. Reuses existing NPM knowledge, but adds a
container on the box and wants ports 80/443.

## Recommendation

- You have a VPS with NPM + wildcard cert → **Option A** (2 minutes, no Pi
  changes beyond `SESSION_COOKIE_SECURE=true`).
- No VPS / offline-only → **Option C**.
- Avoid Option D unless you already run Docker on the Pi.

After any option: verify with `curl -sS https://<your-domain>/health` and
re-test voice input in the browser.
