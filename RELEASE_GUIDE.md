# 📦 Guide de release STARHE Plugin

> Documentation complète des actions effectuées pour mettre en place le système
> de release multi-plateformes (macOS / Linux / Windows) du plugin STARHE.
> Journal de bord opérationnel — **10 juin 2026**.

---

## Table des matières

1. [Vue d'ensemble du système de distribution](#1-vue-densemble)
2. [Architecture en 5 phases](#2-architecture-en-5-phases)
3. [Workflow CI GitHub Actions](#3-workflow-ci-github-actions)
4. [Procédure pour créer une release](#4-procédure-pour-créer-une-release)
5. [Journal des erreurs rencontrées et fixes appliqués](#5-journal-des-erreurs-rencontrées)
6. [Limitations connues et travaux futurs](#6-limitations-connues)
7. [Référence rapide des commandes](#7-référence-rapide)

---

## 1. Vue d'ensemble

Le plugin STARHE est livré sous forme d'**installeurs Electron natifs** par
plateforme, à l'identique de la grille de distribution de MEDomics :

| Plateforme | Architecture | Format(s) actuel(s) |
|---|---|---|
| macOS Apple Silicon | `arm64` | `.dmg`, `.zip` |
| macOS Intel | `x64` | `.dmg`, `.zip` |
| Linux | `x64` | `.deb` |
| Windows | `x64` | `.exe` (NSIS) |

Tous les installeurs sont produits par **GitHub Actions** sur push d'un tag
`v*`, puis publiés dans la section [Releases](https://github.com/cesthugo/PLUGIN1-MEDomics/releases)
du repo avec un fichier `SHA256SUMS.txt` agrégé.

L'objectif final : **un seul clic** pour l'utilisateur final (drag-and-drop
dans Applications / double-clic `.deb` / installeur NSIS), aucun setup Python /
Java / Go manuel requis. La seule dépendance externe restante est **MongoDB**
sur le port 54017.

---

## 2. Architecture en 5 phases

Le système de distribution a été construit progressivement en 5 phases. Chaque
phase ajoute une autonomie supplémentaire à l'installeur en supprimant une
dépendance externe.

### Phase 1 — Coquille Electron + Go server (livrée)

> `.dmg` = 111 MB

- Embarque le **serveur Go compilé** (`go_server` ou `go_server.exe`).
- Embarque la **librairie `weasis-dcm2png`** (JAR + natifs OpenCV).
- L'utilisateur doit avoir Python + Java + MongoDB installés sur sa machine.
- Splash screen pendant le boot, healthcheck `GET /health` sur port 8082
  avant d'afficher la fenêtre principale.

**Fichiers clés** :
- [renderer/electron/main.ts](renderer/electron/main.ts)
- [renderer/electron/splash.html](renderer/electron/splash.html)
- [renderer/package.json](renderer/package.json) (section `"build"`)

### Phase 2 — Worker Python bundlé via PyInstaller (livrée)

> `.dmg` = 284 MB (+173 MB)

- **Plus besoin du venv Python** sur la machine de l'utilisateur.
- PyInstaller `--onedir` bundle torch + mmdet + prepUS + le code STARHE
  dans un dossier `starhe_worker/` (~527 MB extraits).
- Le serveur Go détecte la variable `STARHE_WORKER_BIN` et lance le binaire
  PyInstaller à la place du `python -m starhe_plugin.X` du dev.
- Un **dispatcher unique** [`starhe_worker.py`](pythonCode/modules/starhe_plugin/starhe_worker.py)
  multiplexe 5 entry points via `runpy.run_module()`.

**Fichiers clés** :
- [scripts/starhe_worker.spec](scripts/starhe_worker.spec)
- [pythonCode/modules/starhe_plugin/starhe_worker.py](pythonCode/modules/starhe_plugin/starhe_worker.py)
- [go_server/config.go](go_server/config.go) (helper `pythonCmd`)

### Phase 3 — JRE Temurin 17 embarquée (livrée)

> `.dmg` = 325 MB (+41 MB)

- **Plus besoin de `brew install openjdk@17`** chez l'utilisateur.
- JRE Temurin 17.0.19+10 téléchargée par `scripts/fetch_jre.sh` (Unix) ou
  `scripts/fetch_jre.ps1` (Windows) depuis l'API Adoptium.
- Le bridge [weasis_bridge.py](pythonCode/modules/starhe_plugin/dicom/weasis_bridge.py)
  lit `STARHE_JAVA_BIN` (défini par Electron en mode packagé) et passe ce
  binaire à `subprocess.run([...])`.

**Fichiers clés** :
- [scripts/fetch_jre.sh](scripts/fetch_jre.sh)
- [scripts/fetch_jre.ps1](scripts/fetch_jre.ps1)
- [renderer/build-resources/jre-mac-arm64/](renderer/build-resources/) (gitignored, regénéré par fetch_jre)

### Phase 4 — Modèles `.pth` téléchargés au 1er lancement (livrée)

> `.dmg` reste à 325 MB (modèles non embarqués)

- **Les 750 MB de poids C3D + RTMDet** sont téléchargés depuis une release
  GitHub `STARHE_MODELS` au premier démarrage de l'app.
- Fenêtre Electron 540×340 avec barre de progression, écrit dans
  `app.getPath('userData')/models/` (sur macOS :
  `~/Library/Application Support/starhe-plugin/models/`).
- Override pour tests local : `STARHE_MODELS_BASE_URL=http://localhost:8765`.
- Côté Python, [config.py](pythonCode/modules/starhe_plugin/config.py) résout
  les `.pth` via la variable `STARHE_WEIGHTS_DIR` injectée par Electron.

**Fichiers clés** :
- [renderer/electron/download-models.ts](renderer/electron/download-models.ts)
- [renderer/electron/download-models.html](renderer/electron/download-models.html)
- [renderer/electron/download-preload.ts](renderer/electron/download-preload.ts)

### Phase 5 — CI GitHub Actions multi-plateformes (en cours de validation)

- **Builds automatiques** sur push de tag `v*`.
- Matrice 4 runners : `macos-14` (arm64), `macos-13` (x64), `ubuntu-latest`,
  `windows-latest`.
- Chaque job effectue les phases 1→3 et produit l'installeur correspondant.
- Job final `release` : agrège les artefacts, calcule `SHA256SUMS.txt`,
  crée la release GitHub en **brouillon** (relecture humaine avant publication).

**Fichier clé** :
- [.github/workflows/release.yml](.github/workflows/release.yml)

---

## 3. Workflow CI GitHub Actions

### Triggers

```yaml
on:
  push:
    tags:
      - 'v*'           # déclenche le build + crée une release brouillon
  workflow_dispatch:    # test manuel sans publier de release
```

### Matrice de build (4 jobs parallèles)

| Runner | `platform` | Cibles electron-builder |
|---|---|---|
| `macos-14` (Apple Silicon) | `mac-arm64` | `--mac --arm64` |
| `macos-13` (Intel) | `mac-x64` | `--mac --x64` |
| `ubuntu-latest` | `linux-x64` | `--linux --x64` |
| `windows-latest` | `win-x64` | `--win --x64` |

### Étapes par job (séquentielles)

1. `actions/checkout@v4`
2. `actions/setup-node@v4` — Node 20 + cache npm sur `renderer/package-lock.json`
3. `actions/setup-python@v5` — Python 3.13 + cache pip
4. `actions/setup-go@v5` — Go 1.22 + cache `go.sum`
5. **Linux uniquement** : `apt-get install fakeroot dpkg rpm libarchive-tools`
6. **Build Go** : `go build -trimpath -ldflags "-s -w"` → `go_server[.exe]`
7. **Install Python deps** : `pip install pyinstaller==6.20.0 + requirements.txt`
8. **PyInstaller** : `pyinstaller scripts/starhe_worker.spec --noconfirm`
9. **Fetch JRE** : `fetch_jre.sh` ou `fetch_jre.ps1` selon l'OS
10. `npm ci` dans `renderer/`
11. **Copie `weasis-dcm2png/target/` → `dist/`** (cf. fix #3 dans le journal)
12. `npm run build:electron`
13. `npx electron-builder <flags> --publish never`
14. Copie des installeurs finaux dans `dist-artifacts/`
15. `actions/upload-artifact@v4` nommé `starhe-<platform>`

### Job final `release` (uniquement sur push de tag)

1. `actions/download-artifact@v4` avec `pattern: starhe-*` + `merge-multiple: true`
2. `sha256sum * > SHA256SUMS.txt`
3. `softprops/action-gh-release@v2` :
   - `draft: true` (relecture humaine obligatoire)
   - `generate_release_notes: true` (changelog auto)
   - Upload tous les artefacts incluant `SHA256SUMS.txt`

### Variables d'environnement importantes

| Variable | Rôle |
|---|---|
| `CSC_IDENTITY_AUTO_DISCOVERY=false` | Empêche electron-builder de chercher des certificats absents |
| `GH_TOKEN=${{ secrets.GITHUB_TOKEN }}` | Téléchargement Electron derrière proxy + création de release |

---

## 4. Procédure pour créer une release

### Prérequis (une seule fois)

```bash
# Installer GitHub CLI
brew install gh

# S'authentifier
gh auth login
# → GitHub.com → HTTPS → Yes (Git credentials) → Login with a web browser
# → copier le code à 8 chiffres dans github.com/login/device

# Vérifier
gh auth status
```

### Cycle de release standard

```bash
# 1) Travailler sur main, s'assurer que tout est commit + pushé
git checkout main
git pull origin main
git status   # doit être clean

# 2) Bumper la version dans renderer/package.json
#    IMPORTANT : la version dans package.json DOIT correspondre au tag,
#    sinon electron-builder embarque une version incohérente dans les installeurs.
# Éditer manuellement "version": "0.6.X" dans renderer/package.json
git add renderer/package.json
git commit -m "chore: bump version to 0.6.X"
git push origin main

# 3) Créer un tag annoté (l'annotation est obligatoire, pas un tag léger)
git tag -a v0.6.X -m "Release 0.6.X — description"
git push origin v0.6.X
# → déclenche automatiquement le workflow .github/workflows/release.yml
```

### Suivre l'exécution

```bash
# Liste des runs récents
gh run list --workflow=release.yml --limit 5

# Détail d'un run (statut par job)
gh run view <RUN_ID>

# Watcher temps réel
gh run watch <RUN_ID>

# Logs d'un job qui a échoué
gh run view --job <JOB_ID> --log-failed

# Si run terminé : récupérer les logs via API
gh api repos/cesthugo/PLUGIN1-MEDomics/actions/jobs/<JOB_ID>/logs
```

### Tester sans publier (workflow_dispatch)

Pratique pour valider un fix CI sans pousser de tag :

```bash
# Déclenche manuellement le workflow sur main
gh workflow run release.yml --ref main

# Récupérer les artefacts produits (sans création de release GitHub)
gh run download <RUN_ID>
```

### Publier la release brouillon

Une fois les 4 jobs `build` + le job `release` terminés avec succès :

1. Aller sur https://github.com/cesthugo/PLUGIN1-MEDomics/releases
2. Trouver le brouillon (statut "Draft") nommé `STARHE v0.6.X`
3. **Vérifier** les notes auto-générées (liste des PRs/commits depuis le tag précédent)
4. Vérifier la liste des assets (4 installeurs + `SHA256SUMS.txt`)
5. Cliquer **Publish release**

### Refaire un build sur un tag existant

Si le workflow a échoué et qu'on a fixé le bug :

```bash
# 1) Supprimer la release brouillon et le tag (local + remote)
gh release delete v0.6.X --cleanup-tag --yes 2>/dev/null || true
git tag -d v0.6.X
git push origin :refs/tags/v0.6.X

# 2) Re-tagger sur le nouveau HEAD (avec le fix)
git tag -a v0.6.X -m "Release 0.6.X — retry après fix CI"
git push origin v0.6.X
```

---

## 5. Journal des erreurs rencontrées

Toutes les erreurs rencontrées lors du **premier vrai run de la CI** (10 juin 2026)
et leurs fixes appliqués.

### Run #27319681453 — push tag `v0.6.3` initial

#### Fix #1 — `.pkg` macOS échoue sans certificat Apple Installer

**Erreur** :
```
⨯ ENOENT: no such file or directory, unlink
'renderer/release/com.medomics.starhe-plugin.pkg'
```

**Cause** : electron-builder tente de produire un `.pkg` (installeur signé
macOS) qui nécessite un certificat Apple Developer ID Installer. Sans
certificat, la signature échoue et le fichier final n'est jamais écrit.

**Fix** : retirer la cible `pkg` du `build.mac.target` dans
[renderer/package.json](renderer/package.json). On garde `.dmg` (drag-and-drop)
et `.zip` (archive standalone), qui ne nécessitent pas de signature obligatoire.

```diff
       "target": [
         { "target": "dmg", "arch": ["arm64", "x64"] },
-        { "target": "pkg", "arch": ["arm64", "x64"] },
         { "target": "zip", "arch": ["arm64", "x64"] }
       ]
```

#### Fix #2 — `.AppImage` Linux : disque plein

**Erreur** :
```
⨯ cannot execute  cause=exit status 1
errorOut=Write failed because No space left on device
FATAL ERROR:Failed to write to output filesystem
command=mksquashfs ... STARHE-0.6.2-linux-x86_64.AppImage
```

**Cause** : les runners GitHub `ubuntu-latest` ne disposent que de ~14 GB
d'espace disque libre. Le bundle PyInstaller (527 MB) + Electron (300 MB) +
JRE (150 MB) + AppImage intermédiaire (mksquashfs travaille avec une copie
décompressée) dépasse cette limite.

**Fix** : retirer la cible `AppImage` du `build.linux.target`. On garde le
`.deb` qui suffit pour 95% des cas (Ubuntu, Debian, Mint). Pour ajouter
l'AppImage plus tard, il faudra soit utiliser un runner `larger`
(GitHub-hosted payant), soit nettoyer l'espace disque avant
(`sudo rm -rf /usr/local/lib/android /opt/ghc /opt/hostedtoolcache/CodeQL`
libère ~25 GB).

```diff
       "target": [
-        { "target": "deb", "arch": ["x64"] },
-        { "target": "AppImage", "arch": ["x64"] }
+        { "target": "deb", "arch": ["x64"] }
       ]
```

#### Fix #3 — `weasis-dcm2png/dist/` introuvable sur CI

**Erreur** :
```
• file source doesn't exist
  from=/home/runner/work/.../third_party/weasis-dcm2png/dist
```

**Cause** : `.gitignore` contient une règle globale `dist/` (ligne 30) qui
exclut `third_party/weasis-dcm2png/dist/` du repo. Le JAR et les natifs OpenCV
sont effectivement committés dans `third_party/weasis-dcm2png/target/`
(produits par `mvn package` localement), mais `extraResources` dans
`package.json` pointe vers `dist/`.

**Fix** : ajouter une étape CI qui reconstruit `dist/` depuis `target/` avant
electron-builder. C'est plus propre que de modifier `.gitignore` ou de
dupliquer les fichiers dans le repo.

```yaml
- name: Prepare weasis-dcm2png/dist
  shell: bash
  run: |
    set -eux
    src=third_party/weasis-dcm2png/target
    dst=third_party/weasis-dcm2png/dist
    mkdir -p "$dst/native"
    cp "$src/weasis-dcm2png.jar" "$dst/"
    if [ -d "$src/native" ]; then
      cp -R "$src/native/." "$dst/native/"
    fi
```

#### Commit du fix global

```bash
git add renderer/package.json .github/workflows/release.yml
git commit -m "ci: fix release workflow (drop .pkg/.AppImage, copy weasis target->dist)"
git push origin main
# → commit b066446
```

### Run #27320141284 — workflow_dispatch sur `main` après fixes

Lancé pour valider que les 3 fixes ci-dessus suffisent à débloquer la CI sans
créer une release prématurée.

```bash
gh workflow run release.yml --ref main
```

État : en cours au moment où ce document est écrit. La validation finale
consistera à :
1. Vérifier que les 4 jobs `build` passent au vert.
2. Télécharger les artefacts via `gh run download <RUN_ID>`.
3. Tester un installeur sur chaque plateforme disponible (au minimum le
   `.dmg` mac-arm64 sur la machine de dev).
4. Si OK → supprimer le tag `v0.6.3` (pointe sur le commit pré-fix), le
   recréer sur le commit post-fix `b066446`, pousser → déclenche la vraie
   release brouillon.

---

## 6. Limitations connues

### Limitations bloquantes pour une distribution clinique

| # | Problème | Workaround actuel | Solution propre |
|---|---|---|---|
| 1 | Pas de signature macOS (Gatekeeper bloque) | Clic-droit → Ouvrir → Ouvrir quand même | Apple Developer ID + `xcrun notarytool` |
| 2 | Pas de signature Windows (SmartScreen warning) | Cliquer "Informations complémentaires" → "Exécuter quand même" | EV Code Signing Cert Windows |
| 3 | `weasis-dcm2png/native/` ne contient que `.dylib` macOS | Fallback pydicom silencieux sur Linux/Windows (perte LUT VOI) | `mvn dependency:copy -Dartifact=org.openpnp:opencv:4.13.0:so:linux-x86_64` puis idem `:dll:windows-x86_64` |
| 4 | Release `STARHE_MODELS` privée → erreur 404 sans `GITHUB_TOKEN` | OK pour le dev local | Rendre la release publique ou héberger les `.pth` sur CDN |
| 5 | MongoDB externe requis sur :54017 | Documenté dans README | Bundler `mongod` (+100 MB) ou basculer sur SQLite |

### Limitations non bloquantes (warnings ignorables)

| Warning | Impact réel | À traiter ? |
|---|---|---|
| `WARNING: Failed to collect submodules for 'torch.utils.tensorboard'` | Aucun — tensorboard est exclu volontairement | Non |
| `ERROR: Hidden import 'pydicom.encoders.gdcm' not found` | Aucun — décodeur DICOM optionnel | Non |
| `ERROR: Hidden import 'prepUS' not found` au stade analyse PyInstaller | Faux positif — prepUS est résolu via `pathex=[SRC_ROOT]` au runtime | Non, sauf si crash runtime |
| `Cannot detect repository by .git/config` (electron-builder) | Aucun — sert juste à l'auto-updater (non utilisé) | Ajouter `"repository": "github:cesthugo/PLUGIN1-MEDomics"` dans `package.json` pour silencer |

### Coûts CI à surveiller

Les runners macOS GitHub-hosted consomment **10× les minutes Linux** sur le
quota gratuit (3000 min/mois pour les repos privés). Une release complète
(4 jobs) consomme environ :
- 2× macOS × ~20 min = 40 min × 10 = **400 min équivalent Linux**
- 1× Linux × ~10 min = **10 min**
- 1× Windows × ~15 min = 15 min × 2 = **30 min équivalent Linux**
- **Total ≈ 440 min/release**

Pour un repo privé sur le plan gratuit (3000 min/mois) : **~6 releases/mois max**.
Pour des tests `workflow_dispatch` fréquents, restreindre la matrice à
`ubuntu-latest` uniquement via un input du workflow (à ajouter si besoin).

---

## 7. Référence rapide

### Commandes essentielles

```bash
# ── Authentification ──────────────────────────────────────────────────
gh auth login                       # interactif
gh auth status                      # vérifier

# ── Release ───────────────────────────────────────────────────────────
git tag -a v0.6.X -m "Release"      # créer tag annoté
git push origin v0.6.X              # déclenche la CI

# ── Suivi CI ──────────────────────────────────────────────────────────
gh run list --workflow=release.yml --limit 5
gh run view <RUN_ID>                # statut par job
gh run watch <RUN_ID>               # temps réel
gh run view --job <JOB_ID> --log    # logs complet
gh run view --job <JOB_ID> --log-failed  # logs des steps échoués

# ── Logs via API (si run en cours / archivés) ─────────────────────────
gh api repos/cesthugo/PLUGIN1-MEDomics/actions/jobs/<JOB_ID>/logs

# ── Artefacts ─────────────────────────────────────────────────────────
gh run download <RUN_ID>            # tous les artefacts
gh run download <RUN_ID> --name starhe-mac-arm64  # un seul

# ── Test sans release ─────────────────────────────────────────────────
gh workflow run release.yml --ref main

# ── Annuler / rééxécuter ──────────────────────────────────────────────
gh run cancel <RUN_ID>
gh run rerun <RUN_ID>               # uniquement les jobs échoués
gh run rerun <RUN_ID> --failed      # idem
gh run rerun <RUN_ID> --debug       # avec logs verbeux

# ── Nettoyer une release ratée ────────────────────────────────────────
gh release delete v0.6.X --cleanup-tag --yes
git tag -d v0.6.X
git push origin :refs/tags/v0.6.X

# ── Lister releases ───────────────────────────────────────────────────
gh release list
gh release view v0.6.X
```

### Structure des fichiers de release

```
release/                                    # dossier produit par electron-builder
├── STARHE-0.6.3-mac-arm64.dmg              # ~325 MB
├── STARHE-0.6.3-mac-arm64.zip              # ~325 MB
├── STARHE-0.6.3-mac-x64.dmg                # ~325 MB
├── STARHE-0.6.3-mac-x64.zip                # ~325 MB
├── starhe-plugin_0.6.3_amd64.deb           # ~300 MB
├── STARHE-0.6.3-win-x64.exe                # ~300 MB
└── SHA256SUMS.txt                          # généré par le job release
```

### Fichiers à connaître

| Fichier | Rôle |
|---|---|
| [.github/workflows/release.yml](.github/workflows/release.yml) | Workflow CI multi-plateformes |
| [renderer/package.json](renderer/package.json) | Config electron-builder (section `build`) |
| [scripts/starhe_worker.spec](scripts/starhe_worker.spec) | Spec PyInstaller |
| [scripts/fetch_jre.sh](scripts/fetch_jre.sh) / [.ps1](scripts/fetch_jre.ps1) | Téléchargement JRE Adoptium |
| [renderer/electron/main.ts](renderer/electron/main.ts) | Boot Electron + spawn Go + env vars |
| [renderer/electron/download-models.ts](renderer/electron/download-models.ts) | Téléchargement modèles au 1er lancement |
| [pythonCode/modules/starhe_plugin/config.py](pythonCode/modules/starhe_plugin/config.py) | Lit `STARHE_WEIGHTS_DIR` |
| [TODOLIST.md](TODOLIST.md) | Historique chronologique de toutes les phases |
| [README.md](README.md) | Doc utilisateur + sections "Distribution" |

### Convention de nommage des artefacts

```
STARHE-${version}-${os}-${arch}.${ext}
```

Identique à MEDomics. Configurée via `artifactName` dans `build.dmg`,
`build.pkg`, `build.nsis` de [package.json](renderer/package.json).

---

## Annexe — Historique du repo

| Tag | Date | Notes |
|---|---|---|
| `v0.6.3` (1er essai) | 10 juin 2026 | Premier push de tag. CI échoue sur `.pkg`, `.AppImage`, `weasis dist`. |
| `v0.6.3` (à retagger) | post-fix | Après commit `b066446` qui corrige les 3 problèmes. |

> Pour toute nouvelle release future, suivre la procédure de la
> [section 4](#4-procédure-pour-créer-une-release) — l'essentiel est de
> bumper `renderer/package.json` AVANT de tagger.
