---
applyTo: "pythonCode/modules/starhe_plugin/**"
---

# Contexte IA — Module starhe_plugin

## Ce que ce module fait

`starhe_plugin` est un module Python intégré au plugin MEDomics.
Il prend en entrée un fichier **DICOM** (échographie hépatique) et produit :
- un **score de risque** de cancer du foie (STARHE-RISK, modèle C3D)
- des **détections de lésions** par bounding box (STARHE-DETECT, modèle RTMDet ou DINO-DETR)

Le point d'entrée public est `pipeline.run_pipeline(dicom_path)`.

---

## Architecture du module

```
starhe_plugin/
├── config.py          ← toutes les constantes, chemins, hyperparamètres
├── pipeline.py        ← orchestrateur principal (appelé par le serveur Go)
├── dicom/             ← lecture, crop, anonymisation, bridge prepUS
├── ai/
│   ├── starhe_risk.py    ← wrapper STARHE-RISK (C3D PyTorch pur)
│   ├── starhe_detect.py  ← wrapper STARHE-DETECT (subprocess runner)
│   ├── vendor/
│   │   └── starhe/       ← package Python du projet d'entraînement (vendorisé)
│   └── models/
│       ├── c3d.py              ← architecture C3D + prétraitement clips
│       ├── rtmdet.py           ← inférence RTMDet (stubs mmcv + torchvision NMS)
│       ├── _rtmdet_runner.py   ← script standalone subprocess RTMDet
│       ├── dino.py             ← inférence DINO-DETR (même stubs que rtmdet.py)
│       └── _dino_runner.py     ← script standalone subprocess DINO
├── models/
│   ├── best_acc_mean_cls_f1_epoch_14.pth     ← poids C3D (297 MB)
│   ├── best_coco_bbox_mAP_50_iter_2100.pth   ← poids RTMDet/DINO (419 MB)
│   ├── rtmdet_starhe.py                      ← config mmdet RTMDet (plat)
│   └── c3d_starhe.py                         ← config mmaction2 C3D (plat)
├── db/                ← persistence MongoDB
├── utils/
│   └── go_print.py    ← go_print(), go_progress(), go_result()
└── ui/                ← prototype interface Tkinter
```

---

## Décisions d'architecture importantes

### 1. Le module est entièrement autonome
Tous les fichiers nécessaires sont dans `starhe_plugin/` lui-même.
**Il n'y a aucune dépendance vers un chemin absolu externe.**
Ne jamais recréer de référence à `F:\STAGE\starhe_share` ou tout autre chemin machine.

### 2. Inférence via subprocess (pattern runner)
MMDet/MMAction utilisent des extensions C (`mmcv._ext`) qui ne sont pas
compilées pour Python 3.13 sur Windows. La solution adoptée est :

- Le **processus principal** (plugin) n'importe jamais `mmcv`, `mmdet`, `mmaction2`
- Chaque inférence lance un **sous-processus Python** dédié
  (`_rtmdet_runner.py` ou `_dino_runner.py`) qui applique les stubs nécessaires
- Les résultats transitent par un **fichier JSON temporaire**

Ce pattern doit être conservé pour tout nouveau modèle mmdet/mmaction.

### 3. Stubs mmcv — obligatoires dans les runners
Chaque script runner applique dans cet ordre exact **avant tout import mmdet** :
1. `sys.modules["mmcv._ext"] = _CExtStub(...)` — remplace le module C absent
2. Stub `tqdm` si absent
3. Patch `inspect.getmodule` — bug Python 3.13 / mmengine
4. `NMSop.forward = staticmethod(_tv_nms_fwd)` — NMS via torchvision

Ne jamais réorganiser cet ordre dans les runners.

### 4. Package `starhe` vendorisé dans `ai/vendor/`
Le dossier `ai/vendor/starhe/` est une copie du package Python issu
du projet d'entraînement. Il contient les classes `DINO`, `RAYDINO`, etc.
enregistrées via `@MODELS.register_module()` de mmdet.
Il est requis uniquement par le backend DINO (`_dino_runner.py`).
Ne pas modifier ce dossier manuellement — le resynchroniser depuis
le projet d'entraînement si les architectures changent.

### 5. Switch de backend détection
Dans `config.py`, la variable `DETECT_BACKEND = "rtmdet"` contrôle
quel modèle est utilisé par `STARHEDetectModel`. Valeurs possibles :
- `"rtmdet"` — défaut, plus rapide, modèle local
- `"dino"` — DINO-DETR, nécessite le package `starhe` vendorisé

> **⚠ État actuel :** les fichiers de config DINO (`models/configs/custom/dino_starhe.py`
> et `models/configs/_base_/`) **ne sont pas encore présents** sur disque.
> Le backend DINO ne fonctionnera pas tant que ces fichiers ne sont pas ajoutés.

---

## Chemins importants (config.py)

| Constante | Valeur résolue |
|-----------|---------------|
| `MODELS_DIR` | `starhe_plugin/models/` |
| `VENDOR_DIR` | `starhe_plugin/ai/vendor/` |
| `STARHE_SHARE_ROOT` | `starhe_plugin/ai/vendor/` (= `VENDOR_DIR`) |
| `STARHE_RISK_CHECKPOINT` | `models/best_acc_mean_cls_f1_epoch_14.pth` |
| `STARHE_DETECT_CHECKPOINT` | `models/best_coco_bbox_mAP_50_iter_2100.pth` |
| `STARHE_DINO_CHECKPOINT` | `models/best_coco_bbox_mAP_50_iter_2100.pth` |
| `STARHE_DINO_CONFIG` | `models/configs/custom/dino_starhe.py` ⚠ absent du disque |

---

## Conventions de code

- Tous les logs passent par `go_print(level, message)` de `utils/go_print.py`
  (format `GO_PRINT|level|json` parsé par le serveur Go)
- Les fonctions exposées publiquement retournent des `dict` JSON-sérialisables
- Les frames numpy sont toujours `(T, H, W, 3) uint8 RGB` dans le pipeline,
  et converties en BGR juste avant l'écriture disque ou l'inférence mmdet
- Ne jamais appeler `sys.exit()` depuis le module principal — lever une exception

---

## Flux d'une requête DICOM

### Mode standalone (serveur Go STARHE)

```
Go server STARHE (POST /starhe/analyze)
    → subprocess : python -m starhe_plugin.pipeline <dicom_path> --anon_mode ...
        │
        ├─ dicom/reader.py      → load_dicom() + extract_frames()
        ├─ dicom/anonymizer.py  → anonymize()
        ├─ dicom/prepus_bridge  → preprocess_with_prepus()   (crop + backscan)
        │
        ├─ ai/starhe_risk.py    → STARHERiskModel.predict(frames)
        │       └─ models/c3d.py  (PyTorch pur, pas de subprocess)
        │
        ├─ ai/starhe_detect.py  → STARHEDetectModel.predict(mid_frame)
        │       └─ subprocess → models/_rtmdet_runner.py  (ou _dino_runner.py)
        │                              └─ models/rtmdet.py  (ou dino.py)
        │
        └─ db/mongo_client.py   → save_result()  (graceful si MongoDB absent)
```

Communication : lignes `GO_PRINT|level|json` sur stdout → SSE vers le client.

### Mode intégré MEDomics

```
MEDomics Go server (POST starhe/analyze/)
    → StartPythonScripts(json, "../pythonCode/modules/starhe/run_starhe.py", id)
        │  (env Python MEDomics — PAS le venv STARHE)
        │
        └─ run_starhe.py  (GoExecutionScript)
              │  localise le venv STARHE (starhe_plugin/.venv/)
              │  lance subprocess dans ce venv :
              └─ python -m starhe_plugin.pipeline ...
                    │  (même chaîne que le mode standalone ci-dessus)
                    └─ stdout GO_PRINT|… → traduit en progress*_*/response-ready*_*
```

Communication :
- Pipeline émet `GO_PRINT|progress|json` sur stdout
- `run_starhe.py` traduit → `progress*_*{id}*_*{json}` (protocole MEDomics)
- Résultat final → `response-ready*_*{filepath}`

### Fichiers d'intégration MEDomics

| Fichier (dans ce dépôt) | Destination dans MEDomics |
|--------------------------|---------------------------|
| `pythonCode/modules/starhe/run_starhe.py` | `pythonCode/modules/starhe/run_starhe.py` |
| `medomics_integration/starhe_blueprint.go` | `go_server/blueprints/starhe/starhe.go` |
| `plugin.json` | Manifeste (lu manuellement pour l'intégration) |

Ajout requis dans `MEDomics/go_server/main.go` :
```go
import Starhe "go_module/blueprints/starhe"
// dans main() :
Starhe.AddHandleFunc()
```
