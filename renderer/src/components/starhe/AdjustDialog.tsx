// components/AdjustDialog.tsx — Floating contrast / brightness window
//
// Replicates _AdjustDialog from prototype_tkinter.py.

import React, { useEffect, useRef, useState } from 'react';
import { SIDEBAR_BG, SBAR_FG, SBAR_MUTED, BLUE } from '../../utilities/starhe/colors';

export interface AdjustDialogProps {
  title:    string;
  initial:  number;
  min:      number;
  max:      number;
  neutral:  number;
  onClose:  () => void;
  onChange: (v: number) => void;
}

export function AdjustDialog({
  title, initial, min, max, neutral, onClose, onChange,
}: AdjustDialogProps) {
  const [value, setValue] = useState(initial);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Draggable position (simple — centered on open)
  const [pos, setPos] = useState({ x: window.innerWidth / 2 - 140, y: window.innerHeight / 2 - 100 });
  const dragStartRef = useRef<{ mx: number; my: number; px: number; py: number } | null>(null);

  const onMouseDownHeader = (e: React.MouseEvent) => {
    dragStartRef.current = { mx: e.clientX, my: e.clientY, px: pos.x, py: pos.y };
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragStartRef.current) return;
      const d = dragStartRef.current;
      setPos({ x: d.px + e.clientX - d.mx, y: d.py + e.clientY - d.my });
    };
    const onUp = () => { dragStartRef.current = null; };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, []);

  // Close on Esc
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleChange = (v: number) => {
    setValue(v);
    onChange(v);
  };

  return (
    <div
      ref={dialogRef}
      style={{
        position: 'fixed',
        left: pos.x, top: pos.y,
        width: 280, background: SIDEBAR_BG,
        border: '1px solid #2a2a4e',
        borderRadius: 6, zIndex: 9999,
        boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        userSelect: 'none',
      }}
    >
      {/* En-tête draggable */}
      <div
        onMouseDown={onMouseDownHeader}
        style={{
          padding: '10px 14px 6px',
          cursor: 'move',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}
      >
        <span style={{ color: SBAR_FG, fontWeight: 700, fontSize: 13 }}>{title}</span>
        <button
          onClick={onClose}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: SBAR_MUTED, fontSize: 16, lineHeight: 1,
          }}
        >×</button>
      </div>

      {/* Valeur courante */}
      <div style={{ textAlign: 'center', color: SBAR_FG, fontSize: 13, fontFamily: "'Consolas', monospace" }}>
        {value.toFixed(2)}
      </div>

      {/* Slider */}
      <div style={{ padding: '4px 20px 8px' }}>
        <input
          type="range"
          min={min}
          max={max}
          step={(max - min) / 200}
          value={value}
          style={{ width: '100%', accentColor: BLUE }}
          onChange={e => handleChange(Number(e.target.value))}
        />
      </div>

      {/* Réinitialiser */}
      <div style={{ padding: '0 20px 14px' }}>
        <button
          onClick={() => handleChange(neutral)}
          style={{
            width: '100%', background: '#000', color: '#fff',
            border: 'none', cursor: 'pointer',
            padding: '5px 0', fontSize: 11, fontWeight: 700,
            borderRadius: 3,
          }}
        >
          Reset
        </button>
      </div>
    </div>
  );
}
