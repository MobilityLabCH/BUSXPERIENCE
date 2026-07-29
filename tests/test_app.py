"""BUS XPERIENCE — tests.

Lancer:  python -m pytest tests/ -q
Couvre: santé, cabine, admin, consentement solo/duo, réponses de tous types,
impossibilité de réponse orpheline, concepts, rapport sans IA, rapport admin,
exports, migration v1, redémarrage sans perte, fournisseurs IA simulés.
"""
import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).parent.parent
sys.path.insert(0, str(RACINE))

os.environ.setdefault("ADMIN_PASS", "test-pass")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("AI_PROVIDER", "none")


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    # base isolée pour la session de tests
    donnees = tmp_path_factory.mktemp("data")
    import db
    db.DATA = donnees
    db.DB_PATH = donnees / "busxperience.db"
    db.BACKUPS = donnees / "backups"
    db.AUDIO = donnees / "audio"
    db.VOIX = donnees / "voix"
    db.MEDIAS = donnees / "medias"
    for d in (db.BACKUPS, db.AUDIO, db.VOIX, db.MEDIAS):
        d.mkdir(parents=True, exist_ok=True)
    # simule une ancienne base v1 pour tester la migration
    v1 = sqlite3.connect(donnees / "boite.db")
    v1.executescript("""
        CREATE TABLE lieux (id INTEGER PRIMARY KEY, nom TEXT, remarque TEXT, cree_le TEXT);
        CREATE TABLE sessions (id TEXT PRIMARY KEY, lieu_id INTEGER, lang TEXT, cree_le TEXT);
        CREATE TABLE reponses (id INTEGER PRIMARY KEY, session TEXT, question_id INTEGER,
            choix TEXT, audio TEXT, transcript TEXT, cree_le TEXT);
        INSERT INTO lieux VALUES (99,'Ancien lieu v1','','2026-01-01');
        INSERT INTO reponses (session,question_id,choix,cree_le)
            VALUES ('vieux-uuid',1,'En voiture','2026-01-01');
        INSERT INTO sessions VALUES ('vieux-uuid',99,'fr','2026-01-01');
    """)
    v1.commit(); v1.close()

    import app as module_app
    importlib.reload(module_app)
    from fastapi.testclient import TestClient
    return TestClient(module_app.app)


def _login(client):
    r = client.post("/admin/login", data={"mot_de_passe": "test-pass"},
                    follow_redirects=False)
    assert "bx_admin" in r.headers.get("set-cookie", "")
    return r


# ------------------------------------------------------------- démarrage

def test_health(client):
    d = client.get("/health").json()
    assert d["ok"] and d["app"] == "BUS XPERIENCE" and d["schema"] == 4
    assert d["ai_provider"] == "none"


def test_cabine_servie(client):
    h = client.get("/cabine/").text
    assert "BUS XPERIENCE" in h and "Powered by MobilityLab Sion" in h
    assert "fonts.googleapis" not in h  # hors ligne: aucune police externe


def test_admin_protege(client):
    assert "Mot de passe" in client.get("/admin").text
    _login(client)
    assert "Tableau de bord" in client.get("/admin").text


def test_migration_v1_reprise(client):
    # la vieille session et le vieux lieu ont été repris
    d = client.get("/health").json()
    assert d["sessions"] >= 1
    _login(client)
    assert "Ancien lieu v1" in client.get("/admin").text


# ------------------------------------------------------------- parcours

def test_config_cabine(client):
    d = client.get("/api/config").json()
    assert d["campagne"] and d["lieu"]
    types = {q["type"] for q in d["questions"]}
    assert {"choix", "etoiles", "echelle", "compare", "voix"} <= types
    assert len(d["concepts"]) == 2
    seg = [q for q in d["questions"] if q["params"].get("segment")]
    assert len(seg) == 1  # une seule question de segmentation
    cond = [q for q in d["questions"] if q["condition"]]
    assert cond, "au moins une question conditionnelle"


def _session(client, participants=1, micro=1):
    r = client.post("/api/sessions", data={"lang": "fr",
                    "participants": participants, "consent_micro": micro})
    assert r.status_code == 200
    return r.json()["session_id"]


def test_consentement_solo_et_duo(client):
    assert _session(client, 1)
    sid = _session(client, 2)
    import db
    with db.conn() as c:
        s = c.execute("SELECT participants FROM sessions WHERE id=?", (sid,)).fetchone()
    assert s["participants"] == 2
    r = client.post("/api/sessions", data={"participants": 3})
    assert r.status_code == 400


def test_reponses_tous_types_et_correction(client):
    d = client.get("/api/config").json()
    qs = {q["type"]: q for q in d["questions"]}
    sid = _session(client)
    for type_, valeur in (("choix", "Rarement"), ("etoiles", "4"), ("echelle", "7"),
                          ("compare", "Des bus plus ponctuels")):
        r = client.post(f"/api/sessions/{sid}/reponses",
                        data={"question_id": qs[type_]["id"], "cle": "reponse",
                              "valeur": valeur})
        assert r.status_code == 200
    # retour en arrière = correction, pas de doublon
    client.post(f"/api/sessions/{sid}/reponses",
                data={"question_id": qs["etoiles"]["id"], "cle": "reponse", "valeur": "2"})
    import db
    with db.conn() as c:
        rows = c.execute(
            "SELECT valeur FROM reponses WHERE session=? AND question_id=?",
            (sid, qs["etoiles"]["id"])).fetchall()
    assert len(rows) == 1 and rows[0]["valeur"] == "2"


def test_reponse_orpheline_refusee(client):
    sid = _session(client)
    r = client.post(f"/api/sessions/{sid}/reponses", data={"cle": "reponse", "valeur": "x"})
    assert r.status_code == 400  # jamais de saut sans question ni concept


def test_concepts_impact_adoption(client):
    d = client.get("/api/config").json()
    co = d["concepts"][0]
    sid = _session(client)
    for cle, valeur in (("impact", "5"), ("adoption", "9")):
        r = client.post(f"/api/sessions/{sid}/reponses",
                        data={"concept_id": co["id"], "cle": cle, "valeur": valeur})
        assert r.status_code == 200
    r = client.post(f"/api/sessions/{sid}/reponses",
                    data={"concept_id": co["id"], "cle": "bidon", "valeur": "1"})
    assert r.status_code == 400


def test_micro_sans_consentement_refuse(client):
    sid = _session(client, micro=0)
    d = client.get("/api/config").json()
    q_voix = next(q for q in d["questions"] if q["type"] == "voix")
    r = client.post(f"/api/sessions/{sid}/reponses",
                    data={"question_id": q_voix["id"], "cle": "reponse"},
                    files={"audio": ("x.webm", b"fake", "audio/webm")})
    assert r.status_code == 403


def test_rapport_participant_sans_ia(client):
    d = client.get("/api/config").json()
    qs = {q["type"]: q for q in d["questions"]}
    q_friction = next(q for q in d["questions"]
                      if q["etape"] == "friction" and q["type"] == "choix")
    co = d["concepts"][0]
    sid = _session(client)
    client.post(f"/api/sessions/{sid}/reponses",
                data={"question_id": qs["etoiles"]["id"], "cle": "reponse", "valeur": "4"})
    client.post(f"/api/sessions/{sid}/reponses",
                data={"question_id": q_friction["id"], "cle": "reponse",
                      "valeur": "Un retard sans information"})
    client.post(f"/api/sessions/{sid}/reponses",
                data={"question_id": qs["echelle"]["id"], "cle": "reponse", "valeur": "6"})
    client.post(f"/api/sessions/{sid}/reponses",
                data={"concept_id": co["id"], "cle": "adoption", "valeur": "9"})
    client.post(f"/api/sessions/{sid}/terminer")
    rep = client.post(f"/api/sessions/{sid}/rapport", data={"lang": "fr"}).json()
    assert rep["titre"] and rep["label"] == "Rapport personnalisé automatiquement"
    assert "4" in rep["texte"] and "6/10" in rep["texte"]
    assert co["nom_fr"] in rep["texte"]
    assert rep["texte"].count("\n\n") >= 2  # trois actes
    # idempotent
    rep2 = client.post(f"/api/sessions/{sid}/rapport", data={"lang": "fr"}).json()
    assert rep2["texte"] == rep["texte"]


# ------------------------------------------------------------- admin

def test_admin_sections(client):
    _login(client)
    for url, marqueur in (("/admin/campagnes", "consentement"),
                          ("/admin/questions", "Questionnaire"),
                          ("/admin/concepts", "Concepts"),
                          ("/admin/resultats", "Résultats"),
                          ("/admin/medias", "Klaxon"),
                          ("/admin/systeme", "fournisseur IA")):
        assert marqueur in client.get(url).text, url


def test_rapport_admin_et_exports(client):
    _login(client)
    h = client.get("/admin/rapport").text
    assert "complétion" in h and "Limites méthodologiques" in h
    assert "Concepts les mieux évalués" in h
    csv_ = client.get("/admin/export.csv").text
    assert csv_.startswith("id,date,campagne")
    j = client.get("/admin/export.json").json()
    assert j["busxperience"] and "limites_methodologiques" in j
    assert j["resultats"]["n_sessions"] >= 1


def test_question_crud_et_versionnement(client):
    _login(client)
    r = client.post("/admin/questions/0", data={
        "fr": "Question test ?", "de": "Testfrage?", "type": "choix",
        "etape": "friction", "ordre": 999, "options_fr": "A\nB",
        "options_de": "A\nB", "params": "{}", "condition": "", "actif": 1},
        follow_redirects=False)
    assert r.status_code == 303
    import db
    with db.conn() as c:
        q = c.execute("SELECT * FROM questions WHERE ordre=999").fetchone()
    assert q and q["version"] == 1
    client.post(f"/admin/questions/{q['id']}", data={
        "fr": "Question test v2 ?", "de": "Testfrage?", "type": "choix",
        "etape": "friction", "ordre": 999, "options_fr": "A\nB",
        "options_de": "A\nB", "params": "{}", "condition": "", "actif": 1})
    with db.conn() as c:
        q2 = c.execute("SELECT version FROM questions WHERE id=?", (q["id"],)).fetchone()
    assert q2["version"] == 2
    client.post(f"/admin/questions/{q['id']}", data={"action": "supprimer",
                "fr": "x", "de": "x"})


def test_redemarrage_sans_perte(client):
    import app as module_app
    import db
    with db.conn() as c:
        avant = c.execute("SELECT COUNT(*) n FROM reponses").fetchone()["n"]
    for ligne in db.migrer():
        pass
    import seed
    assert "rien à faire" in seed.semer()  # pas de recréation des questions
    with db.conn() as c:
        apres = c.execute("SELECT COUNT(*) n FROM reponses").fetchone()["n"]
    assert apres == avant


# ------------------------------------------------------------- IA simulée

def test_providers_mocks(client, monkeypatch):
    import ai
    # anthropic simulé
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "cle-de-test")
    monkeypatch.setattr(ai, "_http_json", lambda m, u, **k: {
        "content": [{"text": '{"titre":"Titre simulé","texte":"Corps simulé."}'}]})
    doc = ai.rapport_participant("fr", {"etoiles": "5"})
    assert doc["fournisseur"] == "anthropic" and doc["titre"] == "Titre simulé"
    assert doc["label"] == "Rapport personnalisé par IA"
    # gemini simulé
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "cle-de-test")
    monkeypatch.setattr(ai, "_http_json", lambda m, u, **k: {
        "candidates": [{"content": {"parts": [{"text": '{"titre":"G","texte":"T"}'}]}}]})
    assert ai.rapport_participant("fr", {})["fournisseur"] == "gemini"
    # échec réseau: erreur propre + repli ANNONCÉ (label automatique), pas silencieux
    def kaput(m, u, **k):
        raise RuntimeError("réseau coupé")
    monkeypatch.setattr(ai, "_http_json", kaput)
    doc = ai.rapport_participant("fr", {"etoiles": "3"})
    assert doc["fournisseur"] == "none" and doc["erreur"]
    assert doc["label"] == "Rapport personnalisé automatiquement"
    # test de connexion sans clé
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    assert ai.tester_connexion()["ok"] is False


# ------------------------------------------------------------- voix et sons

def test_config_tts_et_sons(client):
    d = client.get("/api/config").json()
    assert d["tts"]["provider"] == "browser"
    assert d["tts"]["voix_fr"] == "auto" and 0.5 <= d["tts"]["vitesse"] <= 1.5
    assert d["sons"]["klaxon_actif"] == 1 and d["sons"]["klaxon_present"] is True
    assert d["campagne"]["musique"] == "musique-voyage.mp3"
    q = next(q for q in d["questions"] if q["type"] == "voix")
    assert q["parle_fr"] and len(q["parle_fr"]) < len(q["fr"])  # texte parlé plus court


def test_medias_fournis_servis(client):
    for nom in ("klaxon.mp3", "musique-voyage.mp3"):
        r = client.get(f"/medias/{nom}")
        assert r.status_code == 200 and len(r.content) > 50000, nom


def test_reglages_tts_et_sons_admin(client):
    _login(client)
    client.post("/admin/tts", data={"voix_fr": "Microsoft Denise Online (Natural)",
                                    "voix_de": "auto", "vitesse": "0.9"})
    client.post("/admin/sons", data={"klaxon_actif": "1", "klaxon_volume": "0.5"})
    d = client.get("/api/config").json()
    assert d["tts"]["voix_fr"].startswith("Microsoft Denise")
    assert d["tts"]["vitesse"] == 0.9 and d["sons"]["klaxon_volume"] == 0.5
    h = client.get("/admin/medias").text
    assert "Voix du navigateur" in h and "Tester le klaxon" in h
    # retour aux valeurs par defaut pour les autres tests
    client.post("/admin/tts", data={"voix_fr": "auto", "voix_de": "auto", "vitesse": "0.97"})


# ------------------------------------------------------------- buzzer, v4

def test_config_buzzer_et_tonalite(client):
    d = client.get("/api/config").json()
    assert d["buzzer"]["unique"] == 1
    assert d["buzzer"]["lecture"] in ("lente", "normale", "rapide")
    assert 1000 <= d["buzzer"]["etoiles_delai_ms"] <= 6000
    assert 0.7 <= d["tts"]["tonalite"] <= 1.4


def test_reglages_buzzer_admin(client):
    _login(client)
    client.post("/admin/buzzer", data={"buzzer_unique": "1",
                "lecture_vitesse": "lente", "etoiles_delai_ms": "3000"})
    d = client.get("/api/config").json()
    assert d["buzzer"]["lecture"] == "lente" and d["buzzer"]["etoiles_delai_ms"] == 3000
    client.post("/admin/buzzer", data={"buzzer_unique": "1",
                "lecture_vitesse": "normale", "etoiles_delai_ms": "2500"})


def test_rapport_storytelling_utilise_frequence_et_moment(client):
    d = client.get("/api/config").json()
    q_seg = next(q for q in d["questions"] if q["params"].get("segment"))
    q_moment = next(q for q in d["questions"]
                    if q["etape"] == "experience" and q["type"] == "choix"
                    and not q["params"].get("segment"))
    sid = None
    r = client.post("/api/sessions", data={"lang": "fr", "participants": 1,
                                           "consent_micro": 1})
    sid = r.json()["session_id"]
    client.post(f"/api/sessions/{sid}/reponses",
                data={"question_id": q_seg["id"], "cle": "reponse",
                      "valeur": "Presque tous les jours"})
    client.post(f"/api/sessions/{sid}/reponses",
                data={"question_id": q_moment["id"], "cle": "reponse",
                      "valeur": "La correspondance"})
    rep = client.post(f"/api/sessions/{sid}/rapport", data={"lang": "fr"}).json()
    assert "correspondance" in rep["texte"].lower() or "correspondance" in rep["titre"].lower()


# ------------------------------------------------------------- suppression

def _compte(client):
    import db
    with db.conn() as c:
        return {t_: c.execute(f"SELECT COUNT(*) n FROM {t_}").fetchone()["n"]
                for t_ in ("sessions", "reponses", "questions", "concepts",
                           "campagnes", "reglages", "rapports")}


def test_suppression_session_precise(client):
    _login(client)
    sid = client.post("/api/sessions", data={"lang": "fr", "participants": 1}).json()["session_id"]
    d = client.get("/api/config").json()
    q = d["questions"][0]
    client.post(f"/api/sessions/{sid}/reponses",
                data={"question_id": q["id"], "cle": "reponse", "valeur": "X"})
    avant = _compte(client)
    r = client.post("/admin/donnees/supprimer",
                    data={"portee": "session", "session_id": sid},
                    follow_redirects=False)
    assert "supprime=1s-1r" in r.headers["location"]
    apres = _compte(client)
    assert apres["sessions"] == avant["sessions"] - 1
    assert apres["reponses"] == avant["reponses"] - 1
    assert apres["questions"] == avant["questions"]  # jamais touchées


def test_suppression_globale_exige_confirmation(client):
    _login(client)
    avant = _compte(client)
    r = client.post("/admin/donnees/supprimer",
                    data={"portee": "tout", "confirmation": "supprimer"},
                    follow_redirects=False)
    assert "erreur=confirmation" in r.headers["location"]
    assert _compte(client)["sessions"] == avant["sessions"]  # rien effacé


def test_suppression_globale_avec_sauvegarde(client):
    _login(client)
    import db
    avant = _compte(client)
    assert avant["sessions"] > 0
    n_sauvegardes = len(list(db.BACKUPS.iterdir()))
    r = client.post("/admin/donnees/supprimer",
                    data={"portee": "tout", "confirmation": "SUPPRIMER"},
                    follow_redirects=False)
    assert "supprime=" in r.headers["location"]
    apres = _compte(client)
    assert apres["sessions"] == 0 and apres["reponses"] == 0 and apres["rapports"] == 0
    # questions, concepts, campagnes, réglages conservés
    for garde in ("questions", "concepts", "campagnes", "reglages"):
        assert apres[garde] == avant[garde], garde
    # sauvegarde datée créée avant
    assert len(list(db.BACKUPS.iterdir())) == n_sauvegardes + 1
    assert any("avant_suppression_globale" in p.name for p in db.BACKUPS.iterdir())
    # rien ne réapparaît après re-migration/seed (équivalent redémarrage)
    import seed
    db.migrer(); seed.semer()
    assert _compte(client)["sessions"] == 0
