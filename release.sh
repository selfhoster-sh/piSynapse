#!/usr/bin/env bash
set -euo pipefail
# release.sh — piSynapse release klasörünü sıfırdan oluştur.
# Kullanım:  ./release.sh [/path/to/release-dir]
# Varsayılan: $HOME/piSynapse-release

SRC="$(cd "$(dirname "$0")" && pwd)"
DST="${1:-$HOME/piSynapse-release}"

echo "Source: $SRC"
echo "Target: $DST"

# 1. Hedefi sıfırla
rm -rf "$DST"
mkdir -p "$DST"

# 2. Rsync ile temiz kopyala
rsync -a --delete \
  --exclude='venv/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.db' \
  --exclude='*.db-shm' \
  --exclude='*.db-wal' \
  --exclude='*.pyc' \
  --exclude='models/' \
  --exclude='.env' \
  --exclude='.git/' \
  --exclude='.gitignore' \
  --exclude='release.sh' \
  --exclude='.pytest_cache/' \
  --exclude='.mypy_cache/' \
  --exclude='.ruff_cache/' \
  --exclude='NOTES.md' \
  "$SRC"/ "$DST"/

# 3. DB artıklarını temizle
find "$DST" -name '*.db*' -delete 2>/dev/null || true

# 4. Dosya yapısını göster
echo ""
echo "=== Release: $(du -sh "$DST" | cut -f1) ==="
ls -la "$DST"
echo ""
echo "OK — $DST hazir."
