# urscript-debugger

Extension VS Code apportant un vrai débogueur (points d'arrêt, exécution pas-à-pas, inspection de variables) pour le **URScript brut** (Universal Robots) — ce qui manque aujourd'hui à tous les utilisateurs qui écrivent/envoient du script en dehors de PolyScope (intégrateurs, utilisateurs ROS/External Control, développeurs d'URCaps).

## Contexte

Voir `docs/market-research.md` et `docs/feasibility.md`. Résumé :
- PolyScope a des breakpoints natifs depuis la v5.6, mais **aucun outil ne couvre le URScript brut** (fichiers `.script`, code envoyé par socket).
- Un utilisateur du forum officiel UR a déjà validé manuellement le mécanisme de base (fonction `breakPoint()` avec rendez-vous socket) — on package et on fiabilise cette idée plutôt que d'inventer quelque chose de non prouvé.
- URSim (simulateur officiel) tourne en Docker et expose les mêmes interfaces réseau qu'un vrai robot : développement et tests entièrement possibles sans matériel.

## Architecture

1. **Instrumentation de code** : on parse le `.script` de l'utilisateur (parsing syntaxique suffisant, pas un moteur sémantique complet) et on insère un appel `checkpoint()` après CHAQUE ligne exécutable du bloc `def program():` (pas seulement les lignes marquées comme breakpoint). Chaque checkpoint demande d'abord au serveur "dois-je m'arrêter ?" (réponse en un octet). Si oui : le robot exécute lui-même `stopj()` (arrêt décéléré contrôlé), confirme au serveur qu'il est physiquement arrêté, et *seulement à ce moment* le serveur informe VS Code — jamais d'annonce "stopped" avant confirmation réelle. Si non : passage instantané, aucun impact sur un mouvement en cours (important pour ne pas casser des mouvements enchaînés avec rayon de raccordement `r=...`).
2. **Serveur de rendez-vous** : intégré directement dans l'adaptateur DAP (`dap_server.py`), reçoit les connexions socket des `checkpoint()`, décide de suspendre ou laisser passer, tient l'exécution en pause le temps nécessaire, puis envoie le signal de reprise.
3. **Adaptateur DAP (Debug Adapter Protocol)** : traduit les requêtes standard de VS Code (setBreakpoints, continue, next/stepIn/stepOut, threads, stackTrace, scopes, variables, **setVariable, evaluate**) vers le serveur de rendez-vous. C'est ce qui donne gratuitement toute l'UI de débogage de VS Code (marge de breakpoints, pile d'appels, panneau de variables éditable, boutons pas-à-pas) — aucune interface graphique à construire nous-mêmes.
4. **Extension VS Code** : déclare le langage URScript (association `.script` minimale pour l'instant — il existe une extension tierce pour la coloration syntaxique complète, `ahern.urscript`, à étudier/potentiellement contribuer plutôt que dupliquer) + enregistre l'adaptateur DAP. Empaquetée en `.vsix` (voir "Packaging").

## Fondations réutilisables (ne pas repartir de zéro)

- `universalrobots/ursim_e-series` (Docker officiel) — environnement de test.
- `Hirebotics/urscript-tools` — orchestration Docker/URSim pour exécution headless, base possible pour l'infra de test.
- `ahern.urscript` (extension VS Code existante) — coloration syntaxique, à vérifier si réutilisable/contributable avant de dupliquer.

## Fonctionnalités validées

1. ✅ Poser un breakpoint sur une ligne d'un `.script`.
2. ✅ Lancer le script contre URSim (Docker).
3. ✅ L'exécution s'arrête proprement à la ligne marquée.
4. ✅ Voir la valeur des variables locales dans le panneau VS Code (détection automatique par scan des `local X =` précédant la ligne).
5. ✅ Reprendre l'exécution (continue).
6. ✅ **Pas-à-pas (step over/into/out)** : avance ligne par ligne même sur des lignes qui ne sont pas des breakpoints explicites, en s'appuyant sur le même mécanisme de checkpoint.
7. ✅ **Packaging** : l'extension s'empaquette en `.vsix` installable (voir "Packaging").
8. ✅ **Arrêt sécurisé du mouvement** : `stopj()` déclenché par le robot lui-même uniquement quand une vraie pause est décidée, jamais sur un simple passage — validé avec un script à mouvement réel (deux `movej` enchaînés avec rayon de raccordement).
9. ✅ **Watch expressions / évaluation** (`evaluate`) : évalue les variables locales connues à l'endroit courant (affichable dans le panneau Watch ou la console de debug). Limite honnête : pas d'expressions arbitraires (URScript n'a pas d'`eval` dynamique) — seules les variables déjà détectées sont évaluables.
10. ✅ **Édition de variables en direct** (`setVariable`) : modifier une variable numérique dans le panneau Variables affecte réellement l'exécution en cours (testé : changer un compteur en plein milieu d'une boucle court-circuite immédiatement la condition de sortie). Limite honnête : uniquement les valeurs numériques (int/float) pour l'instant — pas de chaînes, listes ou poses.
11. ✅ **Support multi-fichiers** : plusieurs fichiers `.script` dans un même projet, chacun avec ses propres breakpoints correctement isolés ; un seul fichier est "lancé" à la fois (URScript n'a pas de mécanisme d'inclusion entre fichiers comme un `import`, donc il n'y a pas de notion de "programme qui s'étend sur plusieurs fichiers" à proprement parler — mais un breakpoint posé dans un fichier non lancé n'interfère jamais avec la session active).

**Validé de quatre façons, du plus bas niveau au plus réaliste :**
- `tests/test_dap_flow.py` simule un client DAP simplifié contre un vrai URSim — validation rapide de la logique serveur (script sans mouvement).
- `tests/test_motion_safety.py` — même principe mais avec un script qui bouge réellement le robot (`test-scripts/motion_test.script`) : vérifie que le statut de sécurité reste `NORMAL` pendant toute la durée de la pause (3s, deux fois), preuve qu'aucun fault/arrêt protecteur n'est déclenché par notre `stopj()`, même en interrompant un mouvement en cours de raccordement.
- `extension/src/test/suite/debug.test.ts` pilote une **vraie fenêtre VS Code** (via `@vscode/test-electron`) : breakpoints posés par l'API réelle, clics "Continue"/"Step Over" via les vraies commandes, capture de tout le trafic DAP échangé. **5 scénarios** couverts : breakpoints consécutifs, échec propre si le port est occupé, pas-à-pas ligne par ligne, édition de variable en direct, isolation multi-fichiers.
- Validation manuelle dans l'éditeur VS Code par l'utilisateur, en complément si souhaité — voir "Comment tester" ci-dessous.

**Bugs trouvés et corrigés grâce aux tests E2E réels (2026-09-13) :**
- Un port de rendez-vous déjà occupé par une session précédente mal arrêtée faisait échouer `_start_program` silencieusement — aucune erreur ne remontait à VS Code. Corrigé : l'erreur remonte maintenant via un événement `output` explicite + `terminated`, avec test de non-régression.
- La détection de fin de programme par **sondage périodique du dashboard** ratait les scripts rapides (tout le programme peut s'exécuter en moins de 50ms, avant même le premier sondage) — remplacé par un **signal explicite envoyé par le script lui-même juste avant sa fin**, déterministe et instantané, plus de dépendance au timing.
- Une connexion de checkpoint malformée (résidu d'une session précédente pas complètement arrêtée) faisait planter **toute** la boucle de rendez-vous au lieu d'être simplement ignorée — isolé dans un traitement par connexion avec sa propre gestion d'erreur.
- À la déconnexion d'une session, le programme robot n'était pas explicitement arrêté côté contrôleur, pouvant laisser un script tourner et perturber la session suivante — corrigé (`dashboard stop` explicite au nettoyage).

**Détail technique de l'arrêt sécurisé et de l'édition de variables (2026-09-13)** : deux fonctions URScript que j'avais initialement supposées (`socket_read_byte`) n'existaient pas — trouvé via le vrai log d'erreur du contrôleur (`/ursim/URControl.log` dans le conteneur, bien plus fiable que `docker logs` pour ce genre d'erreur), puis confirmé les bonnes fonctions (`socket_read_byte_list`, `socket_read_ascii_float`) dans le manuel officiel Universal Robots avant d'intégrer.

Reste hors scope (voir "Prochaines étapes") : édition de variables non-numériques, publication Marketplace.

## Environnement de test (URSim)

Tout est contenu dans ce dossier — rien n'est installé ailleurs sur la machine.

```bash
cd docker
docker compose up -d      # démarre URSim (dashboard 29999, primary/secondary/realtime/RTDE 30001-30004, PolyScope web sur http://localhost:6080/vnc.html)
docker compose down       # arrête et nettoie le conteneur
```

Les programmes/URCaps persistés vivent dans `ursim-data/` (ignoré par git). Validé le 2026-09-13 : tous les ports de contrôle répondent correctement une fois le conteneur démarré (~1-2 min de démarrage interne).

## Structure du projet

```
urscript-debugger/
├── docs/               # étude de marché + faisabilité technique
├── docker/             # docker-compose.yml pour URSim (environnement de test)
├── server/             # logique Python : instrumentation + serveur DAP
│   ├── instrument.py   # insère checkpoint() dans un .script
│   ├── dap_server.py   # adaptateur DAP, spawné par l'extension VS Code
│   └── .venv/          # environnement Python local au projet
├── extension/          # extension VS Code (TypeScript)
│   ├── src/extension.ts
│   ├── src/test/       # suite de tests E2E (@vscode/test-electron)
│   ├── .vscodeignore   # exclut sources/tests du .vsix packagé
│   └── package.json
├── test-scripts/       # fichiers .script d'exemple (dont motion_test.script à mouvement réel, second_test.script pour le multi-fichiers)
└── tests/              # validation automatisée bas niveau (test_dap_flow.py, test_motion_safety.py)
```

## Faire tourner les tests automatisés (moi ou toi)

```bash
# 1. Démarrer URSim + allumer le robot (voir "Comment tester" ci-dessous, étape 1)
# 2. Test E2E réel dans une vraie fenêtre VS Code (ouvre et referme une fenêtre automatiquement) :
cd extension && npm test
```

`npm test` compile, télécharge une vraie copie de VS Code la première fois (~330 Mo, mise en cache dans `extension/.vscode-test/`, ignoré par git), l'ouvre avec l'extension chargée, exécute les 5 scénarios, et referme la fenêtre (~3s d'exécution des tests une fois VS Code démarré). C'est ce que j'utilise pour vérifier moi-même un changement avant de te dire que ça marche, plutôt que de te demander de tester à chaque fois.

## Comment tester dans VS Code (la partie qui a besoin de toi)

1. `cd docker && docker compose up -d` — attends ~1-2 min, puis démarre le robot simulé :
   ```bash
   python3 -c "
   import socket, time
   s = socket.create_connection(('localhost', 29999), timeout=5)
   s.recv(4096); s.sendall(b'power on\n'); time.sleep(3)
   s.recv(4096); s.sendall(b'brake release\n'); time.sleep(5)
   print(s.recv(4096).decode())
   "
   ```
2. Ouvre le dossier `extension/` dans VS Code, appuie sur **F5** — ça ouvre une seconde fenêtre VS Code ("Extension Development Host") avec l'extension chargée.
3. Dans cette nouvelle fenêtre, ouvre le dossier `test-scripts/` (il contient déjà un `.vscode/launch.json` prêt à l'emploi).
4. Ouvre `counter_clean.script`, clique dans la marge à gauche de la ligne `counter = counter + 1` (ligne 5) pour poser un point d'arrêt.
5. Lance le débogage (F5, ou le triangle vert dans l'onglet Run and Debug).
6. Tu devrais voir l'exécution s'arrêter à cette ligne, la variable `counter` apparaître dans le panneau Variables, et pouvoir cliquer "Continue" pour avancer à l'itération suivante — ou "Step Over" pour avancer ligne par ligne, y compris sur des lignes sans breakpoint.

(Optionnel — je fais déjà cette vérification moi-même via `npm test` avant de te dire qu'un changement fonctionne, inutile de la refaire sauf si tu veux voir l'interface de tes propres yeux.)

## Packaging

```bash
cd extension
npx @vscode/vsce package --allow-missing-repository
```

Produit `urscript-debugger-0.0.1.vsix` (~3 Ko, zéro dépendance runtime — seul `package.json` + `out/extension.js` sont embarqués grâce à `.vscodeignore`). Installable manuellement dans VS Code via "Extensions" → "..." → "Install from VSIX...", ou `code --install-extension urscript-debugger-0.0.1.vsix`.

Avant publication publique sur le Marketplace, il manque encore : un vrai `repository` dans `package.json` (une fois le code poussé sur un dépôt Git distant), un fichier `LICENSE`, une icône, et le modèle de licence freemium (voir discussion précédente sur la monétisation).

## Prochaines étapes (ce qui reste délibérément hors scope pour l'instant)

- Édition de variables non-numériques (chaînes, listes, poses) — nécessiterait un protocole plus riche que `socket_read_ascii_float`.
- Publication Marketplace (reste à faire : `repository` réel dans `package.json`, `LICENSE`, icône) + modèle de licence freemium.

## Statut

Extension complète et fonctionnelle sur toute la portée initialement visée : breakpoints, pas-à-pas, arrêt sécurisé du mouvement, inspection ET édition de variables en direct, multi-fichiers — validée automatiquement de bout en bout via une vraie fenêtre VS Code pilotée en test (5 scénarios), empaquetée en `.vsix` installable. Prête pour un usage réel ; il ne reste que la publication Marketplace comme étape commerciale.
