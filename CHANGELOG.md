# CHANGELOG

## v4.1 — Buzzer corrigé, texte légal centralisé, QR jamais localhost, refonte visuelle du consentement (2026-07-29)

Implémentation technique renforcée. Validation juridique interne (Legal /
Datenschutz de la Poste) encore nécessaire — ceci n'est PAS une certification
juridique.

### Buzzer, Space, Enter — bug corrigé
- Gestionnaire de pression central et unique partagé par le buzzer physique,
  Space, Enter, le buzzer à l'écran et le tactile de secours.
- Cause du bug historique de double activation identifiée et corrigée: les
  boutons générés (choix, échelle, duel, revue vocale) recevaient le focus
  clavier et pouvaient être activés nativement par Space/Enter *en plus* de
  nos propres gestionnaires. Correctif: tous ces boutons sont désormais hors
  tabulation (`tabindex="-1"`), Space/Enter ne sont plus interprétés qu'à un
  seul endroit.
- Seuils clarifiés: appui court < 650 ms (suivant), appui long ≥ 650 ms
  (validation au relâchement), appui très long ≥ 4000 ms (confirmation
  d'abandon). `keydown` fait systématiquement `preventDefault()` et ignore
  `event.repeat`; `keyup` calcule la durée réelle et déclenche une seule
  action.
- Nouveau verrou anti-double-validation pendant les 230 ms de transition
  entre deux écrans (`transitioning`).
- Réinitialisation explicite de l'appui sur `blur`, `visibilitychange`,
  `pointercancel` et à chaque changement d'écran.
- Retour visuel: anneau/barre qui se remplit, carte sélectionnée teintée
  progressivement, signal sonore au franchissement du seuil, message qui
  évolue « Appuie pour changer » → « Continue de maintenir… » → « Relâche
  pour valider » (FR/DE). Aide dédiée affichée une seule fois, à la toute
  première question du parcours.
- Nouvel écran Admin → Système → « Tester le buzzer »: touche, durée, type
  d'appui, doubles événements détectés — sans jamais créer de session.

### Texte légal et QR code
- Le texte réellement affiché sur l'écran de consentement (surtitre, titre,
  corps légal, deux choix) est désormais centralisé et versionné dans
  `config.py` (`CONSENT_TEXT_FR`/`CONSENT_TEXT_DE`,
  `PRIVACY_NOTICE_VERSION`), exposé par `/api/config` (`privacy.text_fr`/
  `text_de`). Les anciens champs `campagne.consent_fr`/`consent_de` sont
  conservés en base (jamais supprimés) mais ne sont plus lus par la Cabine.
- Séparation stricte entre le lien cliquable affiché (toujours relatif:
  `/protection-des-donnees` ou `/datenschutz`, ne pointe jamais vers
  localhost) et l'URL absolue encodée dans le QR code
  (`PUBLIC_PRIVACY_URL_FR/DE` > `PUBLIC_BASE_URL` + chemin > page officielle
  La Poste). Nouveau validateur qui rejette explicitement localhost,
  127.0.0.1, 0.0.0.0 et toute URL relative avant de les utiliser dans un QR —
  corrige un risque réel: en développement, le QR encodait auparavant l'hôte
  de la requête entrante (potentiellement localhost).
- QR généré localement (bibliothèque `qrcode`, aucun service externe), taille
  ~96-112 px, dans une carte « Protection des données / Datenschutz »
  entièrement cliquable.

### Graphisme du consentement
- Refonte en deux zones sur toute la largeur: à gauche surtitre/titre/texte,
  à droite les deux choix et la carte Datenschutz — fini le grand vide
  central, composition éditoriale proche d'une campagne Poste.
- Grille à deux colonnes pour 6 à 8 réponses; la dernière réponse isolée
  s'étire désormais sur toute la largeur au lieu de rester seule dans sa
  colonne (`nth-child(odd)` + `grid-column:1/-1`).

### Tests et vérification
- 46 tests pytest (7 nouveaux): exactement deux choix FR/DE, texte légal réel
  exposé par `/api/config`, QR/liens jamais localhost (unitaire + API +
  `PUBLIC_BASE_URL`), analyse statique de `refuse()` (aucun `fetch`, aucun
  `getUserMedia`), gestionnaire de pression corrigé (seuils, `event.repeat`,
  verrou de transition, resets), écran « Tester le buzzer » sans création de
  session.
- Vérification réelle en navigateur headless (Chromium, Playwright), en
  français et en allemand: appui court change la sélection, appui long
  affiche « Relâche pour valider » puis valide, `event.repeat` n'avance pas
  deux fois, `blur` en cours de maintien n'entraîne aucune validation
  fantôme au relâchement suivant, appui de 4 s ouvre bien la confirmation
  d'abandon et la confirmation supprime réellement la session, question à 7
  réponses sans réponse isolée, rapport final sans Acte/JSON/note, aucun
  débordement à 1366×768 sur les écrans clés. Captures d'écran conservées
  pour cette livraison.

### Reste à faire valider par Legal/Datenschutz
- Responsable précis de BUS XPERIENCE (`DATA_CONTROLLER_FR`/`DE`).
- `AUDIO_RETENTION_DAYS`/`DATA_RETENTION_DAYS` (aucune valeur par défaut).
- `PUBLIC_BASE_URL`/`PUBLIC_PRIVACY_URL_FR`/`DE` à renseigner avant impression
  physique d'un QR code sur la borne définitive.

## v4.0 — Micro obligatoire, consentement réellement explicite, protection des données (2026-07-29)

Implémentation technique renforcée selon les principes de transparence,
consentement explicite et minimisation des données. Validation juridique
interne (Legal / Datenschutz de la Poste) encore nécessaire — ceci n'est PAS
une certification juridique.

### Participation et consentement
- Suppression complète du parcours « sans microphone »: plus de choix
  intermédiaire, plus de questionnaire de repli, plus de tableau fallback,
  plus de branche `consent_micro=0`. Deux choix seulement, en FR comme en DE:
  « Oui, je participe » / « Non merci ».
- Nouveau texte de consentement exact (surtitre, titre, corps, mention de
  ne pas se nommer, rappel du caractère volontaire et du droit d'arrêter).
- Consentement réellement explicite: le microphone n'est JAMAIS ouvert avant
  la validation « Oui » par appui long; le navigateur demande alors
  l'autorisation, les pistes de test sont immédiatement arrêtées, la session
  n'est créée que si l'autorisation est accordée, l'enregistrement réel ne
  commence qu'à la question vocale.
- Refus: aucun appel réseau, aucune session, retour à l'accueil avec un
  message bref.
- Microphone refusé ou indisponible (au consentement ou pendant le parcours):
  message clair « aucune donnée n'a été enregistrée », jamais de repli vers
  un questionnaire structuré, retour à l'accueil (session supprimée si elle
  existait déjà).
- QR code de la page de protection des données, généré **localement**
  (bibliothèque `qrcode`, aucun service externe), à côté du lien discret
  « Protection des données / Datenschutz » sur l'écran de consentement.

### Arrêt pendant le parcours
- Le buzzer unique gère désormais trois durées: appui court (parcourir),
  appui long ≥ 0,7 s (valider), appui très long ≥ 4 s (ouvrir une
  confirmation d'arrêt). Confirmé, l'arrêt supprime immédiatement la session,
  ses réponses, audios, transcriptions et rapport éventuel, puis revient à
  l'accueil.

### Protection des données
- Nouveau module `config.py`: toutes les valeurs de protection des données
  (version de la notice, responsable, contact, durées de conservation, liens
  officiels, destination et pays de traitement de l'IA) centralisées, lues
  depuis des variables d'environnement, jamais codées en dur ailleurs.
  Aucune durée de conservation par défaut inventée: tant qu'elle n'est pas
  configurée, un avertissement explicite s'affiche au lieu d'un silence.
- Nouvelles pages bilingues `/protection-des-donnees` et `/datenschutz`,
  lisibles ordinateur/téléphone, avec lien vers la notice générale de La
  Poste et affichage dynamique du fournisseur IA actif.
- Nouveau code de participation aléatoire (`BX-XXXX-XXXX`) généré à la
  création de chaque session consentie, affiché discrètement en fin de
  parcours; recherche et suppression par ce code dans Admin -> Résultats.
- Schéma v5: `sessions` gagne `consent_audio`, `consent_le`,
  `consent_version`, `privacy_lang`, `participant_code`. `consent_micro` est
  conservé (jamais supprimé) mais n'est plus le mécanisme de décision.
  Migration idempotente, sauvegarde automatique préalable comme toujours.
- Nouveau script `cleanup.py` (`--dry-run` disponible): supprime les audios
  et les données personnelles au-delà des durées configurées, jamais les
  réglages/campagnes/questions/concepts, journal sans texte de réponse,
  idempotent.
- Audit de `ai.py`: seules des réponses textuelles (dont une transcription si
  nécessaire) sont envoyées à un fournisseur IA externe — jamais de fichier
  audio, contenu binaire, chemin local, adresse IP ou identifiant technique.
  Nouveau nettoyage best-effort (`masquer_donnees_personnelles`) avant tout
  envoi externe (e-mails, téléphones, suites de chiffres, URL, « je
  m'appelle X »); le prompt rappelle explicitement de ne pas reproduire ces
  informations. Transcription toujours locale (faster-whisper); plus de
  contenu de réponse dans les journaux techniques (`transcribe.py`).
- Sécurité: fichiers audio retirés du montage statique public `/audio`,
  servis uniquement par `/admin/audio/{nom}` derrière authentification, noms
  de fichiers aléatoires (au lieu de `{session}_{question}.webm`); cookie
  admin `httponly` + `samesite=lax` (+ `secure` en HTTPS); avertissement
  fort si `ADMIN_PASS` garde une valeur par défaut connue; aucune clé API
  jamais affichée; `.gitignore` ajouté (`data/`, secrets).
- Admin -> Système: nouveau bloc « Protection des données » (version,
  responsable, contact, durées de conservation, fournisseur IA et
  destination déclarée, liens FR/DE, nombre de consentements enregistrés,
  nombre de sessions sans information de consentement de l'ancienne version,
  paramètres manquants signalés).
- 40 tests (voir liste ci-dessous), tous passants.

### Testé réellement (pytest 40/40 + serveur lancé, `node --check` sur le JS)
- Santé, migration v1 et v5, cabine servie sans aucune mention « sans
  microphone » ni fallback, exactement deux choix de consentement par langue.
- Aucune session sans `mic_ok=1`; `consent_le`/`consent_version`/
  `privacy_lang`/`participant_code` enregistrés; code au format `BX-XXXX-XXXX`.
- Nom de fichier audio aléatoire; `/audio/...` renvoie 404 (retiré);
  `/admin/audio/...` bloqué sans connexion, servi à l'admin connecté.
- Abandon de session: suppression complète (session, réponses, audio sur
  disque), idempotent.
- Recherche et suppression par code de participation.
- Pages `/protection-des-donnees` et `/datenschutz` accessibles, dans leur
  langue respective; liens officiels de La Poste exacts.
- Masquage des données personnelles (e-mail, téléphone, URL, suites de
  chiffres, « je m'appelle »); aucun indice d'audio brut (`.webm`, chemin
  local) dans la charge utile envoyée au fournisseur IA simulé.
- `cleanup.py --dry-run` s'exécute sans modifier la base et sans écrire de
  texte de réponse dans son journal.
- Bloc « Protection des données » de Admin -> Système, sans fuite de clé API.
- Rapport participant, rapport admin, exports, CRUD questions, réglages TTS/
  buzzer/sons, suppression session/campagne/globale avec sauvegarde: inchangés
  et toujours verts.

### Non testé automatiquement (à vérifier sur la borne, vrai navigateur)
- Rendu visuel de l'écran de consentement à 1366×768 (repose sur les mêmes
  `clamp()`/`overflow:hidden` déjà en place, non vérifiés par capture d'écran
  automatisée dans cette itération).
- Comportement réel de `getUserMedia` (autorisation, refus, révocation en
  cours de parcours) et de l'appui buzzer à exactement 4 secondes sur le
  matériel physique.
- QR code scanné par un téléphone réel.

### Limites restantes
- Le responsable précis du projet BUS XPERIENCE (`DATA_CONTROLLER_FR/DE`)
  n'est pas confirmé: l'admin l'affiche comme « à confirmer » tant que les
  variables d'environnement ne sont pas renseignées.
- `AUDIO_RETENTION_DAYS`/`DATA_RETENTION_DAYS` ne sont pas définis par
  défaut: aucune suppression automatique n'a lieu tant qu'ils ne le sont pas,
  et un avertissement reste visible dans Admin -> Système.
- Cette implémentation ne constitue pas une certification juridique.

## v3.2 — Cabine individuelle et interaction réellement au buzzer (2026-07-29)

- Suppression complète du mode à deux: une session correspond toujours à une
  seule personne; l'API refuse désormais `participants=2`.
- Nouvelle logique uniforme: appui court pour parcourir, appui long pour
  valider. Plus aucune flèche gauche/droite, aucun curseur, aucun bouton de
  retour flottant et aucune navigation de formulaire classique.
- La synthèse vocale lit uniquement la question. Les réponses ne sont plus
  annoncées une à une.
- L'échelle 0-10 devient une rangée de onze cases. Les listes de six réponses
  ou plus passent en grille de deux colonnes, sans défilement vertical.
- Parcours sans micro entièrement fonctionnel: la question ouverte est
  remplacée immédiatement par une question structurée équivalente; aucun faux
  chronomètre ni écran d'enregistrement n'apparaît.
- Refonte graphique complète de la cabine: noir, jaune postal, blanc crème,
  une seule sélection jaune, compositions éditoriales et pied de page unique.
- Nouvelle entrée en matière FR/DE: «Tu montes à bord…» / «Du steigst ein…».
- Traductions centralisées; vérification visuelle du parcours allemand sans
  mélange de boutons français.
- Progression exacte (`3 / 13`), plus de valeurs approximatives «encore ~».
- Mise à jour douce du contenu par défaut: consentement, question de fréquence
  et concept «Une Haltestelle zum Wohlfühlen».
- Rapport final v3.1 conservé: JSON strict pour Gemini, moteur automatique
  FR/DE, ancien rapport cassé régénéré.
- 29 tests réussis. Syntaxe JavaScript vérifiée avec Node. Rendus contrôlés en
  1366×768 pour l'accueil, l'introduction, le consentement, une liste de sept
  réponses, l'échelle 0-10 et le parcours allemand sans micro.

## v3.1 — Profil de voyage final entièrement refait (2026-07-29)

- Suppression totale des « Acte 1 / 2 / 3 », notes de concept et valeurs brutes.
- Nouveau contrat commun Gemini/Anthropic/Ollama: titre, deux paragraphes et
  conclusion, en JSON strict, 60 à 90 mots, sans genre supposé.
- Validation forte de la réponse IA: tout résultat incomplet, trop long,
  mal ponctué ou hors format est rejeté et remplacé par le moteur automatique.
- Nouveau moteur automatique FR/DE avec plus de 50 titres par langue, des
  formulations liées aux irritants réels et des verbatims utilisés seulement
  lorsqu'une idée claire peut être reformulée proprement.
- Les anciens rapports mis en cache sont détectés et régénérés automatiquement.
- Nouvel écran « TON PROFIL DE VOYAGE »: titre très visible, deux paragraphes,
  conclusion mise en valeur et label IA discret.
- 28 tests, dont dix combinaisons FR/DE et un test de réponse IA cassée.

## v3.0 — Buzzer unique, Swiss Post Sans, storytelling (2026-07-29)

- Typographie Swiss Post Sans partout via la feuille officielle fonts.post.ch
  (900/700/400), repli Arial, aucun fichier de police dans le ZIP.
- Buzzer rouge massif et brillant avec enfoncement et halo; clic, Espace et
  buzzer physique identiques. Mode « Buzzer unique + voix »: lecture
  successive des choix avec mise en evidence forte, selection au buzz;
  echelle 0-10 par defilement vocal et visuel; etoiles avec delai reglable et
  appui long pour annuler; jamais de saut sans reponse; tactile en secours.
  Reglages et tests (appui court/long) dans Admin -> Medias.
- Nouvelle introduction: « ET SI LE BUS T'ECOUTAIT VRAIMENT ? », apparition
  progressive de BUS XPERIENCE, pulsation du buzzer, FR/DE en alternance.
- Question vocale repensee en phrase projective: « Termine cette phrase : je
  prendrais le bus plus souvent si… » (migration douce des installations
  existantes non modifiees).
- Rapport final en mini-histoire a trois actes (relation au bus, petit
  mechant, rebondissement), utilisant reellement frequence, etoiles, moment
  de friction, irritant, confiance, concept prefere et verbatim; beaucoup
  plus de titres; messages d'attente amusants; toujours honnete sur IA/auto.
- Rapport admin: recommandations chacune reliee a un chiffre reel (irritant
  dominant avec n et %, concepts avec adoption moyenne et n, confiance).
- Suppression securisee des donnees (session, campagne, tout) avec mot
  SUPPRIMER, sauvegarde datee prealable, decompte affiche, questions/
  reglages/medias toujours conserves, rien de recree au redemarrage.
- TTS: reglage de tonalite en plus de la vitesse, filet anti-onend manquant,
  fr-CH/de-CH pris via u.lang. start.sh corrige (python3 -m uvicorn) et
  copie reellement les medias par defaut avant le demarrage.
- Migration v4 automatique avec sauvegarde. 25 tests.

### Teste reellement (pytest 25/25 + serveur lance via start.sh)
- start.sh (python3 -m uvicorn), /health, /cabine/, /admin, config buzzer/
  tonalite/sons exposee, mp3 servis, migrations v4, seed unique, parcours
  complet par API, rapport storytelling (3 actes, frequence et moment
  utilises), rapport IA simule (mocks Anthropic/Gemini + echec reseau),
  suppressions (session precise avec decompte, refus sans mot exact,
  globale avec sauvegarde creee et conservation questions/concepts/
  campagnes/reglages, rien de recree apres re-migration), reglages admin
  buzzer/TTS/sons, exports CSV/JSON, rapport admin avec recommandations et
  limites.

### Simule
- Fournisseurs IA (mocks), parcours via API.

### Non teste automatiquement (a verifier sur la borne, vrai navigateur)
- Rendu Swiss Post Sans (depend du chargement de fonts.post.ch), animations,
  enfoncement du buzzer, lecture successive audible des choix et son timing,
  appui long au vrai buzzer physique, enregistrement micro reel, coupure/
  reprise de la musique a l'oreille, voix naturelles FR/DE d'Edge, klaxon.
  La logique correspondante est couverte par la validation de syntaxe JS et
  les reglages testes cote serveur.

### Limites restantes
- Hors ligne, la police retombe sur Arial (la feuille fonts.post.ch est un
  chargement reseau, par choix de ne pas embarquer les fichiers de police).
- Le defilement vocal de l'echelle 0-10 depend du rythme du TTS du
  navigateur; ajuster la vitesse de lecture dans l'admin selon la voix.
- Les textes des questions restent au tutoiement en mode duo (interface en
  vous); rediger des variantes si necessaire.
- L'ecran de consentement reste a valider juridiquement (LPD).

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
