"""BUS XPERIENCE — nettoyage selon les durées de conservation.

Usage:
    python3 cleanup.py            # applique les suppressions
    python3 cleanup.py --dry-run  # simule, n'écrit rien, n'efface rien

- Supprime les fichiers audio plus anciens que AUDIO_RETENTION_DAYS.
- Supprime les sessions (et leurs réponses/transcriptions/rapports) plus
  anciennes que DATA_RETENTION_DAYS.
- Ne touche JAMAIS aux réglages, campagnes, questions ou concepts.
- N'écrit jamais de texte de réponse dans son journal: uniquement des
  identifiants et des compteurs.
- Idempotent: relancer sans rien de nouveau à supprimer ne change rien.
- Si une durée n'est pas configurée, l'étape correspondante est ignorée
  avec un avertissement explicite plutôt que de choisir une valeur par défaut.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import config
import db


def _limite(jours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=jours)).isoformat(timespec="seconds")


def nettoyer_audios(c, dry_run: bool) -> dict:
    if config.AUDIO_RETENTION_DAYS is None:
        print("[cleanup] AUDIO_RETENTION_DAYS non configuré: étape audio ignorée.")
        return {"audios_supprimes": 0}
    limite = _limite(config.AUDIO_RETENTION_DAYS)
    rows = c.execute(
        "SELECT id, audio FROM reponses WHERE audio IS NOT NULL AND cree_le < ?",
        (limite,)).fetchall()
    n = 0
    for r in rows:
        chemin = db.AUDIO / r["audio"]
        if chemin.exists():
            if not dry_run:
                chemin.unlink()
            n += 1
        if not dry_run:
            c.execute("UPDATE reponses SET audio=NULL WHERE id=?", (r["id"],))
    print(f"[cleanup] audios {'à supprimer' if dry_run else 'supprimés'} "
          f"(> {config.AUDIO_RETENTION_DAYS} j): {n}")
    return {"audios_supprimes": n}


def nettoyer_sessions(c, dry_run: bool) -> dict:
    if config.DATA_RETENTION_DAYS is None:
        print("[cleanup] DATA_RETENTION_DAYS non configuré: étape sessions ignorée.")
        return {"sessions_supprimees": 0, "reponses_supprimees": 0,
                "audios_supprimes": 0, "rapports_supprimes": 0}
    limite = _limite(config.DATA_RETENTION_DAYS)
    ids = [r["id"] for r in c.execute(
        "SELECT id FROM sessions WHERE demarree_le < ?", (limite,))]
    if dry_run:
        n_reponses = 0
        if ids:
            marque = ",".join("?" * len(ids))
            n_reponses = c.execute(
                f"SELECT COUNT(*) n FROM reponses WHERE session IN ({marque})", ids
            ).fetchone()["n"]
        print(f"[cleanup] sessions à supprimer (> {config.DATA_RETENTION_DAYS} j): "
              f"{len(ids)} (avec {n_reponses} réponses)")
        return {"sessions_supprimees": len(ids), "reponses_supprimees": n_reponses,
                "audios_supprimes": 0, "rapports_supprimes": 0}
    n = db.supprimer_sessions(c, ids)
    print(f"[cleanup] sessions supprimées (> {config.DATA_RETENTION_DAYS} j): "
          f"{n['sessions']} (réponses: {n['reponses']}, audios: {n['audios']}, "
          f"rapports: {n['rapports']})")
    return {"sessions_supprimees": n["sessions"], "reponses_supprimees": n["reponses"],
            "audios_supprimes": n["audios"], "rapports_supprimes": n["rapports"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Nettoyage des données selon la conservation configurée.")
    parser.add_argument("--dry-run", action="store_true",
                        help="simule sans rien supprimer ni modifier")
    args = parser.parse_args()

    if config.AUDIO_RETENTION_DAYS is None and config.DATA_RETENTION_DAYS is None:
        print("[cleanup] AVERTISSEMENT: AUDIO_RETENTION_DAYS et DATA_RETENTION_DAYS "
              "ne sont pas configurés. Aucune suppression automatique n'a lieu. "
              "À valider avant utilisation publique (voir Admin -> Système).")

    with db.conn() as c:
        audios = nettoyer_audios(c, args.dry_run)
        sessions = nettoyer_sessions(c, args.dry_run)
        if not args.dry_run:
            db.journaliser(c, "cleanup",
                           f"audios={audios['audios_supprimes']} "
                           f"sessions={sessions['sessions_supprimees']} "
                           f"reponses={sessions['reponses_supprimees']} "
                           f"rapports={sessions['rapports_supprimes']}")
    print("[cleanup] simulation terminée (--dry-run), rien n'a été modifié." if args.dry_run
          else "[cleanup] terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
