# BUS XPERIENCE

Une installation publique et un outil de recherche utilisateur pour comprendre
et ameliorer l'experience client du bus. Parcours individuel FR/DE de 4 a 5
minutes, un seul buzzer, voix facultative, concepts a tester, profil de voyage
final personnalise et rapport d'analyse administrateur. Powered by MobilityLab Sion.

## Typographie

Toute l'application (cabine, admin, rapports, impressions) utilise Swiss Post
Sans via la feuille officielle fonts.post.ch (Black 900 pour les grands
titres, Bold 700 pour boutons et intertitres, Regular 400 pour les textes),
avec repli Arial/sans-serif si la police ne charge pas ou hors ligne. Aucun
fichier de police n'est inclus dans le projet.

## Un seul buzzer rouge

Le parcours participant est strictement individuel et se pilote avec un seul
buzzer physique. Un appui court parcourt les choix; un appui long (>= 0,7 s)
valide; un appui tres long (4 s) pendant le parcours ouvre une confirmation
d'arret et de suppression immediate de la session (« Tu peux arreter a tout
moment » est une vraie fonction, pas une formule). La meme logique s'applique
aux langues, au consentement, aux questions a choix, aux etoiles, aux
comparaisons et a l'echelle 0-10. Il n'y a plus de fleches gauche/droite, de
curseur, de bouton « corriger » ni de navigation de site web. Espace/Entree
simulent le buzzer pendant les tests; le tactile reste un secours discret.

La synthese vocale lit uniquement la question, jamais les reponses.
BUS XPERIENCE fonctionne desormais uniquement avec le microphone: il n'y a
plus de parcours de repli sans micro. Si l'autorisation est refusee ou le
microphone indisponible, aucune session n'est creee et l'ecran l'indique
clairement avant de revenir a l'accueil.

## Lancement (Codespaces ou local)

1. Pousser ces fichiers dans le depot GitHub (y compris `.devcontainer/`).
2. Code -> Codespaces -> Create codespace on main (les dependances s'installent seules).
3. Dans le terminal:

       ADMIN_PASS="admin" SECRET_KEY="secret-local" AI_PROVIDER="none" TTS_PROVIDER="browser" ./start.sh

4. Ouvrir le port 8000 propose par Codespaces:
   - `/cabine/`  le parcours participant (F11 pour le plein ecran)
   - `/admin`    l'administration
   - `/health`   la sonde d'etat

En local c'est identique: `pip install -r requirements.txt` puis la meme commande.
`ADMIN_PASS="admin"` ci-dessus n'est qu'un exemple de developpement: le
serveur affiche un avertissement fort (console + Admin -> Systeme) tant que
`ADMIN_PASS` garde une valeur par defaut connue. Avant tout usage public,
definir aussi `AUDIO_RETENTION_DAYS`, `DATA_RETENTION_DAYS`,
`DATA_CONTROLLER_FR`/`DATA_CONTROLLER_DE` (voir « Protection des donnees »
plus bas) — sans quoi l'admin affiche des avertissements explicites plutot
que de choisir des valeurs par defaut silencieuses.

Le script verifie la configuration, cree les dossiers, applique les migrations,
affiche le fournisseur IA, signale les medias manquants et lance le port 8000.
Aucune URL n'est codee en dur, tout est relatif.

## Le parcours

Apres le choix de la langue, une introduction forte place immediatement la
personne au centre de l'experience. L'ecran de consentement (« A toi de
decider / Du entscheidest ») ne propose plus que deux choix: « Oui, je
participe » ou « Non merci ». Un refus ne demande jamais le microphone et ne
cree jamais de session. En cas d'accord valide par appui long, le navigateur
demande l'autorisation du microphone; les pistes ouvertes pour ce test sont
immediatement arretees; la session n'est creee (`POST /api/sessions`) que si
l'autorisation est accordee; l'enregistrement reel ne commence qu'a la
question vocale. Un QR code discret, genere localement (bibliotheque
`qrcode`, aucun service externe), et un lien « Protection des donnees /
Datenschutz » accompagnent les deux choix. Une session correspond toujours a
une seule personne.

Chaque ecran tient dans une borne 1366x768 ou 1920x1080, sans defilement. La
progression est exacte. Les listes longues passent automatiquement en grille.
L'echelle 0-10 utilise onze cases lisibles plutot qu'un curseur. Les ecrans FR
et DE sont entierement traduits et ne melangent jamais les langues.

## Concepts

Bibliotheque administrable (FR/DE, image optionnelle, campagne), tires au sort
a chaque session (nombre reglable). Chaque concept mesure l'impact sur
l'experience (1-5 etoiles) et la probabilite de prendre le bus plus souvent
(0-10). Jamais « est-ce une bonne idee ? ».

## IA facultative

`AI_PROVIDER` = `none` (defaut) | `ollama` | `gemini` | `anthropic`.
Le mode none produit deja le rapport participant personnalise et drole, le
rapport administrateur quantitatif, les graphiques et les exports. Aucune
bascule silencieuse: en cas d'echec du fournisseur, l'erreur est journalisee
(admin -> Systeme) et le rapport est etiquete « personnalise automatiquement ».
Cles par variables d'environnement uniquement (`.env.example`), jamais dans le
code ni affichees. Les fichiers audio bruts, chemins locaux, adresses IP et
identifiants techniques ne sont JAMAIS envoyes a un fournisseur externe: seules
les reponses textuelles necessaires au rapport (dont la transcription, si
besoin) le sont. Un nettoyage best-effort (`ai.masquer_donnees_personnelles`)
masque avant envoi les adresses e-mail, numeros de telephone, suites de
chiffres ressemblant a des identifiants, URL et formulations du type « je
m'appelle X »; cette detection n'est pas garantie exhaustive, d'ou la consigne
donnee au participant de ne pas se nommer. La transcription reste locale
(faster-whisper, `python transcribe.py`); l'audio ne quitte jamais la machine.
La page /protection-des-donnees (ou /datenschutz) affiche dynamiquement le
fournisseur IA actif et sa destination declaree.

## Administration

Huit sections: Tableau de bord, Campagnes, Questionnaires (liste compacte avec
recherche, tri par ordre, duplication, edition en page dediee, versionnement),
Concepts, Resultats (par question, par session ou par code de participation,
audio ecoutable par un admin connecte uniquement + correction manuelle des
transcriptions), Rapports (filtres campagne/lieu/periode/langue/parcours/frequence,
frictions, classement des concepts, verbatims, limites
methodologiques, impression/PDF navigateur, exports CSV et JSON), Medias
(musique, klaxon, voix des questions), Systeme (fournisseur IA, test de
connexion, sauvegardes, journal, bloc « Protection des donnees »).

## Voix (TTS_PROVIDER=browser, gratuit, sans cle API)

Aucune voix a enregistrer: la Cabine choisit automatiquement la meilleure voix
naturelle du navigateur pour le francais et l'allemand (les voix
« Natural / Online » d'Edge sont privilegiees, puis Neural/Google/Premium).
Chaque question possede un texte parle plus court et plus naturel que le texte
affiche (editable dans Questionnaires -> Editer). Admin -> Medias permet de
choisir et tester les voix FR/DE, de regler la vitesse, de laisser la
selection automatique, et affiche une alerte si seule une voix basique est
disponible dans le navigateur. Important: les voix appartiennent au navigateur
de la borne, regler et tester depuis celui-ci (Edge ou Chrome recommandes).
Un mp3 charge sur une question garde la priorite sur la synthese.

## Sons fournis dans ce ZIP

`medias-defaut/` contient les deux fichiers fournis par MobilityLab, installes
automatiquement au premier demarrage dans `data/medias/` (jamais ecrases):
- `klaxon.mp3` (Dreiklanghorn): joue a la revelation du rapport final,
  activable et reglable en volume dans Admin -> Medias, testable en un clic;
  s'il est supprime, un son neutre de secours prend le relais.
- `musique-voyage.mp3` : musique de fond de la campagne par defaut. Demarre
  apres la premiere interaction, boucle pendant tout le parcours, baisse
  pendant les voix, coupee totalement avant et pendant le micro, reprend en
  fondu, s'arrete en fondu a la fin. Volume, activation, test et remplacement
  dans Admin -> Campagnes et Medias.

## Donnees et migration

Migrations versionnees et automatiques au demarrage, sauvegarde de la base
dans `data/backups/` avant chaque migration, journal dans Admin -> Systeme.
Une ancienne base `data/boite.db` (version « La Boite ») est reprise
automatiquement (lieux, sessions, reponses). Le contenu par defaut n'est seme
qu'une seule fois (`seed_version`), jamais recree au demarrage. `.gitignore`
exclut `data/` (reponses, audios, transcriptions, sauvegardes, base SQLite)
et les fichiers de secrets locaux.

Schema v5: ajoute aux sessions `consent_audio`, `consent_le`,
`consent_version`, `privacy_lang` et `participant_code`. L'ancienne colonne
`consent_micro` est conservee (jamais supprimee, pour ne pas casser des
donnees existantes) mais n'est plus utilisee comme mecanisme de decision.

## Tests

    python -m pytest tests/ -q        # 40 tests

Voir CHANGELOG.md pour le detail de ce qui est teste, simule et non teste.

## Protection des donnees

Implementation technique renforcee selon les principes de transparence,
consentement explicite et minimisation des donnees. **Ceci n'est pas une
certification juridique**: la validation interne par le service Legal /
Datenschutz de la Poste reste necessaire avant tout usage public.

Configuration centralisee dans `config.py` (toutes les valeurs viennent de
variables d'environnement, jamais codees en dur ailleurs):

| Variable | Role |
|---|---|
| `PRIVACY_NOTICE_VERSION` | Version affichee de la notice |
| `DATA_CONTROLLER_FR` / `DATA_CONTROLLER_DE` | Responsable precis de BUS XPERIENCE (**a confirmer par Legal**, sinon marque « a confirmer » partout) |
| `DATA_CONTROLLER_ADDRESS` | Adresse postale du responsable (defaut: adresse generale La Poste) |
| `PRIVACY_CONTACT_EMAIL` | Contact pour les droits des personnes (defaut: `betroffenenrechte@post.ch`) |
| `AUDIO_RETENTION_DAYS` | Duree de conservation des audios; **non definie par defaut**, avertissement tant qu'elle ne l'est pas |
| `DATA_RETENTION_DAYS` | Duree de conservation des autres donnees personnelles; idem |
| `PRIVACY_URL_FR` / `PRIVACY_URL_DE` | Notice generale de La Poste (valeurs officielles par defaut) |
| `PUBLIC_PRIVACY_URL_FR` / `PUBLIC_PRIVACY_URL_DE` | URL publique propre a BUS XPERIENCE, si elle existe; sinon la page `/protection-des-donnees` ou `/datenschutz` de cette application est utilisee, sinon le lien general La Poste |

Pages bilingues completes: `/protection-des-donnees` et `/datenschutz`
(responsable, donnees collectees, finalites, destinataires/sous-traitants,
fournisseur IA affiche dynamiquement, pays de traitement, duree de
conservation, droits, lien vers la notice generale de La Poste). QR code vers
cette page **genere localement** (bibliotheque `qrcode`, aucun service
externe) sur l'ecran de consentement.

Code de participation: a la creation d'une session consentie, un code court
et aleatoire (`BX-XXXX-XXXX`) est genere et affiche discretement en fin de
parcours. Il permet de demander la suppression de ses reponses: Admin ->
Resultats -> recherche/suppression par code.

`python3 cleanup.py [--dry-run]`: supprime les audios plus vieux que
`AUDIO_RETENTION_DAYS` et les sessions/donnees personnelles plus vieilles que
`DATA_RETENTION_DAYS`; ne touche jamais reglages, campagnes, questions ni
concepts; journal sans aucun texte de reponse; idempotent; n'invente jamais
une duree si elle n'est pas configuree.

Securite minimale verifiee: fichiers audio jamais accessibles par une URL
publique (noms aleatoires, servis uniquement via `/admin/audio/{nom}`
derriere authentification), reponses/transcriptions absentes des journaux
techniques, cookie admin `httponly` + `samesite=lax` (+ `secure` en HTTPS),
avertissement fort si `ADMIN_PASS` vaut encore une valeur par defaut, aucune
cle API jamais affichee.

## Suppression des anciennes reponses

Admin -> Resultats, zone dangereuse clairement separee: suppression d'une
session precise, par code de participation, des donnees d'une campagne, ou de
tout (premier clic, saisie exacte du mot SUPPRIMER, confirmation finale; une
sauvegarde datee de la base est creee automatiquement avant). Sont effaces:
sessions, reponses, audios, transcriptions, rapports participants. Ne sont
jamais touches: questions, concepts, campagnes, reglages, musique, klaxon,
voix. Le nombre d'elements supprimes est affiche, et rien n'est recree au
redemarrage. Le meme mecanisme est utilise par l'abandon volontaire pendant
le parcours (appui de 4 s + confirmation) et par `cleanup.py`.

## Procedure de migration

Remplacer les fichiers du depot par ceux du ZIP et relancer ./start.sh. Le
schema passe automatiquement en v5 (sauvegarde prealable dans
`data/backups/`). Le seed v4 met a jour uniquement les anciens textes par
defaut encore inchanges: consentement (nouveau texte micro-obligatoire),
premiere question de frequence et concept de l'arret confortable. Les textes
personnalises dans l'admin, les donnees, les reglages et les medias sont
conserves.
