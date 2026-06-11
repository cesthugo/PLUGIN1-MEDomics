# build-resources/

Ressources statiques utilisées par **electron-builder** lors de l'empaquetage.

## Fichiers attendus

| Fichier      | Plateforme | Taille recommandée | Comment générer |
|--------------|------------|--------------------|-----------------|
| `icon.icns`  | macOS      | 1024×1024          | `iconutil -c icns icon.iconset` (besoin d'un dossier `.iconset` avec 10 tailles) — ou en ligne via [cloudconvert](https://cloudconvert.com/png-to-icns) |
| `icon.ico`   | Windows    | 256×256 multi-size | `magick icon.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico` (ImageMagick) |
| `icon.png`   | Linux      | 512×512 minimum    | déjà présent (copie du logo MEDomics) |

## Statut actuel

- ✅ `icon.png` — placeholder (logo MEDomics)
- ⏳ `icon.icns` — à générer pour les builds DMG/PKG signés
- ⏳ `icon.ico` — à générer pour le build NSIS Windows

> **Note** : en l'absence de `.icns` / `.ico`, electron-builder loggue un warning mais ne plante pas — il utilise l'icône Electron par défaut. Pour une release officielle, fournir les 3 formats.
