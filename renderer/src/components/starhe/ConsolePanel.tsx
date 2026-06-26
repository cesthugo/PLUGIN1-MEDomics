// components/ConsolePanel.tsx — Console de log style MEDomics (réplique Tkinter)

import React, { useEffect, useRef } from 'react';
import type { LogEntry } from '../../utilities/starhe/types';
import { LOG_BG, SUCCESS_FG, WARN_FG, DANGER_FG, BLUE_TEXT } from '../../utilities/starhe/colors';

const LEVEL_COLOR: Record<string, string> = {
  info:    '#8892a4',
  success: SUCCESS_FG,
  warning: WARN_FG,
  error:   DANGER_FG,
};

const LEVEL_PREFIX: Record<string, string> = {
  info:    'ℹ',
  success: '✓',
  warning: '⚠',
  error:   '✗',
};

export interface ConsolePanelProps {
  entries: LogEntry[];
  darkMode: boolean;
}

export function ConsolePanel({ entries, darkMode }: ConsolePanelProps) {
  const bottomRef  = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [entries]);

  return (
    <div style={{ background: darkMode ? '#0d1117' : '#f4f6fb', padding: '0 14px 10px' }}>
      <div
        style={{
          fontSize: 12, fontWeight: 700,
          color: BLUE_TEXT,
          padding: '4px 0',
          fontFamily: "'Segoe UI', system-ui, sans-serif",
        }}
      >
        Console
      </div>
      <div
        style={{
          background: LOG_BG,
          borderRadius: 4,
          height: 140,
          overflowY: 'auto',
          padding: '4px 0',
          fontFamily: "'Consolas', monospace",
          fontSize: 11,
        }}
      >
        {entries.map(e => (
          <div
            key={e.id}
            style={{ padding: '1px 8px', color: LEVEL_COLOR[e.level] ?? '#8892a4' }}
          >
            {LEVEL_PREFIX[e.level] ?? '·'}{'  '}{e.message}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
