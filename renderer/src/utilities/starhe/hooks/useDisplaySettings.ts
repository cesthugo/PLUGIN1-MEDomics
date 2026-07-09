// hooks/useDisplaySettings.ts — Persistent display settings (localStorage)

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'starhe_display_settings';

// ── Settings interface ────────────────────────────────────────────────────────

export interface DisplaySettings {
  /** Text magnification factor (0.8 – 1.6). Applied via proportional CSS injection. */
  fontScale:  number;
  /** CSS font (full CSS value, e.g. "'Segoe UI', system-ui, sans-serif"). */
  fontFamily: string;
  /** Main text color (hex). */
  textColor:  string;
  /** Side panel background color (hex). */
  sidebarBg:  string;
  /** Main area background color (hex). */
  mainBg:     string;
  /** AI models to run when clicking "Lancer l'analyse". */
  analysisMode: 'both' | 'risk_only' | 'detect_only';
  /** Show or hide the log console at the bottom of the interface. */
  showConsole: boolean;
}

// ── Default values (identical to the current theme) ───────────────────────────

export const DISPLAY_DEFAULTS: DisplaySettings = {
  fontScale:    1.0,
  fontFamily:   "'Segoe UI', system-ui, sans-serif",
  textColor:    '#e2e8f0',
  sidebarBg:    '#151521',
  mainBg:       '#f4f6fb',
  analysisMode: 'both',
  showConsole:  false,
};

// ── Helpers localStorage ──────────────────────────────────────────────────────

function loadSettings(): DisplaySettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DISPLAY_DEFAULTS };
    const parsed = JSON.parse(raw) as Partial<DisplaySettings>;
    // Merge with the defaults to tolerate new keys added in a future version
    return { ...DISPLAY_DEFAULTS, ...parsed };
  } catch {
    return { ...DISPLAY_DEFAULTS };
  }
}

function saveSettings(s: DisplaySettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // Silent on a storage error (private mode, quota, etc.)
  }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useDisplaySettings() {
  const [settings, setSettings] = useState<DisplaySettings>(loadSettings);

  // Automatic persistence on every change
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
