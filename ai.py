"""BUS XPERIENCE — intelligence artificielle facultative.

Architecture commune pour quatre fournisseurs: none, ollama, gemini,
anthropic. AI_PROVIDER=none est le défaut et produit déjà un rapport
participant personnel et drôle grâce à des règles et modèles variés.
Aucune bascule silencieuse: si le fournisseur configuré échoue, l'erreur
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


def provider_actuel() -> str:
    p = os.environ.get("AI_PROVIDER", "none").strip().lower()
    return p if p in PROVIDERS else "none"


def modele_actuel(provider: str) -> str:
    defauts = {"ollama": "llama3.2", "gemini": "gemini-2.0-flash",
               "anthropic": "claude-sonnet-4-6"}
    return os.environ.get("AI_MODEL", "") or defauts.get(provider, "")


def _http_json(methode: str, url: str, **kw) -> dict:
    """Point d'entrée réseau unique, remplacé par un mock dans les tests."""
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
# participant. Le mode none est soigné: titres, structures et chutes
# variés, toujours fondés sur les vraies réponses, jamais moqueurs.

TONS = {
    "complice": "chaleureux et complice, avec un clin d'œil",
    "drole": "franchement drôle, mais jamais moqueur",
    "sobre": "souriant et sobre",
    "institutionnel": "institutionnel avec une pointe d'humour discret",
}

PROMPT_PARTICIPANT = """Tu es BUS XPERIENCE, une installation qui écoute les
voyageurs parler de l'expérience du bus. Rédige le rapport officiel de la
personne, en {langue}, ton {ton}. Structure imposée: TITRE DÉCERNÉ (un titre
de fantaisie flatteur lié à ses réponses), puis 3 à 5 phrases qui reprennent
fidèlement: ce qu'elle apprécie, son principal irritant, le concept qu'elle a
préféré (avec sa note), et une courte citation exacte de sa réponse ouverte si
elle existe. Termine par une chute souriante. Maximum 100 mots. N'invente
RIEN: uniquement les données fournies. Jamais moqueur, jamais infantilisant.
Réponds au format JSON strict: {{"titre": "...", "texte": "..."}}"""

TITRES = {
    "fr": {
        "correspondance": ["Ministre officieux des correspondances réussies",
                           "Grand stratège des trajets sans mauvaise surprise"],
        "retard": ["Chevalier de l'information en temps réel",
                   "Ambassadeur du bus qui arrive quand il l'annonce"],
        "attente": ["Grande enquêtrice des arrêts sous la pluie",
                    "Président du comité des abris enfin dignes"],
        "confort": ["Présidente du comité des sièges enfin confortables",
                    "Inspecteur général du voyage agréable"],
        "billet": ["Docteur honoris causa en billets sans prise de tête"],
        "defaut": ["Voix remarquable de l'expérience bus",
                   "Experte internationale du dernier kilomètre",
                   "Conseiller spécial de la ligne idéale"],
    },
    "de": {
        "correspondance": ["Inoffizieller Minister der gelungenen Anschlüsse",
                           "Grossstratege der Reisen ohne böse Überraschung"],
        "retard": ["Ritterin der Echtzeit-Information",
                   "Botschafter des Busses, der kommt, wenn er es sagt"],
        "attente": ["Grosse Erforscherin der Haltestellen im Regen"],
        "confort": ["Präsident des Komitees der endlich bequemen Sitze"],
        "billet": ["Ehrendoktor der Billette ohne Kopfzerbrechen"],
        "defaut": ["Bemerkenswerte Stimme des Buserlebnisses",
                   "Internationale Expertin der letzten Meile"],
    },
}

_MOTS_CLES = [("correspondance", ["correspondance", "anschluss", "umsteigen"]),
              ("retard", ["retard", "information", "verspätung", "pünktlich", "ponctuel"]),
              ("attente", ["attendre", "arrêt", "froid", "warten", "haltestelle", "kälte"]),
              ("confort", ["bondé", "siège", "confort", "überfüllt", "sitz"]),
              ("billet", ["billet", "payer", "bezahlen", "preis", "prix"])]


def _choisir_titre(lang: str, donnees: dict) -> str:
    corpus = " ".join(str(v) for v in donnees.values()).lower()
    for cle, mots in _MOTS_CLES:
        if any(m in corpus for m in mots):
            pool = TITRES[lang].get(cle) or TITRES[lang]["defaut"]
            return random.choice(pool)
    return random.choice(TITRES[lang]["defaut"])


def _rapport_regles(lang: str, d: dict) -> tuple[str, str]:
    """Rapport automatique sans IA: personnel, varié, fondé sur les réponses."""
    fr = lang != "de"
    titre = _choisir_titre("fr" if fr else "de", d)
    p = []
    intro = random.choice(
        ["Le verdict est tombé, et il est excellent.",
         "Analyse terminée, contradictions comprises.",
         "Témoignage reçu, vérifié, apprécié."] if fr else
        ["Das Urteil ist da, und es ist ausgezeichnet.",
         "Analyse abgeschlossen, Widersprüche inklusive.",
         "Aussage erhalten, geprüft, geschätzt."])
    p.append(intro)
    if d.get("etoiles"):
        p.append((f"Ton dernier trajet récolte {d['etoiles']} étoile(s) sur 5, c'est noté."
                  if fr else
                  f"Deine letzte Fahrt erhält {d['etoiles']} von 5 Sternen, notiert."))
    if d.get("irritant") and d["irritant"] not in ("Rien ne me stresse", "Nichts stresst mich"):
        p.append((f"Ton ennemi juré: {d['irritant'].lower()}."
                  if fr else f"Dein Erzfeind: {d['irritant']}."))
    if d.get("confiance") is not None:
        p.append((f"Confiance dans la ponctualité: {d['confiance']}/10, message reçu cinq sur cinq."
                  if fr else
                  f"Vertrauen in die Pünktlichkeit: {d['confiance']}/10, klar angekommen."))
    if d.get("concept"):
        note = f" ({d['concept_note']}/10)" if d.get("concept_note") is not None else ""
        p.append((f"Ton idée favorite: «{d['concept']}»{note}, presque une déclaration d'amour."
                  if fr else
                  f"Deine Lieblingsidee: «{d['concept']}»{note}, fast eine Liebeserklärung."))
    if d.get("verbatim"):
        v = d["verbatim"][:110].strip()
        p.append((f"Ta proposition officielle: «{v}»." if fr
                  else f"Dein offizieller Vorschlag: «{v}»."))
    chute = random.choice(
        ["BUS XPERIENCE transmet. Elle ne peut pas encore retenir le bus, mais elle travaille son pouvoir de persuasion.",
         "Tout ceci sera vraiment lu. Le bus ne le sait pas encore, mais il va s'améliorer.",
         "Merci. Tes idées prennent la prochaine correspondance vers les bonnes personnes."] if fr else
        ["BUS XPERIENCE leitet weiter. Den Bus aufhalten kann sie noch nicht, aber sie arbeitet an ihrer Überzeugungskraft.",
         "All das wird wirklich gelesen. Der Bus weiss es noch nicht, aber er wird besser.",
         "Danke. Deine Ideen nehmen den nächsten Anschluss zu den richtigen Leuten."])
    p.append(chute)
    return titre, " ".join(p)


def rapport_participant(lang: str, donnees: dict, ton: str = "complice") -> dict:
    """donnees: etoiles, irritant, confiance, concept, concept_note, verbatim,
    apprecie... Retourne titre, texte, fournisseur, erreur, label."""
    provider = provider_actuel()
    erreur = None
    if provider != "none":
        corpus = json.dumps({k: v for k, v in donnees.items() if v not in (None, "")},
                            ensure_ascii=False)
        texte, erreur = generer(
            PROMPT_PARTICIPANT.format(
                langue="français" if lang != "de" else "allemand",
                ton=TONS.get(ton, TONS["complice"])),
            corpus)
        if texte:
            m = re.search(r"\{.*\}", texte, re.S)
            try:
                doc = json.loads(m.group(0) if m else texte)
                return {"titre": doc.get("titre", ""), "texte": doc.get("texte", texte),
                        "fournisseur": provider, "erreur": None,
                        "label": "Rapport personnalisé par IA"}
            except json.JSONDecodeError:
                return {"titre": "", "texte": texte, "fournisseur": provider,
                        "erreur": None, "label": "Rapport personnalisé par IA"}
    titre, texte = _rapport_regles(lang, donnees)
    return {"titre": titre, "texte": texte, "fournisseur": "none", "erreur": erreur,
            "label": "Rapport personnalisé automatiquement"}


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
        texte, erreur = generer(PROMPT_ADMIN, "\n---\n".join(verbatims), max_tokens=1200)
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
