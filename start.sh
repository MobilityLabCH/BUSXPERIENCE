#!/usr/bin/env bash
# BUS XPERIENCE - lancement
set -e
cd "$(dirname "$0")"

echo "== BUS XPERIENCE =="
[ -f .env ] && set -a && . ./.env && set +a

if [ -z "$ADMIN_PASS" ]; then
  echo "ERREUR: ADMIN_PASS n'est pas defini (export ADMIN_PASS=... ou fichier .env)."
  exit 1
fi
if [ -z "$SECRET_KEY" ]; then
  echo "ATTENTION: SECRET_KEY absent, une valeur par defaut peu sure est utilisee."
fi
export AI_PROVIDER="${AI_PROVIDER:-none}"
echo "Fournisseur IA : $AI_PROVIDER"

mkdir -p data/audio data/voix data/medias data/backups
[ -f data/medias/klaxon.mp3 ] || echo "Info: data/medias/klaxon.mp3 absent -> son neutre de secours."
python3 - <<'PY'
import db, seed
for l in db.migrer(): print("[migration]", l)
print("[seed]", seed.semer())
PY
echo "Demarrage sur le port 8000  ->  /cabine/  /admin  /health"
exec uvicorn app:app --host 0.0.0.0 --port 8000
