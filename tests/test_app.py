import json
import re
"""BUS XPERIENCE — tests.

Lancer:  python -m pytest tests/ -q
Couvre: santé, cabine individuelle micro-obligatoire, consentement explicite,
réponses de tous types, impossibilité de réponse orpheline, concepts,
rapport sans IA, rapport admin, exports, migration v1 et v5, redémarrage sans
perte, fournisseurs IA simulés, protection des données (pages, config,
masquage PII, abandon de session, code de participation, cleanup.py).
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


CODE_RE = re.compile(r"^BX-[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}$")


def _session(client, participants=1, mic_ok=1, lang="fr"):
    r = client.post("/api/sessions", data={"lang": lang,
                    "participants": participants, "mic_ok": mic_ok})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


# ------------------------------------------------------------- démarrage

def test_health(client):
    d = client.get("/health").json()
    assert d["ok"] and d["app"] == "BUS XPERIENCE" and d["schema"] == 6
    assert d["ai_provider"] == "none"


def test_cabine_servie(client):
    h = client.get("/cabine/").text
    assert "BUS XPERIENCE" in h and "Powered by MobilityLab Sion" in h
    assert "fonts.googleapis" not in h
    assert "e-duo" not in h and "À deux" not in h and "Zu zweit" not in h
    assert "ArrowLeft" not in h and "ArrowRight" not in h
    assert "class=\"curseur\"" not in h and "id=\"retour\"" not in h
    assert "aucune lecture automatique des réponses" in h
    assert "DU STEIGST EIN" in h and "TON EXPÉRIENCE" in h
    # micro obligatoire: plus aucun parcours ni choix "sans micro"
    assert "sans micro" not in h.lower()
    assert "ohne mikrofon" not in h.lower()
    assert "consentnomicro" not in h.lower()
    assert "consent-no-micro" not in h.lower()
    assert "fallback:[" not in h
    # exactement deux choix de consentement par langue
    assert '"Oui, je participe"' in h or "consentOui:\"Oui, je participe\"" in h
    assert 'consentNon:"Non merci"' in h
    assert 'consentOui:"Ja, ich mache mit"' in h
    assert 'consentNon:"Nein, danke"' in h
    # QR code local + lien discret protection des données
    assert "/api/qr/" in h and "consent-privacy" in h
    # QR suffisamment grand (~96-112px), jamais un service externe
    assert "clamp(96px,9vh,112px)" in h
    assert "api.qrserver.com" not in h and "chart.googleapis.com" not in h
    # carte protection des données entièrement cliquable (toute la carte est un <a>)
    assert '<a class="privacy-card"' in h
    assert 'id="consent-privacy-desc"' in h and 'id="consent-privacy-title"' in h
    # ancien texte d'intro jamais affiché comme consentement
    assert "TU MONTES À BORD" not in h.split('id="e-consent"')[1].split("</section>")[0]


def test_refus_ne_demande_jamais_le_micro_ni_ne_cree_de_session(client):
    """Analyse statique de refuse(): aucun appel réseau, aucun getUserMedia."""
    h = client.get("/cabine/").text
    m = re.search(r"function refuse\(\)\{[^}]*\}", h)
    assert m, "fonction refuse() introuvable"
    corps = m.group(0)
    assert "fetch" not in corps
    assert "getUserMedia" not in corps
    assert "/api/sessions" not in corps
    assert "text().noThanks" in corps


def test_bug_space_appui_long_corrige(client):
    """Le bug historique (double activation Space/appui long) est corrigé:
    gestionnaire central unique, boutons hors tabulation, event.repeat ignoré,
    verrou anti-double-validation pendant les transitions d'écran."""
    h = client.get("/cabine/").text
    assert "LONG_PRESS=650" in h and "STOP_PRESS=4000" in h
    assert "e.repeat" in h and "!e.repeat" in h
    assert 'e.preventDefault()' in h
    assert "tabindex=\"-1\"" in h or "tabIndex=-1" in h
    assert "transitioning=false" in h
    assert "if(transitioning)return" in h
    assert 'addEventListener("blur",resetPress)' in h
    assert 'visibilitychange' in h and "resetPress" in h
    assert 'addEventListener("pointercancel"' in h and "resetPress()" in h
    # une seule fonction traite le relâchement, quelle que soit la source
    assert h.count("function pressUp(") == 1
    assert h.count("function pressDown()") == 1


def test_tout_l_ecran_est_le_buzzer_sur_tactile(client):
    """Sur mobile (iPhone compris), un tap court ou maintenu n'importe où sur
    l'écran doit produire le même effet qu'un appui court/long sur le buzzer
    physique: gestionnaire global unique, pas de raccourci par carte qui
    court-circuiterait ou doublonnerait ce geste."""
    h = client.get("/cabine/").text
    assert 'document.addEventListener("pointerdown"' in h
    assert 'document.addEventListener("pointerup"' in h
    # aucune carte de choix / étoile / échelle / duel n'a plus sa propre
    # action au clic: seul le geste global (court/long) décide
    assert "b.onclick=" not in h
    assert "s.onclick=" not in h
    assert '$("#compare-a").onclick=' not in h
    assert '$("#compare-b").onclick=' not in h
    assert '$("#voice-review").addEventListener("click"' not in h
    # seul le vrai lien "Protection des données" échappe à la capture globale
    assert "pressIgnoredGesture" in h and ".privacy-card" in h


def test_tap_direct_sur_une_carte_la_selectionne(client):
    """Sur tactile, toucher directement une réponse/étoile/duel la
    sélectionne tout de suite (plus naturel au doigt), sans pour autant
    court-circuiter le modèle buzzer: un tap court dessus sélectionne sans
    valider, un tap maintenu dessus sélectionne ET valide. L'échelle n'a
    plus de cartes individuelles (c'est une jauge continue tenue/relâchée),
    donc elle n'a plus besoin de ce cas particulier."""
    h = client.get("/cabine/").text
    assert "function directTapSelect(target)" in h
    assert 'target.closest(".choice")' in h
    assert 'target.closest(".star")' in h
    assert 'target.closest(".scale-value")' not in h
    assert 'target.closest("#compare-a")' in h and 'target.closest("#compare-b")' in h
    # câblé dans le geste global: pointerdown sélectionne, pointerup ne
    # fait PAS aussi défiler vers l'option suivante quand c'était un tap direct
    assert "pressDirectTap=directTapSelect(e.target)" in h
    assert "pressUp(directTap)" in h
    assert "if(directTap)return" in h


def test_lecture_vocale_debloquee_des_le_premier_appui_ios(client):
    """iOS Safari bloque speechSynthesis.speak() tant qu'il n'a pas été
    appelé une fois de façon synchrone dans un vrai geste utilisateur. On le
    déverrouille dès le tout premier appui (buzzer/tactile/clavier), sinon
    les questions restent silencieuses sur iPhone après une transition
    différée (setTimeout/await)."""
    h = client.get("/cabine/").text
    assert "function unlockSpeech()" in h
    assert "speechUnlocked=true" in h
    assert "new SpeechSynthesisUtterance(\"\")" in h
    # appelé au tout début du point d'entrée unique de pression
    m = re.search(r"function pressDown\(\)\{([^}]*)\}", h)
    assert m and "unlockSpeech()" in m.group(1)


def test_deverrouillage_vocal_rearme_a_chaque_pression(client):
    """Constaté en usage: sur iPhone, les toutes premières questions
    restaient parfois silencieuses malgré le déverrouillage initial — la
    fenêtre d'activation accordée par le geste utilisateur peut expirer
    après quelques secondes, largement dépassé par la séquence
    consentement + attente de l'autorisation micro. unlockSpeech() ne doit
    donc plus s'arrêter après le premier appel: il se réarme à chaque
    pression."""
    h = client.get("/cabine/").text
    m = re.search(r"function unlockSpeech\(\)\{([^}]*)\}", h)
    assert m, "fonction unlockSpeech() introuvable"
    corps = m.group(1)
    assert "if(speechUnlocked" not in corps.replace(" ", "")


def test_lecture_vocale_ne_cancel_speak_pas_dans_le_meme_tick_ios(client):
    """Bug WebKit connu sur iPhone: enchaîner speechSynthesis.cancel() puis
    .speak() dans le même tick fait parfois disparaître silencieusement le
    nouvel énoncé (ni erreur ni son), ce qui explique des questions
    "sautées" sans schéma évident. On ne cancel() que si une lecture est
    déjà en cours, et on laisse un court délai avant de relancer speak()."""
    h = client.get("/cabine/").text
    m = re.search(r"function speak\(value,done\)\{.*?\}\}", h)
    assert m, "fonction speak() introuvable"
    corps = m.group(0)
    assert "speechSynthesis.speaking||speechSynthesis.pending" in corps
    assert "setTimeout(lancer,30)" in corps
    assert "speechSynthesis.resume()" in corps


def test_voix_ios_de_meilleure_qualite_preferee(client):
    """Sur iPhone, aucune voix système ne contient les marqueurs
    Chrome/Android (natural/online/neural/google): le score tombait à
    égalité et le tri retenait la première voix "Compact" venue, perçue
    comme une "voix bizarre". Les voix Enhanced/Premium/Siri, nettement
    meilleures et disponibles sur iOS, doivent être préférées."""
    h = client.get("/cabine/").text
    m = re.search(r"function voiceScore\(v\)\{([^}]*)\}", h)
    assert m
    corps = m.group(1)
    for marqueur in ("siri", "enhanced", "premium"):
        assert f'"{marqueur}"' in corps or f"'{marqueur}'" in corps


def test_admin_protege(client):
    assert "Mot de passe" in client.get("/admin").text
    r = _login(client)
    assert "samesite=lax" in r.headers.get("set-cookie", "").lower()
    assert "Tableau de bord" in client.get("/admin").text


def test_migration_v1_reprise(client):
    # la vieille session et le vieux lieu ont été repris
    d = client.get("/health").json()
    assert d["sessions"] >= 1
    _login(client)
    assert "Ancien lieu v1" in client.get("/admin").text


def test_migration_v5_colonnes_consentement(client):
    import db
    with db.conn() as c:
        colonnes = {r["name"] for r in c.execute("PRAGMA table_info(sessions)")}
    for attendue in ("consent_audio", "consent_le", "consent_version",
                      "privacy_lang", "participant_code", "consent_micro"):
        assert attendue in colonnes, attendue


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
    assert d["privacy"]["url_fr"] and d["privacy"]["url_de"]
    assert d["privacy"]["version"]


def test_concepts_titres_benefices_voyageurs(client):
    """Les titres de concepts sont reformulés en bénéfices voyageurs, pas en
    noms techniques de fonctionnalité ou en travail expérimental à tester."""
    d = client.get("/api/config").json()
    noms = " ".join(c["nom_fr"] for c in d["concepts"]) + " " + \
        " ".join(c.get("nom_de", "") for c in d["concepts"])
    for interdit in ("Alerte retard immédiate", "Auslastungsanzeige",
                      "Anschlussgarantie", "idée à tester", "Idee zum Testen"):
        assert interdit not in noms


def test_rapport_final_presente_un_billet_personnalise(client):
    """La dernière page (le rapport) doit prendre la forme d'un billet de
    voyage: souche avec le code de participation mis en avant (preuve
    concrète de personnalisation), pictogramme, et le lieu affiché — pas
    juste un bloc de texte générique."""
    h = client.get("/cabine/").text
    assert 'class="report-main"' in h and 'class="report-stub"' in h
    assert 'id="report-confetti"' in h or 'class="report-confetti"' in h
    assert "lieuNom" in h and "cfg.lieu" in h


def test_billet_integre_le_logo_carpostal(client):
    """Le logo CarPostal doit être intégré discrètement à la souche du
    billet final (à côté des champs buzzer/date/code), servi depuis
    /medias/ comme les autres médias par défaut."""
    h = client.get("/cabine/").text
    assert 'src="/medias/logo-postauto.png"' in h
    assert (RACINE / "medias-defaut" / "logo-postauto.png").exists()


def test_billet_indique_le_buzzer_lheure_exacte_et_un_mot_de_remerciement(client):
    """Le billet final doit dire où se trouve le buzzer utilisé (nom du
    lieu de la campagne), la date et l'heure exactes de la session, et se
    terminer par un mot chaleureux plutôt qu'un simple bloc de données."""
    h = client.get("/cabine/").text
    assert 'id="report-stub-lieu"' in h and 'id="report-stub-datetime"' in h
    assert 'id="report-thanks"' in h
    assert "reportBuzzerLabel" in h and "reportDateLabel" in h and "reportThanks" in h
    # une heure/date réelles, calculées au moment du rapport - pas un texte figé
    assert "new Date()" in h and "toLocaleDateString" in h and "toLocaleTimeString" in h
    # les deux langues ont un message de remerciement distinct et non vide
    assert "Merci pour ce moment passé avec nous" in h
    assert "Danke für diesen Moment mit uns" in h


def test_illustration_du_concept_visible_sur_mobile(client):
    """Bug réel constaté sur téléphone: en dessous de 900px de large,
    .concept-visual (qui contient à la fois la photo et le picto de repli)
    était complètement masqué (display:none), donc ni la photo ajoutée par
    l'admin ni le picto ne s'affichaient jamais sur mobile. L'illustration
    doit rester visible, juste en plus petit."""
    h = client.get("/cabine/").text
    m = re.search(r"@media \(max-width:900px\)\{(.*?)\n\}", h, re.S)
    assert m, "media query max-width:900px introuvable"
    bloc = m.group(1)
    assert ".concept-visual{display:none}" not in bloc
    assert ".concept-visual" in bloc


def test_pictogramme_admin_prioritaire_sur_carte_texte_seul(client):
    """Sans photo, la carte doit utiliser le picto choisi par l'admin s'il
    existe (c.icone). Un picto deviné automatiquement par mots-clés (deux
    emoji collés, jugé peu soigné et hors identité de marque) n'est plus
    généré: sans image ni picto manuel, la carte passe en texte seul."""
    h = re.sub(r"\s+", "", client.get("/cabine/").text)
    assert "manuel=c.icone&&c.icone.trim()" in h
    assert "elseif(manuel)showIcone(manuel)" in h
    assert "elseshowTexteSeul()" in h


def test_photo_de_concept_repli_sur_picto_si_le_fichier_echoue(client):
    """Si l'image d'un concept ne charge pas (fichier manquant, chemin
    invalide), on doit basculer sur le pictogramme manuel s'il existe, sinon
    sur la carte texte seul — jamais un cadre d'image cassé et vide."""
    h = client.get("/cabine/").text
    assert "function showConcept(c){" in h
    assert "img.onerror=()=>manuel?showIcone(manuel):showTexteSeul()" in h.replace(" ", "")


def test_admin_peut_definir_le_picto_dun_concept(client):
    """L'admin peut fixer un pictogramme (emoji) manuel pour un concept,
    qui doit ensuite être proposé dans /api/config et repris tel quel."""
    _login(client)
    import db as module_db
    with module_db.conn() as c:
        row = c.execute("SELECT id, nom_fr, nom_de FROM concepts ORDER BY id LIMIT 1").fetchone()
        concept_id, nom_fr, nom_de = row["id"], row["nom_fr"], row["nom_de"]
    r = client.post("/admin/concepts", data={
        "concept_id": concept_id, "nom_fr": nom_fr, "nom_de": nom_de,
        "desc_fr": "", "desc_de": "",
        "icone": "🚀🎉", "campagne_id": 0, "actif": 1,
    }, follow_redirects=False)
    assert r.status_code == 303
    with module_db.conn() as c:
        icone = c.execute("SELECT icone FROM concepts WHERE id=?", (concept_id,)).fetchone()["icone"]
    assert icone == "🚀🎉"


def test_concept_illustre_par_une_photo_toujours_tire_en_priorite(client):
    """Un concept illustré par une photo (ajoutée par l'admin) doit toujours
    sortir dans le tirage aléatoire des concepts présentés en session -
    sinon, avec peu de concepts tirés au sort parmi beaucoup, la photo
    n'apparaît quasiment jamais et donne l'impression qu'elle ne marche pas."""
    _login(client)
    import db as module_db
    with module_db.conn() as c:
        row = c.execute("SELECT id, nom_fr, nom_de FROM concepts ORDER BY id LIMIT 1").fetchone()
        cid = row["id"]
    files = {"image": ("photo.jpg", b"\xff\xd8\xff\xe0FAKE", "image/jpeg")}
    data = {"concept_id": cid, "nom_fr": row["nom_fr"], "nom_de": row["nom_de"],
            "desc_fr": "", "desc_de": "", "icone": "", "campagne_id": 0, "actif": 1}
    client.post("/admin/concepts", data=data, files=files, follow_redirects=False)
    client.post("/admin/concepts", data={"nb_concepts": 1})
    for _ in range(15):
        cfg = client.get("/api/config").json()
        assert any(c["id"] == cid for c in cfg["concepts"])


def test_musique_coupee_pendant_enregistrement_micro(client):
    """La musique de fond doit être totalement coupée pendant
    l'enregistrement d'une réponse vocale (le micro capte aussi le son
    ambiant de la pièce, pas seulement la voix), pas seulement baissée.
    La coupure démarre à startRecording() (le micro est vraiment actif),
    pas dès l'affichage de la question: coupler la coupure "dure" (pause()
    de la musique) avec la lecture de la question elle-même s'est avéré
    faire échouer silencieusement speechSynthesis sur iPhone (bug WebKit
    de session audio partagée)."""
    h = client.get("/cabine/").text
    assert "function musicMute()" in h
    assert "musicHardMuted" in h
    assert "voiceStream=stream;musicHardMuted=true;musicMute();" in h
    # la question elle-même (avant que le micro soit actif) ne coupe pas la
    # musique, seulement le duck habituel des lectures de questions
    sv = re.search(r"function showVoice\(q\)\{([^}]*)\}", h)
    assert sv and "musicHardMuted=true" not in sv.group(1)
    # restaurée une fois l'enregistrement effectivement terminé
    assert "musicHardMuted=false;musicNormal()" in h
    # musicNormal() n'annule jamais la coupure tant qu'elle est active
    # (sinon la lecture de la question la lèverait pendant l'enregistrement)
    mn = re.search(r"function musicNormal\(\)\{([^}]*)\}", h)
    assert mn and "if(musicHardMuted" in mn.group(0) and "return" in mn.group(0)


def test_coupure_musique_repose_sur_pause_pas_seulement_le_volume(client):
    """Bug réel constaté sur iPhone: iOS/Safari ignore complètement les
    changements de volume appliqués par script sur un <audio> (seuls les
    boutons physiques du téléphone contrôlent le volume) — tout le système
    de fade n'avait donc aucun effet sur mobile, et la musique continuait à
    plein volume pendant l'enregistrement. pause()/play() restent en
    revanche toujours respectés, y compris sur iOS: la coupure "dure" doit
    donc reposer dessus, pas seulement sur le fade du volume."""
    h = client.get("/cabine/").text
    mute = re.search(r"function musicMute\(\)\{([^}]*)\}", h)
    assert mute and "background.pause()" in mute.group(0)
    normal = re.search(r"function musicNormal\(\)\{([^}]*)\}", h)
    assert normal and "background.play()" in normal.group(0)


def test_fade_musique_ne_peut_pas_etre_ecrasee_par_une_rampe_perimee(client):
    """Bug réel identifié en usage: deux fade() qui se chevauchent (ex: un
    fade-up résiduel de 650ms d'une lecture de question qu'on vient
    d'interrompre, suivi de près par le fade-to-0 de 250ms du coupe-son
    micro) continuaient TOUTES LES DEUX de piloter background.volume image
    par image, sans mécanisme d'annulation — la rampe la plus longue, encore
    active après que la coupure a fini la sienne, remontait le son en pleine
    coupure. fade() doit invalider toute rampe précédente dès qu'une
    nouvelle démarre (jeton de génération)."""
    h = client.get("/cabine/").text
    m = re.search(r"function fade\(target,ms\)\{([^}]*(?:\{[^}]*\}[^}]*)*)\}", h)
    assert m, "fonction fade() introuvable"
    corps = m.group(0)
    assert "gen" in corps and "fadeGen" in corps, (
        "fade() doit utiliser un jeton de génération pour invalider les "
        "rampes précédentes encore en cours")
    assert "gen!==fadeGen" in corps or "fadeGen!==gen" in corps


def test_idee_a_tester_devient_innovation_dynamique(client):
    """La séquence « idées à tester » est reformulée en « Ton trajet, en
    mieux », avec un numéro d'innovation dynamique (jamais un nombre fixe:
    le nombre de concepts est variable et aléatoire) et un sous-titre
    positif. Les étoiles génériques ne servent plus à évaluer un concept:
    une échelle de réactions adaptée au critère réel de chaque idée
    (sécurité, confort, simplicité, tranquillité…) les remplace."""
    h = client.get("/cabine/").text
    assert "Ton trajet, en mieux" in h and "Deine Fahrt, verbessert" in h
    assert "Les idées à tester" not in h and "Ideen zum Testen" not in h
    # numéro d'innovation calculé dynamiquement, jamais un total figé
    assert "INNOVATION ${n} SUR ${total}" in h
    assert "INNOVATION ${n} VON ${total}" in h
    assert "conceptSubtitle" in h
    assert "Des innovations pour rendre les transports publics plus agréables" in h
    # le vieux libellé "idée à tester" (eyebrow) a disparu
    assert "concept:\"Idée à tester\"" not in h and "concept:\"Idee zum Testen\"" not in h
    # remplace les étoiles pour l'évaluation d'un concept: un système de
    # réactions distinct, avec plusieurs critères possibles (pas la même
    # question partout)
    assert "function showReaction(concept)" in h
    assert "function conceptCategorie(c)" in h
    assert "cle:\"impact\"" in h  # même format de réponse qu'avant (1 à 5)
    for critere in ("agreable", "securite", "confort", "utilite", "confiance"):
        assert f'{critere}:{{question:' in h.replace(" ", ""), critere
    assert "Cette idée rendrait-elle tes trajets plus agréables ?" in h
    assert "Cette idée te ferait-elle sentir plus en sécurité ?" in h
    # sans image ni picto manuel: carte texte seul, pas d'icône générique
    # devinée par mots-clés (jugée peu soignée, hors identité de la marque)
    assert "no-image" in h and "showTexteSeul" in h


def test_json_privacy_texte_legal_reel(client):
    """Le vrai texte légal (centralisé dans config.py) est bien celui exposé
    par /api/config — plus les anciens champs campagne.consent_fr/de."""
    import config
    d = client.get("/api/config").json()
    priv = d["privacy"]
    assert priv["text_fr"] == config.CONSENT_TEXT_FR
    assert priv["text_de"] == config.CONSENT_TEXT_DE
    assert "Ne donne pas de nom ni d’information personnelle" in priv["text_fr"]
    assert "La participation est volontaire" in priv["text_fr"]
    assert "Bitte nenne keine Namen" in priv["text_de"]
    assert "Die Teilnahme ist freiwillig" in priv["text_de"]
    # liens cliquables toujours relatifs
    assert priv["url_fr"] == "/protection-des-donnees"
    assert priv["url_de"] == "/datenschutz"


def test_qr_et_liens_jamais_localhost(client):
    """Interdiction stricte: aucun lien ni QR ne doit pointer vers localhost,
    127.0.0.1, 0.0.0.0 ou une URL relative/interne."""
    import config
    interdits = ("localhost", "127.0.0.1", "0.0.0.0", "testserver")
    d = client.get("/api/config").json()
    for cle in ("qr_url_fr", "qr_url_de"):
        url = d["privacy"][cle]
        assert url.startswith("http"), (cle, url)
        assert not any(m in url for m in interdits), (cle, url)
    # cohérent avec la fonction de résolution elle-même
    for lang in ("fr", "de"):
        url = config.qr_url(lang)
        assert not any(m in url for m in interdits), url
        assert config._url_publique_utilisable(url)
    # une URL locale explicitement interdite est rejetée par le validateur
    for mauvaise in ("http://localhost:8000/x", "http://127.0.0.1/x",
                     "http://0.0.0.0/x", "/protection-des-donnees", ""):
        assert not config._url_publique_utilisable(mauvaise), mauvaise
    r = client.get("/api/qr/fr.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")
    assert len(r.content) > 100


def test_public_base_url_priorite_qr(monkeypatch):
    """PUBLIC_BASE_URL (configuré, jamais déduit de la requête) prend le
    relais si aucune PUBLIC_PRIVACY_URL_FR/DE n'est fournie."""
    import config
    monkeypatch.setattr(config, "PUBLIC_PRIVACY_URL_FR", "")
    monkeypatch.setattr(config, "PUBLIC_PRIVACY_URL_DE", "")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://busxperience.example.ch")
    assert config.qr_url("fr") == "https://busxperience.example.ch/protection-des-donnees"
    assert config.qr_url("de") == "https://busxperience.example.ch/datenschutz"
    # un PUBLIC_BASE_URL local est ignoré, on retombe sur La Poste
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "http://localhost:8000")
    assert config.qr_url("fr") == config.PRIVACY_URL_FR


def test_session_strictement_individuelle(client):
    sid = _session(client, 1)
    import db
    with db.conn() as c:
        s = c.execute("SELECT participants FROM sessions WHERE id=?", (sid,)).fetchone()
    assert s["participants"] == 1
    assert client.post("/api/sessions",
                       data={"participants": 2, "mic_ok": 1}).status_code == 400
    assert client.post("/api/sessions",
                       data={"participants": 3, "mic_ok": 1}).status_code == 400


def test_session_seulement_apres_autorisation_micro(client):
    """Aucune session n'est créée sans mic_ok=1 (l'équivalent serveur du
    consentement réellement explicite + autorisation navigateur)."""
    import db
    with db.conn() as c:
        avant = c.execute("SELECT COUNT(*) n FROM sessions").fetchone()["n"]
    r = client.post("/api/sessions", data={"lang": "fr", "participants": 1})
    assert r.status_code == 403
    r2 = client.post("/api/sessions",
                     data={"lang": "fr", "participants": 1, "mic_ok": 0})
    assert r2.status_code == 403
    with db.conn() as c:
        apres = c.execute("SELECT COUNT(*) n FROM sessions").fetchone()["n"]
    assert apres == avant


def test_consent_le_version_langue_et_code_enregistres(client):
    sid = _session(client, lang="de")
    import db
    with db.conn() as c:
        s = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    assert s["consent_audio"] == 1
    assert s["consent_le"]
    assert s["consent_version"]
    assert s["privacy_lang"] == "de"
    assert s["participant_code"] and CODE_RE.match(s["participant_code"])


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


def test_audio_nom_aleatoire_et_prive(client):
    d = client.get("/api/config").json()
    q_voix = next(q for q in d["questions"] if q["type"] == "voix")
    sid = _session(client)
    r = client.post(f"/api/sessions/{sid}/reponses",
                    data={"question_id": q_voix["id"], "cle": "reponse"},
                    files={"audio": ("x.webm", b"fake-audio-bytes", "audio/webm")})
    assert r.status_code == 200
    import db
    with db.conn() as c:
        row = c.execute("SELECT audio FROM reponses WHERE session=? AND question_id=?",
                        (sid, q_voix["id"])).fetchone()
    nom = row["audio"]
    # ancien schéma prévisible: "{session}_{question_id}.webm" (avec underscore).
    # nouveau schéma: hex aléatoire uniquement, jamais dérivé de la session/question.
    assert nom and not nom.startswith(sid) and "_" not in nom
    # jamais accessible par une URL publique
    assert client.get(f"/audio/{nom}").status_code == 404
    # accessible seulement à l'admin connecté (client anonyme, sans cookie)
    import app as module_app
    from fastapi.testclient import TestClient
    anon = TestClient(module_app.app)
    r_anon = anon.get(f"/admin/audio/{nom}")
    assert r_anon.status_code == 200 and "Mot de passe" in r_anon.text
    _login(client)
    r_admin = client.get(f"/admin/audio/{nom}")
    assert r_admin.status_code == 200 and r_admin.content == b"fake-audio-bytes"


def test_abandon_supprime_tout(client):
    d = client.get("/api/config").json()
    q_voix = next(q for q in d["questions"] if q["type"] == "voix")
    sid = _session(client)
    client.post(f"/api/sessions/{sid}/reponses",
               data={"question_id": q_voix["id"], "cle": "reponse"},
               files={"audio": ("x.webm", b"data", "audio/webm")})
    import db
    with db.conn() as c:
        nom_audio = c.execute(
            "SELECT audio FROM reponses WHERE session=?", (sid,)).fetchone()["audio"]
    assert (db.AUDIO / nom_audio).exists()
    r = client.post(f"/api/sessions/{sid}/abandonner")
    assert r.status_code == 200
    with db.conn() as c:
        assert c.execute("SELECT COUNT(*) n FROM sessions WHERE id=?", (sid,)).fetchone()["n"] == 0
        assert c.execute("SELECT COUNT(*) n FROM reponses WHERE session=?", (sid,)).fetchone()["n"] == 0
    assert not (db.AUDIO / nom_audio).exists()
    # idempotent
    assert client.post(f"/api/sessions/{sid}/abandonner").status_code == 200


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
    assert rep["titre"] and rep["label"] == "Personnalisé automatiquement"
    assert "quatre étoiles" in rep["texte"]
    assert co["nom_fr"] in rep["texte"]
    assert rep["texte"].count("\n\n") == 2
    assert 60 <= len(rep["texte"].split()) <= 90
    assert "Acte" not in rep["texte"] and "note" not in rep["texte"].lower()
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


def test_admin_buzzer_test_ne_cree_pas_de_session(client):
    _login(client)
    import db
    with db.conn() as c:
        avant = c.execute("SELECT COUNT(*) n FROM sessions").fetchone()["n"]
    h = client.get("/admin/buzzer-test").text
    assert "Tester le buzzer" in h
    assert "aucune session n'est créée" in h.lower()
    assert "/api/sessions" not in h
    with db.conn() as c:
        apres = c.execute("SELECT COUNT(*) n FROM sessions").fetchone()["n"]
    assert apres == avant
    assert "Tester le buzzer" in client.get("/admin/systeme").text


def test_systeme_bloc_protection_donnees(client):
    _login(client)
    h = client.get("/admin/systeme").text
    assert "Protection des données" in h
    assert "Consentements enregistrés" in h
    assert "Sessions sans information de consentement" in h
    assert "GEMINI_API_KEY" not in h and "ANTHROPIC_API_KEY" not in h
    # ADMIN_PASS de test n'est pas une valeur faible connue -> pas d'alerte
    assert "test-pass" not in h


def test_recherche_et_suppression_par_code(client):
    sid = _session(client)
    import db
    with db.conn() as c:
        code = c.execute("SELECT participant_code FROM sessions WHERE id=?",
                         (sid,)).fetchone()["participant_code"]
    _login(client)
    h = client.get(f"/admin/resultats?code={code}").text
    assert sid in h or "Aucune réponse" in h  # session retrouvée (peut être sans réponse)
    r = client.post("/admin/donnees/supprimer",
                    data={"portee": "code", "participant_code": code},
                    follow_redirects=False)
    assert r.status_code == 303
    with db.conn() as c:
        assert c.execute("SELECT COUNT(*) n FROM sessions WHERE id=?", (sid,)).fetchone()["n"] == 0


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
    rapport_json = json.dumps({
        "titre": "Billet clair, esprit léger",
        "paragraphe_1": (
            "Le bus fait partie de ton quotidien et ton dernier trajet obtient quatre "
            "étoiles sur cinq. La relation roule donc plutôt bien, sans être parfaite."
        ),
        "paragraphe_2": (
            "Le vrai point de tension reste le billet: dès qu'il faut deviner le bon "
            "tarif, le voyage devient un petit escape game. Un billet automatique "
            "retirerait ce casse-tête avant même le départ."
        ),
        "conclusion": "Ton verdict: monter, voyager, ne pas calculer.",
    }, ensure_ascii=False)
    monkeypatch.setattr(ai, "_http_json", lambda m, u, **k: {
        "content": [{"text": rapport_json}]})
    doc = ai.rapport_participant("fr", {"etoiles": "5"})
    assert doc["fournisseur"] == "anthropic" and doc["titre"] == "Billet clair, esprit léger"
    assert doc["label"] == "Personnalisé par IA"
    assert doc["texte"].count("\n\n") == 2
    # gemini simulé avec le même contrat JSON
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "cle-de-test")
    monkeypatch.setattr(ai, "_http_json", lambda m, u, **k: {
        "candidates": [{"content": {"parts": [{"text": rapport_json}]}}]})
    assert ai.rapport_participant("fr", {})["fournisseur"] == "gemini"
    # échec réseau: erreur propre + repli ANNONCÉ (label automatique), pas silencieux
    def kaput(m, u, **k):
        raise RuntimeError("réseau coupé")
    monkeypatch.setattr(ai, "_http_json", kaput)
    doc = ai.rapport_participant("fr", {"etoiles": "3"})
    assert doc["fournisseur"] == "none" and doc["erreur"]
    assert doc["label"] == "Personnalisé automatiquement"
    # test de connexion sans clé
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    assert ai.tester_connexion()["ok"] is False


def test_rapport_nouveau_format_dix_combinaisons(monkeypatch):
    import ai
    monkeypatch.setenv("AI_PROVIDER", "none")
    cas = [
        ("fr", {"frequence": "Chaque semaine", "etoiles": "5",
                "irritant": "Ne pas savoir quel billet acheter",
                "verbatim": "Je prendrais le bus plus souvent avec des prises USB"}),
        ("fr", {"frequence": "Presque tous les jours", "etoiles": "2",
                "irritant": "Rater la correspondance", "concept": "Garantie de correspondance"}),
        ("fr", {"frequence": "Rarement", "etoiles": "3",
                "irritant": "Attendre dans le froid ou le noir",
                "concept": "Arrêt confortable et éclairé"}),
        ("fr", {"frequence": "Quelques fois par mois", "etoiles": "4",
                "irritant": "Un bus bondé", "priorite_arbitrage": "Des bus plus fréquents"}),
        ("fr", {"frequence": "Jamais ou presque", "confiance": "3",
                "moment": "Préparer le trajet et l'horaire"}),
        ("de", {"frequence": "Jede Woche", "etoiles": "4",
                "irritant": "Eine Verspätung ohne Information",
                "concept": "Sofortige Verspätungsmeldung"}),
        ("de", {"frequence": "Selten", "etoiles": "2",
                "irritant": "Nicht wissen, welches Billett",
                "verbatim": "Ich würde öfter fahren, wenn das Billett einfacher wäre"}),
        ("de", {"frequence": "Fast täglich", "etoiles": "5",
                "irritant": "Den Anschluss verpassen", "concept": "Anschlussgarantie"}),
        ("de", {"frequence": "Ein paar Mal im Monat", "etoiles": "3",
                "irritant": "Ein überfüllter Bus"}),
        ("de", {"frequence": "Nie oder fast nie", "confiance": "2",
                "irritant": "Warten in Kälte oder Dunkelheit"}),
    ]
    for lang, donnees in cas:
        doc = ai.rapport_participant(lang, donnees)
        assert doc["titre"]
        assert doc["texte"].count("\n\n") == 2
        assert 60 <= ai._mots(doc["texte"]) <= 90
        assert not ai._FORBIDDEN_REPORT_RE.search(doc["titre"] + "\n" + doc["texte"])
        assert "concept_note" not in doc["texte"]


def test_rapport_regles_varie_la_phrase_qui_relie_au_concept_prefere(monkeypatch):
    """Constaté en usage: dès qu'aucune idée précise ne ressort du verbatim,
    la phrase qui relie le point de friction au concept préféré du
    participant était toujours exactement la même («... va donc dans la
    bonne direction: moins d'incertitude, plus de tranquillité»), quel que
    soit le concept — ça donnait l'impression d'un rapport copié-collé
    plutôt que personnel. Elle doit maintenant varier d'une génération à
    l'autre."""
    import ai
    monkeypatch.setenv("AI_PROVIDER", "none")
    donnees = {"frequence": "Chaque semaine", "etoiles": "3",
               "concept": "Un concept quelconque"}
    variantes = {ai._rapport_regles("fr", donnees)["paragraphe_2"] for _ in range(25)}
    assert len(variantes) > 1, "la phrase reliant le concept ne varie jamais"
    assert not any("va donc dans la bonne direction" in v for v in variantes)


def test_prompt_ia_demande_une_conclusion_citation_de_bonne_humeur():
    """Quand un vrai fournisseur IA est configuré (Gemini etc.), le
    "verdict" doit être généré par lui, façon citation qui donne le
    sourire — sans jamais reproduire mot pour mot une réplique protégée
    par le droit d'auteur (Disney et autres)."""
    import ai
    assert "citation" in ai.PROMPT_PARTICIPANT and "sourire" in ai.PROMPT_PARTICIPANT
    assert "droit d’auteur" in ai.PROMPT_PARTICIPANT or "droit d'auteur" in ai.PROMPT_PARTICIPANT
    # le prompt doit fournir des exemples concrets de style et interdire
    # explicitement les conclusions vagues/interchangeables observées en
    # production (ex: "de l'info avant les mauvaises surprises")
    assert "Exemples" in ai.PROMPT_PARTICIPANT
    assert "vague" in ai.PROMPT_PARTICIPANT and "interchangeable" in ai.PROMPT_PARTICIPANT
    # la conclusion doit rester en langage simple et imagé, avec une
    # ouverture (non systématique) sur des métaphores du quotidien suisse
    assert "métaphore" in ai.PROMPT_PARTICIPANT
    assert "suisse" in ai.PROMPT_PARTICIPANT.lower()


def test_verdict_du_ticket_varie_et_reste_dans_le_budget_de_mots(monkeypatch):
    """Le "verdict" final restait plat: un seul intitulé fixe par thème,
    toujours identique. Il doit maintenant varier d'une génération à
    l'autre (clin d'œil à une fable/un proverbe, jamais une citation de
    personnage sous droits d'auteur), tout en restant dans le budget de
    mots existant (60-90 mots au total) même dans les cas les plus courts
    (peu de champs renseignés)."""
    import ai
    monkeypatch.setenv("AI_PROVIDER", "none")
    donnees = {"irritant": "bus bondé", "concept": "Un concept quelconque"}
    variantes = {ai._rapport_regles("fr", donnees)["conclusion"] for _ in range(25)}
    assert len(variantes) > 1, "le verdict ne varie jamais"
    for lang in ("fr", "de"):
        for _ in range(20):
            r = ai._rapport_regles(lang, {"irritant": "rien"})
            assert 60 <= ai._mots(r["texte"]) <= 90, r["texte"]


def test_reponse_ia_invalide_ne_saffiche_jamais(monkeypatch):
    import ai
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "cle-de-test")
    monkeypatch.setattr(ai, "_http_json", lambda m, u, **k: {
        "candidates": [{"content": {"parts": [{"text":
            "Acte 1: texte cassé. Note pour le concept préféré: 3"}]}}]})
    doc = ai.rapport_participant("fr", {"etoiles": "3"})
    assert doc["fournisseur"] == "none"
    assert "Acte" not in doc["texte"]
    assert doc["erreur"]


def test_ancien_rapport_est_regenere():
    import ai
    assert not ai.rapport_cache_valide(
        "Rapport BUS XPERIENCE",
        "Acte 1: ancien texte.\n\nActe 2: suite.\n\nActe 3: fin.",
    )


# --------------------------------------------------- protection des données

def test_masquage_donnees_personnelles():
    import ai
    texte = ("Contacte-moi au 079 123 45 67 ou test@example.com, "
             "je m'appelle Jean Dupont, visite https://exemple.ch/moi maintenant, "
             "mon dossier est le 583920123.")
    masque = ai.masquer_donnees_personnelles(texte)
    assert "test@example.com" not in masque
    assert "079 123 45 67" not in masque
    assert "https://exemple.ch" not in masque
    assert "583920123" not in masque
    assert "je m'appelle Jean Dupont" not in masque


def test_aucun_audio_brut_envoye_a_gemini(monkeypatch):
    import ai
    captures = []

    def capture(methode, url, **kw):
        captures.append(kw)
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({
            "titre": "Titre test", "paragraphe_1": "a " * 40,
            "paragraphe_2": "b " * 40, "conclusion": "c"}, ensure_ascii=False)}]}}]}

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "cle-de-test")
    monkeypatch.setattr(ai, "_http_json", capture)
    ai.rapport_participant("fr", {
        "verbatim": "Une réponse vocale transcrite localement, sans info perso.",
        "etoiles": "5",
    })
    assert captures, "aucune requête interceptée"
    charge = json.dumps(captures[0], ensure_ascii=False)
    assert ".webm" not in charge
    assert "audio" not in charge.lower()
    assert "/data/" not in charge and str(Path.cwd()) not in charge


def test_pages_protection_des_donnees_accessibles(client):
    for url, mots in (("/protection-des-donnees",
                       ["Protection des données", "Responsable du traitement", "Vos droits"]),
                      ("/datenschutz",
                       ["Datenschutz", "Verantwortliche Stelle", "Ihre Rechte"])):
        r = client.get(url)
        assert r.status_code == 200
        for mot in mots:
            assert mot in r.text, (url, mot)
    # chaque page reste dans sa langue: pas de titre de section de l'autre langue
    fr = client.get("/protection-des-donnees").text
    de = client.get("/datenschutz").text
    assert "Verantwortliche Stelle" not in fr
    assert "Responsable du traitement" not in de


def test_liens_officiels_poste_corrects():
    import config
    assert config.PRIVACY_URL_FR == (
        "https://www.post.ch/fr/pages/footer/protection-des-donnees-et-informations-legales")
    assert config.PRIVACY_URL_DE == (
        "https://www.post.ch/de/pages/footer/datenschutz-und-rechtliches")


def test_cleanup_dry_run(client, capsys):
    import cleanup
    old_argv = sys.argv
    try:
        sys.argv = ["cleanup.py", "--dry-run"]
        assert cleanup.main() == 0
    finally:
        sys.argv = old_argv
    sortie = capsys.readouterr().out
    assert "simulation terminée" in sortie
    # jamais de texte de réponse dans le journal de nettoyage
    assert "Rarement" not in sortie and "correspondance" not in sortie.lower()


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


def test_arret_buzzer_present_dans_interface(client):
    """« Tu peux arrêter à tout moment » correspond à une vraie fonction:
    appui de 4 secondes + écran de confirmation, sans navigation JS classique."""
    h = client.get("/cabine/").text
    assert "STOP_PRESS=4000" in h
    assert "openStopConfirm" in h and "confirmStopDelete" in h
    assert "Arrêter et supprimer cette session ?" in h
    assert "Sitzung abbrechen und löschen?" in h


def test_rapport_storytelling_utilise_frequence_et_moment(client):
    d = client.get("/api/config").json()
    q_seg = next(q for q in d["questions"] if q["params"].get("segment"))
    q_moment = next(q for q in d["questions"]
                    if q["etape"] == "experience" and q["type"] == "choix"
                    and not q["params"].get("segment"))
    sid = _session(client)
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
    sid = _session(client)
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
    sid = _session(client)  # garantit au moins une session avant suppression globale
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


def test_consigne_ecran_vocal_juste_sous_la_question(client):
    """Sur l'écran de la question vocale, la consigne (déjà affichée via
    #voice-status: "Appuie pour répondre librement.", etc.) doit apparaître
    juste sous la question, alignée au bloc principal (regroupée avec elle
    dans .voice-heading) plutôt que dans le bandeau flottant tout en bas de
    l'écran, déconnecté visuellement de la question sur grand écran — ce
    bandeau générique redondant est donc masqué sur cet écran précis."""
    h = client.get("/cabine/").text
    m = re.search(r'<div class="voice-heading">(.*?)</div>', h, re.S)
    assert m and 'id="voice-question"' in m.group(1) and 'id="voice-status"' in m.group(1)
    hf = re.search(r"function helpText\(value\)\{([^}]*)\}", h)
    assert hf and "surEcranVocal" in hf.group(1)


def test_echelle_est_une_jauge_a_maintenir(client):
    """L'échelle par boutons (chiffres puis émojis puis barres de niveau
    cliquables) demandait toujours plusieurs pressions courtes pour
    atteindre la valeur voulue, et un essai avec des émojis faisait
    doublon avec l'écran de réaction (concept-impact) qui en affiche déjà
    juste avant dans le parcours. L'échelle est maintenant une jauge
    unique: maintenir le buzzer la remplit progressivement, la relâcher
    fige et envoie directement la valeur atteinte — un seul geste, sans
    étape de sélection puis confirmation séparée."""
    h = client.get("/cabine/").text
    assert "EMOJIS_ECHELLE" not in h and "scale-value" not in h
    assert "SCALE_FILL_MS" in h and "scale-fill" in h
    m = re.search(r"function releaseScale\(duration\)\{([^}]*)\}", h)
    assert m and "validateScale" in m.group(1) and "SCALE_FILL_MS" in m.group(1)
    # pressUp doit court-circuiter le cycle court-presse/long-presse habituel
    # pour l'échelle: le relâchement seul détermine et envoie la réponse
    pu = re.search(r"function pressUp\(directTap\)\{(.*?)\n\}", h, re.S)
    assert pu and "releaseScale(duration)" in pu.group(1)


def test_echelle_a_sa_propre_consigne_de_maintien(client):
    """Le geste de l'échelle (maintenir pour monter, relâcher pour valider)
    diffère du reste du parcours (pression courte = suivant, longue =
    valider); l'instruction affichée doit donc l'expliquer spécifiquement
    plutôt que reprendre le texte générique "Appuie pour changer"."""
    h = client.get("/cabine/").text
    assert "scaleHelp" in h and "firstScaleHint" in h
    m = re.search(r"function setHelpChoose\(\)\{([^}]*)\}", h)
    assert m and 'state==="scale"' in m.group(1)


def test_voix_compact_ios_moins_prioritaire(client):
    """Les voix "Compact" (qualité la plus basse disponible sur iOS,
    perçue comme "robotique") doivent être évitées quand une meilleure
    voix existe."""
    h = client.get("/cabine/").text
    m = re.search(r"function voiceScore\(v\)\{([^}]*)\}", h)
    assert m and '"compact"' in m.group(1) and "-4" in m.group(1)


def test_reactions_ne_se_repartissent_pas_de_facon_inegale_sur_mobile(client):
    """5 réactions avec flex:1 1 0 se répartissaient de façon inégale sur
    téléphone (ex: 4 sur une ligne puis 1 tout seul en dessous, comme
    "oublié"). En dessous de 900px, une largeur fixe à 3 par ligne doit
    donner deux lignes propres et centrées."""
    h = client.get("/cabine/").text
    m = re.search(r"@media \(max-width:900px\)\{(.*?)\n\}", h, re.S)
    assert m and "width:calc(33.333% - 8px)" in m.group(1)
