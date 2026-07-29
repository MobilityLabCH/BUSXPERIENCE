# BUS XPERIENCE

Une installation publique et un outil de recherche utilisateur pour comprendre
et ameliorer l'experience client du bus. Parcours FR/DE de 4 a 5 minutes,
buzzer, ecran tactile, concepts a tester, rapport final personnalise, rapport
d'analyse pour l'administrateur. Powered by MobilityLab Sion.

## Typographie

Toute l'application (cabine, admin, rapports, impressions) utilise Swiss Post
Sans via la feuille officielle fonts.post.ch (Black 900 pour les grands
titres, Bold 700 pour boutons et intertitres, Regular 400 pour les textes),
avec repli Arial/sans-serif si la police ne charge pas ou hors ligne. Aucun
fichier de police n'est inclus dans le projet.

## Un seul buzzer rouge

Le parcours est entierement utilisable avec un seul gros buzzer rouge (le
clic sur le bouton visuel, la touche Espace et le futur buzzer physique
declenchent exactement la meme action). Pour les choix, la voix annonce les
reponses une a une, la reponse lue est fortement mise en evidence, on buzze
quand la bonne est annoncee. Etoiles: un buzz = une etoile, anneau de
validation reglable, appui long (>= 0,7 s) pour annuler et recommencer.
Echelle 0-10: les valeurs defilent vocalement et visuellement, on buzze sur
la bonne. Voix: un appui demarre, un appui arrete, le silence arrete aussi.
Un appui ne saute jamais une question sans reponse. Le tactile reste une
solution de secours. Admin -> Medias: mode « Buzzer unique + voix », vitesse
de lecture lente/normale/rapide, duree de validation des etoiles, test du
buzzer et de l'appui long.

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
Le script verifie la configuration, cree les dossiers, applique les migrations,
affiche le fournisseur IA, signale les medias manquants et lance le port 8000.
Aucune URL n'est codee en dur, tout est relatif.

## Le parcours

Consentement configurable (LPD: information, volontariat, finalite) avec
« Oui, je participe », « Participer sans micro », « Non merci », puis
participation seul·e ou a deux (double accord requis a deux). Etapes visibles
avec progression: Ton experience -> Ce qui coince -> Les idees a tester ->
Ta priorite -> Ton rapport. Interactions selon la question: choix tactile ou
fleches + buzzer, etoiles au buzzer (un buzz = une etoile, anneau de
validation, correction par la fleche gauche), curseur 0-10, duel gauche/droite,
voix 45 s avec compte a rebours, detection de silence, reecoute et reprise.
Bouton « corriger » pour revenir en arriere (la reponse est remplacee, jamais
dupliquee). Un appui buzzer ne saute jamais une question sans reponse.

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
code ni affichees. Les fichiers audio bruts ne sont JAMAIS envoyes a un
fournisseur externe: la transcription est locale (faster-whisper,
`python transcribe.py`).

## Administration

Huit sections: Tableau de bord, Campagnes, Questionnaires (liste compacte avec
recherche, tri par ordre, duplication, edition en page dediee, versionnement),
Concepts, Resultats (par question, par session, audio + correction manuelle des
transcriptions), Rapports (filtres campagne/lieu/periode/langue/participation/
termine/frequence, frictions, classement des concepts, verbatims, limites
methodologiques, impression/PDF navigateur, exports CSV et JSON), Medias
(musique, klaxon, voix des questions), Systeme (fournisseur IA, test de
connexion, sauvegardes, journal).

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
exclut reponses, audios, transcriptions, sauvegardes et cles.

## Tests

    python -m pytest tests/ -q        # 16 tests

Voir CHANGELOG.md pour le detail de ce qui est teste, simule et non teste.

## Protection des donnees: a verifier par les responsables competents

L'ecran de consentement applique les principes LPD (information, volontariat,
finalite, mention de l'enregistrement et de l'analyse automatique) mais ne
constitue pas a lui seul une validation juridique. A faire valider: duree de
conservation, procedure d'effacement sur demande, registre des traitements,
information sur le fournisseur IA actif lorsqu'un service externe est utilise,
affichage sur site.

## Suppression des anciennes reponses

Admin -> Resultats, zone dangereuse clairement separee: suppression d'une
session precise, des donnees d'une campagne, ou de tout (premier clic, saisie
exacte du mot SUPPRIMER, confirmation finale; une sauvegarde datee de la base
est creee automatiquement avant). Sont effaces: sessions, reponses, audios,
transcriptions, rapports participants. Ne sont jamais touches: questions,
concepts, campagnes, reglages, musique, klaxon, voix. Le nombre d'elements
supprimes est affiche, et rien n'est recree au redemarrage.

## Procedure de migration

Remplacer les fichiers du depot par ceux du ZIP et relancer ./start.sh. La
migration v4 s'applique automatiquement avec sauvegarde prealable dans
data/backups/ (reglages buzzer et tonalite; la question vocale par defaut
devient « Termine cette phrase : je prendrais le bus plus souvent si… » si
elle n'avait pas ete modifiee a la main). Les donnees, reglages et medias
existants sont conserves entre les redemarrages.
