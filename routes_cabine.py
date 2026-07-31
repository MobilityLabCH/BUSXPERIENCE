"""BUS XPERIENCE — API du parcours participant (la Cabine)."""
from __future__ import annotations

import json
import os
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

import ai
import config as vieprivee
import db
import qr

router = APIRouter(prefix="/api", tags=["cabine"])


@router.get("/config")
def config():
    with db.conn() as c:
        camp_id = int(db.reglage(c, "campagne_courante", "1") or 1)
        lieu_id = int(db.reglage(c, "lieu_courant", "1") or 1)
        nb_concepts = int(db.reglage(c, "nb_concepts", "2") or 2)
        camp = (c.execute("SELECT * FROM campagnes WHERE id=?", (camp_id,)).fetchone()
                or c.execute("SELECT * FROM campagnes ORDER BY id LIMIT 1").fetchone())
        lieu = (c.execute("SELECT * FROM lieux WHERE id=?", (lieu_id,)).fetchone()
                or c.execute("SELECT * FROM lieux ORDER BY id LIMIT 1").fetchone())
        qs = c.execute("SELECT * FROM questions WHERE actif=1 ORDER BY ordre").fetchall()
        cos = c.execute(
            "SELECT * FROM concepts WHERE actif=1 AND (campagne_id IS NULL OR campagne_id=?)",
            (camp_id,)).fetchall()
        tts = {"provider": os.environ.get("TTS_PROVIDER", "browser"),
               "voix_fr": db.reglage(c, "tts_voix_fr", "auto"),
               "voix_de": db.reglage(c, "tts_voix_de", "auto"),
               "vitesse": float(db.reglage(c, "tts_vitesse", "0.97")),
               "tonalite": float(db.reglage(c, "tts_tonalite", "1.05"))}
        buzzer = {"unique": int(db.reglage(c, "buzzer_unique", "1")),
                  "lecture": db.reglage(c, "lecture_vitesse", "normale"),
                  "etoiles_delai_ms": int(db.reglage(c, "etoiles_delai_ms", "2500"))}
        sons = {"klaxon_actif": int(db.reglage(c, "klaxon_actif", "1")),
                "klaxon_volume": float(db.reglage(c, "klaxon_volume", "0.9")),
                "klaxon_present": (db.MEDIAS / "klaxon.mp3").exists()}
    concepts = [dict(r) for r in cos]
    random.shuffle(concepts)
    # priorise les concepts illustrés par une photo (ajoutée par l'admin) —
    # sinon ils peuvent ne jamais sortir dans le tirage aléatoire et donner
    # l'impression que les photos ne s'affichent jamais
    concepts.sort(key=lambda co: 0 if co.get("image") else 1)
    musique = camp["musique"] if camp and camp["musique"] else (
        "musique-voyage.mp3" if (db.MEDIAS / "musique-voyage.mp3").exists() else None)
    return {
        "tts": tts, "sons": sons, "buzzer": buzzer,
        "campagne": {"id": camp["id"], "nom": camp["nom"],
                     "consent_fr": camp["consent_fr"], "consent_de": camp["consent_de"],
                     "musique": musique, "musique_volume": camp["musique_volume"],
                     "musique_active": camp["musique_active"], "ton": camp["ton"]}
                    if camp else None,
        "lieu": dict(lieu) if lieu else None,
        "questions": [{
            "id": q["id"], "ordre": q["ordre"], "etape": q["etape"], "type": q["type"],
            "fr": q["fr"], "de": q["de"],
            "options_fr": [o for o in (q["options_fr"] or "").splitlines() if o.strip()],
            "options_de": [o for o in (q["options_de"] or "").splitlines() if o.strip()],
            "parle_fr": q["texte_parle_fr"] or "", "parle_de": q["texte_parle_de"] or "",
            "params": db.parse_json(q["params"]),
            "condition": db.parse_json(q["condition"], None) or None,
            "audio_fr": q["audio_fr"], "audio_de": q["audio_de"],
        } for q in qs],
        "concepts": concepts[:nb_concepts],
        "privacy": {
            "version": vieprivee.PRIVACY_NOTICE_VERSION,
            "text_fr": vieprivee.CONSENT_TEXT_FR,
            "text_de": vieprivee.CONSENT_TEXT_DE,
            # Lien cliquable affiché à l'écran: toujours relatif, ne dépend
            # jamais du domaine (jamais localhost) sur lequel tourne le serveur.
            "url_fr": vieprivee.lien_page_protection("fr"),
            "url_de": vieprivee.lien_page_protection("de"),
            # URL absolue réellement encodée dans le QR (jamais localhost/
            # 127.0.0.1/relative): PUBLIC_PRIVACY_URL_FR/DE > PUBLIC_BASE_URL
            # + chemin > page officielle de La Poste.
            "qr_url_fr": vieprivee.qr_url("fr"),
            "qr_url_de": vieprivee.qr_url("de"),
        },
    }


@router.get("/qr/{lang}.svg")
def qr_consentement(lang: str):
    """QR code généré localement (aucun service externe) vers la notice
    de protection des données, dans la langue de l'écran de consentement.
    N'encode jamais localhost/127.0.0.1/0.0.0.0 ni une URL relative."""
    url = vieprivee.qr_url("de" if lang == "de" else "fr")
    return Response(qr.qr_svg(url), media_type="image/svg+xml")


@router.post("/sessions")
def creer_session(lang: str = Form("fr"), participants: int = Form(1),
                  mic_ok: int = Form(0),
                  consent_version: str = Form("")):
    """Crée une session individuelle et strictement consentie.

    BUS XPERIENCE ne fonctionne plus qu'avec le microphone: une session
    n'est créée que si le navigateur a explicitement accordé l'accès au
    microphone (mic_ok=1), après un consentement « Oui, je participe »
    validé par appui long. Un refus, ou un microphone indisponible, ne crée
    jamais de session ni de ligne en base.
    """
    if participants != 1:
        raise HTTPException(400, "BUS XPERIENCE est une expérience individuelle")
    if not mic_ok:
        raise HTTPException(403, "consentement microphone requis")
    sid = str(uuid.uuid4())
    code = db.code_participant()
    with db.conn() as c:
        c.execute(
            """INSERT INTO sessions (id, campagne_id, lieu_id, lang, participants,
               consent_micro, consent_audio, consent_le, consent_version,
               privacy_lang, participant_code, demarree_le)
               VALUES (?,?,?,?,?,1,1,?,?,?,?,?)""",
            (sid, int(db.reglage(c, "campagne_courante", "1") or 1),
             int(db.reglage(c, "lieu_courant", "1") or 1),
             lang, 1, db.now(), consent_version or vieprivee.PRIVACY_NOTICE_VERSION,
             lang, code, db.now()))
    return {"session_id": sid, "participant_code": code}


@router.post("/sessions/{sid}/abandonner")
def abandonner(sid: str):
    """Arrêt volontaire pendant le parcours (appui très long sur le buzzer,
    confirmé). Supprime immédiatement et intégralement la session: réponses,
    audios, transcriptions et rapport éventuel. Idempotent."""
    with db.conn() as c:
        n = db.supprimer_sessions(c, [sid])
        db.journaliser(c, "abandon", f"session {sid[:8]} arrêtée par le participant")
    return {"ok": True, **n}


@router.post("/sessions/{sid}/reponses")
async def repondre(sid: str, question_id: int = Form(0), concept_id: int = Form(0),
                   cle: str = Form("reponse"), valeur: str = Form(None),
                   audio: UploadFile | None = File(None)):
    """Enregistre OU remplace (retour en arrière = corriger, jamais dupliquer)."""
    if cle not in ("reponse", "impact", "adoption"):
        raise HTTPException(400, "cle invalide")
    if not question_id and not concept_id:
        raise HTTPException(400, "question_id ou concept_id requis")
    with db.conn() as c:
        s = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "session inconnue")
        chemin = None
        if audio is not None:
            if not s["consent_audio"]:
                raise HTTPException(403, "pas de consentement micro pour cette session")
            # Nom de fichier aléatoire: jamais de schéma prévisible
            # (session/question) qui permettrait de deviner une URL d'audio.
            chemin = f"{uuid.uuid4().hex}.webm"
            (db.AUDIO / chemin).write_bytes(await audio.read())
        c.execute(
            """INSERT INTO reponses (session, question_id, concept_id, cle, valeur,
               audio, cree_le) VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(session, question_id, concept_id, cle)
               DO UPDATE SET valeur=excluded.valeur,
                             audio=COALESCE(excluded.audio, reponses.audio),
                             transcript=CASE WHEN excluded.audio IS NOT NULL
                                        THEN NULL ELSE reponses.transcript END,
                             cree_le=excluded.cree_le""",
            (sid, question_id or 0, concept_id or 0, cle, valeur, chemin, db.now()))
    return {"ok": True}


@router.post("/sessions/{sid}/terminer")
def terminer(sid: str):
    with db.conn() as c:
        s = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "session inconnue")
        debut = datetime.fromisoformat(s["demarree_le"])
        duree = int((datetime.now(timezone.utc) - debut).total_seconds())
        c.execute("UPDATE sessions SET terminee_le=?, duree_s=? WHERE id=?",
                  (db.now(), duree, sid))
    return {"ok": True, "duree_s": duree}


def _transcrire_local(chemin) -> str | None:
    """faster-whisper local uniquement. L'audio ne quitte jamais la machine."""
    try:
        from faster_whisper import WhisperModel
        if not hasattr(_transcrire_local, "modele"):
            _transcrire_local.modele = WhisperModel("small", device="auto",
                                                    compute_type="int8")
        segments, _ = _transcrire_local.modele.transcribe(str(chemin), vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
    except Exception:
        return None


@router.post("/sessions/{sid}/rapport")
def rapport(sid: str, lang: str = Form("fr")):
    with db.conn() as c:
        deja = c.execute("SELECT * FROM rapports WHERE session=?", (sid,)).fetchone()
        # La colonne « titre » (héritée du schéma précédent) porte désormais
        # le titre_profil du nouveau contrat.
        deja_doc = ({"titre_profil": deja["titre"], "plaisir": deja["plaisir"],
                     "friction": deja["friction"], "idee_a_tester": deja["idee_a_tester"],
                     "verdict": deja["verdict"], "categorie_visuelle": deja["categorie_visuelle"]}
                    if deja else None)
        if deja_doc and ai.rapport_cache_valide(deja_doc):
            ia_utilisee = deja["fournisseur"] != "none"
            label = ("Mit KI personalisiert" if ia_utilisee else "Automatisch personalisiert")
            if lang != "de":
                label = "Personnalisé par IA" if ia_utilisee else "Personnalisé automatiquement"
            return {**deja_doc, "label": label}
        if deja:
            # Les rapports d'un ancien format (paragraphe_1/2, conclusion...)
            # ou incomplets sont supprimés puis régénérés avec le nouveau
            # contrat de sortie.
            c.execute("DELETE FROM rapports WHERE session=?", (sid,))
        camp = c.execute(
            """SELECT ca.ton FROM sessions s LEFT JOIN campagnes ca
               ON ca.id=s.campagne_id WHERE s.id=?""", (sid,)).fetchone()
        rows = c.execute(
            """SELECT r.*, q.type AS q_type, q.etape, q.params, co.nom_fr, co.nom_de
               FROM reponses r LEFT JOIN questions q ON q.id=r.question_id
               LEFT JOIN concepts co ON co.id=r.concept_id
               WHERE r.session=? ORDER BY r.id""", (sid,)).fetchall()

    donnees: dict = {}
    # Une innovation évaluée par ligne: son nom, la réaction à chaud
    # (impact, 1-5) et le potentiel d'adoption exprimé (0-10) — envoyés à
    # l'IA pour qu'elle dispose du contexte complet, pas seulement du
    # concept le mieux noté.
    innovations: dict[int, dict] = {}
    meilleur_concept, meilleure_note = None, -1
    for r in rows:
        params_q = db.parse_json(r["params"]) if r["params"] else {}
        if r["q_type"] == "etoiles" and r["valeur"]:
            donnees["etoiles"] = r["valeur"]
        if r["q_type"] == "echelle" and r["valeur"]:
            donnees["confiance"] = r["valeur"]
        if r["q_type"] == "choix" and r["etape"] == "experience" and r["valeur"]:
            if params_q.get("segment"):
                donnees["frequence"] = r["valeur"]
            else:
                donnees["moment"] = r["valeur"]
        if r["q_type"] == "choix" and r["etape"] == "friction" and r["valeur"]:
            donnees["irritant"] = r["valeur"]
        if r["q_type"] == "choix" and r["etape"] == "priorite" and r["valeur"]:
            donnees["apprecie"] = r["valeur"]
        if r["q_type"] == "compare" and r["valeur"]:
            donnees["priorite_arbitrage"] = r["valeur"]
        if r["cle"] in ("impact", "adoption") and r["valeur"] and r["concept_id"]:
            nom = r["nom_de"] if lang == "de" else r["nom_fr"]
            entree = innovations.setdefault(r["concept_id"], {"nom": nom})
            entree[r["cle"]] = r["valeur"]
        if r["cle"] == "adoption" and r["valeur"]:
            note = float(r["valeur"])
            if note > meilleure_note:
                meilleure_note = note
                meilleur_concept = r["nom_de"] if lang == "de" else r["nom_fr"]
        if r["q_type"] == "voix":
            transcript = r["transcript"]
            if not transcript and r["audio"]:
                transcript = _transcrire_local(db.AUDIO / r["audio"])
                if transcript:
                    with db.conn() as c:
                        c.execute("UPDATE reponses SET transcript=? WHERE id=?",
                                  (transcript, r["id"]))
            if transcript:
                donnees["verbatim"] = transcript
    if innovations:
        donnees["innovations_evaluees"] = list(innovations.values())
    if meilleur_concept:
        # La note sert uniquement à sélectionner l'idée favorite; elle ne doit
        # jamais apparaître dans le rapport participant ni être envoyée telle
        # quelle à l'IA (seul le nom du concept l'est, via innovations_evaluees).
        donnees["concept"] = meilleur_concept

    doc = ai.rapport_participant(lang, donnees, ton=(camp["ton"] if camp else "complice"))
    with db.conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO rapports
               (session, lang, titre, texte, plaisir, friction, idee_a_tester,
                verdict, categorie_visuelle, fournisseur, erreur, cree_le)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, lang, doc["titre_profil"],
             "\n\n".join((doc["plaisir"], doc["friction"], doc["idee_a_tester"], doc["verdict"])),
             doc["plaisir"], doc["friction"], doc["idee_a_tester"], doc["verdict"],
             doc["categorie_visuelle"], doc["fournisseur"], doc.get("erreur"), db.now()))
        if doc.get("erreur"):
            db.journaliser(c, "ia_erreur", f"rapport {sid}: {doc['erreur']}")
    return {"titre_profil": doc["titre_profil"], "plaisir": doc["plaisir"],
            "friction": doc["friction"], "idee_a_tester": doc["idee_a_tester"],
            "verdict": doc["verdict"], "categorie_visuelle": doc["categorie_visuelle"],
            "label": doc["label"]}
