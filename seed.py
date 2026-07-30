"""BUS XPERIENCE — contenu par défaut, semé UNE seule fois.

Le questionnaire est conçu comme un parcours de recherche UX sur
l'expérience client du bus, pas comme une enquête sur les modes de
transport. Chaque question a une utilité déclarée en commentaire.
Le réglage seed_version empêche toute recréation au démarrage.
"""
from __future__ import annotations

import json

import db

SEED_VERSION = "5"

# (ordre, etape, type, fr, de, options_fr, options_de, params, condition, parle_fr, parle_de)
QUESTIONS = [
    # ---------- ÉTAPE 1 · Ton expérience -------------------------------
    # Segmentation: permet de comparer usagers réguliers / occasionnels /
    # non-usagers. Une seule question, jamais le sujet central.
    (10, "experience", "choix",
     "Pour commencer: le bus, tu le prends…",
     "Zum Start: Wie oft nimmst du den Bus?",
     "Presque tous les jours\nChaque semaine\nQuelques fois par mois\nRarement\nJamais ou presque",
     "Fast täglich\nJede Woche\nEin paar Mal im Monat\nSelten\nNie oder fast nie",
     {"segment": True}, None,
     "Alors, le bus, tu le prends souvent ?", "Wie oft nimmst du eigentlich den Bus?"),
    # Baseline émotionnelle mesurable et comparable entre campagnes.
    # Notation au buzzer: un buzz = une étoile.
    (20, "experience", "etoiles",
     "Ton dernier trajet en bus, il mérite combien d'étoiles ?",
     "Deine letzte Busfahrt: Wie viele Sterne verdient sie?",
     "", "", {"max": 5},
     {"question_ordre": 10, "valeurs": ["Jamais ou presque", "Nie oder fast nie"],
      "regle": "masquer_si"},
     "Ton dernier trajet en bus… combien d'étoiles ?", "Deine letzte Busfahrt… wie viele Sterne?"),
    # Localise la dégradation dans le parcours client (avant / pendant / après).
    (30, "experience", "choix",
     "Dans un trajet en bus, le moment le moins agréable, c'est plutôt…",
     "Der unangenehmste Moment einer Busreise ist für dich eher…",
     "Préparer le trajet et l'horaire\nAttendre à l'arrêt\nMonter et payer\nLe voyage à bord\nLa correspondance\nRien de tout ça\nJe ne sais pas",
     "Reise und Fahrplan vorbereiten\nAn der Haltestelle warten\nEinsteigen und bezahlen\nDie Fahrt selbst\nDas Umsteigen\nNichts davon\nWeiss nicht",
     {}, None,
     "Et le moment le moins agréable, c'est lequel ?", "Und der unangenehmste Moment, welcher ist das?"),

    # ---------- ÉTAPE 2 · Ce qui coince --------------------------------
    # Identifie l'irritant dominant côté incertitude/stress, formulations
    # équilibrées, avec porte de sortie non orientée.
    (40, "friction", "choix",
     "Qu'est-ce qui te stresse le plus quand tu comptes sur le bus ?",
     "Was stresst dich am meisten, wenn du dich auf den Bus verlässt?",
     "Un retard sans information\nRater la correspondance\nNe pas savoir quel billet acheter\nUn bus bondé\nAttendre dans le froid ou le noir\nRien ne me stresse\nAutre chose",
     "Eine Verspätung ohne Information\nDen Anschluss verpassen\nNicht wissen, welches Billett\nEin überfüllter Bus\nWarten in Kälte oder Dunkelheit\nNichts stresst mich\nEtwas anderes",
     {}, None,
     "Qu'est-ce qui te stresse le plus avec le bus ?", "Was stresst dich am meisten beim Bus?"),
    # Mesure la confiance dans la fiabilité, le levier n°1 face à la voiture.
    # Échelle 0-10 en onze cases, pilotée au buzzer, comparable entre campagnes.
    (50, "friction", "echelle",
     "Rendez-vous important à 9h. Tu fais confiance au bus pour y être à l'heure ?",
     "Wichtiger Termin um 9 Uhr. Vertraust du dem Bus, pünktlich dort zu sein?",
     "", "", {"max": 10, "min_libelle_fr": "Pas du tout", "max_libelle_fr": "Totalement",
              "min_libelle_de": "Gar nicht", "max_libelle_de": "Voll und ganz"}, None,
     "Rendez-vous à neuf heures… tu fais confiance au bus ?", "Termin um neun… vertraust du dem Bus?"),
    # Arbitrage forcé entre deux leviers, plus informatif qu'une note isolée.
    (60, "friction", "compare",
     "Si CarPostal ne pouvait améliorer qu'une chose, tu choisis quoi ?",
     "Wenn PostAuto nur eines verbessern könnte, was wählst du?",
     "Des bus plus fréquents\nDes bus plus ponctuels",
     "Häufigere Busse\nPünktlichere Busse",
     {}, None,
     "Une seule amélioration possible. Tu choisis quoi ?", "Nur eine Verbesserung. Was wählst du?"),

    # ---------- ÉTAPE 3 · Les idées à tester ---------------------------
    # Les concepts tirés au sort s'insèrent automatiquement ici (voir table
    # concepts). Chaque concept mesure impact (étoiles) + adoption (échelle).

    # ---------- ÉTAPE 4 · Ta priorité ----------------------------------
    # LA question ouverte, unique et forte. Voix, 45 s max.
    # Phrase projective à compléter: réduit l'effet page blanche, produit des
    # verbatims orientés solution, directement exploitables.
    (80, "priorite", "voix",
     "Termine cette phrase : je prendrais le bus plus souvent si…",
     "Vervollständige diesen Satz: Ich würde öfter den Bus nehmen, wenn…",
     "", "", {"duree_voix": 45}, None,
     "Termine cette phrase… je prendrais le bus plus souvent si…",
     "Vervollständige den Satz… ich würde öfter den Bus nehmen, wenn…"),
    # Touche d'humour utile: préférence de confort réelle, ton léger,
    # donne aussi une accroche au rapport final.
    (90, "priorite", "choix",
     "Dernière question, très sérieuse: ta place préférée dans le bus ?",
     "Letzte, sehr ernste Frage: dein Lieblingsplatz im Bus?",
     "Tout devant, vue panoramique\nAu fond, comme au cinéma\nCôté fenêtre, mode contemplation\nPrès de la porte, sortie rapide\nPeu importe, tant que je suis assis·e",
     "Ganz vorne, Panoramablick\nGanz hinten, wie im Kino\nAm Fenster, Kontemplationsmodus\nBei der Tür, schneller Ausstieg\nEgal, Hauptsache sitzen",
     {}, None,
     "Dernière question, très sérieuse… ta place préférée ?", "Letzte, sehr ernste Frage… dein Lieblingsplatz?"),
]

# Concepts testés: impact sur l'expérience (étoiles 1-5) + probabilité de
# prendre le bus plus souvent (échelle 0-10). Jamais « bonne idée ? ».
CONCEPTS = [
    ("Ne jamais rater ta correspondance",
     "Deinen Anschluss nie mehr verpassen",
     "Si ton bus est en retard, ta correspondance t'attend ou une solution t'est proposée immédiatement.",
     "Ist dein Bus verspätet, wartet dein Anschluss oder du erhältst sofort eine Lösung."),
    ("Savoir tout de suite si ton bus a du retard",
     "Sofort wissen, wenn dein Bus Verspätung hat",
     "Dès qu'un retard est connu, tu es prévenu·e avec le nouveau temps d'attente réel.",
     "Sobald eine Verspätung bekannt ist, wirst du mit der neuen realen Wartezeit informiert."),
    ("Toujours avoir un plan B en cas de perturbation",
     "Bei Störungen immer einen Plan B haben",
     "En cas de perturbation, un autre itinéraire t'est proposé tout seul, sans chercher.",
     "Bei Störungen wird dir automatisch eine andere Route vorgeschlagen, ohne Suchen."),
    ("Savoir à l'avance si ton bus est bondé",
     "Vorher wissen, ob dein Bus voll ist",
     "Avant de monter, tu sais si le bus est vide, normal ou bondé.",
     "Vor dem Einsteigen siehst du, ob der Bus leer, normal oder überfüllt ist."),
    ("Partir de chez toi pile au bon moment",
     "Genau zur richtigen Zeit von zuhause losgehen",
     "Ton téléphone te dit quand partir de chez toi pour arriver pile à l'arrêt.",
     "Dein Handy sagt dir, wann du losgehen musst, um genau richtig an der Haltestelle zu sein."),
    ("Voyager sans jamais penser au billet",
     "Fahren, ohne je ans Billett zu denken",
     "Tu montes, tu voyages, le bon prix se calcule tout seul. Zéro réflexion billet.",
     "Einsteigen, fahren, der richtige Preis berechnet sich von selbst. Null Billett-Denken."),
    ("Attendre ton bus au sec et en confiance",
     "Trocken und entspannt auf den Bus warten",
     "À l’abri de la pluie, avec un bon éclairage et une vraie place pour s’asseoir. L’attente devient plus confortable et rassurante.",
     "Geschützt vor Regen, gut beleuchtet und mit einer richtigen Sitzgelegenheit. So wird das Warten angenehmer und entspannter."),
    ("Signaler un souci en un instant",
     "Ein Problem in Sekunden melden",
     "Un problème à bord ou à l'arrêt ? Tu le signales en deux gestes depuis ton téléphone.",
     "Ein Problem im Bus oder an der Haltestelle? In zwei Gesten vom Handy gemeldet."),
    ("Rejoindre le bus même sans arrêt à proximité",
     "Zum Bus kommen, auch ohne Haltestelle in der Nähe",
     "Un petit véhicule vient te chercher pour rejoindre la ligne principale quand il n'y a pas d'arrêt proche.",
     "Ein kleines Fahrzeug holt dich ab und bringt dich zur Hauptlinie, wenn keine Haltestelle nah ist."),
    ("Savoir comment finir ton trajet sans réfléchir",
     "Ohne Nachdenken wissen, wie du ans Ziel kommst",
     "À l'arrivée, on te montre comment finir le trajet: à pied, vélo en libre-service, correspondance.",
     "Bei der Ankunft siehst du, wie du ans Ziel kommst: zu Fuss, Leihvelo, Anschluss."),
]

CONSENT_FR = """En participant, une ou deux de tes réponses seront enregistrées au micro, transcrites et analysées automatiquement afin de mieux comprendre ton expérience et d’améliorer les services de bus.

Ne donne pas de nom ni d’information personnelle dans tes réponses.

La participation est volontaire. Tu peux arrêter à tout moment."""

CONSENT_DE = """Wenn du teilnimmst, werden ein bis zwei deiner Antworten mit dem Mikrofon aufgenommen, transkribiert und automatisch ausgewertet. So können wir dein Erlebnis besser verstehen und das Busangebot verbessern.

Bitte nenne keine Namen oder persönlichen Angaben.

Die Teilnahme ist freiwillig. Du kannst jederzeit abbrechen."""


def semer() -> str:
    """Sème le contenu par défaut une seule fois (seed_version)."""
    with db.conn() as c:
        if db.reglage(c, "seed_version") == SEED_VERSION:
            return "contenu déjà semé, rien à faire"
        deja_questions = c.execute("SELECT COUNT(*) n FROM questions").fetchone()["n"]
        if not deja_questions:
            for (ordre, etape, type_, fr, de, ofr, ode, params, cond,
                 parle_fr, parle_de) in QUESTIONS:
                c.execute(
                    """INSERT INTO questions (ordre, etape, type, fr, de, options_fr,
                       options_de, params, condition, texte_parle_fr, texte_parle_de,
                       modifie_le) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (ordre, etape, type_, fr, de, ofr, ode,
                     json.dumps(params, ensure_ascii=False),
                     json.dumps(cond, ensure_ascii=False) if cond else "",
                     parle_fr, parle_de, db.now()))
        if not c.execute("SELECT COUNT(*) n FROM concepts").fetchone()["n"]:
            for nom_fr, nom_de, desc_fr, desc_de in CONCEPTS:
                c.execute(
                    "INSERT INTO concepts (nom_fr, nom_de, desc_fr, desc_de) VALUES (?,?,?,?)",
                    (nom_fr, nom_de, desc_fr, desc_de))
        if not c.execute("SELECT COUNT(*) n FROM campagnes").fetchone()["n"]:
            c.execute(
                """INSERT INTO campagnes (nom, consent_fr, consent_de, musique,
                   musique_active, cree_le) VALUES (?,?,?,?,1,?)""",
                ("Campagne de lancement", CONSENT_FR, CONSENT_DE,
                 "musique-voyage.mp3", db.now()))
            db.poser_reglage(c, "campagne_courante",
                             str(c.execute("SELECT last_insert_rowid() i").fetchone()["i"]))
        if not c.execute("SELECT COUNT(*) n FROM lieux").fetchone()["n"]:
            c.execute("INSERT INTO lieux (nom, remarque, cree_le) VALUES (?,?,?)",
                      ("Dépôt CarPostal Sion", "Lieu de test", db.now()))
            db.poser_reglage(c, "lieu_courant",
                             str(c.execute("SELECT last_insert_rowid() i").fetchone()["i"]))
        for cle, valeur in (("nb_concepts", "2"),):
            if db.reglage(c, cle) is None:
                db.poser_reglage(c, cle, valeur)

        # Mise à jour douce des anciens contenus par défaut. On ne remplace
        # jamais un texte déjà personnalisé dans l'administration.
        c.execute(
            """UPDATE questions SET fr=?, de=?, options_fr=?, options_de=?,
               texte_parle_fr=?, texte_parle_de=?, modifie_le=?
               WHERE ordre=10 AND fr='Pour commencer: le bus, tu le prends…'""",
            (QUESTIONS[0][3], QUESTIONS[0][4], QUESTIONS[0][5], QUESTIONS[0][6],
             QUESTIONS[0][9], QUESTIONS[0][10], db.now()))
        c.execute(
            """UPDATE concepts SET nom_fr=?, nom_de=?, desc_fr=?, desc_de=?
               WHERE nom_fr='Arrêt confortable et éclairé'
               AND nom_de='Komfortable, beleuchtete Haltestelle'""",
            ("Un arrêt où l’on se sent bien", "Eine Haltestelle zum Wohlfühlen",
             "À l’abri de la pluie, avec un bon éclairage et une vraie place pour s’asseoir. L’attente devient plus confortable et rassurante.",
             "Geschützt vor Regen, gut beleuchtet und mit einer richtigen Sitzgelegenheit. So wird das Warten angenehmer und entspannter."))
        anciens_fr = (
            "Bienvenue dans BUS XPERIENCE !\nQuelques minutes pour améliorer l'expérience du bus.\n\n"
            "Tes réponses servent à l'innovation, à la recherche utilisateur et à\n"
            "l'amélioration des services — pas pour analyser toute ta vie.\n"
            "Une ou deux réponses peuvent être enregistrées au micro puis transcrites\n"
            "et analysées automatiquement. La participation est volontaire et tu peux\n"
            "t'arrêter à tout moment."
        )
        c.execute("UPDATE campagnes SET consent_fr=? WHERE consent_fr=?", (CONSENT_FR, anciens_fr))
        anciens_de = (
            "Willkommen bei BUS XPERIENCE!\nEin paar Minuten, um das Buserlebnis zu verbessern.\n\n"
            "Deine Antworten dienen Innovation, Nutzerforschung und besseren\n"
            "Services — nicht, um dein ganzes Leben zu analysieren.\n"
            "Ein bis zwei Antworten können per Mikrofon aufgenommen, transkribiert und\n"
            "automatisch ausgewertet werden. Die Teilnahme ist freiwillig, du kannst\n"
            "jederzeit aufhören."
        )
        c.execute("UPDATE campagnes SET consent_de=? WHERE consent_de=?", (CONSENT_DE, anciens_de))
        # v4 (seed): le consentement devient micro-obligatoire, deux choix
        # seulement. L'ancien texte v3.x (encore éditable, jamais personnalisé)
        # est remplacé par le nouveau texte légal, jamais un texte déjà modifié
        # dans l'admin.
        v3_fr = ("Tes réponses nous aident à comprendre ce qui fonctionne, ce qui agace et ce "
                 "qui devrait changer dans l’expérience du bus.\n\nElles servent à l’innovation, "
                 "à la recherche utilisateur et à l’amélioration des services — pas à savoir ce "
                 "que tu as mangé à midi.\n\nAvec le micro, une ou deux réponses peuvent être "
                 "enregistrées, transcrites et analysées automatiquement. Tu peux aussi "
                 "participer sans micro. La participation est volontaire et tu peux arrêter à "
                 "tout moment.")
        c.execute("UPDATE campagnes SET consent_fr=? WHERE consent_fr=?", (CONSENT_FR, v3_fr))
        v3_de = ("Deine Antworten helfen uns zu verstehen, was gut funktioniert, was stört und "
                 "was sich am Bus-Erlebnis ändern sollte.\n\nSie dienen Innovation, "
                 "Nutzerforschung und der Verbesserung unserer Angebote — nicht dazu, "
                 "herauszufinden, was du zu Mittag gegessen hast.\n\nMit Mikrofon können ein "
                 "bis zwei Antworten aufgenommen, transkribiert und automatisch ausgewertet "
                 "werden. Du kannst auch ohne Mikrofon teilnehmen. Die Teilnahme ist freiwillig "
                 "und du kannst jederzeit aufhören.")
        c.execute("UPDATE campagnes SET consent_de=? WHERE consent_de=?", (CONSENT_DE, v3_de))
        # v5 (seed): les titres de concepts deviennent des bénéfices voyageurs
        # ("Savoir tout de suite si ton bus a du retard" plutôt qu'un nom
        # technique de fonctionnalité). Ne remplace que les anciens titres par
        # défaut exacts, jamais un concept renommé dans l'admin.
        ANCIENS_TITRES_CONCEPTS = (
            ("Garantie de correspondance", "Anschlussgarantie"),
            ("Alerte retard immédiate", "Sofortige Verspätungsmeldung"),
            ("Itinéraire alternatif automatique", "Automatische Alternativroute"),
            ("Niveau d'occupation du bus", "Auslastungsanzeige"),
            ("Alerte départ de la maison", "Losgeh-Alarm"),
            ("Billet automatique simplifié", "Automatisches einfaches Billett"),
            ("Un arrêt où l’on se sent bien", "Eine Haltestelle zum Wohlfühlen"),
            ("Signalement en deux secondes", "Melden in zwei Sekunden"),
            ("Rabattement à la demande", "Zubringer auf Abruf"),
            ("Info dernier kilomètre", "Letzte-Meile-Info"),
        )
        for (ancien_fr, ancien_de), (nouveau_fr, nouveau_de, *_reste) in zip(
                ANCIENS_TITRES_CONCEPTS, CONCEPTS):
            c.execute(
                "UPDATE concepts SET nom_fr=?, nom_de=? WHERE nom_fr=? AND nom_de=?",
                (nouveau_fr, nouveau_de, ancien_fr, ancien_de))
        db.poser_reglage(c, "seed_version", SEED_VERSION)
        db.journaliser(c, "seed", f"contenu par défaut v{SEED_VERSION}")
    return "contenu par défaut semé"
