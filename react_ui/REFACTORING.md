# Refactoring de `StarhePlugin/index.tsx`

## Résumé

| Métrique          | Avant      | Après     |
|-------------------|------------|-----------|
| Lignes `index.tsx`| **1 723**  | **895**   |
| Réduction         | —          | −48 %     |
| Nouveaux fichiers | —          | 7         |

---

## Fichiers créés

### Hooks

#### `hooks/useTabManager.ts`
Centralise toute la gestion d'état des onglets et des patients.

**API exportée :**
```ts
export interface TabManagerParams {
  addLog:       (msg: string, level?: LogLevel) => void;
  isPlaying:    boolean;
  setIsPlaying: React.Dispatch<React.SetStateAction<boolean>>;
}

export interface TabManagerResult {
  tabs, activeTabId, patients, activePatientName,
  activeTab, activeTabIdx, activePatientIdx,
  addTab, openBatchResultAsTab,
  switchTab, closeTab, updateActiveTab, updateTabById,
  setActiveTabId, setActivePatientName,
}
```

**Responsabilités :**
- `useState` pour `tabs`, `activeTabId`, `patients`, `activePatientName`
- `useRef` pour les lectures synchrones hors updater (nécessaires dans `closeTab`)
- `addTab` : injection d'un onglet après chargement DICOM réussi
- `openBatchResultAsTab` : chargement d'un résultat batch + création d'onglet
- `switchTab` / `closeTab` : navigation et fermeture avec nettoyage des patients
- `updateActiveTab` / `updateTabById` : mutation d'un onglet par ID

---

#### `hooks/useKeyboardShortcuts.ts`
Extrait le `useEffect` de raccourcis clavier (~90 lignes).

**Raccourcis gérés :**
- `Space` / `P` : play/pause
- `←` / `→` : frame précédente / suivante
- `Shift+←` / `Shift+→` : ±10 frames
- `R` : reset vidéo  
- `M` : cycle mode vue
- `S` : reset vue (zoom/pan)
- `C` / `L` : ouvrir dialogue contraste / luminosité
- `+` / `-` : vitesse ×1.25 / ÷1.25
- `B` : toggle boucle
- `Cmd/Ctrl + =` / `-` / `0` : zoom +/−/reset
- `Cmd/Ctrl + Tab` : onglet suivant du patient
- `Cmd/Ctrl + W` : fermer onglet courant

---

### Composants

#### `components/PatientTabBar.tsx`
Barre de navigation entre patients (onglets horizontaux en haut de la carte).

**Props :**
```ts
{ patients: Patient[]; activePatientIdx: number; onSwitchPatient: (idx: number) => void }
```

---

#### `components/FileThumbnailStrip.tsx`
Bande de vignettes DICOM en bas du visualiseur, remplace l'ancienne `FileTabBar` textuelle.

**Fonctionnalités :**
- Vignette visuelle (premier frame en base64 si disponible, sinon icône SVG)
- Label date d'étude + nom de fichier
- Drag & drop vers multi-panneau (`draggable`, `data-transfer: starhe-tab:<id>`)
- Bouton × pour fermer l'onglet
- Bouton + pour ouvrir un nouveau fichier
- Scroll horizontal automatique

**Props :**
```ts
{ tabs: TabState[]; activeTabId: number; onSwitchTab, onCloseTab, onOpenNew }
```

---

#### `components/MultiPanelView.tsx`
Vue multi-panneaux (split-v, split-h, quad) avec handles de redimensionnement.

**Fonctionnalités :**
- Resize par drag sur les séparateurs (colSplit / rowSplit en %)
- Mise en évidence du panneau actif
- Drag & drop pour déplacer / échanger les panneaux
- Zone d'expansion (affichée quand < 4 panneaux) pour glisser un fichier supplémentaire
- Bouton ✕ par panneau pour le retirer
- Bouton « Quitter » pour revenir en vue simple

**Interface :**
```ts
interface MultiPanelViewProps {
  layout: LayoutMode; tabIds: number[]; tabs: TabState[];
  activeTabId: number;
  onFocusPanel, onExit, onDropToPanel, onExpandLayout, onRemovePanel,
  onZoomPan, onContrastBright, onFrameChange,
  onMeasureAdd, onMeasureMove, onMeasureLabelMove, onMeasureSelect,
  onContextMenu,
}
```

---

### Utilitaires

#### `utils.ts`
```ts
export function isDicomFile(f: File): boolean
export function nextTabId(): number
```

---

## Transformations dans `index.tsx`

| Transformation                         | Détail                                              |
|----------------------------------------|-----------------------------------------------------|
| `useRef` retiré des imports React      | Déplacé dans `useTabManager`                        |
| `PTAB_BG`, `TAB_BG`, etc. retirés     | Utilisés uniquement dans les composants extraits    |
| `makeTabLabel` retiré                  | Utilisé uniquement dans `useTabManager`             |
| `_nextTabId` / `nextTabId` retirés     | Déplacés dans `utils.ts`                            |
| `makeDefaultTab` retirée               | Déplacée dans `useTabManager` (interne)             |
| Bloc état onglets/patients remplacé    | `useTabManager({ addLog, isPlaying, setIsPlaying })` |
| `handleFrameChange` mis à jour         | `updateActiveTab(t => ...)` au lieu de `setTabs(...)` |
| `lastResult` useEffect mis à jour      | `updateTabById(...)` au lieu de `setTabs(prev => prev.map(...))` |
| `addTab` + `openBatchResultAsTab` retirés | Fournis par `useTabManager`                      |
| `isDicomFile` lambdas inline retirées  | Importée depuis `utils.ts`                         |
| `updateActiveTab` retiré               | Fourni par `useTabManager`                         |
| `switchTab` + `closeTab` retirés       | Fournis par `useTabManager`                        |
| Keyboard `useEffect` remplacé          | `useKeyboardShortcuts({ ... })`                    |
| Fonctions locales `PatientTabBar`, `FileThumbnailStrip`, `MultiPanelView` retirées | Importées depuis leurs modules |

---

## Architecture avant / après

### Avant
```
index.tsx (1723 lignes)
  ├── Imports
  ├── _nextTabId, nextTabId, makeDefaultTab
  ├── StarhePlugin
  │   ├── useState ×4 (tabs, activeTabId, patients, activePatientName)
  │   ├── useRef ×2
  │   ├── isPlaying, handleFrameChange, usePlayback
  │   ├── logs, addLog
  │   ├── usePipelineSSE, lastResult useEffect
  │   ├── addTab (useCallback ~30 lignes)
  │   ├── openBatchResultAsTab (useCallback ~40 lignes)
  │   ├── doLoadPath, doLoadFile, onLoadDicom, onLoadDicomFiles, onLoadPath
  │   ├── updateActiveTab (useCallback)
  │   ├── onPrevFrame, onNextFrame, onTogglePlay, ... (navigation)
  │   ├── switchTab, closeTab (useCallback ~40 lignes)
  │   ├── keyboard useEffect (~90 lignes)
  │   └── JSX (~320 lignes)
  ├── function PatientTabBar (local)
  ├── function FileThumbnailStrip (local)
  ├── export default StarhePlugin
  └── interface + function MultiPanelView (après l'export !)
```

### Après
```
index.tsx (895 lignes)
  ├── Imports (inclut hooks + composants extraits)
  ├── _nextLogId, nextLogId
  └── StarhePlugin
      ├── logs, addLog
      ├── isPlaying
      ├── useTabManager → tabs, activeTabId, patients, activeTab, ...
      ├── handleFrameChange, handleStop, usePlayback
      ├── usePipelineSSE, lastResult useEffect (updateTabById)
      ├── doLoadPath, doLoadFile, onLoadDicom, onLoadDicomFiles, onLoadPath
      ├── navigation (onPrevFrame, onNextFrame, ...)
      ├── useKeyboardShortcuts({ ... })
      └── JSX (~320 lignes)

hooks/useTabManager.ts     (~170 lignes)
hooks/useKeyboardShortcuts.ts (~100 lignes)
components/PatientTabBar.tsx   (~55 lignes)
components/FileThumbnailStrip.tsx (~130 lignes)
components/MultiPanelView.tsx  (~330 lignes)
utils.ts                       (~15 lignes)
```
