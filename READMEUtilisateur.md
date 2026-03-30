# 👤 Guide Utilisateur — Interface STARHE

> Ce document explique comment utiliser le prototype d'interface du plug-in STARHE,  
> dédié à l'analyse échographique hépatique pour la détection du carcinome hépatocellulaire (CHC).

---

## 🚀 Lancement de l'Interface

Depuis la racine du projet, exécutez le script PowerShell :

```powershell
.\run_tkinter.ps1
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
║ ✓ Pan / Zoom                 ║  ← mode courant
║   Outil de mesure            ║
║   Défilement de séries       ║
║ ─────────────────────────────║
║   Contraste…                 ║
║   Luminosité…                ║
║ ─────────────────────────────║
║   Réinitialiser la vue       ║
╚══════════════════════════════╝
```

---

## 🔍 4. Pan & Zoom

**Activation :** Clic droit → **Pan / Zoom** (curseur devient une main ✋)

| Action | Résultat |
|---|---|
| **Clic-glisser** | Déplace l'image dans le canvas |
| **Molette vers le haut** | Zoom avant (×1.1 par cran) |
| **Molette vers le bas** | Zoom arrière (÷1.1 par cran) |

Pour revenir à la vue initiale : Clic droit → **Réinitialiser la vue**

---

## 📏 5. Outil de Mesure

**Activation :** Clic droit → **Outil de mesure** (curseur devient une croix ✛)

1. **Cliquez et maintenez** le bouton gauche sur le point de départ de votre mesure
2. **Glissez** jusqu'au point d'arrivée — une ligne jaune pointillée s'affiche en temps réel
3. **Relâchez** pour fixer la mesure — la distance s'affiche au-dessus de la ligne

**Affichage de la distance :**
- Si le fichier DICOM contient une calibration spatiale : **`X.X mm`**
- Sinon : **`X.X px (pas de calibration)`**

> La calibration est automatiquement extraite depuis les tags `PixelSpacing`,  
> `ImagerPixelSpacing`, ou `SequenceOfUltrasoundRegions` (échographies).

Pour effacer la mesure : activez un autre mode ou cliquez sur **Réinitialiser la vue**.

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
