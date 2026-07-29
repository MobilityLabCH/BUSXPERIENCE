"""BUS XPERIENCE — statistiques du rapport administrateur.

Tout est calculé depuis la base, rien n'est inventé. Chaque chiffre
retourné cite son effectif.
"""
from __future__ import annotations

import statistics as st

import db


def _filtres_sql(f: dict) -> tuple[str, list]:
    cond, args = ["1=1"], []
    if f.get("campagne"):
        cond.append("s.campagne_id=?"); args.append(f["campagne"])
    if f.get("lieu"):
        cond.append("s.lieu_id=?"); args.append(f["lieu"])
    if f.get("lang"):
        cond.append("s.lang=?"); args.append(f["lang"])
    if f.get("participants"):
        cond.append("s.participants=?"); args.append(f["participants"])
    if f.get("termine") == "oui":
        cond.append("s.terminee_le IS NOT NULL")
    if f.get("termine") == "non":
        cond.append("s.terminee_le IS NULL")
    if f.get("depuis"):
        cond.append("s.demarree_le>=?"); args.append(f["depuis"])
    if f.get("jusqua"):
        cond.append("s.demarree_le<=?"); args.append(f["jusqua"] + "T23:59:59")
    return " AND ".join(cond), args


def _sessions_frequence(c, valeur: str) -> list[str]:
    rows = c.execute(
        """SELECT r.session FROM reponses r JOIN questions q ON q.id=r.question_id
           WHERE q.params LIKE '%"segment"%' AND r.valeur=?""", (valeur,)).fetchall()
    return [r["session"] for r in rows]


def calculer(f: dict) -> dict:
    with db.conn() as c:
        cond, args = _filtres_sql(f)
        ids = [r["id"] for r in c.execute(
            f"SELECT s.id FROM sessions s WHERE {cond}", args)]
        if f.get("frequence"):
            garder = set(_sessions_frequence(c, f["frequence"]))
            ids = [i for i in ids if i in garder]
        if not ids:
            return {"n_sessions": 0, "vide": True}
        marque = ",".join("?" * len(ids))

        sess = c.execute(
            f"""SELECT COUNT(*) n, SUM(terminee_le IS NOT NULL) fini,
                SUM(participants=2) duos FROM sessions WHERE id IN ({marque})""",
            ids).fetchone()
        durees = [r["duree_s"] for r in c.execute(
            f"SELECT duree_s FROM sessions WHERE id IN ({marque}) AND duree_s IS NOT NULL",
            ids)]

        # distributions par question
        questions = []
        for q in c.execute("SELECT * FROM questions WHERE actif=1 ORDER BY ordre"):
            rows = c.execute(
                f"""SELECT valeur FROM reponses WHERE question_id=? AND cle='reponse'
                    AND session IN ({marque}) AND valeur IS NOT NULL""",
                [q["id"], *ids]).fetchall()
            vals = [r["valeur"] for r in rows]
            item = {"id": q["id"], "ordre": q["ordre"], "etape": q["etape"],
                    "type": q["type"], "fr": q["fr"], "n": len(vals),
                    "manquants": sess["n"] - len(vals)}
            if q["type"] in ("choix", "compare"):
                dist = {}
                for v in vals:
                    dist[v] = dist.get(v, 0) + 1
                item["distribution"] = sorted(dist.items(), key=lambda x: -x[1])
            elif q["type"] in ("etoiles", "echelle"):
                nums = [float(v) for v in vals if str(v).replace(".", "").isdigit()]
                if nums:
                    item["moyenne"] = round(st.mean(nums), 2)
                    item["mediane"] = st.median(nums)
                    dist = {}
                    for v in nums:
                        dist[int(v)] = dist.get(int(v), 0) + 1
                    item["distribution"] = sorted(dist.items())
            elif q["type"] == "voix":
                item["verbatims"] = [r["transcript"] for r in c.execute(
                    f"""SELECT transcript FROM reponses WHERE question_id=?
                        AND session IN ({marque}) AND transcript IS NOT NULL
                        AND length(transcript)>3""", [q["id"], *ids])]
                item["en_attente"] = c.execute(
                    f"""SELECT COUNT(*) n FROM reponses WHERE question_id=?
                        AND session IN ({marque}) AND audio IS NOT NULL
                        AND transcript IS NULL""", [q["id"], *ids]).fetchone()["n"]
            questions.append(item)

        # concepts: impact (1-5) et adoption (0-10)
        concepts = []
        for co in c.execute("SELECT * FROM concepts WHERE actif=1"):
            imp = [float(r["valeur"]) for r in c.execute(
                f"""SELECT valeur FROM reponses WHERE concept_id=? AND cle='impact'
                    AND session IN ({marque})""", [co["id"], *ids])]
            ado = [float(r["valeur"]) for r in c.execute(
                f"""SELECT valeur FROM reponses WHERE concept_id=? AND cle='adoption'
                    AND session IN ({marque})""", [co["id"], *ids])]
            if imp or ado:
                concepts.append({
                    "id": co["id"], "nom": co["nom_fr"], "n": max(len(imp), len(ado)),
                    "impact_moyen": round(st.mean(imp), 2) if imp else None,
                    "adoption_moyenne": round(st.mean(ado), 2) if ado else None,
                    "adoption_8plus": (round(100 * sum(1 for a in ado if a >= 8)
                                             / len(ado)) if ado else None)})
        concepts.sort(key=lambda x: -(x["adoption_moyenne"] or 0))

        # frictions dominantes (question choix de l'étape friction la plus répondue)
        frictions = next((q.get("distribution") for q in questions
                          if q["etape"] == "friction" and q["type"] == "choix"
                          and q.get("distribution")), [])

    return {
        "n_sessions": sess["n"], "n_terminees": sess["fini"] or 0,
        "taux_completion": round(100 * (sess["fini"] or 0) / sess["n"]) if sess["n"] else 0,
        "n_duos": sess["duos"] or 0,
        "duree_moyenne_s": round(st.mean(durees)) if durees else None,
        "duree_mediane_s": round(st.median(durees)) if durees else None,
        "questions": questions, "concepts": concepts, "frictions": frictions,
        "session_ids": ids,
    }


LIMITES_FR = [
    "Participation volontaire: l'échantillon n'est pas représentatif de la population.",
    "Le lieu et l'événement influencent qui participe et ce qui se dit.",
    "Certains effectifs peuvent être petits: lire les pourcentages avec prudence.",
    "Les réponses sont déclaratives, pas des comportements observés.",
    "Résultats à interpréter comme des signaux et des pistes d'amélioration, pas des mesures définitives.",
]
