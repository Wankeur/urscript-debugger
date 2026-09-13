# Étude de marché — niche robotique industrielle

Suite à l'étude de marché PLC (voir le projet `plc-code-bridge`, où un concurrent gratuit direct a été trouvé sur l'idée de conversion de code inter-marques), cette recherche s'est orientée côté robotique, avec vérification systématique de la concurrence pour chaque piste avant de la retenir.

## Pistes évaluées

**1. Portabilité de programmes robots entre marques (RAPID/KRL/TP/URScript) — écartée.**
Aucune conversion inter-marques automatique ne semble exister, mais pour une raison structurelle et non une opportunité : les instructions de mouvement dépendent de la cinématique physique du robot (géométrie, singularités, conventions d'outil). Une mauvaise conversion peut produire des trajectoires dangereuses. Risque élevé, valeur incertaine.

**2. IDE/débogueur pour URScript (Universal Robots) — retenue.**
Demande réelle et récurrente sur plusieurs années sur le forum officiel UR ("URScript IDE for writing and debugging", "Breakpoint in debugging URScript"). Concurrence vérifiée et confirmée faible : seulement une extension VS Code de coloration syntaxique (`ahern.urscript`) et un projet open source d'exécution headless (`Hirebotics/urscript-tools`) — aucun outil avec débogage pas-à-pas/breakpoints. Universal Robots a le plus gros parc de cobots installés au monde.

**3. Simulation/programmation hors-ligne de cellules robotisées — écartée.**
RoboDK (1800-5000$ perpétuel) domine déjà ce marché aux côtés d'OCTOPUZ, SprutCAM X Robot, RoboCell, RobotWorks. Marché établi, déjà bien pourvu en concurrents sérieux.

**4. Conformité PackML — confirmée faible.**
Douleur réelle documentée (thread P&G sur des implémentations peu robustes) mais MathWorks propose déjà un produit PackML dans Simulink (vérification de machine à états + génération de tests). Incumbent majeur déjà en place.

**5. Signal freelance (Upwork)** : ~2980 offres "Automation" et 48 "PLC Programming" — demande de service réelle mais trop générique pour pointer vers un produit précis.

## Décision

Produit retenu : **IDE/débogueur URScript pour Universal Robots**, seule piste combinant demande documentée et récurrente, absence confirmée de concurrent dominant, parc installé massif, et faisabilité solo réaliste.
