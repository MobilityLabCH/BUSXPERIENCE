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
personne en {langue}, ton {ton}, comme une MINI-HISTOIRE en trois actes:
Acte 1, la personne et sa relation au bus (fréquence, note en étoiles).
Acte 2, le petit méchant de son voyage (moment de friction, irritant,
niveau de confiance). Acte 3, le rebondissement: le concept qu'elle a préféré
(avec sa note) et, si elle existe, une courte citation exacte de sa réponse
vocale. Termine par « Verdict officiel : » suivi d'un titre de fantaisie
flatteur lié à ses réponses. 80 à 120 mots. N'invente RIEN: uniquement les
données fournies. Jamais moqueur, jamais infantilisant, jamais administratif.
Réponds au format JSON strict: {{"titre": "...", "texte": "..."}}"""

TITRES = {
    "fr": {
        "correspondance": ["Ministre des correspondances sans sprint",
                           "Grand stratège des trajets sans mauvaise surprise",
                           "Gardienne officielle des correspondances qui attendent",
                           "Négociateur en chef des changements de quai sereins"],
        "retard": ["Chevalier de l'information en temps réel",
                   "Ambassadeur des bus qui tiennent leurs promesses",
                   "Vigie suprême des horaires qui disent la vérité",
                   "Commissaire aux retards enfin annoncés"],
        "attente": ["Grande enquêtrice des arrêts sous la pluie",
                    "Président du comité des abris enfin dignes",
                    "Sentinelle des quais éclairés et des bancs secs"],
        "confort": ["Présidente du comité des sièges enfin confortables",
                    "Inspecteur général du voyage agréable",
                    "Défenseur officiel de la place assise côté fenêtre"],
        "billet": ["Docteur honoris causa en billets sans prise de tête",
                   "Championne du voyage sans calcul mental"],
        "defaut": ["Voix remarquable de l'expérience bus",
                   "Experte internationale du dernier kilomètre",
                   "Conseiller spécial de la ligne idéale",
                   "Éclaireuse en chef des trajets qui donnent envie",
                   "Ambassadeur itinérant du bus de demain"],
    },
    "de": {
        "correspondance": ["Minister der Anschlüsse ohne Sprint",
                           "Grossstratege der Reisen ohne böse Überraschung",
                           "Hüterin der Anschlüsse, die wirklich warten"],
        "retard": ["Ritterin der Echtzeit-Information",
                   "Botschafter der Busse, die ihr Wort halten",
                   "Oberste Wache der ehrlichen Fahrpläne"],
        "attente": ["Grosse Erforscherin der Haltestellen im Regen",
                    "Wächter der beleuchteten, trockenen Haltestellen"],
        "confort": ["Präsident des Komitees der endlich bequemen Sitze",
                    "Verteidigerin des Fensterplatzes"],
        "billet": ["Ehrendoktor der Billette ohne Kopfzerbrechen"],
        "defaut": ["Bemerkenswerte Stimme des Buserlebnisses",
                   "Internationale Expertin der letzten Meile",
                   "Reisender Botschafter des Busses von morgen"],
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
    """Sans IA: une mini-histoire en trois actes, variée, fidèle aux réponses.
    Acte 1 la relation au bus, acte 2 le petit méchant, acte 3 le rebondissement."""
    fr = lang != "de"
    titre = _choisir_titre("fr" if fr else "de", d)

    # --- acte 1: la personne et le bus (fréquence + étoiles)
    freq = (d.get("frequence") or "").lower()
    if fr:
        if "jamais" in freq:
            a1 = "Tout commence par un aveu: le bus et toi, c'est encore une histoire à écrire."
        elif "jours" in freq or "semaine" in freq:
            a1 = random.choice([
                "Tout commence plutôt bien: toi, le bus, une vieille histoire qui roule.",
                "Acte un: un·e habitué·e monte à bord, et le bus le sent."])
        else:
            a1 = "Tout commence prudemment: toi et le bus, vous vous voyez de temps en temps."
        if d.get("etoiles"):
            a1 += f" Dernier trajet: {d['etoiles']} étoile(s) sur 5, la critique est tombée."
    else:
        if "nie" in freq:
            a1 = "Alles beginnt mit einem Geständnis: du und der Bus, das ist noch eine unbeschriebene Geschichte."
        elif "täglich" in freq or "woche" in freq:
            a1 = "Alles beginnt gut: du, der Bus, eine eingespielte Geschichte."
        else:
            a1 = "Alles beginnt vorsichtig: du und der Bus, ihr seht euch ab und zu."
        if d.get("etoiles"):
            a1 += f" Letzte Fahrt: {d['etoiles']} von 5 Sternen, das Urteil steht."

    # --- acte 2: le petit méchant (moment, irritant, confiance)
    mechant = d.get("irritant") or d.get("moment")
    if fr:
        if mechant and mechant not in ("Rien ne me stresse", "Rien de tout ça"):
            a2 = random.choice([
                f"Puis entre en scène ton adversaire officiel: {mechant.lower()}.",
                f"Mais chaque histoire a son petit méchant, et le tien s'appelle: {mechant.lower()}."])
        else:
            a2 = "Petit rebondissement: aucun méchant déclaré, le suspense reste entier."
        if d.get("confiance") is not None:
            a2 += f" Confiance pour arriver à l'heure: {d['confiance']}/10, tout est dit."
    else:
        if mechant and mechant not in ("Nichts stresst mich", "Nichts davon"):
            a2 = f"Dann betritt dein offizieller Gegenspieler die Bühne: {mechant}."
        else:
            a2 = "Kleine Wendung: kein erklärter Bösewicht, die Spannung bleibt."
        if d.get("confiance") is not None:
            a2 += f" Vertrauen, pünktlich anzukommen: {d['confiance']}/10, alles gesagt."

    # --- acte 3: le rebondissement (concept + verbatim)
    if fr:
        if d.get("concept"):
            note = f" ({d['concept_note']}/10)" if d.get("concept_note") is not None else ""
            a3 = random.choice([
                f"Heureusement, tu as choisi ton arme secrète: «{d['concept']}»{note}. "
                "Avec ça, la voiture pourrait bien se reposer un peu.",
                f"Le rebondissement porte un nom: «{d['concept']}»{note}. "
                "Presque une déclaration d'amour, avec horaire fiable."])
        else:
            a3 = "Le rebondissement reste à écrire, et c'est exactement pour ça qu'on t'a écouté."
        if d.get("verbatim"):
            a3 += f" Ta réplique culte: «{d['verbatim'][:100].strip()}»."
        a3 += " " + random.choice([
            "Tout ceci part vraiment vers les bonnes personnes.",
            "BUS XPERIENCE transmet, le bus ne le sait pas encore, mais il va s'améliorer.",
            "Tes idées prennent la prochaine correspondance vers ceux qui décident."])
    else:
        if d.get("concept"):
            note = f" ({d['concept_note']}/10)" if d.get("concept_note") is not None else ""
            a3 = (f"Zum Glück hast du deine Geheimwaffe gewählt: «{d['concept']}»{note}. "
                  "Damit könnte das Auto sich mal ausruhen.")
        else:
            a3 = "Die Wendung ist noch offen, genau darum haben wir dir zugehört."
        if d.get("verbatim"):
            a3 += f" Dein Kultsatz: «{d['verbatim'][:100].strip()}»."
        a3 += " Alles geht wirklich an die richtigen Leute."

    return titre, "\n\n".join([a1, a2, a3])


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
