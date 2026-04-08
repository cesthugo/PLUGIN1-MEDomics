# 👤 Guide Utilisateur — Interface STARHE

> Ce document explique comment utiliser le prototype d'interface du plug-in STARHE,  
> dédié à l'analyse échographique hépatique pour la détection du carcinome hépatocellulaire (CHC).

---

## 🚀 Lancement de l'Interface

```powershell
# Windows (PowerShell)
.\run_tkinter.ps1

# macOS / Linux
./run_tkinter.sh
```

La fenêtre s'ouvre avec la sidebar de contrôle à gauche et la zone de visualisation à droite.

---

## 📂 1. Charger un ou Plusieurs Fichiers DICOM

1. Dans la sidebar, section **FICHIER DICOM**, cliquez sur **📂 Charger un fichier DICOM**.
2. La boîte de dialogue permet de sélectionner **un ou plusieurs fichiers** simultanément (`Ctrl+clic` ou `Shift+clic`).
3. Formats acceptés :
   - Fichiers `.dcm` classiques
   - **Fichiers sans extension** (ex. `A0000`, `IM-0001`) — utilisez le filtre **« Tous fichiers »**

**À l'import, automatiquement :**
- Les **métadonnées sensibles** sont supprimées des tags DICOM
- Le **bandeau d'en-tête** de l'imageur est **noirci**
- Le **pixel spacing** est extrait pour les mesures en millimètres
- Un **onglet** est créé pour chaque fichier chargé, intitulé par la date du DICOM (`JJ/MM/AAAA`)

---

## 📄 2. Onglets Multi-Fichiers

La **barre d'onglets** est située en bas de la visionneuse, comme un navigateur web.

| Action | Résultat |
|---|---|
| Cliquer sur un onglet | Bascule vers ce fichier (la visionneuse, les résultats, les mesures et l'état de lecture sont préservés) |
| Cliquer sur **×** d'un onglet | Ferme ce fichier (le dernier onglet réinitialise tout) |
| Cliquer sur **+** (à droite) | Ouvre le sélect eur de fichiers pour ajouter d'autres DICOM |
| Défilement horizontal molette | Défile si trop d'onglets |
| `Ctrl+Tab` | Onglet suivant |
| `Ctrl+Shift+Tab` | Onglet précédent |
| `Ctrl+W` | Ferme l'onglet actif |

**Label des onglets :** extrait du tag `StudyDate` DICOM (format `JJ/MM/AAAA`). Si absent, le nom du fichier est utilisé.

---

## ▶ 3. Navigation dans la Séquence

### Boutons de navigation
| Contrôle | Action |
|---|---|
| **◄** | Frame précédente |
| **►** | Frame suivante |
| Scrollbar horizontale | Glisser pour aller directement à une position |
| **► Play** | Lance la lecture automatique |
| **⏸ Pause** | Met la lecture en pause |
| **⏮ Revenir au début** | Stoppe et revient au frame 0 |

### Vitesse de lecture
- Slider **×-vitesse** (0.25× à 3.0×) dans la sidebar
- La vitesse de base est calibrée automatiquement depuis le tag `FrameTime` du DICOM
- En dessous de ×1 : lecture ralentie ; au-dessus : frames sautées pour accélérer

### Mode boucle
- Cochez **Boucle** pour que la lecture recommence automatiquement à la fin de la séquence

---

## ⌨️ 4. Raccourcis Clavier

> Les raccourcis sont désactivés lorsqu'un champ de saisie a le focus.

### Navigation vidéo
| Touche | Action |
|---|---|
| `Espace` | ► Play / ⏸ Pause |
| `←` / `→` | Frame précédente / suivante |
| `Shift+←` / `Shift+→` | −10 / +10 frames |
| `Home` / `End` | Premier / Dernier frame |

### Modes de vue
| Touche | Action |
|---|---|
| `P` | Toggle **Pan/Zoom** |
| `M` | Toggle **Mesure** |
| `S` | Toggle **Défilement série** (molette = frames) |
| `Échap` | Désélectionne la mesure active, sinon réinitialise la vue |
| `R` | **Réinitialiser** la vue (zoom, pan, contraste, luminosité) |

### Ajustements image
| Touche | Action |
|---|---|
| `C` | Ouvrir dialog **Contraste** |
| `L` | Ouvrir dialog **Luminosité** |
| `+` ou `=` | Vitesse de lecture ×1.25 |
| `-` | Vitesse de lecture ×0.80 |
| `B` | Toggle **Boucle** |

### Zoom
| Touche | Action |
|---|---|
| `Cmd+=` / `Ctrl+=` | **Zoom avant** (×1.25) |
| `Cmd+-` / `Ctrl+-` | **Zoom arrière** (÷1.25) |
| `Cmd+0` / `Ctrl+0` | **Réinitialiser** zoom à 100 % |

### Onglets
| Touche | Action |
|---|---|
| `Ctrl+Tab` | Onglet suivant |
| `Ctrl+Shift+Tab` | Onglet précédent |
| `Ctrl+W` | Fermer l'onglet actif |

---

## 🔍 5. Pan & Zoom

**Activation du pan :** Clic droit → **Déplacer / Zoomer** ou touche `P` (curseur devient une main)

| Action | Résultat |
|---|---|
| **Clic-glisser** (mode Pan) | Déplace l'image dans le canvas |
| **Boutons `−` / `+`** (en-tête de la visionneuse) | Zoom arrière / avant (×1.25) |
| `Cmd+=` / `Ctrl+=` | Zoom avant |
| `Cmd+-` / `Ctrl+-` | Zoom arrière |
| `Cmd+0` / `Ctrl+0` | Réinitialiser zoom à 100 % |

Le **pourcentage de zoom** s'affiche entre les boutons `−` et `+` dans l'en-tête.

Pour revenir à la vue initiale : touche `R` ou Clic droit → **Réinitialiser la vue**

> **Note macOS (Tk 9.0)** : le scroll trackpad (molette) ne génère pas d'événement dans Tkinter avec Tk 9.0.3. Utilisez les boutons ou les raccourcis clavier pour zoomer.

---

## 📏 6. Outil de Mesure (Multi-Segments)

**Activation :** Clic droit → **Outil de mesure** ou touche `M` (curseur devient une croix)

### Dessiner un nouveau segment
1. **Cliquez et maintenez** sur une zone vide du canvas
2. **Glissez** jusqu'au point d'arrivée — une ligne jaune pointillée s'affiche en temps réel
3. **Relâchez** — le segment est fixé, la distance s'affiche en jaune

Plusieurs mesures peuvent être tracées simultanément.

### Persistance des mesures
- Les mesures **restent visibles** lorsque vous changez de mode (Pan/Zoom, Normal, etc.)
- Les mesures **suivent le zoom et le pan** : elles restent proportionnelles à l'image
- Seule l'action **Réinitialiser la vue** (touche `R`) efface les mesures

### Sélectionner / Éditer / Supprimer
| Action | Résultat |
|---|---|
| Cliquer **près d'un segment** | Le sélectionne (passe en orange) |
| Cliquer-glisser **sur un endpoint** (extrémité) | Déplace uniquement cet endpoint |
| Cliquer-glisser **au milieu d'un segment** | Déplace tout le segment |
| `Delete` ou `BackSpace` | Supprime le segment sélectionné |
| `Échap` | Désélectionne sans supprimer |

**Affichage de la distance :**
- Si le DICOM contient une calibration : **`X.X mm`**
- Sinon : **`X.X px (pas de calibration)`**

> La calibration est extraite depuis `PixelSpacing`, `ImagerPixelSpacing`, ou `SequenceOfUltrasoundRegions`.

---

## 📜 7. Défilement de Séries (Molette Frame-par-Frame)

**Activation :** Clic droit → **Défilement de séries** ou touche `S`

| Action | Résultat |
|---|---|
| **Molette vers le bas** | Frame suivant |
| **Molette vers le haut** | Frame précédent |

En mode **Normal** (sans mode spécial activé), glisser verticalement au bouton gauche permet aussi de défiler frame par frame (1 frame tous les 8 pixels de déplacement).

---

## 🎨 8. Réglages Contraste & Luminosité

### Via le menu contextuel
- Clic droit → **Contraste…** ou **Luminosité…** — ouvre une fenêtre flottante avec curseur
- Bouton **Réinitialiser** pour revenir aux valeurs neutres (contraste 1.0, luminosité 0)

### Via le clic droit maintenu
- **Maintenir le clic droit + glisser** :
  - Vers la droite/gauche : contraste + / −
  - Vers le bas/haut : luminosité + / −
- L'image se met à jour en temps réel

### Via les raccourcis
- Touche `C` : ouvre la fenêtre Contraste
- Touche `L` : ouvre la fenêtre Luminosité

---

## 🔄 9. Réinitialiser la Vue

Touche `R` ou Clic droit → **Réinitialiser la vue** : réinitialise en une action :
- Zoom → 1.0 (fit automatique)
- Pan → centré
- Contraste → 1.0
- Luminosité → 0
- Mode → Normal
- Mesures → effacées

---

## ⚙️ 10. Pré-Traitement

1. Chargez d'abord un fichier DICOM
2. Dans la section **PRÉ-TRAITEMENT**, configurez :
   - ☑ **Backscan (512×512)** — cochée : affiche la reconstruction rectangulaire (recommandé pour l'IA)
3. Cliquez sur **⚙ Pré-Traitement**
4. Indicateur d'état :
   - `⟳ Traitement en cours…` — en attente
   - `✓ Terminé` — succès
   - `✗ Erreur` — voir la console
5. Cochez **Afficher résultat pré-traitement** pour basculer entre l'image originale et le résultat

---

## 🧠 11. Analyse IA

1. Chargez un DICOM et lancez le pré-traitement (optionnel)
2. Cliquez sur **🧠 Lancer l'analyse STARHE**
3. Section **RÉSULTATS** :

| Champ | Description |
|---|---|
| **Mode** | Surface analysée (Backscan 512×512 / Pré-traitement / Original) |
| **Risque CHC** | Score 0–1 + label `Faible` (vert) ou `Élevé` (rouge) |
| **Lésions** | Nb frames avec lésion(s) |

**Frames avec tumeur** : liste des numéros 1-basés cliquables — cliquer navigue vers ce frame.

**Cache automatique** : si le fichier a déjà été analysé, les résultats sont restaurés **instantanément** depuis MongoDB.

**🗑 Réinitialiser l'analyse** : efface les résultats MongoDB pour ce fichier afin de forcer une nouvelle analyse.

---

## 💬 12. Console

La **Console** en bas de la fenêtre affiche en temps réel :
- Les étapes de chargement et d'anonymisation
- La progression du pré-traitement
- Les résultats de l'analyse IA
- Les erreurs éventuelles (en rouge)

Elle est en lecture seule.

---

## 🎗 13. Thème Clair / Sombre

Le bouton **🌙 Thème sombre** en bas de la sidebar bascule entre thème clair et sombre.  
La sidebar reste toujours sombre dans les deux modes.

---

## ⚠️ Notes Importantes

- **Anonymisation** : chaque fichier chargé est anonymisé **en mémoire**. Le fichier original sur le disque **n'est pas modifié**.
- **Plusieurs fichiers ouverts** : chaque onglet dispose de son propre état indépendant (lecture, zoom, mesures, résultats). Basculer d'onglet sauvegarde et restaure automatiquement tout l'état.
- **Analyse en cours + changement d'onglet** : si une analyse IA ou un pré-traitement est en cours, ne pas changer d'onglet avant la fin pour éviter un mélange d'états.
- **Calibration mm** : si `Pixel : N/A` s'affiche, la mesure sera affichée en pixels.
- **Fichiers sans extension** : si votre fichier n'apparaît pas dans le sélecteur, changez le filtre sur **« Tous fichiers (*.*) »**.

---

*Pour toute question technique, consultez le [README.md](README.md) ou la [TODOLIST.md](TODOLIST.md).*

Depuis la racine du projet :

```powershell
# Windows (PowerShell)
.\run_tkinter.ps1

# macOS / Linux
./run_tkinter.sh
```

La fenêtre s'ouvre avec la sidebar de contrôle à gauche et la zone de visualisation à droite.

---

## 📂 1. Charger un Fichier DICOM

1. Dans la sidebar, section **FICHIER DICOM**, cliquez sur **📂 Charger un fichier DICOM**.
2. La boîte de dialogue s'ouvre dans le dossier de données configuré.
3. Sélectionnez votre fichier :
   - Fichiers `.dcm` classiques
   - Fichiers **sans extension** (ex. `A0000`, `IM-0001` — format Canon Aplio, Toshiba, etc.)
   - Utilisez le filtre **"Tous fichiers"** si votre fichier n'apparaît pas

**À l'import, automatiquement :**
- Les **métadonnées sensibles** (nom patient, ID, dates, UIDs…) sont supprimées des tags DICOM
- Le **bandeau d'en-tête** de l'imageur (informations patient brûlées dans les pixels) est **noirci**
- Le **pixel spacing** est extrait pour permettre les mesures en millimètres

Les informations non-sensibles s'affichent dans la sidebar :
```
Modalité : US
Taille   : 1280×890
Frames   : 120
Pixel    : 0.275 mm/px
```

---

## ▶ 2. Navigation dans la Séquence

### Boutons de navigation
| Contrôle | Action |
|---|---|
| **◀** | Frame précédente |
| **▶** | Frame suivante |
| Scrollbar horizontale | Glisser pour aller directement à une position |
| **▶ Play** | Lance la lecture automatique |
| **⏸ Pause** | Met la lecture en pause |
| **⏮ Revenir au début** | Stoppe et revient au frame 0 |

### Vitesse de lecture
- Slider **×-vitesse** (0.25× à 3.0×, pas de 0.25×) dans la sidebar — glissez le curseur
- Le label **×1.00** se met à jour dynamiquement
- La vitesse de base est calibrée automatiquement depuis le tag `FrameTime` du DICOM
- En dessous de ×1 : lecture ralentie (intervalle étendu) ; au-dessus : frames sautées pour accélérer

### Mode boucle
- Cochez **Boucle** pour que la lecture recommence automatiquement à la fin de la séquence
- Décochez pour un arrêt automatique au dernier frame

---

## 🖱️ 3. Menu Contextuel (Clic Droit)

Un **clic droit sur le canvas** ouvre un menu avec 7 options.  
Le mode actif est marqué d'un **✓**.

```
╔══════════════════════════════╗
║ ✓ Déplacer / Zoomer          ║  ← mode courant
║   Mesurer                    ║
║ ─────────────────────────────║
║   Contraste…                 ║
║   Luminosité…                ║
║ ─────────────────────────────║
║   Series Scroll              ║
║ ─────────────────────────────║
║   Réinitialiser la vue       ║
╚══════════════════════════════╝
```

---

## 🔍 4. Pan & Zoom

**Activation du pan :** Clic droit → **Déplacer / Zoomer** (curseur devient une main ✋)

| Action | Résultat |
|---|---|
| **Clic-glisser** (mode Pan) | Déplace l'image dans le canvas |
| **Boutons `−` / `+`** (en-tête de la visionneuse) | Zoom arrière / avant (×1.25) |
| `Cmd+=` / `Ctrl+=` | Zoom avant |
| `Cmd+-` / `Ctrl+-` | Zoom arrière |
| `Cmd+0` / `Ctrl+0` | Réinitialiser zoom à 100 % |

Le **pourcentage de zoom** s'affiche entre les boutons.

Pour revenir à la vue initiale : Clic droit → **Réinitialiser la vue**

---

## 📏 5. Outil de Mesure

**Activation :** Clic droit → **Mesurer** (curseur devient une croix ✛)

1. **Cliquez et maintenez** le bouton gauche sur le point de départ de votre mesure
2. **Glissez** jusqu'au point d'arrivée — une ligne jaune pointillée s'affiche en temps réel
3. **Relâchez** pour fixer la mesure — la distance s'affiche au-dessus de la ligne

Plusieurs mesures peuvent être tracées simultanément. Les mesures **persistent** lorsque vous changez de mode et **suivent le zoom/pan** de l'image.

**Affichage de la distance :**
- Si le fichier DICOM contient une calibration spatiale : **`X.X mm`**
- Sinon : **`X.X px (pas de calibration)`**

> La calibration est automatiquement extraite depuis les tags `PixelSpacing`,  
> `ImagerPixelSpacing`, ou `SequenceOfUltrasoundRegions` (échographies).

Pour effacer les mesures : cliquez sur **Réinitialiser la vue**.

---

## 📜 6. Défilement de Séries (Molette Frame-par-Frame)

**Activation :** Clic droit → **Défilement de séries** (curseur devient une double flèche ↕)

| Action | Résultat |
|---|---|
| **Molette vers le bas** | Frame suivant |
| **Molette vers le haut** | Frame précédent |

Utile pour parcourir la séquence lentement sans utiliser la scrollbar.

---

## 🎨 7. Réglages Contraste & Luminosité

### Contraste
1. Clic droit → **Contraste…**
2. Une fenêtre flottante s'ouvre avec un curseur (0.1 — 3.0, neutre = 1.0)
3. Déplacez le curseur — l'image se met à jour en temps réel
4. Bouton **Réinitialiser** pour revenir à la valeur neutre (1.0)

### Luminosité
1. Clic droit → **Luminosité…**
2. Curseur de −100 à +100 (neutre = 0)
3. Même fonctionnement que le contraste

Les deux fenêtres peuvent être ouvertes simultanément.

---

## 🔄 8. Réinitialiser la Vue

Clic droit → **Réinitialiser la vue** — Réinitialise en une action :
- Zoom → 1.0 (fit automatique)
- Pan → centré
- Contraste → 1.0
- Luminosité → 0
- Mesure → effacée

---

## ⚙️ 9. Pré-Traitement

Le pré-traitement utilise **prepUS** pour supprimer les annotations et l'interface graphique de l'imageur.

1. Chargez d'abord un fichier DICOM
2. Dans la section **PRÉ-TRAITEMENT**, configurez :
   - ☑ **Backscan (512×512)** — cochée : affiche la reconstruction rectangulaire (recommandé pour l'IA)
   - Décochez pour afficher le crop masqué (image originale sans l'interface de l'imageur)
3. Cliquez sur **⚙ Pré-Traitement**
4. Un indicateur d'état apparaît sous le bouton :
   - `⟳ Traitement en cours…` — en attente
   - `✓ Terminé` — succès
   - `✗ Erreur` — voir la console

5. Cochez **Afficher résultat pré-traitement** pour basculer entre l'image originale et le résultat
6. La checkbox **Backscan (512×512)** peut être basculée **après** le traitement sans relancer prepUS

---

## 🧠 10. Analyse IA

1. Assurez-vous d'avoir chargé un DICOM (et idéalement lancé le pré-traitement)
2. Cliquez sur **🧠 Lancer l'analyse STARHE**
3. Les résultats s'affichent dans la section **RÉSULTATS** :

| Champ | Description |
|---|---|
| **Risque CHC** | Score 0–1 + label `Faible` (vert) ou `Élevé` (rouge) |
| **Lésions** | Nombre de lésions détectées + score de confiance moyen |

Les bounding boxes de détection s'affichent directement sur le canvas.

**Frames avec tumeur** : après l'analyse, la section **Frames avec tumeur** dans la sidebar affiche la liste des numéros de frames (1-basés) où une lésion a été détectée, en **bleu cliquable**. Cliquer sur un numéro navigue directement vers ce frame.

**Cache automatique** : si le fichier `.dcm` a été analysé lors d'une session précédente, les résultats sont restaurés **instantanément** depuis MongoDB sans relancer les modèles IA.

---

## 💬 11. Console

La **Console** en bas de la fenêtre affiche en temps réel :
- Les étapes de chargement et d'anonymisation
- La progression du pré-traitement
- Les résultats de l'analyse IA
- Les erreurs éventuelles

Elle est en lecture seule. Les messages d'erreur apparaissent en rouge.

---

## 🌗 12. Thème Clair / Sombre

Le bouton **🌙 Thème sombre** en bas de la sidebar bascule entre :
- **Thème clair** — zone principale `#f4f6fb`, cartes blanches
- **Thème sombre** — zone principale `#1a1a2e`, cartes `#16213e`

La sidebar reste toujours sombre dans les deux modes.

---

## ⚠️ Notes Importantes

- **Anonymisation** : chaque fichier chargé est automatiquement anonymisé en mémoire. Le fichier original sur le disque **n'est pas modifié**.
- **Bandeau imageur** : le bandeau d'en-tête (informations patient visibles) est noirci automatiquement. Si le bandeau n'est pas détecté, vérifiez que l'image a un fond noir autour du cône échographique.
- **Calibration mm** : si `Pixel : N/A` s'affiche dans la sidebar, le fichier DICOM ne contient pas de calibration spatiale et la mesure sera affichée en pixels.
- **Fichiers sans extension** : si votre fichier n'apparaît pas dans le sélecteur, changez le filtre sur **"Tous fichiers (*.*)"**.

---

*Pour toute question technique, consultez le [README.md](README.md) ou la [TODOLIST.md](TODOLIST.md).*
