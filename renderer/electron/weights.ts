/**
 * electron/weights.ts — Local (offline) provisioning of the STARHE AI weights.
 *
 * For confidentiality, the model weights are NOT hosted anywhere and are NOT
 * downloaded automatically. The user provides them from their own computer:
 * per AI model, when its weight is missing, the React UI asks the user to pick
 * the file, which is copied into `app.getPath('userData')/models/` under the
 * canonical name the pipeline expects (resolved via `STARHE_WEIGHTS_DIR`).
 *
 * Extensible: to support a new AI model, add an entry to MODELS below — no other
 * change is needed on the Electron side.
 */

import { app } from 'electron';
import * as path from 'path';
import * as fs from 'fs';

/** One selectable AI model whose weight the user provides locally. */
export interface ModelSpec {
  /** Stable id used by the UI to request a specific model's weight. */
  id: string;
  /** Human-readable name shown in dialogs/UI. */
  name: string;
  /** Canonical file name the pipeline expects in the weights dir. */
  file: string;
  /** Reference size (bytes), used to sanity-check a renamed pick. Optional. */
  sizeHint?: number;
}

/**
 * Registry of AI models. Add new models here as the plugin grows — the status
 * and per-model loading flow pick them up automatically.
 */
export const MODELS: ModelSpec[] = [
  {
    id: 'risk',
    name: 'STARHE-RISK (C3D)',
    file: 'best_acc_mean_cls_f1_epoch_14.pth',
    sizeHint: 312_198_292,
  },
  {
    id: 'detect',
    name: 'STARHE-DETECT (RTMDet)',
    file: 'best_coco_bbox_mAP_50_iter_2100.pth',
    sizeHint: 438_998_465,
  },
];

/** Directory where the weights must sit before running the pipeline. */
export function getWeightsDir(): string {
  return path.join(app.getPath('userData'), 'models');
}

function fileSize(p: string): number {
  try { return fs.statSync(p).size; } catch { return 0; }
}

/** True if the given model's weight is present locally (> 1 MB sanity check). */
export function isModelPresent(spec: ModelSpec): boolean {
  return fileSize(path.join(getWeightsDir(), spec.file)) > 1_000_000;
}

export interface ModelStatus {
  id: string;
  name: string;
  file: string;
  present: boolean;
}

/** Per-model presence status for the whole registry. */
export function modelsStatus(): ModelStatus[] {
  return MODELS.map((m) => ({ id: m.id, name: m.name, file: m.file, present: isModelPresent(m) }));
}

/** Look up a model spec by id. */
export function findModel(id: string): ModelSpec | undefined {
  return MODELS.find((m) => m.id === id);
}

/**
 * Installs a user-selected weight file for a specific model: copies it into the
 * weights dir under the model's canonical name. Returns the outcome (+ a soft
 * warning if the picked file's size is far from the expected one).
 */
export function installModelWeight(id: string, sourcePath: string): {
  ok: boolean;
  id: string;
  error?: string;
  warning?: string;
} {
  const spec = findModel(id);
  if (!spec) return { ok: false, id, error: `Modèle inconnu : ${id}` };

  const size = fileSize(sourcePath);
  if (size === 0) return { ok: false, id, error: `Fichier illisible : ${path.basename(sourcePath)}` };

  let warning: string | undefined;
  if (spec.sizeHint && Math.abs(size - spec.sizeHint) / spec.sizeHint > 0.2) {
    warning = `Taille inattendue pour ${spec.name} (${Math.round(size / 1e6)} Mo vs ~${Math.round(spec.sizeHint / 1e6)} Mo attendus).`;
  }

  const dir = getWeightsDir();
  fs.mkdirSync(dir, { recursive: true });
  try {
    fs.copyFileSync(sourcePath, path.join(dir, spec.file));
  } catch (e) {
    return { ok: false, id, error: `Copie échouée : ${(e as Error).message}` };
  }
  return { ok: isModelPresent(spec), id, warning };
}
