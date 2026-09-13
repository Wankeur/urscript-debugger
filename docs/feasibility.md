# Analyse de faisabilité technique

## Interfaces réseau du contrôleur UR / URSim

- **Dashboard Server (29999)** : commandes `play`/`pause`/`stop`/`load`. Le `pause` ne suspend pas proprement l'exécution d'un script en cours — confirmé par un utilisateur du forum officiel ("le robot ne sait plus quoi exécuter, il a tué la dernière ligne de script"). Pas utilisable tel quel pour du débogage fiable.
- **Primary (30001) / Secondary (30002)** : 10 Hz, envoi de commandes URScript et retour d'état robot.
- **Realtime (30003)** : 500 Hz, écriture uniquement, sans accusé de réception fiable.
- **RTDE (30004)** : registres d'entrée/sortie configurables à fréquence de contrôle — bon canal de télémétrie continue, mais nombre de registres limité, pas taillé pour inspecter un nombre arbitraire de variables utilisateur.

## Pas de pause/reprise native pour du script brut — confirmé, avec une nuance importante

PolyScope a des breakpoints natifs sur les nœuds du programme graphique depuis la v5.6.x.x, mais un utilisateur du forum officiel confirme explicitement qu'il n'y a aucun moyen d'appliquer ça à un fichier script. Le gap réel est précis : **aucun débogage pour du URScript écrit/envoyé en texte brut**, pas "aucun débogage UR" en général.

Un utilisateur de ce même forum a déjà bricolé la solution manuellement : une fonction `breakPoint()` maison utilisant `socket_open` vers un serveur local pour suspendre l'exécution sur commande. Ça valide directement l'architecture retenue ci-dessous comme idiome déjà découvert par la communauté, juste jamais packagé proprement en outil.

Source : [Breakpoint in debugging URScript (forum UR officiel)](https://forum.universal-robots.com/t/breakpoint-in-debugging-urscript/7469)

## Hirebotics/urscript-tools

Exécuteur headless contre URSim en Docker, façon CI (pass/fail) — pas un débogueur interactif, aucune pause/step/inspection. Utile comme infrastructure d'orchestration Docker/URSim à réutiliser ; la logique de débogage reste entièrement à construire.

## Architecture retenue : instrumentation de code + Debug Adapter Protocol

**Pourquoi pas un interpréteur URScript réimplémenté** (l'alternative envisagée) : perd toute fidélité dès qu'il y a du mouvement réel (`movej`/`movel` ne se "simulent" pas fidèlement hors du contrôleur/URSim), aucun précédent trouvé pour cette approche sur un langage robot. Écartée.

**Architecture retenue :**
1. Parser le `.script` utilisateur (parsing syntaxique suffisant pour repérer les frontières d'instructions, pas un moteur sémantique complet) et insérer des appels `breakPoint()` aux lignes marquées.
2. Avant de bloquer sur le socket, arrêter proprement tout mouvement en cours (`stopl`/`stopj`) — ne pas reproduire le bug du `pause` du Dashboard Server qui gèle au milieu d'un mouvement.
3. Serveur de rendez-vous externe (Python) qui reçoit la connexion socket, tient la pause, lit/écrit des variables, envoie le signal de reprise.
4. **Adaptateur DAP (Debug Adapter Protocol)** par-dessus ce serveur : traduit les requêtes standard de VS Code (setBreakpoints, continue, next, variables, evaluate) vers le mécanisme socket. Donne gratuitement toute l'UI de débogage de VS Code, sans rien construire côté interface.

## URSim

Images Docker officielles disponibles (`universalrobots/ursim_e-series`, `universalrobots/ursim_cb3`, modèle robot sélectionnable par variable d'environnement). Expose les mêmes interfaces réseau qu'un vrai contrôleur — développement et test entièrement faisables en simulation avant tout accès à un robot réel.

## Évaluation globale

**Faisabilité : bonne.** Mécanisme central déjà pratiqué informellement par la communauté, testable entièrement sur URSim dockerisé. Prototype fonctionnel (parse + instrumentation + pause/continue + variable basique) réaliste en quelques semaines à temps partiel ; un IDE poli, quelques mois.

## Risques principaux

- **Marché plus étroit que "tous les utilisateurs UR"** : la cible réelle est les auteurs de script brut (intégrateurs, utilisateurs ROS/External Control, développeurs d'URCap) — les utilisateurs PolyScope classiques ont déjà des breakpoints natifs depuis la v5.6.
- **RTDE limité en nombre de registres** — garder le canal socket ad hoc pour l'inspection de variables arbitraires, RTDE pour la télémétrie haute fréquence seulement.
- **Sécurité du point d'arrêt** : ne jamais bloquer naïvement au milieu d'un mouvement en cours — arrêter proprement (`stopl`/`stopj`) avant de suspendre, sous peine de reproduire le bug du Dashboard Server.
