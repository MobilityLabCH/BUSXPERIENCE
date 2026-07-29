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
valide. La meme logique s'applique aux langues, au consentement, aux questions
a choix, aux etoiles, aux comparaisons et a l'echelle 0-10. Il n'y a plus de
fleches gauche/droite, de curseur, de bouton « corriger » ni de navigation de
site web. Espace/Entree simulent le buzzer pendant les tests; le tactile reste
un secours discret.

La synthese vocale lit uniquement la question, jamais les reponses. Avec le
micro, une question ouverte peut etre enregistree. Sans micro ou si le micro
est indisponible, une question structuree equivalente apparait directement,
sans chronometre ni faux ecran d'enregistrement.

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

Apres le choix de la langue, une introduction forte place immediatement la
personne au centre de l'experience. Le consentement propose trois voies:
participer avec le micro, participer sans micro ou refuser. Une session
correspond toujours a une seule personne.

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
code ni affichees. Les fichiers audio bruts ne sont JAMAIS envoyes a un
fournisseur externe: la transcription est locale (faster-whisper,
`python transcribe.py`).

## Administration

Huit sections: Tableau de bord, Campagnes, Questionnaires (liste compacte avec
recherche, tri par ordre, duplication, edition en page dediee, versionnement),
Concepts, Resultats (par question, par session, audio + correction manuelle des
transcriptions), Rapports (filtres campagne/lieu/periode/langue/parcours/frequence,
frictions, classement des concepts, verbatims, limites
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

    python -m pytest tests/ -q        # 29 tests

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

Remplacer les fichiers du depot par ceux du ZIP et relancer ./start.sh. Le
schema reste en v4. Le seed v3 met a jour uniquement les anciens textes par
defaut encore inchanges: consentement, premiere question de frequence et
concept de l'arret confortable. Les textes personnalises dans l'admin, les
donnees, les reglages et les medias sont conserves.
