#!/usr/bin/env bash
# Lancement developpement avec rechargement automatique
ADMIN_PASS="${ADMIN_PASS:-dev}" SECRET_KEY="${SECRET_KEY:-dev}" AI_PROVIDER="${AI_PROVIDER:-none}" \
exec uvicorn app:app --host 0.0.0.0 --port 8000 --reload
