"""BUS XPERIENCE — base de données et migrations.

SQLite, migrations versionnées, sauvegarde automatique avant chaque
migration. Les données d'une ancienne installation « boite.db » (v1)
sont reprises automatiquement, jamais supprimées.
"""
from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).parent
DATA = RACINE / "data"
DB_PATH = DATA / "busxperience.db"
BACKUPS = DATA / "backups"
AUDIO = DATA / "audio"          # réponses vocales des participants
VOIX = DATA / "voix"            # voix enregistrées des questions
MEDIAS = DATA / "medias"        # musique, klaxon, images de concepts
for d in (DATA, BACKUPS, AUDIO, VOIX, MEDIAS):
    d.mkdir(parents=True, exist_ok=True)

VERSION_SCHEMA = 5


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS reglages (cle TEXT PRIMARY KEY, valeur TEXT);

CREATE TABLE IF NOT EXISTS lieux (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    remarque TEXT DEFAULT '',
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campagnes (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    actif INTEGER DEFAULT 1,
    consent_fr TEXT DEFAULT '',
    consent_de TEXT DEFAULT '',
    musique TEXT,                 -- fichier dans data/medias
    musique_volume REAL DEFAULT 0.35,
    musique_active INTEGER DEFAULT 1,
    ton TEXT DEFAULT 'complice',  -- complice | drole | sobre | institutionnel
    cree_le TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    ordre INTEGER NOT NULL DEFAULT 100,
    etape TEXT NOT NULL DEFAULT 'experience',
        -- experience | friction | idees | priorite
    type TEXT NOT NULL DEFAULT 'choix',
        -- choix | etoiles | echelle | compare | voix
    fr TEXT NOT NULL,
    de TEXT NOT NULL,
    options_fr TEXT DEFAULT '',   -- une option par ligne (choix, compare=2 lignes)
    options_de TEXT DEFAULT '',
    params TEXT DEFAULT '{}',     -- JSON: max, duree_voix, segment, libelles...
    condition TEXT DEFAULT '',    -- JSON: {"question_id":X,"valeurs":[...],"regle":"masquer_si"}
    texte_parle_fr TEXT DEFAULT '',   -- version parlée, plus courte et naturelle
    texte_parle_de TEXT DEFAULT '',
    audio_fr TEXT,
    audio_de TEXT,
    actif INTEGER DEFAULT 1,
    version INTEGER DEFAULT 1,
    modifie_le TEXT
);

CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY,
    nom_fr TEXT NOT NULL,
    nom_de TEXT NOT NULL,
    desc_fr TEXT DEFAULT '',
    desc_de TEXT DEFAULT '',
    image TEXT,                   -- fichier dans data/medias
    campagne_id INTEGER,          -- NULL = toutes campagnes
    actif INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    campagne_id INTEGER,
    lieu_id INTEGER,
    lang TEXT DEFAULT 'fr',
    participants INTEGER DEFAULT 1,
    consent_micro INTEGER DEFAULT 0,
    demarree_le TEXT NOT NULL,
    terminee_le TEXT,
    duree_s INTEGER
);

CREATE TABLE IF NOT EXISTS reponses (
    id INTEGER PRIMARY KEY,
    session TEXT NOT NULL,
    question_id INTEGER NOT NULL DEFAULT 0,
    concept_id INTEGER NOT NULL DEFAULT 0,
    cle TEXT NOT NULL DEFAULT 'reponse',   -- reponse | impact | adoption
    valeur TEXT,
    audio TEXT,
    transcript TEXT,
    cree_le TEXT NOT NULL,
    UNIQUE(session, question_id, concept_id, cle)
);

CREATE TABLE IF NOT EXISTS rapports (
    session TEXT PRIMARY KEY,
    lang TEXT,
    texte TEXT,
    titre TEXT,
    fournisseur TEXT,             -- none | ollama | gemini | anthropic
    erreur TEXT,
    cree_le TEXT
);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    detail TEXT,
    cree_le TEXT NOT NULL
);
"""


def journaliser(c, type_: str, detail: str = ""):
    c.execute("INSERT INTO journal (type, detail, cree_le) VALUES (?,?,?)",
              (type_, detail, now()))


def reglage(c, cle: str, defaut: str | None = None) -> str | None:
    r = c.execute("SELECT valeur FROM reglages WHERE cle=?", (cle,)).fetchone()
    return r["valeur"] if r else defaut


def poser_reglage(c, cle: str, valeur: str):
    c.execute("INSERT OR REPLACE INTO reglages VALUES (?,?)", (cle, str(valeur)))


# ---------------------------------------------------------------- migrations

def _sauvegarder(chemin: Path, motif: str) -> Path | None:
    if not chemin.exists():
        return None
    cible = BACKUPS / f"{chemin.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{motif}.db"
    shutil.copy2(chemin, cible)
    return cible


def _version_actuelle(c) -> int:
    try:
        r = c.execute("SELECT version FROM schema_version").fetchone()
        return r["version"] if r else 0
    except sqlite3.OperationalError:
        return 0


def _importer_v1(c) -> str:
    """Reprend les données d'une ancienne base « boite.db » (La Boîte v1)."""
    ancienne = DATA / "boite.db"
    if not ancienne.exists():
        return "aucune base v1 trouvée"
    _sauvegarder(ancienne, "avant_import_v1")
    v1 = sqlite3.connect(ancienne)
    v1.row_factory = sqlite3.Row
    n = {"lieux": 0, "sessions": 0, "reponses": 0}
    try:
        for r in v1.execute("SELECT * FROM lieux"):
            c.execute("INSERT OR IGNORE INTO lieux (id, nom, remarque, cree_le) VALUES (?,?,?,?)",
                      (r["id"], r["nom"], r["remarque"], r["cree_le"]))
            n["lieux"] += 1
        for r in v1.execute("SELECT * FROM sessions"):
            c.execute("""INSERT OR IGNORE INTO sessions
                         (id, lieu_id, lang, demarree_le) VALUES (?,?,?,?)""",
                      (r["id"], r["lieu_id"], r["lang"], r["cree_le"]
                       if "cree_le" in r.keys() else now()))
            n["sessions"] += 1
    except sqlite3.OperationalError:
        pass
    try:
        for r in v1.execute("SELECT * FROM reponses"):
            c.execute("""INSERT OR IGNORE INTO reponses
                         (session, question_id, concept_id, cle, valeur, audio, transcript, cree_le)
                         VALUES (?,?,0,'reponse',?,?,?,?)""",
                      (r["session"], r["question_id"] or 0, r["choix"],
                       r["audio"], r["transcript"], r["cree_le"]))
            n["reponses"] += 1
    except sqlite3.OperationalError:
        pass
    v1.close()
    return f"import v1: {n}"


def migrer() -> list[str]:
    """Applique les migrations manquantes. Sauvegarde avant. Idempotent."""
    journal_migration: list[str] = []
    with conn() as c:
        version = _version_actuelle(c)
        if version < VERSION_SCHEMA:
            sauvegarde = _sauvegarder(DB_PATH, f"avant_v{VERSION_SCHEMA}")
            if sauvegarde:
                journal_migration.append(f"sauvegarde: {sauvegarde.name}")
            c.executescript(SCHEMA_V2)
            for alt in ("ALTER TABLE questions ADD COLUMN texte_parle_fr TEXT DEFAULT ''",
                        "ALTER TABLE questions ADD COLUMN texte_parle_de TEXT DEFAULT ''",
                        # v5: consentement micro explicite, plus de mécanisme ambigu
                        # consent_micro. Les anciennes colonnes sont conservées
                        # (jamais supprimées) pour ne jamais casser des données
                        # existantes, mais ne sont plus utilisées comme logique.
                        "ALTER TABLE sessions ADD COLUMN consent_audio INTEGER DEFAULT 0",
                        "ALTER TABLE sessions ADD COLUMN consent_le TEXT",
                        "ALTER TABLE sessions ADD COLUMN consent_version TEXT",
                        "ALTER TABLE sessions ADD COLUMN privacy_lang TEXT",
                        "ALTER TABLE sessions ADD COLUMN participant_code TEXT"):
                try:
                    c.execute(alt)
                except sqlite3.OperationalError:
                    pass
            for cle, val in (("tts_voix_fr", "auto"), ("tts_voix_de", "auto"),
                             ("tts_vitesse", "0.97"), ("tts_tonalite", "1.05"),
                             ("klaxon_actif", "1"), ("klaxon_volume", "0.9"),
                             ("buzzer_unique", "1"), ("lecture_vitesse", "normale"),
                             ("etoiles_delai_ms", "2500")):
                if reglage(c, cle) is None:
                    poser_reglage(c, cle, val)
            if version == 0:
                detail = _importer_v1(c)
                journal_migration.append(detail)
            if 0 < version < 4:
                # v4: la question vocale par défaut devient une phrase à compléter
                c.execute("""UPDATE questions SET
                    fr='Termine cette phrase : je prendrais le bus plus souvent si…',
                    de='Vervollständige diesen Satz: Ich würde öfter den Bus nehmen, wenn…',
                    texte_parle_fr='Termine cette phrase… je prendrais le bus plus souvent si…',
                    texte_parle_de='Vervollständige den Satz… ich würde öfter den Bus nehmen, wenn…',
                    version=version+1, modifie_le=?
                    WHERE type='voix'
                    AND fr='Si tu pouvais changer une seule chose dans l''expérience du bus, tu changerais quoi en premier ?'""",
                    (now(),))
            c.execute("DELETE FROM schema_version")
            c.execute("INSERT INTO schema_version VALUES (?)", (VERSION_SCHEMA,))
            journaliser(c, "migration",
                        f"v{version} -> v{VERSION_SCHEMA}; " + "; ".join(journal_migration))
            journal_migration.append(f"schéma v{VERSION_SCHEMA} appliqué")
        else:
            journal_migration.append(f"schéma déjà en v{version}, rien à faire")
    return journal_migration


_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # sans 0/O/1/I, ambiguïté réduite


def code_participant() -> str:
    """Code court, aléatoire et facile à recopier: BX-XXXX-XXXX."""
    groupe = lambda: "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
    return f"BX-{groupe()}-{groupe()}"


def supprimer_sessions(c, ids: list[str]) -> dict:
    """Supprime intégralement des sessions: réponses, audios, transcriptions
    (incluses dans les réponses) et rapports. Ne touche jamais aux questions,
    concepts, campagnes, réglages ni médias. Utilisé par l'admin (zone
    dangereuse) et par l'abandon volontaire pendant le parcours."""
    n = {"sessions": 0, "reponses": 0, "audios": 0, "rapports": 0}
    if not ids:
        return n
    marque = ",".join("?" * len(ids))
    for r in c.execute(
            f"SELECT audio FROM reponses WHERE session IN ({marque})"
            " AND audio IS NOT NULL", ids):
        chemin = AUDIO / r["audio"]
        if chemin.exists():
            chemin.unlink()
            n["audios"] += 1
    n["reponses"] = c.execute(
        f"DELETE FROM reponses WHERE session IN ({marque})", ids).rowcount
    n["rapports"] = c.execute(
        f"DELETE FROM rapports WHERE session IN ({marque})", ids).rowcount
    n["sessions"] = c.execute(
        f"DELETE FROM sessions WHERE id IN ({marque})", ids).rowcount
    return n


def parse_json(texte: str | None, defaut=None):
    if not texte:
        return defaut if defaut is not None else {}
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        return defaut if defaut is not None else {}


MEDIAS_DEFAUT = RACINE / "medias-defaut"


def copier_medias_defaut() -> list[str]:
    """Copie klaxon et musique fournis avec le projet vers data/medias
    s'ils n'y sont pas déjà. Jamais d'écrasement."""
    copies = []
    if MEDIAS_DEFAUT.exists():
        for f in MEDIAS_DEFAUT.iterdir():
            cible = MEDIAS / f.name
            if f.is_file() and not cible.exists():
                shutil.copy2(f, cible)
                copies.append(f.name)
    return copies
