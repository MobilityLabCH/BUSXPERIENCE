"""BUS XPERIENCE — pages publiques d'information sur la protection des
données, bilingues, lisibles sur ordinateur et téléphone.

Implémentation technique et transparente, PAS une certification juridique:
voir le bandeau affiché en bas de chaque page.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import ai
import config as vieprivee
import db

router = APIRouter(tags=["public"])
templates = Jinja2Templates(directory=str(db.RACINE / "templates"))


def _contexte(lang: str) -> dict:
    provider = ai.provider_actuel()
    return {
        "lang": lang,
        "version": vieprivee.PRIVACY_NOTICE_VERSION,
        "responsable": vieprivee.DATA_CONTROLLER_DE if lang == "de" else vieprivee.DATA_CONTROLLER_FR,
        "responsable_confirme": vieprivee.DATA_CONTROLLER_IS_CONFIRMED,
        "adresse": vieprivee.DATA_CONTROLLER_ADDRESS,
        "contact": vieprivee.PRIVACY_CONTACT_EMAIL,
        "audio_jours": vieprivee.AUDIO_RETENTION_DAYS,
        "donnees_jours": vieprivee.DATA_RETENTION_DAYS,
        "provider": provider,
        "destination": vieprivee.ai_data_destination_de(provider) if lang == "de"
                       else vieprivee.ai_data_destination_fr(provider),
        "pays": vieprivee.ai_processing_countries_de(provider) if lang == "de"
                else vieprivee.ai_processing_countries_fr(provider),
        "lien_general": vieprivee.PRIVACY_URL_DE if lang == "de" else vieprivee.PRIVACY_URL_FR,
    }


@router.get("/protection-des-donnees", response_class=HTMLResponse)
def protection_des_donnees(request: Request):
    return templates.TemplateResponse(request, "protection.html", _contexte("fr"))


@router.get("/datenschutz", response_class=HTMLResponse)
def datenschutz(request: Request):
    return templates.TemplateResponse(request, "protection.html", _contexte("de"))
