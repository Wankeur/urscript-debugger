# Publication sur le VS Code Marketplace

Trois choses nécessitent ton compte personnel — je ne peux pas les faire à ta place.

## 1. Créer un "publisher" Marketplace

1. Va sur https://marketplace.visualstudio.com/manage (connexion avec un compte Microsoft).
2. "Create publisher" — choisis un identifiant (ex: `radermacker` ou le nom de ta future entreprise). C'est cet identifiant qu'il faudra me donner pour le champ `publisher` de `package.json`.

## 2. Créer un token d'accès (PAT)

1. Va sur https://dev.azure.com, connecte-toi avec le même compte Microsoft.
2. Icône utilisateur (en haut à droite) → "Personal access tokens" → "New Token".
3. Organisation : "All accessible organizations". Scope : "Marketplace" → coche "Manage".
4. Copie le token généré (il ne sera plus affiché après).

**Ne me colle jamais ce token dans le chat.** Ajoute-le plutôt à ton `~/.bashrc` (ou `~/.profile`) :

```bash
echo 'export VSCE_PAT="colle_ton_token_ici"' >> ~/.bashrc
source ~/.bashrc
```

Comme mon environnement shell se charge depuis ton profil à chaque commande, je pourrai ensuite lancer `vsce publish -p "$VSCE_PAT"` sans jamais voir la valeur réelle dans la conversation — même principe que pour les clés API Bybit.

## 3. Créer le dépôt Git distant

1. Crée un dépôt **vide** sur GitHub (ou GitLab/autre) — ne pas cocher "Initialize with README".
2. Donne-moi l'URL (ex: `https://github.com/ton-compte/urscript-debugger.git`), je pousse le code dessus et je mets à jour le `repository` dans `package.json`.

## 4. Publier

Une fois les trois étapes ci-dessus faites, la commande est :

```bash
cd extension
npx @vscode/vsce publish
```

`vsce` lit automatiquement `VSCE_PAT` depuis l'environnement — pas besoin de le passer en argument si tu as suivi l'étape 2. Je peux lancer cette commande moi-même à ce moment-là, puisque le token ne transite jamais par la conversation.

## Après la première publication

- Chaque nouvelle version : changer `version` dans `package.json` (semver), puis relancer `vsce publish` (ou `vsce publish patch`/`minor`/`major` pour incrémenter automatiquement).
- La page Marketplace de l'extension devient : `https://marketplace.visualstudio.com/items?itemName=<publisher>.urscript-debugger`.
