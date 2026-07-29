# CHANGELOG

## v2.1 — Voix naturelles et sons integres (2026-07-29)

- TTS navigateur (TTS_PROVIDER=browser, gratuit, sans cle): selection
  automatique de la meilleure voix FR/DE (Natural/Online d'Edge privilegiees),
  vitesse reglable, ton legerement souriant (pitch), texte parle distinct et
  plus court que le texte affiche pour chaque question (seme par defaut,
  editable dans l'admin). Admin -> Medias: choix et test des voix, alerte si
  seule une voix basique est disponible dans le navigateur.
- Sons reels integres: medias-defaut/klaxon.mp3 (Dreiklanghorn) et
  medias-defaut/musique-voyage.mp3, installes automatiquement au demarrage,
  musique rattachee a la campagne par defaut. Klaxon reserve a la revelation
  du rapport final, activable, volume separe, test en un clic; musique avec
  boucle, fondu, ducking voix, coupure totale micro, reprise progressive.
- Migration v3 automatique (colonnes textes parles + reglages TTS/sons),
  sauvegarde prealable de la base comme toujours.
- Tests: 19 (les 3 nouveaux verifient la config TTS/sons exposee a la Cabine,
  la presence et la taille des deux mp3 servis par le serveur, et les
  reglages admin). La lecture sonore effective dans un haut-parleur et le
  rendu des voix restent a verifier a l'oreille sur la borne (Edge/Chrome).

## v2.0 — BUS XPERIENCE (2026-07-29)

Renommage complet: « La Boite » devient BUS XPERIENCE (graphie exacte),
mention « Powered by MobilityLab Sion » sur l'accueil, le parcours, le rapport
participant, les rapports admin et les impressions.

### Nouveau
- Questionnaire repense (recherche UX experience client du bus): segmentation
  frequence, etoiles baseline, localisation de la friction dans le parcours,
  irritant dominant, confiance 0-10, arbitrage frequence/ponctualite, question
  vocale unique forte, question de confort legere. Question conditionnelle
  (etoiles masquees pour les non-usagers).
- Concepts administrables FR/DE tires au sort, mesures impact (1-5) et
  adoption (0-10), classement dans le rapport admin.
- Parcours: consentement configurable, solo/duo avec double accord, etapes et
  progression visibles, retour/correction, aucune question sautee sans reponse.
- Interactions: tactile, clavier, fleches, Espace/Entree, notation par buzz
  avec anneau de validation et correction, curseur 0-10, duel gauche/droite,
  voix 45 s avec compte a rebours, detection de silence, reecoute, reprise.
- Musique de fond par campagne (fondu, ducking voix, coupure totale micro),
  sons de validation/transition/erreur synthetises, klaxon optionnel avec
  son neutre de secours. Tout administrable dans Medias/Campagnes.
- Rapport participant « wow »: mise en scene d'analyse, revelation, diplome
  tamponne, titre de fantaisie, ~100 mots, fonde uniquement sur les reponses,
  etiquete honnetement (par IA / automatiquement), plusieurs styles et tons.
- Rapport administrateur: filtres, completion, durees, distributions,
  frictions, classement des concepts, verbatims, themes vocaux, limites
  methodologiques, impression/PDF, exports CSV et JSON.
- Admin refaite en 8 sections, liste de questions compacte avec recherche,
  duplication, deplacement, versionnement, edition en page dediee.
- IA facultative none/ollama/gemini/anthropic, architecture commune, test de
  connexion, aucune cle stockee ni affichee, aucun basculement silencieux,
  audio jamais envoye a l'exterieur.
- Migrations versionnees avec sauvegarde automatique et reprise des donnees
  v1 (boite.db). Hors ligne: aucune police externe, aucun CDN.
- Infrastructure Codespaces: .devcontainer, start.sh, start-dev.sh,
  .env.example, .gitignore, 16 tests pytest.

### Teste reellement (pytest + serveur lance)
- Demarrage type Codespaces (start.sh, port 8000), /health, /cabine/, /admin
- Migration v1 -> v2 avec reprise des donnees et sauvegarde
- Redemarrage sans perte et sans recreation des questions
- Sessions solo et duo, refus participants invalides
- Reponses choix/etoiles/echelle/compare/concepts, correction sans doublon,
  refus des reponses orphelines, refus du micro sans consentement
- Rapport participant sans IA (contenu fonde sur les reponses, idempotent)
- Rapport admin, exports CSV/JSON, CRUD questions avec versionnement
- Fournisseurs anthropic et gemini avec mocks, echec reseau -> erreur propre
  et repli annonce, test de connexion sans cle

### Simule
- Appels Gemini/Anthropic (mocks, aucun credit consomme)
- Parcours participant complet via API (equivalent des ecrans)

### Non teste automatiquement / depend du materiel
- Rendu visuel et animations dans un vrai navigateur (verifie par lecture,
  syntaxe JS validee)
- Vrai micro (getUserMedia), vraie detection de silence, vrai buzzer USB,
  ecran tactile physique
- Ollama (necessite une instance locale), vraies cles Gemini/Anthropic
- faster-whisper (optionnel, non installe dans l'environnement de test)

### Limites connues
- A deux, l'interface passe au « vous » sur les ecrans d'accueil mais les
  textes des questions restent tels que rediges (le tutoiement est conserve);
  rediger des variantes « vous » dans l'admin si necessaire.
- Le versionnement des questions est un compteur + date, pas un historique
  complet des contenus.
- La detection de silence utilise un seuil RMS simple, a ajuster selon le
  bruit ambiant du lieu.
- L'ecran de consentement doit etre valide juridiquement (voir README).
