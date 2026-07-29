"""BUS XPERIENCE — serveur principal.

Lancer:  ./start.sh   ou   uvicorn app:app --host 0.0.0.0 --port 8000
Routes:  /cabine/   /admin   /health
"""
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

import ai
import db
import seed
import routes_admin
import routes_cabine

app = FastAPI(title="BUS XPERIENCE", docs_url="/api/docs")

for ligne in db.migrer():
    print(f"[migration] {ligne}")
print(f"[seed] {seed.semer()}")
for f in db.copier_medias_defaut():
    print(f"[medias] {f} installé")
print(f"[ia] fournisseur: {ai.provider_actuel()}")

app.include_router(routes_cabine.router)
app.include_router(routes_admin.router)

app.mount("/cabine", StaticFiles(directory=db.RACINE / "cabine", html=True), name="cabine")
app.mount("/audio", StaticFiles(directory=db.AUDIO), name="audio")
app.mount("/voix", StaticFiles(directory=db.VOIX), name="voix")
app.mount("/medias", StaticFiles(directory=db.MEDIAS), name="medias")


@app.get("/")
def racine():
    return RedirectResponse("/cabine/")


@app.get("/health")
def health():
    with db.conn() as c:
        n = c.execute("SELECT COUNT(*) n FROM sessions").fetchone()["n"]
        version = c.execute("SELECT version FROM schema_version").fetchone()["version"]
    return {"ok": True, "app": "BUS XPERIENCE", "schema": version,
            "sessions": n, "ai_provider": ai.provider_actuel()}
