// components/PatientTabBar.tsx — Patient bar (patient tabs)
import { PTAB_BG, PTAB_ACT_BG, BLUE } from '../../utilities/starhe/colors';
import type { Patient } from '../../utilities/starhe/types';

export function PatientTabBar({
  patients,
  activePatientIdx,
  onSwitchPatient,
}: {
  patients:         Patient[];
  activePatientIdx: number;
  onSwitchPatient:  (idx: number) => void;
}) {
  if (!patients.length) return null;
  return (
    <div
      style={{
        background: PTAB_BG, height: 30, minHeight: 30,
        display: 'flex', alignItems: 'stretch', overflowX: 'auto',
        flexShrink: 0,
      }}
    >
      {patients.map((p, idx) => (
        <PatientTab
          key={p.name}
          name={p.name}
          active={idx === activePatientIdx}
          onClick={() => onSwitchPatient(idx)}
        />
      ))}
    </div>
  );
}

function PatientTab({
  name, active, onClick,
}: {
  name: string; active: boolean; onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        cursor: 'pointer',
        background: active ? PTAB_ACT_BG : PTAB_BG,
        color: active ? '#e5e7eb' : '#6b7280',
        fontSize: 11, fontWeight: 700,
        padding: '0 12px',
        display: 'flex', alignItems: 'center',
        borderBottom: active ? `2px solid ${BLUE}` : '2px solid transparent',
        whiteSpace: 'nowrap', userSelect: 'none',
      }}
    >
      {name}
    </div>
  );
}
