/**
 * electron/weights.ts — Local (offline) provisioning of the STARHE AI weights.
 *
 * For confidentiality, the `.pth` model weights are NOT hosted anywhere and are
 * NOT downloaded automatically. The user provides them from their own computer:
 * the React UI asks for the files before an analysis, and they are copied into
 * `app.getPath('userData')/models/` — the directory the Go server / Python
 * pipeline resolves via `STARHE_WEIGHTS_DIR`.
 */

import { app } from 'electron';
import * as path from 'path';
import * as fs from 'fs';

/** Canonical file names the pipeline expects (config.py / STARHE_*_CHECKPOINT). */
export const REQUIRED_MODELS = [
  'best_acc_mean_cls_f1_epoch_14.pth',    // C3D    — STARHE-RISK   (~312 MB)
  'best_coco_bbox_mAP_50_iter_2100.pth',  // RTMDet — STARHE-DETECT (~439 MB)
];

/** Reference sizes (bytes) used to map a picked file to the right model when
 *  the user renamed it. Matching is tolerant (±5 %). */
const SIZE_HINTS: Record<string, number> = {
  'best_acc_mean_cls_f1_epoch_14.pth':   312_198_292,
  'best_coco_bbox_mAP_50_iter_2100.pth': 438_998_465,
};

/** Directory where the `.pth` weights must sit before running the pipeline. */
export function getWeightsDir(): string {
  return path.join(app.getPath('userData'), 'models');
}

function isPresent(name: string): boolean {
  try {
    return fs.statSync(path.join(getWeightsDir(), name)).size > 1_000_000;
  } catch {
    return false;
  }
}

/** True if all required weights are present (> 1 MB sanity check). */
export function modelsReady(): boolean {
  return REQUIRED_MODELS.every(isPresent);
}

/** Names of the weights still missing from the weights dir. */
export function missingModels(): string[] {
  return REQUIRED_MODELS.filter((n) => !isPresent(n));
}

/** Map a picked `.pth` to a canonical model name: exact filename first, then
 *  size (±5 %). Returns null if it matches nothing known. */
function resolveTarget(srcPath: string): string | null {
  const base = path.basename(srcPath);
  if (REQUIRED_MODELS.includes(base)) return base;
  let size = 0;
  try { size = fs.statSync(srcPath).size; } catch { return null; }
  for (const name of REQUIRED_MODELS) {
    const ref = SIZE_HINTS[name];
    if (ref && Math.abs(size - ref) / ref < 0.05) return name;
  }
  return null;
}

/**
 * Copies user-selected `.pth` files into the weights dir under their canonical
 * names. Returns the resulting status.
 */
export function installWeights(sourcePaths: string[]): {
  ready: boolean;
  installed: string[];
  missing: string[];
  error?: string;
} {
  const dir = getWeightsDir();
  fs.mkdirSync(dir, { recursive: true });

  const installed: string[] = [];
  const unrecognized: string[] = [];

  for (const src of sourcePaths) {
    const target = resolveTarget(src);
    if (!target) { unrecognized.push(path.basename(src)); continue; }
    try {
      fs.copyFileSync(src, path.join(dir, target));
      installed.push(target);
    } catch (e) {
      return { ready: modelsReady(), installed, missing: missingModels(),
               error: `Copie échouée pour ${path.basename(src)}: ${(e as Error).message}` };
    }
  }

  const ready = modelsReady();
  let error: string | undefined;
  if (!ready) {
    error = `Poids manquants : ${missingModels().join(', ')}`;
    if (unrecognized.length) error += ` — fichier(s) non reconnu(s) : ${unrecognized.join(', ')}`;
  }
  return { ready, installed, missing: missingModels(), error };
}
