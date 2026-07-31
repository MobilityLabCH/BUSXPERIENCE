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

PROMPT_PARTICIPANT = """Tu écris le profil de voyage BUS XPERIENCE d'une seule
personne. Langue: {langue}. Ton: {ton}.

À partir des données JSON fournies, sélectionne seulement 3 ou 4 informations
réellement intéressantes. Transforme les valeurs brutes en langage naturel.
N'invente rien et ne cherche jamais à tout reprendre.

Le résultat doit contenir exactement:
1. un titre personnalisé, court, mémorable et légèrement drôle;
2. paragraphe_1: la relation de la personne au bus;
3. paragraphe_2: son principal irritant et l'amélioration qui lui serait utile;
4. une conclusion qui donne le sourire: une phrase courte façon citation ou
   pensée positive (style fable, proverbe, sagesse populaire ou grand nom
   connu), reliée avec humour au sujet réel de sa réponse — jamais une
   formule vague ou interchangeable d'un profil à l'autre.

Exemples du niveau de qualité attendu pour la conclusion (uniquement pour le
style, ne recopie jamais ces phrases telles quelles):
- pour un irritant "correspondance ratée": «Ton verdict: la Fontaine l'a
  dit — mieux vaut partir à point.»
- pour un irritant "retard sans info": «Ton verdict: même un coucou suisse
  te préviendrait mieux avant de sonner.»
- pour un irritant "bus bondé": «Ton verdict: on ne tasse pas les gens
  comme une fondue à partager.»
Chaque exemple nomme un décalage concret et inattendu avec l'irritant réel,
avec une image simple à visualiser, au lieu d'une morale générique ou
abstraite. Une conclusion comme «de l'info avant les mauvaises surprises»
ou «la patience, ça paie» est un échec: c'est vague, interchangeable et
sans surprise — à proscrire absolument.

Contraintes absolues:
- ne reproduis jamais un nom de personne, numéro de téléphone, adresse
  postale, e-mail ou autre information personnelle qui aurait pu être
  prononcée par erreur dans une transcription; si une telle information
  apparaît dans les données, ignore-la simplement;
- 60 à 90 mots au total pour les trois textes, titre non compris;
- tutoiement en français, «du» en allemand;
- aucun genre supposé;
- aucun «Acte 1», «Acte 2», «Acte 3» ou structure annoncée;
- aucun nom technique de question, numéro de question, score de concept,
  valeur brute incompréhensible, JSON visible ou formule administrative;
- ne jamais écrire «le répondant a indiqué» ni son équivalent;
- ne pas recopier une transcription maladroite: reformule-la sans en changer le sens;
- une image légère est bienvenue, mais pas une plaisanterie dans chaque phrase;
- vocabulaire simple et concret partout, y compris dans la conclusion:
  une image ou métaphore facile à visualiser plutôt qu'une formule
  abstraite; les images du quotidien suisse (montagnes, lacs, précision
  horlogère, fondue, chocolat, cornet, etc.) sont bienvenues quand elles
  collent naturellement au sujet, sans en forcer une à chaque fois;
- la conclusion peut s'inspirer du ton ou de l'esprit d'une citation
  célèbre, d'une fable ou d'un proverbe, mais toujours reformulée avec tes
  propres mots: ne recopie jamais mot pour mot une réplique de film, de
  dessin animé ou de toute autre œuvre protégée par le droit d'auteur;
- le titre ne dépasse pas 10 mots;
- aucun markdown.

Réponds uniquement avec ce JSON strict:
{{"titre":"...","paragraphe_1":"...","paragraphe_2":"...","conclusion":"..."}}"""

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


def _valider_rapport_ia(texte: str) -> dict | None:
    doc = _extraire_json(texte)
    if not doc:
        return None
    cles = ("titre", "paragraphe_1", "paragraphe_2", "conclusion")
    if any(not isinstance(doc.get(cle), str) for cle in cles):
        return None
    propre = {cle: _nettoyer_fragment(doc[cle], 160 if cle == "titre" else 520)
              for cle in cles}
    if any(not propre[cle] for cle in cles):
        return None
    if _mots(propre["titre"]) > 10:
        return None
    corps = "\n\n".join(propre[cle] for cle in cles[1:])
    if not 60 <= _mots(corps) <= 90:
        return None
    tout = propre["titre"] + "\n" + corps
    if _FORBIDDEN_REPORT_RE.search(tout) or "{" in tout or "}" in tout:
        return None
    if not _quotes_equilibrees(tout):
        return None
    return {
        "titre": propre["titre"],
        "paragraphe_1": propre["paragraphe_1"],
        "paragraphe_2": propre["paragraphe_2"],
        "conclusion": propre["conclusion"],
        "texte": corps,
    }


def rapport_cache_valide(titre: str, texte: str) -> bool:
    """Écarte les anciens rapports afin qu’ils soient régénérés après mise à jour."""
    titre, texte = _nettoyer_fragment(titre, 180), (texte or "").strip()
    if not titre or not texte or _FORBIDDEN_REPORT_RE.search(titre + "\n" + texte):
        return False
    parties = [p.strip() for p in re.split(r"\n\s*\n", texte) if p.strip()]
    return len(parties) == 3 and 45 <= _mots(texte) <= 100 and _quotes_equilibrees(texte)


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


def _phrase_relation(lang: str, d: dict) -> str:
    fr = lang != "de"
    profil = _profil_frequence(str(d.get("frequence") or ""), lang)
    etoiles = _entier(d, "etoiles", 1, 5)

    if fr:
        debuts = {
            "quotidien": "Le bus fait clairement partie de ton quotidien.",
            "hebdo": "Le bus et toi, vous vous retrouvez chaque semaine.",
            "mensuel": "Le bus et toi, vous vous croisez quelques fois par mois.",
            "rare": "Le bus et toi, c’est encore une relation occasionnelle.",
            "jamais": "Le bus et toi, c’est encore une relation à construire.",
            "inconnu": "Le bus et toi, vous avez déjà quelques kilomètres en commun.",
        }
        suites = {
            1: "Ton dernier trajet ne décroche qu’une étoile sur cinq: le service a du travail.",
            2: "Ton dernier trajet obtient deux étoiles sur cinq: la marge de progression est généreuse.",
            3: "Ton dernier trajet obtient trois étoiles sur cinq: correct, sans encore donner envie d’applaudir.",
            4: "Ton dernier trajet récolte quatre étoiles sur cinq: ça roule plutôt bien.",
            5: "Ton dernier trajet décroche cinq étoiles: cette fois, le bus a parfaitement joué son rôle.",
        }
    else:
        debuts = {
            "quotidien": "Der Bus gehört klar zu deinem Alltag.",
            "hebdo": "Du und der Bus, ihr trefft euch jede Woche.",
            "mensuel": "Du und der Bus, ihr seht euch ein paar Mal pro Monat.",
            "rare": "Du und der Bus, das ist noch eine gelegentliche Beziehung.",
            "jamais": "Du und der Bus, diese Beziehung muss erst noch entstehen.",
            "inconnu": "Du und der Bus, ihr habt schon einige Kilometer gemeinsam.",
        }
        suites = {
            1: "Die letzte Fahrt erhält nur einen von fünf Sternen: da wartet noch Arbeit.",
            2: "Die letzte Fahrt bekommt zwei von fünf Sternen: Luft nach oben gibt es reichlich.",
            3: "Die letzte Fahrt bekommt drei von fünf Sternen: ordentlich, aber noch ohne Applaus.",
            4: "Die letzte Fahrt sammelt vier von fünf Sternen: das läuft schon ziemlich gut.",
            5: "Die letzte Fahrt verdient fünf Sterne: diesmal hat der Bus seinen Job perfekt gemacht.",
        }
    if etoiles:
        return f"{debuts[profil]} {suites[etoiles]}"
    confiance = _entier(d, "confiance", 0, 10)
    if confiance is not None:
        return (f"{debuts[profil]} Pour un rendez-vous important, ta confiance atteint {confiance} sur 10."
                if fr else
                f"{debuts[profil]} Für einen wichtigen Termin liegt dein Vertrauen bei {confiance} von 10.")
    return debuts[profil]


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


def _idee_verbatim(verbatim: str, lang: str) -> tuple[str | None, str | None]:
    """Transforme seulement les idées reconnues; un verbatim maladroit reste invisible."""
    v = _nettoyer_fragment(verbatim, 300).lower()
    fr = lang != "de"
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
    theme = next((cle for cle, mots in correspondances if any(m in v for m in mots)), None)
    if not theme:
        return None, None
    phrases_fr = {
        "telephone": "Et quelques prises USB éviteraient que ton téléphone ne descende avant toi.",
        "panorama": "Une place avec vue panoramique rendrait aussi le voyage nettement plus agréable.",
        "frequence": "Des départs plus fréquents rendraient le bus beaucoup plus facile à choisir.",
        "ponctualite": "Des horaires plus ponctuels transformeraient cette confiance en vraie habitude.",
        "billet": "Un billet simple et automatique retirerait un casse-tête avant même le départ.",
        "attente": "Un arrêt abrité, éclairé et équipé d’une vraie assise améliorerait déjà le voyage.",
    }
    phrases_de = {
        "telephone": "Ein paar USB-Anschlüsse würden verhindern, dass dein Handy vor dir aussteigt.",
        "panorama": "Ein Platz mit Panoramablick würde die Fahrt ebenfalls deutlich angenehmer machen.",
        "frequence": "Häufigere Abfahrten würden den Bus viel leichter zur ersten Wahl machen.",
        "ponctualite": "Mehr Pünktlichkeit würde aus Vertrauen eine echte Gewohnheit machen.",
        "billet": "Ein einfaches automatisches Billett würde schon vor der Abfahrt ein Rätsel beseitigen.",
        "attente": "Eine geschützte, beleuchtete Haltestelle mit richtigem Sitzplatz würde die Reise sofort verbessern.",
    }
    return theme, (phrases_fr if fr else phrases_de)[theme]


# Plusieurs formulations pour relier le point de friction à l'innovation
# préférée du participant: une seule phrase fixe («va donc dans la bonne
# direction: moins d'incertitude, plus de tranquillité») revenait à
# l'identique dans tous les rapports dès qu'aucune idée précise n'émergeait
# du verbatim — ça sonnait comme un copier-coller plutôt qu'un profil
# personnel, même si le nom du concept, lui, changeait bien à chaque fois.
_GABARITS_IDEE_CONCEPT = {
    "fr": [
        "L’idée «{concept}» va justement dans cette direction: moins d’incertitude, plus de tranquillité.",
        "Et «{concept}» tombe plutôt bien: exactement le genre de coup de pouce qui change un trajet.",
        "«{concept}» a d’ailleurs tout pour plaire ici: une réponse concrète, sans complication ajoutée.",
        "Bonne nouvelle: «{concept}» répond justement à ce point-là, sans en rajouter.",
        "«{concept}» arrive au bon moment: le genre d’idée qui simplifie sans se faire remarquer.",
        "Et si «{concept}» voyait le jour, ce serait un pas de plus vers un trajet plus tranquille.",
    ],
    "de": [
        "Die Idee «{concept}» geht genau in diese Richtung: weniger Unsicherheit, mehr Ruhe.",
        "Und «{concept}» kommt gerade richtig: genau der Schub, der eine Fahrt verändert.",
        "«{concept}» hat hier eigentlich alles: eine konkrete Antwort, ganz ohne zusätzlichen Aufwand.",
        "Gute Nachricht: «{concept}» beantwortet genau diesen Punkt, ganz ohne Umwege.",
        "«{concept}» kommt zur rechten Zeit: die Art Idee, die vieles einfacher macht, ohne aufzufallen.",
        "Und würde «{concept}» Realität, wäre das ein Schritt zu einer entspannteren Fahrt.",
    ],
}

# Le "verdict" final se voulait drôle ou surprenant mais restait un peu
# plat (un seul intitulé fixe par thème, toujours le même). Plusieurs
# variantes par thème, tirées au sort sans répétition immédiate, avec un
# clin d'œil à une fable, un proverbe ou un grand nom — jamais une citation
# de personnage sous droits d'auteur (Disney etc.), toujours du domaine
# public ou de la sagesse populaire générique.
_CONCLUSIONS_FR = {
    "correspondance": [
        "Ton verdict: la Fontaine l’a dit — mieux vaut partir à point.",
        "Ton verdict: même Ulysse planifiait mieux ses correspondances.",
    ],
    "retard": [
        "Ton verdict: l’incertitude, c’est bon pour les romans, pas pour un bus.",
        "Ton verdict: même une horloge arrêtée informe mieux que ce silence.",
    ],
    "billet": [
        "Ton verdict: le meilleur calcul est celui qu’on n’a pas à faire.",
        "Ton verdict: Confucius lui-même aurait détesté deviner le prix du billet.",
    ],
    "foule": [
        "Ton verdict: les sardines ont un abonnement, pas envie de le partager.",
        "Ton verdict: l’union fait la force, pas l’entassement le confort.",
    ],
    "attente": [
        "Ton verdict: même le loup de la fable cherchait un toit.",
        "Ton verdict: un banc et un abri changent toute la morale de l’histoire.",
    ],
    "telephone": [
        "Ton verdict: ton téléphone mérite d’arriver aussi frais que toi.",
        "Ton verdict: la panique du 1 % de batterie, ce n’est pas une légende.",
    ],
    "panorama": [
        "Ton verdict: les meilleures idées naissent en regardant par la fenêtre.",
        "Ton verdict: un trajet avec vue n’a jamais nui à personne.",
    ],
    "frequence": [
        "Ton verdict: patienter avec sagesse, oui — patienter pour rien, non merci.",
        "Ton verdict: le bus idéal est celui qu’on n’a jamais à guetter.",
    ],
    "ponctualite": [
        "Ton verdict: un horaire qui tient parole vaut toutes les promesses du monde.",
        "Ton verdict: même les sages apprécient un rendez-vous respecté.",
    ],
    "aucun": [
        "Ton verdict: pas besoin de morale compliquée quand tout va déjà bien.",
        "Ton verdict: la meilleure fable est parfois celle qui n’a pas de problème à résoudre.",
    ],
    "defaut": [
        "Ton verdict: le mieux est souvent l’ennemi du simple.",
        "Ton verdict: une bonne histoire commence toujours par un trajet sans accroc.",
    ],
}
_CONCLUSIONS_DE = {
    "correspondance": [
        "Dein Fazit: schon der Hase aus der Fabel hätte besseres Timing gebraucht.",
        "Dein Fazit: gute Verbindungen schlagen jeden Sprint.",
    ],
    "retard": [
        "Dein Fazit: Unsicherheit passt zu Romanen, nicht zum Busfahrplan.",
        "Dein Fazit: selbst eine stehengebliebene Uhr informiert besser als dieses Schweigen.",
    ],
    "billet": [
        "Dein Fazit: die beste Rechnung ist die, die man nicht selbst machen muss.",
        "Dein Fazit: schon Konfuzius hätte den Billettpreis nicht gern erraten.",
    ],
    "foule": [
        "Dein Fazit: Sardinen haben ein Abo, aber keine Lust, es zu teilen.",
        "Dein Fazit: Zusammenhalt macht stark, Gedränge macht nur müde.",
    ],
    "attente": [
        "Dein Fazit: selbst der Wolf aus der Fabel suchte ein Dach.",
        "Dein Fazit: eine Bank und ein Dach ändern die ganze Geschichte.",
    ],
    "telephone": [
        "Dein Fazit: dein Handy verdient es, genauso frisch anzukommen wie du.",
        "Dein Fazit: die Ein-Prozent-Panik ist keine Legende.",
    ],
    "panorama": [
        "Dein Fazit: die besten Ideen entstehen beim Blick aus dem Fenster.",
        "Dein Fazit: eine Fahrt mit Aussicht hat noch niemandem geschadet.",
    ],
    "frequence": [
        "Dein Fazit: geduldig warten ja, sinnlos warten nein danke.",
        "Dein Fazit: der ideale Bus ist der, auf den man nie starren muss.",
    ],
    "ponctualite": [
        "Dein Fazit: ein Fahrplan, der Wort hält, schlägt jedes Versprechen.",
        "Dein Fazit: sogar Weise schätzen einen eingehaltenen Termin.",
    ],
    "aucun": [
        "Dein Fazit: manchmal braucht es keine komplizierte Moral, wenn schon alles passt.",
        "Dein Fazit: die beste Fabel ist manchmal die ohne Problem.",
    ],
    "defaut": [
        "Dein Fazit: das Bessere ist oft der Feind des Einfachen.",
        "Dein Fazit: jede gute Geschichte beginnt mit einer Fahrt ohne Umweg.",
    ],
}

_COMPLEMENTS_FR = [
    " L’objectif n’est pas d’en faire plus, mais de rendre chaque étape plus évidente.",
    " Rien de spectaculaire à prévoir: juste un service qui tient ses promesses, trajet après trajet.",
    " Ce genre de détail change peu de choses en apparence, mais beaucoup une fois répété chaque jour.",
]
_COMPLEMENTS_DE = [
    " Das Ziel ist nicht mehr Aufwand, sondern ein klarerer Ablauf bei jedem Schritt.",
    " Nichts Spektakuläres nötig: nur ein Service, der Fahrt für Fahrt sein Versprechen hält.",
    " Das klingt nach wenig, macht aber jeden Tag aufs Neue einen Unterschied.",
]


def _phrase_irritant_solution(lang: str, d: dict) -> tuple[str, str]:
    fr = lang != "de"
    theme = _theme_irritant(d)
    problemes_fr = {
        "correspondance": "Le vrai point de tension, c’est la correspondance ratée: quelques minutes suffisent pour transformer le trajet en sprint.",
        "retard": "Ce qui gâche le voyage, c’est le retard sans information: le bus est annoncé, mais semble avoir quitté le scénario.",
        "billet": "Le moment critique, c’est le billet: dès qu’il faut deviner le bon tarif, le trajet devient un petit escape game.",
        "foule": "Le bus bondé reste ton principal frein: quand le trajet ressemble à une partie de Tetris, le confort descend au prochain arrêt.",
        "attente": "Attendre dans le froid ou le noir reste le point faible: avant même de monter, le voyage a déjà perdu des points.",
        "aucun": "Bonne nouvelle: aucun irritant majeur ne prend toute la place dans ton trajet.",
        "defaut": "Le principal enjeu reste simple: enlever les petites frictions qui compliquent le voyage sans raison.",
    }
    problemes_de = {
        "correspondance": "Der heikle Punkt ist der verpasste Anschluss: Ein paar Minuten machen aus der Reise plötzlich einen Sprint.",
        "retard": "Was die Fahrt trübt, ist eine Verspätung ohne Information: Der Bus ist angekündigt, aber aus der Handlung verschwunden.",
        "billet": "Der kritische Moment ist das Billett: Sobald der richtige Tarif erraten werden muss, wird die Fahrt zum kleinen Escape Game.",
        "foule": "Der überfüllte Bus bleibt dein grösster Bremsklotz: Wird die Fahrt zu Tetris, steigt der Komfort an der nächsten Haltestelle aus.",
        "attente": "Warten in Kälte oder Dunkelheit bleibt die Schwachstelle: Noch vor dem Einsteigen hat die Reise bereits Punkte verloren.",
        "aucun": "Gute Nachricht: Kein grosser Störfaktor nimmt auf deiner Fahrt den ganzen Raum ein.",
        "defaut": "Das wichtigste Ziel ist einfach: kleine Reibungen entfernen, die die Reise unnötig kompliziert machen.",
    }

    idee_theme, idee = _idee_verbatim(str(d.get("verbatim") or ""), lang)
    if not idee and d.get("concept"):
        concept = _nettoyer_fragment(d.get("concept"), 120)
        gabarit = _choix_sans_repetition(
            f"concept_idee:{'de' if not fr else 'fr'}",
            _GABARITS_IDEE_CONCEPT["de" if not fr else "fr"],
        )
        idee = gabarit.format(concept=concept)
    if not idee and d.get("priorite_arbitrage"):
        priorite = _nettoyer_fragment(d.get("priorite_arbitrage"), 120)
        idee = (f"Deine Priorität ist klar: {priorite[:1].lower() + priorite[1:]} ." if not fr else
                f"Ta priorité est claire: {priorite[:1].lower() + priorite[1:]}.")
        idee = idee.replace(" .", ".")
    if not idee and d.get("apprecie"):
        place = _nettoyer_fragment(d.get("apprecie"), 120)
        idee = (f"Und wenn möglich, gehört «{place}» ebenfalls zu einer gelungenen Fahrt."
                if not fr else
                f"Et tant qu’à faire, «{place}» fait aussi partie d’un trajet réussi.")
    if not idee:
        idee = ("Pas besoin d’en faire trop: le service doit surtout être clair, fiable et facile à utiliser."
                if fr else
                "Es braucht nicht viel: Der Service muss vor allem klar, zuverlässig und einfach nutzbar sein.")

    conclusion_theme = idee_theme or theme
    probleme = (problemes_fr if fr else problemes_de)[theme]
    variantes = (_CONCLUSIONS_FR if fr else _CONCLUSIONS_DE).get(
        conclusion_theme, (_CONCLUSIONS_FR if fr else _CONCLUSIONS_DE)["defaut"]
    )
    conclusion = _choix_sans_repetition(
        f"conclusion:{'fr' if fr else 'de'}:{conclusion_theme}", variantes
    )
    return f"{probleme} {idee}", conclusion


def _rapport_regles(lang: str, d: dict) -> dict:
    """Rapport sans IA: naturel, compact et strictement fondé sur les réponses."""
    langue = "de" if lang == "de" else "fr"
    titre = _choisir_titre(langue, d)
    p1 = _phrase_relation(langue, d)
    p2, conclusion = _phrase_irritant_solution(langue, d)

    corps = "\n\n".join((p1, p2, conclusion))
    if _mots(corps) < 60:
        # Un seul complément fixe ne suffisait pas toujours (le déficit de
        # mots varie selon les données disponibles et la variante de
        # conclusion tirée au sort): on ajoute autant de compléments que
        # nécessaire, dans l'ordre, jusqu'à atteindre le minimum.
        confiance = _entier(d, "confiance", 0, 10)
        complements = list(_COMPLEMENTS_FR if langue == "fr" else _COMPLEMENTS_DE)
        if confiance is not None:
            complements.insert(0,
                (f" Avec {confiance} sur 10 de confiance pour arriver à l’heure, tu attends surtout que cette promesse devienne une habitude."
                 if langue == "fr" else
                 f" Mit {confiance} von 10 Punkten Vertrauen in die pünktliche Ankunft soll dieses Versprechen nun zur Gewohnheit werden."))
        for ajout in complements:
            if _mots(corps) >= 60:
                break
            p2 += ajout
            corps = "\n\n".join((p1, p2, conclusion))

    # Les modèles ci-dessus restent volontairement courts. Cette protection
    # évite toutefois qu'une valeur administrateur anormalement longue déborde.
    if _mots(corps) > 90:
        p2 = re.sub(r"\s+", " ", p2)
        mots = p2.split()
        surplus = _mots(corps) - 88
        if surplus > 0 and len(mots) > surplus + 8:
            p2 = " ".join(mots[:-surplus]).rstrip(" ,;:") + "."
        corps = "\n\n".join((p1, p2, conclusion))

    return {
        "titre": titre,
        "paragraphe_1": p1,
        "paragraphe_2": p2,
        "conclusion": conclusion,
        "texte": corps,
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
