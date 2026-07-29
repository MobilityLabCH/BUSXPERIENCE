"""BUS XPERIENCE — administration en huit sections.

Tableau de bord, Campagnes, Questionnaires, Concepts, Résultats,
Rapports, Médias, Système. Authentification par mot de passe (ADMIN_PASS)
et cookie signé (SECRET_KEY). Aucun secret n'est jamais affiché.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

import ai
import db
import stats

router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory=str(db.RACINE / "templates"))

ADMIN_PASS = os.environ.get("ADMIN_PASS", "busxperience")
SECRET_KEY = os.environ.get("SECRET_KEY", "a-changer-en-production")


def _jeton() -> str:
    return hmac.new(SECRET_KEY.encode(), ADMIN_PASS.encode(),
                    hashlib.sha256).hexdigest()


def connecte(request: Request) -> bool:
    return hmac.compare_digest(request.cookies.get("bx_admin", ""), _jeton())


def page_login(request: Request, erreur: str = ""):
    return templates.TemplateResponse(request, "login.html", {"erreur": erreur})


def ctx_commun(c, section: str) -> dict:
    return {
        "section": section,
        "campagnes": [dict(r) for r in c.execute("SELECT * FROM campagnes ORDER BY id DESC")],
        "lieux": [dict(r) for r in c.execute("SELECT * FROM lieux ORDER BY id DESC")],
        "campagne_courante": int(db.reglage(c, "campagne_courante", "1") or 1),
        "lieu_courant": int(db.reglage(c, "lieu_courant", "1") or 1),
    }


@router.post("/admin/login")
def login(mot_de_passe: str = Form(...)):
    rep = RedirectResponse("/admin", status_code=303)
    if hmac.compare_digest(mot_de_passe, ADMIN_PASS):
        rep.set_cookie("bx_admin", _jeton(), httponly=True, max_age=86400 * 30)
    return rep


# ------------------------------------------------------------ 1. tableau de bord

@router.get("/admin", response_class=HTMLResponse)
def dashboard(request: Request):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        ctx = ctx_commun(c, "dashboard")
        ctx["stats"] = dict(c.execute(
            """SELECT COUNT(*) n, SUM(terminee_le IS NOT NULL) fini FROM sessions"""
        ).fetchone())
        ctx["n_reponses"] = c.execute("SELECT COUNT(*) n FROM reponses").fetchone()["n"]
        ctx["n_attente_transcription"] = c.execute(
            "SELECT COUNT(*) n FROM reponses WHERE audio IS NOT NULL AND transcript IS NULL"
        ).fetchone()["n"]
        ctx["provider"] = ai.provider_actuel()
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@router.post("/admin/courant")
def courant(request: Request, campagne_id: int = Form(0), lieu_id: int = Form(0)):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        if campagne_id:
            db.poser_reglage(c, "campagne_courante", str(campagne_id))
        if lieu_id:
            db.poser_reglage(c, "lieu_courant", str(lieu_id))
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/lieux")
def creer_lieu(request: Request, nom: str = Form(...), remarque: str = Form("")):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        c.execute("INSERT INTO lieux (nom, remarque, cree_le) VALUES (?,?,?)",
                  (nom.strip(), remarque.strip(), db.now()))
        db.poser_reglage(c, "lieu_courant",
                         str(c.execute("SELECT last_insert_rowid() i").fetchone()["i"]))
    return RedirectResponse("/admin", status_code=303)


# ------------------------------------------------------------ 2. campagnes

@router.get("/admin/campagnes", response_class=HTMLResponse)
def campagnes(request: Request):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        ctx = ctx_commun(c, "campagnes")
    return templates.TemplateResponse(request, "campagnes.html", ctx)


@router.post("/admin/campagnes")
async def sauver_campagne(request: Request, campagne_id: int = Form(0),
                          nom: str = Form(...), ton: str = Form("complice"),
                          consent_fr: str = Form(""), consent_de: str = Form(""),
                          musique_volume: float = Form(0.35),
                          musique_active: int = Form(0),
                          musique: UploadFile | None = File(None)):
    if not connecte(request):
        return page_login(request)
    fichier = None
    if musique is not None and musique.filename:
        fichier = f"musique_c{campagne_id or 'new'}_{musique.filename}".replace(" ", "_")
        (db.MEDIAS / fichier).write_bytes(await musique.read())
    with db.conn() as c:
        if campagne_id:
            c.execute(
                """UPDATE campagnes SET nom=?, ton=?, consent_fr=?, consent_de=?,
                   musique_volume=?, musique_active=?,
                   musique=COALESCE(?, musique) WHERE id=?""",
                (nom, ton, consent_fr, consent_de, musique_volume, musique_active,
                 fichier, campagne_id))
        else:
            c.execute(
                """INSERT INTO campagnes (nom, ton, consent_fr, consent_de,
                   musique_volume, musique_active, musique, cree_le)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (nom, ton, consent_fr, consent_de, musique_volume, musique_active,
                 fichier, db.now()))
    return RedirectResponse("/admin/campagnes", status_code=303)


# ------------------------------------------------------------ 3. questionnaires

@router.get("/admin/questions", response_class=HTMLResponse)
def questions(request: Request):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        ctx = ctx_commun(c, "questions")
        ctx["questions"] = [dict(r) for r in
                            c.execute("SELECT * FROM questions ORDER BY ordre")]
    return templates.TemplateResponse(request, "questions.html", ctx)


@router.get("/admin/questions/{qid}", response_class=HTMLResponse)
def question_edit(request: Request, qid: int):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        ctx = ctx_commun(c, "questions")
        if qid:
            ctx["q"] = dict(c.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone())
        else:
            ctx["q"] = {"id": 0, "ordre": 100, "etape": "experience", "type": "choix",
                        "fr": "", "de": "", "options_fr": "", "options_de": "",
                        "params": "{}", "condition": "", "actif": 1, "version": 0,
                        "audio_fr": None, "audio_de": None}
        ctx["toutes"] = [dict(r) for r in c.execute(
            "SELECT id, ordre, fr FROM questions ORDER BY ordre")]
    return templates.TemplateResponse(request, "question_edit.html", ctx)


@router.post("/admin/questions/{qid}")
async def question_sauver(request: Request, qid: int, action: str = Form("sauver"),
                          ordre: int = Form(100), etape: str = Form("experience"),
                          type: str = Form("choix"), fr: str = Form(""),
                          de: str = Form(""), texte_parle_fr: str = Form(""),
                          texte_parle_de: str = Form(""), options_fr: str = Form(""),
                          options_de: str = Form(""), params: str = Form("{}"),
                          condition: str = Form(""), actif: int = Form(0),
                          voix_fr: UploadFile | None = File(None),
                          voix_de: UploadFile | None = File(None)):
    if not connecte(request):
        return page_login(request)

    async def _voix(f: UploadFile | None, suffixe: str) -> str | None:
        if f is None or not f.filename:
            return None
        nom = f"q{qid or 'n'}_{suffixe}_{f.filename}".replace(" ", "_")
        (db.VOIX / nom).write_bytes(await f.read())
        return nom

    with db.conn() as c:
        if action == "supprimer" and qid:
            c.execute("DELETE FROM questions WHERE id=?", (qid,))
            return RedirectResponse("/admin/questions", status_code=303)
        if action == "dupliquer" and qid:
            q = c.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
            c.execute(
                """INSERT INTO questions (ordre,etape,type,fr,de,options_fr,options_de,
                   params,condition,actif,modifie_le)
                   VALUES (?,?,?,?,?,?,?,?,?,0,?)""",
                (q["ordre"] + 1, q["etape"], q["type"], q["fr"] + " (copie)", q["de"],
                 q["options_fr"], q["options_de"], q["params"], q["condition"], db.now()))
            return RedirectResponse("/admin/questions", status_code=303)
        afr, ade = await _voix(voix_fr, "fr"), await _voix(voix_de, "de")
        for champ in ("params", "condition"):
            valeur = {"params": params, "condition": condition}[champ]
            if valeur.strip():
                db.parse_json(valeur)  # valide silencieusement
        if qid:
            c.execute(
                """UPDATE questions SET ordre=?,etape=?,type=?,fr=?,de=?,
                   texte_parle_fr=?,texte_parle_de=?,options_fr=?,
                   options_de=?,params=?,condition=?,actif=?,version=version+1,
                   modifie_le=?, audio_fr=COALESCE(?,audio_fr),
                   audio_de=COALESCE(?,audio_de) WHERE id=?""",
                (ordre, etape, type, fr, de, texte_parle_fr, texte_parle_de,
                 options_fr, options_de, params,
                 condition, actif, db.now(), afr, ade, qid))
        else:
            c.execute(
                """INSERT INTO questions (ordre,etape,type,fr,de,texte_parle_fr,
                   texte_parle_de,options_fr,options_de,
                   params,condition,actif,audio_fr,audio_de,modifie_le)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
                (ordre, etape, type, fr, de, texte_parle_fr, texte_parle_de,
                 options_fr, options_de, params,
                 condition, afr, ade, db.now()))
    return RedirectResponse("/admin/questions", status_code=303)


@router.post("/admin/questions/{qid}/deplacer")
def question_deplacer(request: Request, qid: int, sens: str = Form("haut")):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        q = c.execute("SELECT id, ordre FROM questions WHERE id=?", (qid,)).fetchone()
        voisin = c.execute(
            f"""SELECT id, ordre FROM questions WHERE ordre {'<' if sens == 'haut' else '>'} ?
                ORDER BY ordre {'DESC' if sens == 'haut' else 'ASC'} LIMIT 1""",
            (q["ordre"],)).fetchone()
        if voisin:
            c.execute("UPDATE questions SET ordre=? WHERE id=?", (voisin["ordre"], q["id"]))
            c.execute("UPDATE questions SET ordre=? WHERE id=?", (q["ordre"], voisin["id"]))
    return RedirectResponse("/admin/questions", status_code=303)


# ------------------------------------------------------------ 4. concepts

@router.get("/admin/concepts", response_class=HTMLResponse)
def concepts(request: Request):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        ctx = ctx_commun(c, "concepts")
        ctx["concepts"] = [dict(r) for r in c.execute("SELECT * FROM concepts ORDER BY id")]
        ctx["nb_concepts"] = int(db.reglage(c, "nb_concepts", "2") or 2)
    return templates.TemplateResponse(request, "concepts.html", ctx)


@router.post("/admin/concepts")
async def sauver_concept(request: Request, concept_id: int = Form(0),
                         nom_fr: str = Form(""), nom_de: str = Form(""),
                         desc_fr: str = Form(""), desc_de: str = Form(""),
                         campagne_id: int = Form(0), actif: int = Form(0),
                         supprimer: int = Form(0), nb_concepts: int = Form(0),
                         image: UploadFile | None = File(None)):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        if nb_concepts:
            db.poser_reglage(c, "nb_concepts", str(max(0, min(5, nb_concepts))))
            return RedirectResponse("/admin/concepts", status_code=303)
        if supprimer and concept_id:
            c.execute("DELETE FROM concepts WHERE id=?", (concept_id,))
            return RedirectResponse("/admin/concepts", status_code=303)
        img = None
        if image is not None and image.filename:
            img = f"concept_{concept_id or 'n'}_{image.filename}".replace(" ", "_")
            (db.MEDIAS / img).write_bytes(await image.read())
        if concept_id:
            c.execute(
                """UPDATE concepts SET nom_fr=?,nom_de=?,desc_fr=?,desc_de=?,
                   campagne_id=?,actif=?, image=COALESCE(?,image) WHERE id=?""",
                (nom_fr, nom_de, desc_fr, desc_de, campagne_id or None, actif,
                 img, concept_id))
        else:
            c.execute(
                """INSERT INTO concepts (nom_fr,nom_de,desc_fr,desc_de,campagne_id,
                   image,actif) VALUES (?,?,?,?,?,?,1)""",
                (nom_fr, nom_de, desc_fr, desc_de, campagne_id or None, img))
    return RedirectResponse("/admin/concepts", status_code=303)


# ------------------------------------------------------------ 5. résultats

@router.get("/admin/resultats", response_class=HTMLResponse)
def resultats(request: Request, question: int = 0, session: str = ""):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        ctx = ctx_commun(c, "resultats")
        ctx["toutes"] = [dict(r) for r in c.execute(
            "SELECT id, ordre, type, fr FROM questions ORDER BY ordre")]
        ctx["question"], ctx["session"] = question, session
        ctx["supprime"] = request.query_params.get("supprime")
        ctx["erreur"] = request.query_params.get("erreur")
        cond, args = [], []
        if question:
            cond.append("r.question_id=?"); args.append(question)
        if session:
            cond.append("r.session=?"); args.append(session)
        sql_cond = ("WHERE " + " AND ".join(cond)) if cond else ""
        ctx["reponses"] = [dict(r) for r in c.execute(f"""
            SELECT r.*, q.fr AS q_fr, co.nom_fr AS c_nom, s.lang, s.participants
            FROM reponses r LEFT JOIN questions q ON q.id=r.question_id
            LEFT JOIN concepts co ON co.id=r.concept_id
            LEFT JOIN sessions s ON s.id=r.session
            {sql_cond} ORDER BY r.id DESC LIMIT 300""", args)]
    return templates.TemplateResponse(request, "resultats.html", ctx)


@router.post("/admin/donnees/supprimer")
def supprimer_donnees(request: Request, portee: str = Form(...),
                      session_id: str = Form(""), campagne_id: int = Form(0),
                      confirmation: str = Form("")):
    """Zone dangereuse: efface sessions, réponses, audios, transcriptions et
    rapports participants. Questions, concepts, campagnes, réglages et médias
    sont TOUJOURS conservés. Suppression globale: mot SUPPRIMER exigé et
    sauvegarde datée de la base créée avant."""
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        if portee == "session" and session_id.strip():
            cible = "s.id=?"
            args = [session_id.strip()]
        elif portee == "campagne" and campagne_id:
            cible = "s.campagne_id=?"
            args = [campagne_id]
        elif portee == "tout":
            if confirmation.strip() != "SUPPRIMER":
                return RedirectResponse("/admin/resultats?erreur=confirmation",
                                        status_code=303)
            sauvegarde = db._sauvegarder(db.DB_PATH, "avant_suppression_globale")
            db.journaliser(c, "suppression",
                           f"sauvegarde préalable: {sauvegarde.name if sauvegarde else '—'}")
            cible, args = "1=1", []
        else:
            return RedirectResponse("/admin/resultats?erreur=portee", status_code=303)
        ids = [r["id"] for r in c.execute(
            f"SELECT s.id FROM sessions s WHERE {cible}", args)]
        n = {"sessions": 0, "reponses": 0, "audios": 0, "rapports": 0}
        if ids:
            marque = ",".join("?" * len(ids))
            for r in c.execute(
                    f"SELECT audio FROM reponses WHERE session IN ({marque})"
                    " AND audio IS NOT NULL", ids):
                chemin = db.AUDIO / r["audio"]
                if chemin.exists():
                    chemin.unlink()
                    n["audios"] += 1
            n["reponses"] = c.execute(
                f"DELETE FROM reponses WHERE session IN ({marque})", ids).rowcount
            n["rapports"] = c.execute(
                f"DELETE FROM rapports WHERE session IN ({marque})", ids).rowcount
            n["sessions"] = c.execute(
                f"DELETE FROM sessions WHERE id IN ({marque})", ids).rowcount
        db.journaliser(c, "suppression", f"portée={portee} {n}")
    return RedirectResponse(
        f"/admin/resultats?supprime={n['sessions']}s-{n['reponses']}r-"
        f"{n['audios']}a-{n['rapports']}rap", status_code=303)


@router.post("/admin/reponses/{rid}/transcript")
def corriger_transcript(request: Request, rid: int, transcript: str = Form("")):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        c.execute("UPDATE reponses SET transcript=? WHERE id=?", (transcript.strip(), rid))
    return RedirectResponse("/admin/resultats", status_code=303)


# ------------------------------------------------------------ 6. rapports

def _filtres_depuis(request: Request) -> dict:
    q = request.query_params
    return {k: q.get(k) or None for k in
            ("campagne", "lieu", "lang", "participants", "termine",
             "depuis", "jusqua", "frequence")}


@router.get("/admin/rapport", response_class=HTMLResponse)
def rapport_admin(request: Request):
    if not connecte(request):
        return page_login(request)
    f = _filtres_depuis(request)
    r = stats.calculer(f)
    with db.conn() as c:
        ctx = ctx_commun(c, "rapport")
    verbatims = [v for q in r.get("questions", []) for v in q.get("verbatims", [])]
    ctx.update({"r": r, "f": f, "limites": stats.LIMITES_FR,
                "recommandations": stats.recommandations(r),
                "qualitatif": ai.analyse_qualitative(verbatims) if verbatims else None,
                "provider": ai.provider_actuel()})
    return templates.TemplateResponse(request, "rapport.html", ctx)


@router.get("/admin/export.csv")
def export_csv(request: Request):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        rows = c.execute("""
            SELECT r.id, r.cree_le, s.campagne_id, s.lieu_id, s.lang, s.participants,
                   r.session, q.fr AS question, co.nom_fr AS concept, r.cle,
                   r.valeur, r.transcript
            FROM reponses r LEFT JOIN sessions s ON s.id=r.session
            LEFT JOIN questions q ON q.id=r.question_id
            LEFT JOIN concepts co ON co.id=r.concept_id ORDER BY r.id""").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "date", "campagne", "lieu", "langue", "participants",
                "session", "question", "concept", "cle", "valeur", "transcription"])
    for r in rows:
        w.writerow([r[k] for k in r.keys()])
    buf.seek(0)
    return StreamingResponse(iter([buf.read()]), media_type="text/csv",
                             headers={"Content-Disposition":
                                      "attachment; filename=busxperience.csv"})


@router.get("/admin/export.json")
def export_json(request: Request):
    if not connecte(request):
        return page_login(request)
    f = _filtres_depuis(request)
    r = stats.calculer(f)
    r.pop("session_ids", None)
    return {"busxperience": True, "filtres": f, "resultats": r,
            "limites_methodologiques": stats.LIMITES_FR}


# ------------------------------------------------------------ 7. médias

@router.get("/admin/medias", response_class=HTMLResponse)
def medias(request: Request):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        ctx = ctx_commun(c, "medias")
        ctx["questions_voix"] = [dict(r) for r in c.execute(
            "SELECT id, ordre, fr, audio_fr, audio_de FROM questions ORDER BY ordre")]
    ctx["fichiers"] = sorted(p.name for p in db.MEDIAS.iterdir() if p.is_file())
    ctx["klaxon_present"] = (db.MEDIAS / "klaxon.mp3").exists()
    with db.conn() as c:
        ctx["tts"] = {"voix_fr": db.reglage(c, "tts_voix_fr", "auto"),
                      "voix_de": db.reglage(c, "tts_voix_de", "auto"),
                      "vitesse": db.reglage(c, "tts_vitesse", "0.97")}
        ctx["sons"] = {"klaxon_actif": int(db.reglage(c, "klaxon_actif", "1")),
                       "klaxon_volume": db.reglage(c, "klaxon_volume", "0.9")}
        ctx["tts"]["tonalite"] = db.reglage(c, "tts_tonalite", "1.05")
        ctx["buzzer"] = {"unique": int(db.reglage(c, "buzzer_unique", "1")),
                         "lecture": db.reglage(c, "lecture_vitesse", "normale"),
                         "etoiles_delai_ms": int(db.reglage(c, "etoiles_delai_ms", "2500"))}
    return templates.TemplateResponse(request, "medias.html", ctx)


@router.post("/admin/tts")
def reglages_tts(request: Request, voix_fr: str = Form("auto"),
                 voix_de: str = Form("auto"), vitesse: float = Form(0.97),
                 tonalite: float = Form(1.05)):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        db.poser_reglage(c, "tts_voix_fr", voix_fr.strip() or "auto")
        db.poser_reglage(c, "tts_voix_de", voix_de.strip() or "auto")
        db.poser_reglage(c, "tts_vitesse", str(max(0.5, min(1.5, vitesse))))
        db.poser_reglage(c, "tts_tonalite", str(max(0.7, min(1.4, tonalite))))
    return RedirectResponse("/admin/medias", status_code=303)


@router.post("/admin/buzzer")
def reglages_buzzer(request: Request, buzzer_unique: int = Form(0),
                    lecture_vitesse: str = Form("normale"),
                    etoiles_delai_ms: int = Form(2500)):
    if not connecte(request):
        return page_login(request)
    if lecture_vitesse not in ("lente", "normale", "rapide"):
        lecture_vitesse = "normale"
    with db.conn() as c:
        db.poser_reglage(c, "buzzer_unique", str(buzzer_unique))
        db.poser_reglage(c, "lecture_vitesse", lecture_vitesse)
        db.poser_reglage(c, "etoiles_delai_ms", str(max(1000, min(6000, etoiles_delai_ms))))
    return RedirectResponse("/admin/medias", status_code=303)


@router.post("/admin/sons")
def reglages_sons(request: Request, klaxon_actif: int = Form(0),
                  klaxon_volume: float = Form(0.9)):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        db.poser_reglage(c, "klaxon_actif", str(klaxon_actif))
        db.poser_reglage(c, "klaxon_volume", str(max(0.0, min(1.0, klaxon_volume))))
    return RedirectResponse("/admin/medias", status_code=303)


@router.post("/admin/medias")
async def deposer_media(request: Request, fichier: UploadFile = File(...),
                        nom: str = Form("")):
    if not connecte(request):
        return page_login(request)
    cible = (nom.strip() or fichier.filename).replace(" ", "_").replace("/", "")
    (db.MEDIAS / cible).write_bytes(await fichier.read())
    return RedirectResponse("/admin/medias", status_code=303)


@router.post("/admin/medias/supprimer")
def supprimer_media(request: Request, nom: str = Form(...)):
    if not connecte(request):
        return page_login(request)
    cible = db.MEDIAS / nom.replace("/", "")
    if cible.exists():
        cible.unlink()
    return RedirectResponse("/admin/medias", status_code=303)


@router.post("/admin/questions/{qid}/voix/supprimer")
def supprimer_voix(request: Request, qid: int, langue: str = Form("fr")):
    if not connecte(request):
        return page_login(request)
    col = "audio_de" if langue == "de" else "audio_fr"
    with db.conn() as c:
        c.execute(f"UPDATE questions SET {col}=NULL WHERE id=?", (qid,))
    return RedirectResponse("/admin/medias", status_code=303)


# ------------------------------------------------------------ 8. système

@router.get("/admin/systeme", response_class=HTMLResponse)
def systeme(request: Request):
    if not connecte(request):
        return page_login(request)
    with db.conn() as c:
        ctx = ctx_commun(c, "systeme")
        ctx["journal"] = [dict(r) for r in c.execute(
            "SELECT * FROM journal ORDER BY id DESC LIMIT 40")]
        ctx["n_attente"] = c.execute(
            "SELECT COUNT(*) n FROM reponses WHERE audio IS NOT NULL AND transcript IS NULL"
        ).fetchone()["n"]
        ctx["version_schema"] = db.VERSION_SCHEMA
    ctx["provider"] = ai.provider_actuel()
    ctx["modele"] = ai.modele_actuel(ctx["provider"])
    ctx["sauvegardes"] = sorted((p.name for p in db.BACKUPS.iterdir()), reverse=True)[:10]
    return templates.TemplateResponse(request, "systeme.html", ctx)


@router.post("/admin/systeme/tester-ia")
def tester_ia(request: Request):
    if not connecte(request):
        return page_login(request)
    resultat = ai.tester_connexion()
    with db.conn() as c:
        db.journaliser(c, "ia_test", json.dumps(resultat, ensure_ascii=False))
    return RedirectResponse("/admin/systeme", status_code=303)
