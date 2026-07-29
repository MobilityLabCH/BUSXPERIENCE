"""BUS XPERIENCE — configuration protection des données, centralisée.

Toutes les valeurs présentées au public ou à l'administration sur le
consentement, le responsable de traitement et la conservation des données
viennent d'ici, jamais codées en dur ailleurs. Rien n'est inventé: quand une
valeur précise à BUS XPERIENCE n'est pas confirmée, le champ reste marqué
« à confirmer » plutôt que de recevoir une valeur plausible mais fausse.

Cette implémentation est technique et ne constitue pas une validation
juridique. Voir README.md.
"""
from __future__ import annotations

import os

# ------------------------------------------------------------- notice

PRIVACY_NOTICE_VERSION = os.environ.get("PRIVACY_NOTICE_VERSION", "1.0")

# Responsable précis du projet BUS XPERIENCE: reste à confirmer par le
# service Legal / Datenschutz. Ne jamais remplacer par une valeur inventée.
_A_CONFIRMER_FR = "À confirmer par Legal/Datenschutz — La Poste Suisse SA, projet BUS XPERIENCE / MobilityLab"
_A_CONFIRMER_DE = "Von Legal/Datenschutz zu bestätigen — Die Schweizerische Post AG, Projekt BUS XPERIENCE / MobilityLab"

DATA_CONTROLLER_FR = os.environ.get("DATA_CONTROLLER_FR", _A_CONFIRMER_FR)
DATA_CONTROLLER_DE = os.environ.get("DATA_CONTROLLER_DE", _A_CONFIRMER_DE)
DATA_CONTROLLER_IS_CONFIRMED = bool(os.environ.get("DATA_CONTROLLER_FR")) and bool(
    os.environ.get("DATA_CONTROLLER_DE"))

# Adresse et contact public de La Poste (valeurs publiques par défaut).
DATA_CONTROLLER_ADDRESS = os.environ.get(
    "DATA_CONTROLLER_ADDRESS",
    "La Poste Suisse SA, Protection des données, Legal, Wankdorfallee 4, 3030 Berne",
)
PRIVACY_CONTACT_EMAIL = os.environ.get("PRIVACY_CONTACT_EMAIL", "betroffenenrechte@post.ch")

# ------------------------------------------------------------- conservation
# Volontairement PAS de valeur par défaut: choisir silencieusement une durée
# légale serait prétendre à une conformité non vérifiée. Tant que ces
# variables ne sont pas définies, l'admin affiche un avertissement explicite
# et cleanup.py refuse de deviner.


def _jours(nom: str) -> int | None:
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        return None
    try:
        n = int(valeur)
        return n if n > 0 else None
    except ValueError:
        return None


AUDIO_RETENTION_DAYS = _jours("AUDIO_RETENTION_DAYS")
DATA_RETENTION_DAYS = _jours("DATA_RETENTION_DAYS")

# ------------------------------------------------------------- liens

PRIVACY_URL_FR = os.environ.get(
    "PRIVACY_URL_FR",
    "https://www.post.ch/fr/pages/footer/protection-des-donnees-et-informations-legales",
)
PRIVACY_URL_DE = os.environ.get(
    "PRIVACY_URL_DE",
    "https://www.post.ch/de/pages/footer/datenschutz-und-rechtliches",
)

# Page détaillée propre à BUS XPERIENCE, si publiée à une URL publique
# distincte de ce serveur (ex. site vitrine). Si absente, le QR code et les
# liens de la Cabine pointent vers la page /protection-des-donnees servie
# par cette application, ou à défaut vers PRIVACY_URL_FR/DE.
PUBLIC_PRIVACY_URL_FR = os.environ.get("PUBLIC_PRIVACY_URL_FR", "").strip()
PUBLIC_PRIVACY_URL_DE = os.environ.get("PUBLIC_PRIVACY_URL_DE", "").strip()


def lien_consentement(lang: str, base_url: str = "") -> str:
    """URL à afficher/encoder en QR sur l'écran de consentement.

    Priorité: URL publique propre à BUS XPERIENCE > page détaillée servie par
    cette application > page générale de La Poste.
    """
    de = lang == "de"
    propre = PUBLIC_PRIVACY_URL_DE if de else PUBLIC_PRIVACY_URL_FR
    if propre:
        return propre
    if base_url:
        return base_url.rstrip("/") + ("/datenschutz" if de else "/protection-des-donnees")
    return PRIVACY_URL_DE if de else PRIVACY_URL_FR


# ------------------------------------------------------------- IA

_DESTINATIONS_FR = {
    "none": "Traitement local uniquement. Aucune donnée textuelle n'est envoyée à un fournisseur externe.",
    "ollama": "Traitement local (Ollama). Aucune donnée textuelle n'est envoyée à un fournisseur externe.",
    "gemini": "Google Gemini (Google Ireland Limited / Google LLC) reçoit uniquement les réponses textuelles nécessaires à la génération du profil de voyage — jamais l'audio.",
    "anthropic": "Anthropic reçoit uniquement les réponses textuelles nécessaires à la génération du profil de voyage — jamais l'audio.",
}
_DESTINATIONS_DE = {
    "none": "Nur lokale Verarbeitung. Es werden keine Textdaten an einen externen Anbieter gesendet.",
    "ollama": "Lokale Verarbeitung (Ollama). Es werden keine Textdaten an einen externen Anbieter gesendet.",
    "gemini": "Google Gemini (Google Ireland Limited / Google LLC) erhält ausschliesslich die für das Reiseprofil nötigen Textantworten — nie die Audiodatei.",
    "anthropic": "Anthropic erhält ausschliesslich die für das Reiseprofil nötigen Textantworten — nie die Audiodatei.",
}
_PAYS_FR = {
    "none": "Suisse uniquement (traitement local, sur site).",
    "ollama": "Suisse uniquement (traitement local, sur site).",
    "gemini": "Selon la configuration Google Gemini — Union européenne et/ou États-Unis. Pays exacts à confirmer par Legal avant usage public.",
    "anthropic": "États-Unis (Anthropic). Pays exacts à confirmer par Legal avant usage public.",
}
_PAYS_DE = {
    "none": "Nur Schweiz (lokale Verarbeitung, vor Ort).",
    "ollama": "Nur Schweiz (lokale Verarbeitung, vor Ort).",
    "gemini": "Je nach Google-Gemini-Konfiguration — Europäische Union und/oder USA. Genaue Länder vor öffentlichem Einsatz durch Legal zu bestätigen.",
    "anthropic": "USA (Anthropic). Genaue Länder vor öffentlichem Einsatz durch Legal zu bestätigen.",
}


def ai_data_destination_fr(provider: str) -> str:
    return _DESTINATIONS_FR.get(provider, _DESTINATIONS_FR["none"])


def ai_data_destination_de(provider: str) -> str:
    return _DESTINATIONS_DE.get(provider, _DESTINATIONS_DE["none"])


def ai_processing_countries_fr(provider: str) -> str:
    return _PAYS_FR.get(provider, _PAYS_FR["none"])


def ai_processing_countries_de(provider: str) -> str:
    return _PAYS_DE.get(provider, _PAYS_DE["none"])


# ------------------------------------------------------------- diagnostic

def etat_configuration() -> dict:
    """Résumé des paramètres manquants ou à confirmer, pour Admin -> Système."""
    manquants = []
    if not (os.environ.get("DATA_CONTROLLER_FR") and os.environ.get("DATA_CONTROLLER_DE")):
        manquants.append("responsable précis de BUS XPERIENCE (DATA_CONTROLLER_FR/DE)")
    if AUDIO_RETENTION_DAYS is None:
        manquants.append("AUDIO_RETENTION_DAYS")
    if DATA_RETENTION_DAYS is None:
        manquants.append("DATA_RETENTION_DAYS")
    return {"manquants": manquants, "complet": not manquants}
