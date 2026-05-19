// hooks/useTabManager.ts — Gestion des onglets et des patients
//
// Centralise tout l'état lié aux onglets (TabState[]) et aux patients (Patient[]).
// Extrait de index.tsx pour alléger le composant racine.
//
// Responsabilités :
//  - État : tabs, activeTabId, patients, activePatientName
//  - Références synchrones (useRef) pour les lectures dans les callbacks
//  - Valeurs dérivées : activeTab, activeTabIdx, activePatientIdx
//  - Actions : addTab, openBatchResultAsTab, switchTab, closeTab, updateActiveTab

import { useCallback, useRef, useState } from 'react';
import { loadDicom, loadDicomFile, makeTabLabel } from '../api';
import type { TabState, Patient, DicomData, LogLevel } from '../types';
import type { BatchResultToOpen } from '../components/BatchModal';
import { nextTabId } from '../utils';

// ── Valeur initiale d'un onglet ───────────────────────────────────────────────
function makeDefaultTab(): TabState {
  return {
    id:              nextTabId(),
    label:           '—',
    patientName:     'Patient inconnu',
    dicomPath:       '',
    data:            null,
    frameIdx:        0,
    detectionsBy:    {},
    resultsBy:       {},
    measuresByFrame: {},
    selectedMeasure: null,
    zoom:            1,
    panX:            0,
    panY:            0,
    contrast:        1,
    brightness:      0,
    viewMode:        'normal',
    speedMult:       1,
    loop:            true,
  };
}

// ── Interface publique du hook ─────────────────────────────────────────────────

export interface TabManagerParams {
  addLog:       (msg: string, level: LogLevel) => void;
  isPlaying:    boolean;
  setIsPlaying: (v: boolean) => void;
}

export interface TabManagerResult {
  // État
  tabs:              TabState[];
  activeTabId:       number;
  patients:          Patient[];
  activePatientName: string;
  // Valeurs dérivées
  activeTab:         TabState | null;
  activeTabIdx:      number;
  activePatientIdx:  number;
  // Actions
  addTab:               (displayName: string, dicomPath: string, data: DicomData) => void;
  openBatchResultAsTab: (result: BatchResultToOpen) => Promise<number>;
  switchTab:            (tabId: number) => void;
  closeTab:             (tabId: number) => void;
  updateActiveTab:      (updater: (t: TabState) => TabState) => void;
  updateTabById:        (tabId: number, updater: (t: TabState) => TabState) => void;
  // Setters exposés pour les cas d'usage directs (focus panneau, etc.)
  setActiveTabId:       React.Dispatch<React.SetStateAction<number>>;
  setActivePatientName: React.Dispatch<React.SetStateAction<string>>;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useTabManager({
  addLog, isPlaying, setIsPlaying,
}: TabManagerParams): TabManagerResult {

  const [tabs,              setTabs]             = useState<TabState[]>([]);
  const [activeTabId,       setActiveTabId]      = useState<number>(-1);
  const [patients,          setPatients]         = useState<Patient[]>([]);
  const [activePatientName, setActivePatientName] = useState<string>('');

  // Références synchrones pour les lectures dans les callbacks
  // (évite les closures périmées en React StrictMode ou en React batching)
  const tabsRef     = useRef<TabState[]>(tabs);
  tabsRef.current   = tabs;
  const patientsRef = useRef<Patient[]>(patients);
  patientsRef.current = patients;

  // Valeurs dérivées — recalculées à chaque render
  const activeTabIdx    = tabs.findIndex(t => t.id === activeTabId);
  const activeTab       = activeTabIdx >= 0 ? tabs[activeTabIdx] : null;
  const activePatientIdx = patients.findIndex(p => p.name === activePatientName);

  // ── Helpers internes ────────────────────────────────────────────────────────

  /** Ajoute ou met à jour un patient dans la liste */
  const upsertPatient = (
    prev:    Patient[],
    patName: string,
    tabId:   number,
  ): Patient[] => {
    const existIdx = prev.findIndex(p => p.name === patName);
    if (existIdx >= 0) {
      const updated = [...prev];
      updated[existIdx] = { ...updated[existIdx], tabIds: [...updated[existIdx].tabIds, tabId] };
      return updated;
    }
    return [...prev, { name: patName, tabIds: [tabId] }];
  };

  // ── Actions ────────────────────────────────────────────────────────────────

  /** Ajoute un onglet après un chargement DICOM réussi */
  const addTab = useCallback((
    displayName: string,
    dicomPath:   string,
    data:        DicomData,
  ) => {
    const label  = makeTabLabel(data.studyDate, data.fileName);
    const newTab: TabState = { ...makeDefaultTab(), label, patientName: data.patientName, dicomPath, data };
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(newTab.id);
    setPatients(prev => upsertPatient(prev, data.patientName, newTab.id));
    setActivePatientName(data.patientName);
    addLog(`DICOM chargé — ${data.frameCount} frame(s), ${data.rows}×${data.cols} px.`, 'success');
  }, [addLog]);

  /** Charge un DICOM depuis un résultat batch et retourne l'ID du nouvel onglet */
  const openBatchResultAsTab = useCallback(async (result: BatchResultToOpen): Promise<number> => {
    addLog(`Chargement : ${result.name}`, 'info');
    let data: Awaited<ReturnType<typeof loadDicom>>;
    try {
      data = await loadDicom(result.serverPath);
    } catch (err) {
      // Temp file expiré — on re-uploade le fichier original si disponible
      const msg = err instanceof Error ? err.message : String(err);
      if (result.file && /introuvable|not found|no such file/i.test(msg)) {
        addLog(`Fichier temporaire expiré — re-upload de ${result.name}…`, 'info');
        data = await loadDicomFile(result.file);
      } else {
        throw err;
      }
    }
    const label = makeTabLabel(data.studyDate, data.fileName);
    const newTab: TabState = {
      ...makeDefaultTab(),
      label,
      patientName: data.patientName,
      dicomPath:   result.serverPath,
      data,
      detectionsBy: result.detections?.length ? { original: result.detections } : {},
      resultsBy: result.risk ? {
        original: {
          riskText: `${result.risk.label} (${(result.risk.score * 100).toFixed(1)} %)`,
          riskFg:   /élevé|high/i.test(result.risk.label) ? '#f87171' : '#4ade80',
          detText:  `${result.detections?.reduce((a, fd) => a + fd.length, 0) ?? 0} lésion(s)`,
          detFg:    '#facc15',
        },
      } : {},
    };
    setTabs(prev => [...prev, newTab]);
    setPatients(prev => upsertPatient(prev, data.patientName, newTab.id));
    setActivePatientName(data.patientName);
    addLog(`DICOM chargé avec résultats — ${data.frameCount} frame(s).`, 'success');
    return newTab.id;
    // Note : setActiveTabId est intentionnellement absent ici.
    // Le caller est responsable d'activer l'onglet (cas batch multi ou unique).
  }, [addLog]);

  /** Bascule vers un onglet existant */
  const switchTab = useCallback((tabId: number) => {
    if (!tabsRef.current.some(t => t.id === tabId)) return;
    if (isPlaying) setIsPlaying(false);
    setActiveTabId(tabId);
    const patient = patientsRef.current.find(p => p.tabIds.includes(tabId));
    if (patient) setActivePatientName(patient.name);
  }, [isPlaying, setIsPlaying]);

  /** Ferme un onglet et sélectionne l'onglet voisin */
  const closeTab = useCallback((tabId: number) => {
    const currentTabs = tabsRef.current;
    if (currentTabs.length <= 1) {
      setTabs([]);
      setActiveTabId(-1);
      setPatients([]);
      setActivePatientName('');
      setIsPlaying(false);
      return;
    }
    const idx         = currentTabs.findIndex(t => t.id === tabId);
    const next        = currentTabs.filter(t => t.id !== tabId);
    const newActiveTab = next[Math.max(0, Math.min(idx, next.length - 1))];
    setTabs(next);
    setActiveTabId(newActiveTab?.id ?? -1);
    const updatedPatients = patientsRef.current
      .map(p => ({ ...p, tabIds: p.tabIds.filter(id => id !== tabId) }))
      .filter(p => p.tabIds.length > 0);
    setPatients(updatedPatients);
    const newPatient = updatedPatients.find(p => p.tabIds.includes(newActiveTab?.id ?? -1));
    if (newPatient) setActivePatientName(newPatient.name);
  }, [setIsPlaying]);

  /** Met à jour l'onglet actif via un updater fonctionnel */
  const updateActiveTab = useCallback((updater: (t: TabState) => TabState) => {
    setTabs(prev => prev.map(t => t.id === activeTabId ? updater(t) : t));
  }, [activeTabId]);

  /** Met à jour un onglet quelconque par son ID (ex. injection résultat d'analyse) */
  const updateTabById = useCallback((tabId: number, updater: (t: TabState) => TabState) => {
    setTabs(prev => prev.map(t => t.id === tabId ? updater(t) : t));
  }, []);

  return {
    tabs, activeTabId, patients, activePatientName,
    activeTab, activeTabIdx, activePatientIdx,
    addTab, openBatchResultAsTab,
    switchTab, closeTab, updateActiveTab, updateTabById,
    setActiveTabId, setActivePatientName,
  };
}
