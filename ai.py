"""BUS XPERIENCE — intelligence artificielle facultative.

Architecture commune pour quatre fournisseurs: none, ollama, gemini,
anthropic. AI_PROVIDER=none est le défaut et produit déjà un rapport
participant personnel et drôle grâce à des règles et modèles variés.
Aucune bascule silencieuse: si le fournisseur configuré échoue, l’erreur
est journalisée et le mode automatique prend le relais EN LE DISANT.
Les fichiers audio bruts ne quittent jamais la machine, seuls des textes
déjà transcrits localement peuvent être envoyés à un fournisseur externe
explicitement activé.
"""
from __future__ import annotations

import json
import os
import random
import re

import requests

PROVIDERS = ("none", "ollama", "gemini", "anthropic")

# ---------------------------------------------------------------- PII

# Nettoyage best-effort avant tout envoi externe. Cette détection n'est PAS
# parfaite (ce serait prétendre à une garantie qui n'existe pas): elle réduit
# le risque évident (adresse e-mail, téléphone, URL, suite de chiffres
# ressemblant à un identifiant, "je m'appelle …") sans se substituer à la
# consigne donnée au participant de ne pas se nommer.
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_RE_TEL = re.compile(r"(?:\+?\d[\d .\-/]{6,}\d)")
_RE_ID_NUM = re.compile(r"\b\d{5,}\b")
_RE_NOM = re.compile(
    r"\b(?:je\s+m['’]appelle|mon\s+nom\s+est|ich\s+hei(?:ss|ß)e|"
    r"mein\s+name\s+ist)\b[^.!?\n]*", re.IGNORECASE)


def masquer_donnees_personnelles(texte: str) -> str:
    """Masque au mieux les informations personnelles évidentes d’un texte
    avant tout envoi à un fournisseur IA externe. Ne garantit pas
    l’exhaustivité."""
    if not isinstance(texte, str) or not texte:
        return texte
    t = _RE_NOM.sub("[information personnelle retirée]", texte)
    t = _RE_EMAIL.sub("[e-mail retiré]", t)
    t = _RE_URL.sub("[lien retiré]", t)
    t = _RE_TEL.sub("[numéro retiré]", t)
    t = _RE_ID_NUM.sub("[nombre retiré]", t)
    return t


def provider_actuel() -> str:
    p = os.environ.get("AI_PROVIDER", "none").strip().lower()
    return p if p in PROVIDERS else "none"


def modele_actuel(provider: str) -> str:
    defauts = {"ollama": "llama3.2", "gemini": "gemini-2.0-flash",
               "anthropic": "claude-sonnet-4-6"}
    return os.environ.get("AI_MODEL", "") or defauts.get(provider, "")


def _http_json(methode: str, url: str, **kw) -> dict:
    """Point d’entrée réseau unique, remplacé par un mock dans les tests."""
    r = requests.request(methode, url, timeout=kw.pop("timeout", 60), **kw)
    r.raise_for_status()
    return r.json()


def generer(system: str, user: str, provider: str | None = None,
            max_tokens: int = 600) -> tuple[str | None, str | None]:
    """Retourne (texte, erreur). texte=None si provider none ou échec."""
    provider = provider or provider_actuel()
    modele = modele_actuel(provider)
    try:
        if provider == "none":
            return None, None
        if provider == "ollama":
            base = os.environ.get("OLLAMA_URL", "http://localhost:11434")
            d = _http_json("POST", f"{base}/api/chat", json={
                "model": modele, "stream": False,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]})
            return d["message"]["content"].strip(), None
        if provider == "gemini":
            cle = os.environ.get("GEMINI_API_KEY", "")
            if not cle:
                return None, "GEMINI_API_KEY manquant"
            d = _http_json(
                "POST",
                f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent",
                params={"key": cle},
                json={"system_instruction": {"parts": [{"text": system}]},
                      "contents": [{"parts": [{"text": user}]}],
                      "generationConfig": {"maxOutputTokens": max_tokens}})
            return d["candidates"][0]["content"]["parts"][0]["text"].strip(), None
        if provider == "anthropic":
            cle = os.environ.get("ANTHROPIC_API_KEY", "")
            if not cle:
                return None, "ANTHROPIC_API_KEY manquant"
            d = _http_json(
                "POST", "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": cle, "anthropic-version": "2023-06-01"},
                json={"model": modele, "max_tokens": max_tokens, "system": system,
                      "messages": [{"role": "user", "content": user}]})
            return d["content"][0]["text"].strip(), None
    except Exception as e:  # réseau, quota, format: on remonte, on n'invente pas
        return None, f"{type(e).__name__}: {e}"
    return None, f"fournisseur inconnu: {provider}"


def tester_connexion(provider: str | None = None) -> dict:
    provider = provider or provider_actuel()
    if provider == "none":
        return {"provider": "none", "ok": True,
                "detail": "Mode automatique sans IA, toujours disponible."}
    texte, erreur = generer("Réponds uniquement: OK", "Test de connexion.",
                            provider=provider, max_tokens=10)
    return {"provider": provider, "modele": modele_actuel(provider),
            "ok": bool(texte), "detail": erreur or (texte or "")[:80]}


# ================================================================ rapport
# participant. Deux moteurs partagent le même contrat de sortie:
# un titre, deux paragraphes courts et une conclusion. Le mode automatique
# reste soigné quand aucun fournisseur IA n'est configuré ou disponible.

TONS = {
    "complice": "chaleureux, complice et légèrement drôle",
    "drole": "drôle avec finesse, sans moquerie ni effet forcé",
    "sobre": "simple, fluide et souriant",
    "institutionnel": "professionnel, humain et très légèrement souriant",
}

CATEGORIES_VISUELLES = (
    "panorama", "ponctualite", "information", "confort", "affluence",
    "securite", "prix", "correspondance", "dernier_kilometre", "generique",
)

PROMPT_PARTICIPANT = """Tu écris le profil de voyage BUS XPERIENCE d'une seule
personne, à partir de ses réponses réelles à un parcours BUS XPERIENCE
(réponses structurées, préférences, frustrations, transcriptions vocales,
innovations évaluées et leur potentiel d'adoption). Langue: {langue}. Ton:
{ton}.

Le profil doit provoquer, dans cet ordre, trois réactions chez la personne
qui le lit: « c'est moi », puis « c'est drôle », puis « cette conclusion est
utile ». Sélectionne seulement les informations réellement intéressantes
dans les données fournies; n'invente jamais un fait absent des réponses et
ne cherche jamais à tout reprendre. N'écris ni un simple résumé, ni un
langage institutionnel.

Réponds uniquement avec ce JSON strict, exactement ces six clés:
{{"titre_profil":"...","plaisir":"...","friction":"...","idee_a_tester":"...","verdict":"...","categorie_visuelle":"..."}}

Contenu attendu pour chaque clé:
- titre_profil: un nom de profil court, amusant et mémorable, 3 à 7 mots,
  qui tient sur deux lignes maximum à l'affichage;
- plaisir: ce que la personne apprécie réellement dans le bus, fondé sur une
  préférence qu'elle a vraiment exprimée, 15 à 28 mots;
- friction: son principal point de friction, fondé sur un problème qu'elle a
  vraiment exprimé, 15 à 28 mots;
- idee_a_tester: une solution concrète, réaliste et testable par CarPostal
  pour répondre à cette friction, 10 à 20 mots;
- verdict: une excellente punchline personnelle, intelligente et légèrement
  impertinente, qui conclut le profil avec humour, 12 à 25 mots;
- categorie_visuelle: exactement une valeur parmi panorama, ponctualite,
  information, confort, affluence, securite, prix, correspondance,
  dernier_kilometre, generique — celle qui correspond le mieux au sujet
  principal du profil (utilise "generique" si aucune ne convient vraiment).

Exemple du niveau de qualité attendu (uniquement pour le style et le
calibrage des longueurs, ne recopie jamais ces phrases telles quelles, et
n'utilise ce clin d'œil suisse que si les réponses réelles s'y prêtent):
{{"titre_profil":"Le guetteur du premier rang","plaisir":"Tu montes rarement dans le bus, mais quand tu le fais, tu choisis la fenêtre et tu regardes le monde passer.","friction":"Tu acceptes qu'un trajet prenne du retard. Beaucoup moins que personne ne te dise pourquoi.","idee_a_tester":"Une information immédiate en cas de retard, avec une alternative claire.","verdict":"Tu n'exiges pas la précision d'une montre suisse. Juste qu'on te dise pourquoi elle retarde.","categorie_visuelle":"panorama"}}

Contraintes absolues:
- ne reproduis jamais un nom de personne, numéro de téléphone, adresse
  postale, e-mail ou autre information personnelle qui aurait pu être
  prononcée par erreur dans une transcription; si une telle information
  apparaît dans les données, ignore-la simplement;
- tutoiement en français, «du» en allemand;
- aucun genre supposé;
- aucun «Acte 1», «Acte 2», «Acte 3» ou structure annoncée;
- aucun nom technique de question, numéro de question, score de concept,
  valeur brute incompréhensible, JSON visible ou formule administrative;
- ne jamais écrire «le répondant a indiqué» ni son équivalent;
- ne pas recopier une transcription maladroite: reformule-la sans en changer le sens;
- vocabulaire simple et concret partout: une image ou métaphore facile à
  visualiser plutôt qu'une formule abstraite;
- un seul clin d'œil suisse maximum sur l'ensemble du ticket (montre
  suisse, fondue, raclette, chocolat, montagne, météo, précision, etc.), et
  seulement s'il sert directement le verdict — jamais ajouté artificiellement,
  jamais dans plusieurs champs à la fois;
- n'invente jamais de citation et ne mentionne jamais Einstein ni aucune
  autre personnalité, réelle ou fictive;
- ne recopie jamais mot pour mot une réplique de film, de dessin animé ou
  de toute autre œuvre protégée par le droit d'auteur;
- ne répète dans aucune valeur JSON l'intitulé de sa propre rubrique
  («Ton verdict», «Ton plaisir», «Ce qui te refroidit», etc.) ni aucun
  équivalent dans l'autre langue: le texte va directement au contenu;
- écris directement en français ou en allemand naturel selon la langue
  demandée, jamais une traduction littérale de l'autre langue;
- aucun markdown, aucun emoji.

Réponds uniquement avec le JSON demandé, rien d'autre."""

# Plus de 50 titres par langue, organisés par thème. Aucun titre ne suppose
# le genre de la personne.
TITRES = {
    "fr": {
        "correspondance": [
            "Mission correspondance sans sprint",
            "Correspondances sans cardio obligatoire",
            "Plan anti-correspondance ratée",
            "Cap sur la bonne connexion",
            "Timing parfait, chaussures tranquilles",
            "Changer de bus sans battre un record",
        ],
        "retard": [
            "Retard annoncé, stress évité",
            "Le radar des bus portés disparus",
            "Mission temps réel, zéro mystère",
            "Des horaires qui disent la vérité",
            "Attendre, oui — deviner, non",
            "Plan anti-retard surprise",
        ],
        "attente": [
            "Attendre au sec, enfin",
            "Prochain arrêt: pieds au chaud",
            "Lumière allumée, attente apaisée",
            "Mission abribus vraiment accueillant",
            "Un siège avant même le voyage",
            "L’arrêt où l’on se sent bien",
        ],
        "confort": [
            "Confort à bord, esprit léger",
            "Mission voyage sans contorsion",
            "Le trajet qui ménage le dos",
            "Place assise, humeur debout",
            "Le bus version grand confort",
            "Plus de douceur par kilomètre",
        ],
        "billet": [
            "Billet clair, esprit léger",
            "Mission tarif sans casse-tête",
            "Monter plutôt que calculer",
            "Le bon prix, sans mode d’emploi",
            "Zéro question avant de voyager",
            "Trajet simple, billet compris",
        ],
        "foule": [
            "Plus d’espace, moins de Tetris",
            "Mission bus sans compression",
            "Voyager sans jouer des coudes",
            "Un peu d’air entre deux arrêts",
            "Le confort sans foule compacte",
            "Place personnelle en circulation",
        ],
        "frequence": [
            "Plus de bus, moins d’attente",
            "Mission prochain départ bientôt",
            "Un horaire qui laisse le choix",
            "Le bus quand on en a besoin",
            "Cadence fluide, journée tranquille",
            "Moins d’attente entre deux idées",
        ],
        "ponctualite": [
            "Ponctuel, le nouveau premium",
            "Mission neuf heures à neuf heures",
            "La minute juste au bon endroit",
            "Un bus qui tient parole",
            "Cap sur l’arrivée à l’heure",
            "L’horaire sans suspense final",
        ],
        "telephone": [
            "Batterie pleine jusqu’au terminus",
            "USB contre la panique du 1 %",
            "Le trajet qui recharge aussi",
            "Mission téléphone encore vivant",
            "Prises branchées, voyage détendu",
            "Arriver avec plus de batterie",
        ],
        "panorama": [
            "Premier rang, vue panoramique",
            "Fenêtre ouverte sur le trajet",
            "Le bus en version grand écran",
            "Cap sur la meilleure place",
            "Panorama inclus dans le billet",
            "Un trajet avec vue",
        ],
        "defaut": [
            "Le bus avec moins de points d’interrogation",
            "Prochain arrêt: plus simple",
            "Cinq minutes, une idée très claire",
            "Le bus de demain écoute déjà",
            "Plus de sérénité par kilomètre",
            "Monter simplement, arriver mieux",
        ],
    },
    "de": {
        "correspondance": [
            "Mission Anschluss ohne Sprint",
            "Umsteigen ohne Pulsrekord",
            "Plan gegen verpasste Anschlüsse",
            "Kurs auf die richtige Verbindung",
            "Gutes Timing, ruhige Schuhe",
            "Anschluss geschafft, ganz ohne Rennen",
        ],
        "retard": [
            "Verspätung ja, Überraschung nein",
            "Radar für verschwundene Busse",
            "Mission Echtzeit statt Rätselraten",
            "Fahrpläne, die ehrlich bleiben",
            "Warten ja, raten nein",
            "Plan gegen Verspätungsüberraschungen",
        ],
        "attente": [
            "Warten, aber bitte trocken",
            "Nächster Halt: warme Füsse",
            "Licht an, Anspannung aus",
            "Mission Haltestelle zum Wohlfühlen",
            "Ein Sitzplatz vor der Fahrt",
            "Warten ohne Wetterprüfung",
        ],
        "confort": [
            "Komfort an Bord, Kopf frei",
            "Mission Fahrt ohne Verrenkung",
            "Eine Reise, die den Rücken schont",
            "Sitzplatz da, Laune oben",
            "Busfahren mit Komfortmodus",
            "Mehr Ruhe pro Kilometer",
        ],
        "billet": [
            "Billett klar, Kopf frei",
            "Mission Tarif ohne Denksport",
            "Einsteigen statt rechnen",
            "Der richtige Preis, ganz einfach",
            "Fahren ohne Billett-Fragezeichen",
            "Einfache Reise, Billett inklusive",
        ],
        "foule": [
            "Mehr Platz, weniger Tetris",
            "Mission Bus ohne Kompression",
            "Fahren ohne Ellbogenprogramm",
            "Etwas Luft zwischen zwei Halten",
            "Komfort ohne Gedränge",
            "Persönlicher Raum in Bewegung",
        ],
        "frequence": [
            "Mehr Bus, weniger Warten",
            "Mission nächste Abfahrt bald",
            "Ein Fahrplan mit echter Auswahl",
            "Der Bus, wenn man ihn braucht",
            "Guter Takt, ruhiger Tag",
            "Weniger Pause zwischen zwei Plänen",
        ],
        "ponctualite": [
            "Pünktlich ist das neue Premium",
            "Mission neun Uhr um neun",
            "Die richtige Minute am richtigen Ort",
            "Ein Bus, der Wort hält",
            "Kurs auf pünktliche Ankunft",
            "Fahrplan ohne Schluss-Spannung",
        ],
        "telephone": [
            "Akku voll bis zur Endstation",
            "USB gegen die Ein-Prozent-Panik",
            "Eine Fahrt, die auch auflädt",
            "Mission Handy noch am Leben",
            "Steckdose an, Reise entspannt",
            "Mit mehr Akku ankommen",
        ],
        "panorama": [
            "Erste Reihe mit Panoramablick",
            "Fensterplatz für die ganze Strecke",
            "Busfahren im Grossbildformat",
            "Kurs auf den besten Platz",
            "Panorama im Billett inbegriffen",
            "Eine Fahrt mit Aussicht",
        ],
        "defaut": [
            "Busfahren mit weniger Fragezeichen",
            "Nächster Halt: einfacher",
            "Fünf Minuten, eine klare Ansage",
            "Der Bus von morgen hört schon zu",
            "Mehr Gelassenheit pro Kilometer",
            "Einfach einsteigen, besser ankommen",
        ],
    },
}

_MOTS_CLES = [
    ("telephone", ["usb", "batterie", "recharger", "akku", "laden", "steckdose"]),
    ("panorama", ["panoram", "tout devant", "fenêtre", "fenster", "ganz vorne"]),
    ("correspondance", ["correspondance", "anschluss", "umsteigen"]),
    ("retard", ["retard", "information", "verspätung", "temps réel", "echtzeit"]),
    ("attente", ["attendre", "arrêt", "froid", "noir", "warten", "haltestelle", "kälte", "dunkel"]),
    ("foule", ["bondé", "foule", "überfüllt", "gedränge"]),
    ("billet", ["billet", "payer", "tarif", "billett", "bezahlen", "preis"]),
    ("ponctualite", ["ponctuel", "à l'heure", "pünktlich"]),
    ("frequence", ["fréquent", "plus souvent", "häufiger", "öfter"]),
    ("confort", ["siège", "confort", "sitz", "komfort"]),
]

_DERNIERS_CHOIX: dict[str, str] = {}
_FORBIDDEN_REPORT_RE = re.compile(
    r"\b(acte\s*[123]|akt\s*[123]|paragraphe[_ ]?[12]|concept[_ ]?note|"
    r"note\s+(?:du|pour le)\s+concept|concept\s+préféré\s*[:=]|"
    r"lieblingskonzept\s*[:=]|le répondant|la répondante|befragte person|"
    r"rapport bus xperience|rapport officiel)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿÄÖÜäöü]+(?:['’\-][0-9A-Za-zÀ-ÖØ-öø-ÿÄÖÜäöü]+)*")


def _choix_sans_repetition(cle: str, pool: list[str]) -> str:
    disponibles = [x for x in pool if x != _DERNIERS_CHOIX.get(cle)] or pool
    choix = random.choice(disponibles)
    _DERNIERS_CHOIX[cle] = choix
    return choix


def _categorie(donnees: dict) -> str:
    corpus = " ".join(str(v) for v in donnees.values()).lower()
    for cle, mots in _MOTS_CLES:
        if any(mot in corpus for mot in mots):
            return cle
    return "defaut"


def _choisir_titre(lang: str, donnees: dict) -> str:
    langue = "de" if lang == "de" else "fr"
    categorie = _categorie(donnees)
    return _choix_sans_repetition(
        f"titre:{langue}:{categorie}", TITRES[langue][categorie]
    )


def _mots(texte: str) -> int:
    return len(_WORD_RE.findall(texte or ""))


def _nettoyer_fragment(valeur: object, max_chars: int = 420) -> str:
    if not isinstance(valeur, str):
        return ""
    texte = valeur.replace("```json", "").replace("```", "")
    texte = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip(" \t\r\n-–—")
    return texte[:max_chars].strip()


def _quotes_equilibrees(texte: str) -> bool:
    if texte.count("«") != texte.count("»"):
        return False
    # Les guillemets droits doivent aller par paire. Les apostrophes ne comptent pas.
    return texte.count('"') % 2 == 0


def _extraire_json(texte: str) -> dict | None:
    if not isinstance(texte, str):
        return None
    propre = texte.strip().replace("```json", "").replace("```", "").strip()
    debut, fin = propre.find("{"), propre.rfind("}")
    if debut < 0 or fin <= debut:
        return None
    try:
        doc = json.loads(propre[debut:fin + 1])
    except (json.JSONDecodeError, TypeError):
        return None
    return doc if isinstance(doc, dict) else None


# Longueur attendue (en mots) pour chaque champ du nouveau contrat de
# rapport. Partagée entre la validation de la réponse IA et le moteur de
# règles (qui doit lui aussi respecter ces bornes par construction).
_LONGUEURS_CHAMPS = {
    "titre_profil": (3, 7),
    "plaisir": (15, 28),
    "friction": (15, 28),
    "idee_a_tester": (10, 20),
    "verdict": (12, 25),
}

# Un fournisseur IA respecte rarement à 100% la consigne "ne répète pas
# l'intitulé de la rubrique dans la valeur": on nettoie ce préfixe s'il
# apparaît malgré tout, plutôt que de rejeter toute la réponse pour ça.
_RE_PREFIXE_RUBRIQUE = re.compile(
    r"^(ton\s+plaisir|ce\s+qui\s+te\s+refroidit|"
    r"l['’]idée\s+qui\s+te\s+ferait\s+remonter\s+à\s+bord|ton\s+verdict|"
    r"ton\s+profil(?:\s+de\s+voyage)?|deine\s+freude|was\s+dich\s+abkühlt|"
    r"deine\s+comeback[- ]idee|dein\s+fazit|dein\s+reiseprofil)\s*[:\-–—]\s*",
    re.IGNORECASE,
)


def _sans_guillemets_englobants(texte: str) -> str:
    """Retire une seule paire de guillemets qui engloberait tout le texte
    (Gemini renvoie parfois «comme ceci» au lieu de comme ceci)."""
    t = texte.strip()
    for ouvre, ferme in (("«", "»"), ("“", "”"), ('"', '"'), ("'", "'")):
        if len(t) >= 2 and t.startswith(ouvre) and t.endswith(ferme):
            return t[len(ouvre):-len(ferme)].strip()
    return t


def _valider_rapport_ia(texte: str) -> dict | None:
    doc = _extraire_json(texte)
    if not doc:
        return None
    cles = ("titre_profil", "plaisir", "friction", "idee_a_tester", "verdict")
    if any(not isinstance(doc.get(cle), str) for cle in cles):
        return None
    propre = {}
    for cle in cles:
        valeur = _nettoyer_fragment(doc[cle], 90 if cle == "titre_profil" else 260)
        valeur = _RE_PREFIXE_RUBRIQUE.sub("", valeur, count=1).strip()
        valeur = _sans_guillemets_englobants(valeur)
        propre[cle] = valeur
    if any(not propre[cle] for cle in cles):
        return None
    for cle, (mini, maxi) in _LONGUEURS_CHAMPS.items():
        if not mini <= _mots(propre[cle]) <= maxi:
            return None
    categorie = doc.get("categorie_visuelle")
    categorie = categorie.strip().lower() if isinstance(categorie, str) else ""
    if categorie not in CATEGORIES_VISUELLES:
        categorie = "generique"
    tout = " ".join(propre.values())
    if _FORBIDDEN_REPORT_RE.search(tout) or "{" in tout or "}" in tout:
        return None
    if "einstein" in tout.lower():
        return None
    if not _quotes_equilibrees(tout):
        return None
    return {**propre, "categorie_visuelle": categorie}


def rapport_cache_valide(doc: dict) -> bool:
    """Écarte les rapports d’un ancien format ou incomplets afin qu’ils
    soient régénérés après une mise à jour du contrat de sortie."""
    if not isinstance(doc, dict):
        return False
    cles = ("titre_profil", "plaisir", "friction", "idee_a_tester", "verdict")
    valeurs = {cle: _nettoyer_fragment(doc.get(cle) or "", 260) for cle in cles}
    if any(not v for v in valeurs.values()):
        return False
    if _FORBIDDEN_REPORT_RE.search(" ".join(valeurs.values())):
        return False
    for cle, (mini, maxi) in _LONGUEURS_CHAMPS.items():
        if not mini <= _mots(valeurs[cle]) <= maxi:
            return False
    return doc.get("categorie_visuelle") in CATEGORIES_VISUELLES


def _entier(d: dict, cle: str, mini: int, maxi: int) -> int | None:
    try:
        valeur = int(float(str(d.get(cle, "")).replace(",", ".")))
    except (TypeError, ValueError):
        return None
    return valeur if mini <= valeur <= maxi else None


def _profil_frequence(valeur: str, lang: str) -> str:
    v = (valeur or "").lower()
    if any(x in v for x in ("tous les jours", "presque tous", "fast täglich", "täglich")):
        return "quotidien"
    if any(x in v for x in ("semaine", "woche")):
        return "hebdo"
    if any(x in v for x in ("mois", "monat")):
        return "mensuel"
    if any(x in v for x in ("jamais", "nie")):
        return "jamais"
    if any(x in v for x in ("rare", "selten")):
        return "rare"
    return "inconnu"


# plaisir: fondé sur la fréquence réellement déclarée (un vrai signal de
# préférence exprimée) plutôt que sur un fait qui pourrait ne pas avoir été
# communiqué. Deux variantes par profil, tirées au sort sans répétition
# immédiate — toutes vérifiées entre 15 et 28 mots.
_PLAISIR_FR = {
    "quotidien": [
        "Le bus fait clairement partie de ton quotidien, et ça se voit: tu montes presque sans y penser, comme un réflexe bien rodé.",
        "Tu prends le bus tous les jours ou presque, et cette habitude a quelque chose de rassurant: un vrai point fixe dans ta journée.",
    ],
    "hebdo": [
        "Le bus et toi, vous avez un vrai rythme: chaque semaine, ce même trajet trouve naturellement sa place dans ton quotidien.",
        "Une ou deux fois par semaine, tu retrouves le bus avec une aisance qui montre que le trajet fait déjà partie de tes habitudes.",
    ],
    "mensuel": [
        "Le bus et toi, c’est une habitude choisie plutôt que subie: quelques fois par mois, et toujours avec le même naturel.",
        "Tu montes dans le bus quelques fois par mois, juste assez pour apprécier ce moment sans qu’il devienne une contrainte du quotidien.",
    ],
    "rare": [
        "Le bus reste une relation occasionnelle, mais assumée: quand tu montes à bord, c’est toujours par choix, jamais par défaut.",
        "Tu ne prends le bus que rarement, mais chaque trajet compte double: une vraie petite parenthèse plutôt qu’une habitude banale.",
    ],
    "jamais": [
        "Le bus et toi, c’est une histoire qui commence à peine, avec la curiosité de qui découvre un tout nouveau trajet.",
        "Tu ne prends presque jamais le bus, ce qui rend ce moment un peu à part: l’occasion parfaite pour se faire un premier avis.",
    ],
    "inconnu": [
        "Le bus et toi partagez déjà quelques kilomètres, assez pour savoir ce qui, dans ce trajet, te convient vraiment le mieux.",
        "Ta relation avec le bus a déjà pris forme, avec ses petites habitudes et ce que tu apprécies sans même y penser.",
    ],
}
_PLAISIR_DE = {
    "quotidien": [
        "Der Bus gehört klar zu deinem Alltag, das merkt man: Du steigst fast automatisch ein, wie ein gut eingespielter Reflex.",
        "Du fährst fast täglich Bus, und diese Gewohnheit hat etwas Beruhigendes: ein richtiger fester Punkt in deinem Tag.",
    ],
    "hebdo": [
        "Du und der Bus, ihr habt einen echten Rhythmus: Jede Woche findet diese Fahrt ganz natürlich ihren Platz in deinem Alltag.",
        "Ein- oder zweimal pro Woche triffst du den Bus mit einer Selbstverständlichkeit, die zeigt: Diese Fahrt gehört schon zur Gewohnheit.",
    ],
    "mensuel": [
        "Du und der Bus, das ist eine bewusst gewählte statt aufgezwungene Gewohnheit: ein paar Mal im Monat, immer mit derselben Selbstverständlichkeit.",
        "Du fährst ein paar Mal im Monat Bus, gerade genug, um den Moment zu geniessen, ohne dass er zur Last wird.",
    ],
    "rare": [
        "Der Bus bleibt eine gelegentliche Beziehung, aber eine bewusste: Wenn du einsteigst, dann immer aus eigener Wahl, nie aus Mangel an Alternativen.",
        "Du fährst nur selten Bus, aber jede Fahrt zählt doppelt: eine echte kleine Auszeit statt einer banalen Gewohnheit.",
    ],
    "jamais": [
        "Du und der Bus, diese Geschichte fängt gerade erst an, mit der Neugier von jemandem, der eine neue Strecke entdeckt.",
        "Du fährst fast nie Bus, was diesen Moment etwas Besonderes macht: die perfekte Gelegenheit für einen ersten echten Eindruck.",
    ],
    "inconnu": [
        "Du und der Bus, ihr habt schon einige Kilometer gemeinsam, genug, um zu wissen, was an dieser Fahrt wirklich zu dir passt.",
        "Deine Beziehung zum Bus hat schon Form angenommen, mit ihren kleinen Gewohnheiten und dem, was dir gefällt, ohne dass du gross darüber nachdenkst.",
    ],
}


def _phrase_plaisir(lang: str, d: dict) -> str:
    profil = _profil_frequence(str(d.get("frequence") or ""), lang)
    pool = _PLAISIR_FR if lang != "de" else _PLAISIR_DE
    return _choix_sans_repetition(f"plaisir:{lang}:{profil}", pool[profil])


def _theme_irritant(d: dict) -> str:
    texte = " ".join(str(d.get(k) or "") for k in ("irritant", "moment")).lower()
    if any(x in texte for x in ("correspondance", "anschluss", "umsteigen")):
        return "correspondance"
    if any(x in texte for x in ("retard", "verspätung", "information")):
        return "retard"
    if any(x in texte for x in ("billet", "payer", "billett", "bezahlen")):
        return "billet"
    if any(x in texte for x in ("bondé", "überfüllt", "foule", "gedränge")):
        return "foule"
    if any(x in texte for x in ("froid", "noir", "attendre", "kälte", "dunkel", "warten")):
        return "attente"
    if any(x in texte for x in ("rien", "nichts")):
        return "aucun"
    return "defaut"


def _theme_idee_verbatim(verbatim: str) -> str | None:
    """Un thème plus précis que l'irritant déclaré, détecté dans la réponse
    vocale libre — reconnu seulement sur des mots-clés explicites, jamais
    déduit d'un verbatim maladroit."""
    v = _nettoyer_fragment(verbatim, 300).lower()
    correspondances = [
        ("telephone", ("usb", "batterie", "recharger", "akku", "laden", "steckdose")),
        ("panorama", ("panorama", "tout devant", "ganz vorne", "fenêtre", "fenster")),
        ("ponctualite", ("ponctuel", "à l'heure", "pünktlich")),
        ("billet", ("billet", "tarif", "billett", "preis")),
        ("attente", ("abri", "lumière", "siège", "dach", "licht", "sitz")),
        # «plus souvent / öfter» fait déjà partie de la question vocale;
        # ce thème générique ne doit gagner qu'en l'absence d'une idée précise.
        ("frequence", ("plus souvent", "plus fréquent", "häufiger", "öfter")),
    ]
    return next((cle for cle, mots in correspondances if any(m in v for m in mots)), None)


# Thème détecté (irritant déclaré ou, si plus précis, sujet de la réponse
# vocale) -> catégorie visuelle limitée à la bibliothèque locale d'icônes.
_CATEGORIE_VISUELLE_PAR_THEME = {
    "correspondance": "correspondance",
    "retard": "information",
    "billet": "prix",
    "foule": "affluence",
    "attente": "confort",
    "telephone": "confort",
    "panorama": "panorama",
    "frequence": "generique",
    "ponctualite": "ponctualite",
    "aucun": "generique",
    "defaut": "generique",
}

# friction: le point de friction seul (15-28 mots), sans la solution — les
# deux sont désormais deux champs séparés du ticket plutôt qu'un paragraphe
# combiné.
_FRICTION_FR = {
    "correspondance": [
        "Le vrai point de tension, c’est la correspondance ratée: quelques minutes suffisent pour transformer un trajet tranquille en sprint improvisé.",
        "Ce qui use ta patience, c’est la correspondance qui file sous ton nez alors que tu cours déjà pour l’attraper.",
    ],
    "retard": [
        "Ce qui gâche le voyage, c’est le retard sans aucune information: le bus est annoncé, mais semble avoir quitté le scénario.",
        "Le vrai problème n’est pas le retard lui-même, c’est de ne jamais savoir pourquoi ni combien de temps il durera.",
    ],
    "billet": [
        "Le moment critique, c’est le billet: dès qu’il faut deviner le bon tarif, un trajet tout simple devient un petit escape game.",
        "Ce qui te freine, c’est le prix du billet: jamais clair avant de monter, toujours source d’un petit doute inutile.",
    ],
    "foule": [
        "Le bus bondé reste ton principal frein: quand le trajet ressemble à une partie de Tetris, le confort descend au prochain arrêt.",
        "Ce qui te refroidit, c’est la cohue: entre les sacs et les coudes, il ne reste plus vraiment de place pour toi.",
    ],
    "attente": [
        "Attendre dans le froid ou dans le noir reste le point faible: avant même de monter, le voyage a déjà perdu des points.",
        "Ce qui pèse, c’est l’attente sans abri ni lumière: le trajet commence mal bien avant que le bus n’arrive.",
    ],
    "telephone": [
        "Ce qui inquiète, c’est la batterie du téléphone: elle descend plus vite que le trajet n’avance, et ça se voit sur ton visage.",
        "Ton vrai souci, c’est un téléphone à bout de souffle avant même d’arriver à destination, sans aucune prise pour le sauver.",
    ],
    "frequence": [
        "Ce qui te refroidit, c’est l’attente entre deux bus: quand les départs se font rares, le trajet perd toute sa spontanéité.",
        "Le vrai frein, c’est la fréquence: quand il faut consulter l’horaire trois fois avant de sortir, l’envie retombe vite.",
    ],
    "ponctualite": [
        "Ce qui te refroidit, c’est l’incertitude sur l’heure d’arrivée: un horaire qui varie chaque jour retire toute confiance au service.",
        "Le vrai problème, c’est de ne jamais savoir si le bus tiendra l’heure annoncée, jour après jour, sans jamais te le dire.",
    ],
    "aucun": [
        "Bonne nouvelle: aucun irritant majeur ne prend toute la place dans ton trajet, ce qui n’est déjà pas si fréquent.",
        "Rien ne vient vraiment gâcher le voyage: le principal point de friction, ici, c’est surtout qu’il n’y en a pas.",
    ],
    "defaut": [
        "Le principal enjeu reste simple: retirer les petites frictions du quotidien qui compliquent un trajet qui pourrait rester évident.",
        "Ce qui te refroidit n’a rien de spectaculaire: ce sont surtout les petits détails jamais réglés qui finissent par peser.",
    ],
}
_FRICTION_DE = {
    "correspondance": [
        "Der heikle Punkt ist der Anschluss: Ein paar Minuten reichen, um aus einer ruhigen Fahrt einen spontanen Sprint zu machen.",
        "Was an deiner Geduld nagt, ist der Anschluss, der dir vor der Nase wegfährt, während du schon rennst, um ihn zu erreichen.",
    ],
    "retard": [
        "Was die Fahrt trübt, ist eine Verspätung ganz ohne Information: Der Bus ist angekündigt, aber offenbar aus der Handlung verschwunden.",
        "Das eigentliche Problem ist nicht die Verspätung selbst, sondern nie zu wissen, warum und wie lange sie dauern wird.",
    ],
    "billet": [
        "Der kritische Moment ist das Billett: Sobald der richtige Tarif erraten werden muss, wird eine einfache Fahrt zum kleinen Escape Game.",
        "Was dich bremst, ist der Billettpreis: Vor dem Einsteigen nie ganz klar, immer eine kleine unnötige Unsicherheit.",
    ],
    "foule": [
        "Der überfüllte Bus bleibt dein grösster Bremsklotz: Wird die Fahrt zu Tetris, steigt der Komfort schon an der nächsten Haltestelle aus.",
        "Was dich abkühlt, ist das Gedränge: Zwischen Taschen und Ellbogen bleibt für dich eigentlich kein richtiger Platz mehr übrig.",
    ],
    "attente": [
        "Warten in Kälte oder Dunkelheit bleibt die Schwachstelle: Noch vor dem Einsteigen hat die Reise bereits Punkte verloren.",
        "Was schwer wiegt, ist das Warten ohne Dach und Licht: Die Fahrt beginnt schon schlecht, lange bevor der Bus ankommt.",
    ],
    "telephone": [
        "Was dich beunruhigt, ist der Akkustand: Er sinkt schneller als die Fahrt vorankommt, und man sieht es dir richtig an.",
        "Deine echte Sorge ist ein Handy, das vor dem Ziel schon fast leer ist, ganz ohne Steckdose, die es retten könnte.",
    ],
    "frequence": [
        "Was dich abkühlt, ist die Wartezeit zwischen zwei Bussen: Sind die Abfahrten selten, verliert die Fahrt jede Spontaneität.",
        "Der eigentliche Bremsklotz ist der Takt: Muss man dreimal auf den Fahrplan schauen, bevor man losgeht, sinkt die Lust schnell.",
    ],
    "ponctualite": [
        "Was dich abkühlt, ist die Unsicherheit bei der Ankunftszeit: Ein Fahrplan, der jeden Tag anders ausfällt, kostet echtes Vertrauen.",
        "Das eigentliche Problem ist, nie zu wissen, ob der Bus die angekündigte Zeit hält, Tag für Tag, ohne es dir je zu sagen.",
    ],
    "aucun": [
        "Gute Nachricht: Kein grosser Störfaktor nimmt auf deiner Fahrt den ganzen Raum ein, was gar nicht so häufig vorkommt.",
        "Nichts trübt die Fahrt wirklich: Der grösste Störfaktor ist hier vor allem, dass es keinen gibt.",
    ],
    "defaut": [
        "Das wichtigste Ziel bleibt einfach: kleine alltägliche Reibungen entfernen, die eine eigentlich klare Fahrt unnötig komplizieren.",
        "Was dich abkühlt, ist nichts Spektakuläres: Es sind vor allem die kleinen, nie gelösten Details, die am Ende ins Gewicht fallen.",
    ],
}

# idee_a_tester: une solution concrète et testable par CarPostal (10-20
# mots), classée par le même thème que friction/verdict — plus « panorama »,
# qui ne peut venir que de la réponse vocale libre, jamais de l'irritant
# déclaré (voir _theme_idee_verbatim).
_IDEE_FR = {
    "correspondance": [
        "Une vraie garantie de correspondance, avec un bus qui attend ou une alternative annoncée aussitôt.",
        "Un compte à rebours visible à la correspondance, pour savoir en un coup d’œil s’il faut courir.",
    ],
    "retard": [
        "Une information en temps réel sur le retard, avec la vraie raison, pas juste un chiffre.",
        "Un message automatique dès qu’un retard est détecté, envoyé avant que tu ne l’attendes en vain.",
    ],
    "billet": [
        "Un billet automatique et sans réflexion, calculé tout seul selon le trajet réellement effectué.",
        "Un tarif affiché clairement avant de monter, sans calcul ni hésitation au moment de payer.",
    ],
    "foule": [
        "Un indicateur d’affluence en temps réel, pour choisir le bus suivant plutôt que se comprimer.",
        "Plus de bus aux heures de pointe, pour que chaque trajet garde un peu d’air.",
    ],
    "attente": [
        "Un arrêt abrité, éclairé et équipé d’une vraie assise, pour que l’attente pèse enfin moins.",
        "Un abribus chauffé et lumineux, pour que les minutes d’attente ne se sentent plus autant.",
    ],
    "telephone": [
        "Quelques prises USB à bord, pour que le téléphone tienne au moins jusqu’au terminus.",
        "Une prise de recharge par siège, simple et discrète, pour voyager sans compter le pourcentage.",
    ],
    "frequence": [
        "Des départs plus fréquents aux heures utiles, pour que le bus devienne un vrai réflexe.",
        "Un bus toutes les dix minutes plutôt qu’une attente à deviner, pour choisir sans calculer.",
    ],
    "ponctualite": [
        "Des horaires réellement tenus, jour après jour, pour transformer la confiance en habitude durable.",
        "Un suivi public de la ponctualité par ligne, pour que tenir l’heure devienne la norme.",
    ],
    "panorama": [
        "Une place vitrée bien placée, mise en avant sur les trajets qui valent vraiment le coup d’œil.",
        "Un itinéraire pensé aussi pour la vue, pas seulement pour la vitesse du trajet.",
    ],
    "aucun": [
        "Continuer simplement sur cette lancée, sans rien complexifier qui n’a pas besoin de l’être.",
        "Garder ce qui fonctionne déjà bien, sans ajouter de complexité inutile au quotidien.",
    ],
    "defaut": [
        "Un service clair, fiable et facile à utiliser, sans besoin d’en faire plus que ça.",
        "De petits ajustements simples et concrets, plutôt qu’une grande réforme qui complique tout.",
    ],
}
_IDEE_DE = {
    "correspondance": [
        "Eine echte Anschlussgarantie, mit wartendem Bus oder sofort angezeigter Alternative.",
        "Ein sichtbarer Countdown beim Anschluss, um auf einen Blick zu wissen, ob Rennen nötig ist.",
    ],
    "retard": [
        "Echtzeit-Information zur Verspätung, mit dem wirklichen Grund statt nur einer Zahl.",
        "Eine automatische Meldung, sobald eine Verspätung erkannt wird, statt vergeblichem Warten.",
    ],
    "billet": [
        "Ein automatisches Billett ganz ohne Nachdenken, berechnet nach der tatsächlich gefahrenen Strecke.",
        "Ein klar angezeigter Tarif vor dem Einsteigen, ohne Rechnen oder Zögern beim Bezahlen.",
    ],
    "foule": [
        "Eine Echtzeit-Auslastungsanzeige, um lieber den nächsten Bus zu nehmen statt sich zu quetschen.",
        "Mehr Busse zu den Stosszeiten, damit jede Fahrt ein bisschen Luft behält.",
    ],
    "attente": [
        "Eine geschützte, beleuchtete Haltestelle mit richtigem Sitzplatz, damit das Warten endlich weniger wiegt.",
        "Ein beheiztes, helles Wartehäuschen, damit die Wartezeit sich nicht mehr so lang anfühlt.",
    ],
    "telephone": [
        "Ein paar USB-Anschlüsse an Bord, damit das Handy wenigstens bis zur Endstation durchhält.",
        "Eine Steckdose pro Sitzplatz, einfach und diskret, um zu fahren, ohne den Akku zu zählen.",
    ],
    "frequence": [
        "Häufigere Abfahrten zu den Stosszeiten, damit der Bus zum echten Reflex wird.",
        "Ein Bus alle zehn Minuten statt einer Wartezeit zum Raten, um ohne Rechnen loszufahren.",
    ],
    "ponctualite": [
        "Fahrpläne, die wirklich eingehalten werden, Tag für Tag, bis daraus echtes Vertrauen wird.",
        "Eine öffentliche Pünktlichkeitsanzeige pro Linie, damit Pünktlichkeit zur Norm wird.",
    ],
    "panorama": [
        "Ein gut platzierter Fensterplatz, gezielt hervorgehoben auf Strecken, die einen Blick wirklich wert sind.",
        "Eine Route, die auch an die Aussicht denkt, nicht nur an die schnellste Verbindung.",
    ],
    "aucun": [
        "Einfach so weitermachen, ohne etwas zu verkomplizieren, das es gar nicht nötig hat.",
        "Behalten, was schon gut funktioniert, ohne unnötige Komplexität im Alltag hinzuzufügen.",
    ],
    "defaut": [
        "Ein klarer, zuverlässiger und einfach nutzbarer Service, ohne mehr als nötig zu tun.",
        "Kleine, konkrete Anpassungen statt einer grossen Reform, die am Ende alles komplizierter macht.",
    ],
}

# verdict: la punchline finale (12-25 mots). Réécrite pour le nouveau
# contrat: plus aucune personnalité nommée (fable, personnage historique...)
# — seulement une image concrète, éventuellement un clin d'œil suisse léger.
_VERDICT_FR = {
    "correspondance": [
        "Tu ne demandes pas la lune, juste deux minutes de plus pour ne pas sprinter comme si le bus était en feu.",
        "Ton verdict tient en une phrase: rater sa correspondance ne devrait jamais dépendre de la vitesse de tes jambes.",
    ],
    "retard": [
        "Tu ne demandes pas la précision d’une horloge suisse. Juste qu’on te dise pourquoi elle retarde, au lieu de te laisser deviner.",
        "Le silence, tu peux vivre avec. C’est l’absence totale d’explication qui transforme un simple retard en petit mystère irritant.",
    ],
    "billet": [
        "Payer, tu veux bien. Deviner combien avant de monter, nettement moins: le bus n’a pas besoin d’un examen de maths.",
        "Un billet ne devrait jamais demander plus de réflexion que le trajet lui-même. Le tien, visiblement, mérite un peu de simplicité.",
    ],
    "foule": [
        "Tu aimes bien la compagnie, jusqu’à un certain point: celui où ton coude devient l’otage d’un sac à dos.",
        "Un bus bondé, ce n’est pas de la convivialité, c’est juste un jeu de Tetris que personne n’a envie de jouer.",
    ],
    "attente": [
        "Attendre, tu sais faire. Attendre dans le noir sans banc ni toit, un peu moins: même un arrêt de bus mérite un minimum d’égards.",
        "Ton verdict est sans appel: un abri et un peu de lumière suffiraient à transformer l’attente en simple pause plutôt qu’en épreuve.",
    ],
    "telephone": [
        "Ton téléphone finit le trajet plus fatigué que toi, et ce n’est vraiment pas normal pour un simple passage en bus.",
        "Une prise USB, ce n’est pas un luxe: c’est juste la différence entre arriver joignable et arriver en mode avion malgré toi.",
    ],
    "frequence": [
        "Tu n’as rien contre attendre un peu. C’est attendre sans savoir combien de temps qui finit par user la patience.",
        "Un bus plus fréquent ne changerait pas ta vie, juste ton humeur à chaque arrêt, ce qui n’est déjà pas rien.",
    ],
    "ponctualite": [
        "Tu ne demandes pas des miracles, juste qu’un horaire annoncé ressemble, de temps en temps, à l’heure réelle d’arrivée.",
        "La ponctualité n’est pas un exploit suisse réservé aux trains: un bus qui tient parole devrait être la norme, pas l’exception.",
    ],
    "panorama": [
        "Tu n’as pas besoin d’un guide touristique. Juste d’une fenêtre bien placée et d’un trajet qui ne va pas trop vite.",
        "Ton verdict est limpide: les meilleures idées naissent en regardant par la fenêtre, pas en fixant un écran de téléphone.",
    ],
    "aucun": [
        "Quand tout va déjà bien, le seul vrai défi devient de ne pas tout compliquer pour le plaisir de changer quelque chose.",
        "Ton verdict est presque décevant à écrire: rien à corriger, juste à préserver ce qui fonctionne déjà très bien.",
    ],
    "defaut": [
        "Tu ne demandes pas un bus parfait, juste un bus qui n’ajoute pas ses propres complications à ta journée déjà chargée.",
        "Le mieux, parfois, c’est simplement d’arrêter de compliquer ce qui pourrait rester évident depuis le premier arrêt.",
    ],
}
_VERDICT_DE = {
    "correspondance": [
        "Du willst nicht den Mond. Nur zwei Minuten mehr, um nicht zu rennen, als würde der Bus gleich in Flammen aufgehen.",
        "Dein Fazit passt in einen Satz: Einen Anschluss zu verpassen, sollte nie von der Geschwindigkeit deiner Beine abhängen.",
    ],
    "retard": [
        "Du willst nicht die Präzision einer Schweizer Uhr. Nur, dass man dir sagt, warum sie nachgeht, statt dich raten zu lassen.",
        "Die Stille erträgst du. Es ist das völlige Fehlen einer Erklärung, das aus einer Verspätung ein kleines, nerviges Rätsel macht.",
    ],
    "billet": [
        "Zahlen, das machst du gern. Vorher raten müssen, wie viel, eher weniger: der Bus braucht keine Matheprüfung vor der Abfahrt.",
        "Ein Billett sollte nie mehr Nachdenken verlangen als die Fahrt selbst. Deins, offensichtlich, hätte etwas mehr Einfachheit verdient.",
    ],
    "foule": [
        "Gesellschaft magst du, bis zu einem gewissen Punkt: dort, wo dein Ellbogen zur Geisel eines Rucksacks wird.",
        "Ein überfüllter Bus ist keine Gemütlichkeit, sondern einfach ein Tetris-Spiel, auf das eigentlich niemand Lust hat.",
    ],
    "attente": [
        "Warten kannst du. Warten im Dunkeln ohne Bank oder Dach, etwas weniger: selbst eine Haltestelle verdient ein Minimum an Respekt.",
        "Dein Fazit ist eindeutig: Ein Dach und etwas Licht würden reichen, um aus dem Warten eine Pause statt eine Prüfung zu machen.",
    ],
    "telephone": [
        "Dein Handy beendet die Fahrt müder als du selbst, und das ist für eine simple Busfahrt eigentlich nicht normal.",
        "Eine USB-Steckdose ist kein Luxus: Sie ist einfach der Unterschied zwischen erreichbar ankommen und ungewollt im Flugmodus landen.",
    ],
    "frequence": [
        "Etwas Warten macht dir nichts aus. Warten, ohne zu wissen wie lange, das ist es, was am Ende die Geduld aufbraucht.",
        "Ein häufigerer Bus würde dein Leben nicht verändern, nur deine Laune an jeder Haltestelle, und das ist schon einiges wert.",
    ],
    "ponctualite": [
        "Du willst keine Wunder, nur dass ein angekündigter Fahrplan hin und wieder der tatsächlichen Ankunftszeit ähnelt.",
        "Pünktlichkeit ist keine Schweizer Spezialität, die nur Zügen vorbehalten ist: Ein Bus, der Wort hält, sollte die Regel sein, nicht die Ausnahme.",
    ],
    "panorama": [
        "Du brauchst keinen Reiseführer. Nur einen gut platzierten Fensterplatz und eine Fahrt, die nicht zu schnell vorbeirauscht.",
        "Dein Fazit ist klar: Die besten Ideen entstehen beim Blick aus dem Fenster, nicht beim Starren aufs Handy.",
    ],
    "aucun": [
        "Wenn schon alles gut läuft, besteht die einzige echte Herausforderung darin, nicht alles nur um der Veränderung willen zu verkomplizieren.",
        "Dein Fazit ist fast enttäuschend kurz: nichts zu korrigieren, nur zu bewahren, was schon sehr gut funktioniert.",
    ],
    "defaut": [
        "Du willst keinen perfekten Bus, nur einen, der deinem ohnehin vollen Tag nicht noch eigene Komplikationen hinzufügt.",
        "Das Beste ist manchmal einfach, aufzuhören, das zu komplizieren, was seit der ersten Haltestelle klar sein könnte.",
    ],
}


def _friction_idee_verdict(lang: str, d: dict) -> tuple[str, str, str, str]:
    """Un seul thème pilote les trois champs pour rester cohérent: l'irritant
    déclaré, ou — s'il est plus précis — le sujet détecté dans la réponse
    vocale libre. Retourne (friction, idee_a_tester, verdict, categorie_visuelle)."""
    theme_irritant = _theme_irritant(d)
    theme_idee = _theme_idee_verbatim(str(d.get("verbatim") or ""))
    theme = theme_idee or theme_irritant

    friction_pool = _FRICTION_FR if lang != "de" else _FRICTION_DE
    idee_pool = _IDEE_FR if lang != "de" else _IDEE_DE
    verdict_pool = _VERDICT_FR if lang != "de" else _VERDICT_DE

    friction = _choix_sans_repetition(
        f"friction:{lang}:{theme_irritant}", friction_pool[theme_irritant])
    idee = _choix_sans_repetition(f"idee:{lang}:{theme}", idee_pool[theme])
    verdict = _choix_sans_repetition(f"verdict:{lang}:{theme}", verdict_pool[theme])
    categorie = _CATEGORIE_VISUELLE_PAR_THEME[theme]
    return friction, idee, verdict, categorie


def _rapport_regles(lang: str, d: dict) -> dict:
    """Rapport sans IA: naturel, compact et strictement fondé sur les
    réponses. Chaque champ est construit à partir de bassins de phrases déjà
    vérifiés dans les bornes de longueur du nouveau contrat — pas besoin de
    compléter ni de tronquer après coup."""
    langue = "de" if lang == "de" else "fr"
    titre_profil = _choisir_titre(langue, d)
    plaisir = _phrase_plaisir(langue, d)
    friction, idee_a_tester, verdict, categorie_visuelle = _friction_idee_verdict(langue, d)
    return {
        "titre_profil": titre_profil,
        "plaisir": plaisir,
        "friction": friction,
        "idee_a_tester": idee_a_tester,
        "verdict": verdict,
        "categorie_visuelle": categorie_visuelle,
    }


def _label_rapport(lang: str, ia: bool) -> str:
    if lang == "de":
        return "Mit KI personalisiert" if ia else "Automatisch personalisiert"
    return "Personnalisé par IA" if ia else "Personnalisé automatiquement"


def rapport_participant(lang: str, donnees: dict, ton: str = "complice") -> dict:
    """Retourne un rapport toujours valide; l’IA invalide bascule vers les règles."""
    langue = "de" if lang == "de" else "fr"
    provider = provider_actuel()
    erreur = None
    if provider != "none":
        # Seules des valeurs textuelles utiles au rapport sont transmises:
        # jamais de fichier audio, de contenu binaire, de chemin local, de
        # numéro de session/identifiant technique ni d'adresse IP. Un
        # nettoyage best-effort retire en plus les informations personnelles
        # évidentes qui auraient pu être prononcées par erreur.
        corpus = json.dumps(
            {k: masquer_donnees_personnelles(str(v)) if isinstance(v, str) else v
             for k, v in donnees.items() if v not in (None, "")},
            ensure_ascii=False,
        )
        texte, erreur = generer(
            PROMPT_PARTICIPANT.format(
                langue="allemand de Suisse" if langue == "de" else "français",
                ton=TONS.get(ton, TONS["complice"]),
            ),
            corpus,
            max_tokens=500,
        )
        if texte:
            doc = _valider_rapport_ia(texte)
            if doc:
                return {
                    **doc,
                    "fournisseur": provider,
                    "erreur": None,
                    "label": _label_rapport(langue, True),
                }
            erreur = "Réponse IA invalide ou hors format; rapport automatique utilisé."

    doc = _rapport_regles(langue, donnees)
    return {
        **doc,
        "fournisseur": "none",
        "erreur": erreur,
        "label": _label_rapport(langue, False),
    }


# ------------------------------------------------- analyse qualitative admin

PROMPT_ADMIN = """Tu analyses des verbatims de voyageurs sur l'expérience du
bus. Regroupe-les en thèmes (irritants, attentes, idées nouvelles). Pour
chaque thème: nom court, nombre de mentions, 1 à 2 verbatims représentatifs
recopiés mot pour mot. N'invente RIEN, ne compte que ce qui est fourni.
Réponds en JSON strict:
{"themes":[{"nom":"...","type":"irritant|attente|idee","mentions":N,
"verbatims":["..."]}]}"""


def analyse_qualitative(verbatims: list[str]) -> dict:
    """Thèmes des réponses vocales. Sans IA: comptage de mots-clés honnête."""
    provider = provider_actuel()
    if provider != "none" and verbatims:
        corpus = "\n---\n".join(masquer_donnees_personnelles(v) for v in verbatims)
        texte, erreur = generer(PROMPT_ADMIN, corpus, max_tokens=1200)
        if texte:
            m = re.search(r"\{.*\}", texte, re.S)
            try:
                doc = json.loads(m.group(0) if m else texte)
                doc["fournisseur"] = provider
                return doc
            except json.JSONDecodeError:
                erreur = "réponse IA non parsable"
        return {"themes": [], "fournisseur": provider, "erreur": erreur}
    themes = []
    for nom, mots in _MOTS_CLES:
        touches = [v for v in verbatims
                   if any(m in v.lower() for m in mots)]
        if touches:
            themes.append({"nom": nom, "type": "irritant", "mentions": len(touches),
                           "verbatims": touches[:2]})
    return {"themes": themes, "fournisseur": "none",
            "note": "Regroupement par mots-clés simples, sans IA."}
