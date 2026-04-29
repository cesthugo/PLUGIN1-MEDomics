// hooks/useDisplaySettings.ts — Paramètres d'affichage persistants (localStorage)

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'starhe_display_settings';

// ── Interface des paramètres ──────────────────────────────────────────────────

export interface DisplaySettings {
  /** Facteur d'agrandissement du texte (0.8 – 1.6). Appliqué via injection CSS proportionnelle. */
  fontScale:  number;
  /** Police CSS (valeur CSS complète, ex. "'Segoe UI', system-ui, sans-serif"). */
  fontFamily: string;
  /** Couleur principale du texte (hex). */
  textColor:  string;
  /** Couleur de fond du panneau latéral (hex). */
  sidebarBg:  string;
  /** Couleur de fond de la zone principale (hex). */
  mainBg:     string;
  /** Modèles IA à exécuter lors du clic sur "Lancer l'analyse". */
  analysisMode: 'both' | 'risk_only' | 'detect_only';
}

// ── Valeurs par défaut (identiques au thème actuel) ───────────────────────────

export const DISPLAY_DEFAULTS: DisplaySettings = {
  fontScale:    1.0,
  fontFamily:   "'Segoe UI', system-ui, sans-serif",
  textColor:    '#e2e8f0',
  sidebarBg:    '#151521',
  mainBg:       '#f4f6fb',
  analysisMode: 'both',
};

// ── Helpers localStorage ──────────────────────────────────────────────────────

function loadSettings(): DisplaySettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DISPLAY_DEFAULTS };
    const parsed = JSON.parse(raw) as Partial<DisplaySettings>;
    // Merge avec les defaults pour résister aux nouvelles clés ajoutées en v future
    return { ...DISPLAY_DEFAULTS, ...parsed };
  } catch {
    return { ...DISPLAY_DEFAULTS };
  }
}

function saveSettings(s: DisplaySettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // Silencieux en cas d'erreur de stockage (mode privé, quota, etc.)
  }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useDisplaySettings() {
  const [settings, setSettings] = useState<DisplaySettings>(loadSettings);

  // Persistance automatique à chaque changement
  useEffect(() => {
    saveSettings(settings);
  }, [settings]);

  const updateSettings = useCallback((patch: Partial<DisplaySettings>) => {
    setSettings(prev => ({ ...prev, ...patch }));
  }, []);

  const resetSettings = useCallback(() => {
    setSettings({ ...DISPLAY_DEFAULTS });
  }, []);

  return { settings, updateSettings, resetSettings };
}
