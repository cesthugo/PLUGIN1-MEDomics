// components/SettingsPanel.tsx — Panneau flottant de réglages d'affichage
//
// Apparaît en haut à droite quand l'utilisateur clique sur "⚙ Réglages".
// Toutes les modifications sont appliquées en temps réel et persistées via le hook.

import React, { useEffect, useRef } from 'react';
import type { DisplaySettings } from '../hooks/useDisplaySettings';
import { DISPLAY_DEFAULTS } from '../hooks/useDisplaySettings';
import { SIDEBAR_BG, SBAR_FG, SBAR_MUTED } from '../colors';

// ── Options de polices proposées ──────────────────────────────────────────────

const FONT_OPTIONS: { label: string; value: string }[] = [
  { label: 'Segoe UI (défaut)',  value: "'Segoe UI', system-ui, sans-serif" },
  { label: 'Arial',              value: 'Arial, sans-serif' },
  { label: 'Georgia',            value: 'Georgia, serif' },
  { label: 'Courier New',        value: "'Courier New', monospace" },
  { label: 'Inter',              value: 'Inter, sans-serif' },
  { label: 'Roboto',             value: 'Roboto, sans-serif' },
];

// ── Props ─────────────────────────────────────────────────────────────────────

interface SettingsPanelProps {
  settings:  DisplaySettings;
  onUpdate:  (patch: Partial<DisplaySettings>) => void;
  onReset:   () => void;
  onClose:   () => void;
}

// ── Composant ─────────────────────────────────────────────────────────────────

export function SettingsPanel({ settings, onUpdate, onReset, onClose }: SettingsPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Fermeture au clic extérieur
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // Délai léger pour éviter que le clic d'ouverture ferme immédiatement le panneau
    const id = setTimeout(() => document.addEventListener('mousedown', handler), 50);
    return () => {
      clearTimeout(id);
      document.removeEventListener('mousedown', handler);
    };
  }, [onClose]);

  // Fermeture à la touche Échap
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-label="Réglages d'affichage"
      style={{
        position:     'fixed',
        top:          54,
        right:        16,
        width:        310,
        background:   '#1e1d2f',
        border:       '1px solid #2a3245',
        borderRadius: 8,
        boxShadow:    '0 8px 32px rgba(0,0,0,0.65)',
        zIndex:       2000,
        overflow:     'hidden',
        // Le panneau lui-même utilise les settings courants pour la prévisualisation
        fontFamily:   settings.fontFamily,
      }}
    >
      {/* ── En-tête ─────────────────────────────────────────────────────── */}
      <div
        style={{
          background: SIDEBAR_BG,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 14px',
          borderBottom: '1px solid #2a3245',
        }}
      >
        <span style={{ color: SBAR_FG, fontSize: 13, fontWeight: 700 }}>
          ⚙&nbsp; Réglages d'affichage
        </span>
        <button
          onClick={onClose}
          title="Fermer (Échap)"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: SBAR_MUTED, fontSize: 20, lineHeight: 1, padding: '0 4px',
          }}
        >
          ×
        </button>
      </div>

      {/* ── Corps ───────────────────────────────────────────────────────── */}
      <div
        style={{
          padding: '14px 16px',
          display: 'flex', flexDirection: 'column', gap: 18,
        }}
      >
        {/* Agrandissement du texte */}
        <SettingRow label="Taille du texte">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: SBAR_MUTED, fontSize: 11 }}>A</span>
            <input
              type="range"
              min={0.8} max={1.6} step={0.05}
              value={settings.fontScale}
              onChange={e => onUpdate({ fontScale: parseFloat(e.target.value) })}
              style={{ flex: 1, accentColor: '#1565C0' }}
            />
            <span style={{ color: SBAR_MUTED, fontSize: 14, fontWeight: 700 }}>A</span>
            <input
              type="number"
              min={80} max={160} step={5}
              value={Math.round(settings.fontScale * 100)}
              onChange={e => {
                const v = parseInt(e.target.value, 10);
                if (!isNaN(v) && v >= 80 && v <= 160) {
                  onUpdate({ fontScale: v / 100 });
                }
              }}
              style={{
                width: 52, background: '#111827', color: SBAR_FG,
                border: '1px solid #2a3245', borderRadius: 4,
                padding: '4px 6px', fontSize: 12,
                fontFamily: "'Consolas', monospace",
                textAlign: 'right',
              }}
            />
            <span style={{ color: SBAR_MUTED, fontSize: 11 }}>%</span>
          </div>
        </SettingRow>

        {/* Police du texte */}
        <SettingRow label="Police du texte">
          <select
            value={settings.fontFamily}
            onChange={e => onUpdate({ fontFamily: e.target.value })}
            style={{
              width: '100%',
              background: '#111827', color: SBAR_FG,
              border: '1px solid #2a3245', borderRadius: 4,
              padding: '6px 8px', fontSize: 12,
              fontFamily: settings.fontFamily,
              cursor: 'pointer',
            }}
          >
            {FONT_OPTIONS.map(f => (
              <option key={f.value} value={f.value} style={{ fontFamily: f.value }}>
                {f.label}
              </option>
            ))}
          </select>
        </SettingRow>

        {/* Couleur du texte */}
        <SettingRow label="Couleur du texte">
          <ColorRow
            value={settings.textColor}
            defaultValue={DISPLAY_DEFAULTS.textColor}
            onChange={v => onUpdate({ textColor: v })}
          />
          {settings.textColor !== DISPLAY_DEFAULTS.textColor && (
            <p style={{ color: SBAR_MUTED, fontSize: 10, margin: '5px 0 0', lineHeight: 1.4 }}>
              ⚠️ Remplace toutes les couleurs de texte, y compris les indicateurs (risque, erreurs).
            </p>
          )}
        </SettingRow>

        {/* Couleur panneau latéral */}
        <SettingRow label="Couleur panneau latéral">
          <ColorRow
            value={settings.sidebarBg}
            defaultValue={DISPLAY_DEFAULTS.sidebarBg}
            onChange={v => onUpdate({ sidebarBg: v })}
          />
        </SettingRow>

        {/* Couleur zone principale */}
        <SettingRow label="Couleur zone principale">
          <ColorRow
            value={settings.mainBg}
            defaultValue={DISPLAY_DEFAULTS.mainBg}
            onChange={v => onUpdate({ mainBg: v })}
          />
        </SettingRow>

        {/* ───────────────────────────────────────────────────── */}
        <div style={{ borderTop: '1px solid #2a3245', margin: '4px 0' }} />
        {/* Affichage de la console */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={settings.showConsole}
            onChange={e => onUpdate({ showConsole: e.target.checked })}
            style={{ accentColor: '#1565C0', width: 14, height: 14, flexShrink: 0 }}
          />
          <div>
            <div style={{ color: SBAR_FG, fontSize: 12, fontWeight: 700 }}>Afficher la console</div>
            <div style={{ color: SBAR_MUTED, fontSize: 10, marginTop: 1 }}>Journal des événements en bas de l'interface</div>
          </div>
        </label>

        {/* Bouton réinitialiser */}
        <button
          onClick={onReset}
          style={{
            background: '#0d1117', color: '#9ca3af',
            border: '1px solid #2a3245', borderRadius: 4,
            padding: '7px 12px', cursor: 'pointer',
            fontSize: 12, fontWeight: 600,
            transition: 'background 0.1s',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = '#1a1a2e'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '#0d1117'; }}
        >
          ↺&nbsp; Réinitialiser les réglages
        </button>
      </div>
    </div>
  );
}

// ── Sous-composants ───────────────────────────────────────────────────────────

function SettingRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label
        style={{
          color: SBAR_MUTED, fontSize: 10, fontWeight: 700,
          display: 'block', marginBottom: 7,
          textTransform: 'uppercase', letterSpacing: '0.07em',
        }}
      >
        {label}
      </label>
      {children}
    </div>
  );
}

function ColorRow({
  value, defaultValue, onChange,
}: { value: string; defaultValue: string; onChange: (v: string) => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <input
        type="color"
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          width: 36, height: 30,
          border: '1px solid #2a3245', borderRadius: 4,
          cursor: 'pointer', padding: 2, background: '#111827',
        }}
      />
      {/* Prévisualisation de la couleur */}
      <div
        style={{
          width: 30, height: 20, borderRadius: 3,
          background: value,
          border: '1px solid #2a3245',
          flexShrink: 0,
        }}
      />
      <span
        style={{
          color: SBAR_FG, fontSize: 12,
          fontFamily: "'Consolas', monospace",
          flex: 1,
        }}
      >
        {value}
      </span>
      {/* Bouton retour à la valeur par défaut */}
      {value !== defaultValue && (
        <button
          onClick={() => onChange(defaultValue)}
          title="Valeur par défaut"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: SBAR_MUTED, fontSize: 14, padding: '0 2px',
          }}
        >
          ↺
        </button>
      )}
    </div>
  );
}
