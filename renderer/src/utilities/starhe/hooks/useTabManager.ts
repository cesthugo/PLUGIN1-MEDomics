// hooks/useTabManager.ts — Tab and patient management
//
// Centralizes all the state related to tabs (TabState[]) and patients (Patient[]).
// Extracted from index.tsx to lighten the root component.
//
// Responsibilities:
//  - État : tabs, activeTabId, patients, activePatientName
//  - Synchronous references (useRef) for reads inside the callbacks
//  - Derived values: activeTab, activeTabIdx, activePatientIdx
//  - Actions : addTab, openBatchResultAsTab, switchTab, closeTab, updateActiveTab

import { useCallback, useRef, useState } from 'react';
import { loadDicom, loadDicomFile, loadMp4, loadMp4File, makeTabLabel } from '../api';
import type { TabState, Patient, DicomData, LogLevel } from '../types';
import type { BatchResultToOpen } from '../../../components/starhe/BatchModal';
import { nextTabId } from '../utils';

// ── Initial value of a tab ────────────────────────────────────────────────────
function makeDefaultTab(): TabState {
  return {
    id:              nextTabId(),
    label:           '—',
    patientName:     'Unknown patient',
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

// ── Public hook interface ──────────────────────────────────────────────────────

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
  // Derived values
  activeTab:         TabState | null;
  activeTabIdx:      number;
  activePatientIdx:  number;
  // Actions
  addTab:               (displayName: string, dicomPath: string, data: DicomData) => void;
  addMp4Tab:            (displayName: string, serverPath: string, data: DicomData) => void;
  openBatchResultAsTab: (result: BatchResultToOpen) => Promise<number>;
  switchTab:            (tabId: number) => void;
  closeTab:             (tabId: number) => void;
  updateActiveTab:      (updater: (t: TabState) => TabState) => void;
  updateTabById:        (tabId: number, updater: (t: TabState) => TabState) => void;
  // Setters exposed for direct use cases (panel focus, etc.)
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

  // Synchronous references for reads inside the callbacks
  // (avoids stale closures in React StrictMode or React batching)
  const tabsRef     = useRef<TabState[]>(tabs);
  tabsRef.current   = tabs;
  const patientsRef = useRef<Patient[]>(patients);
  patientsRef.current = patients;

  // Derived values — recomputed on each render
  const activeTabIdx    = tabs.findIndex(t => t.id === activeTabId);
  const activeTab       = activeTabIdx >= 0 ? tabs[activeTabIdx] : null;
  const activePatientIdx = patients.findIndex(p => p.name === activePatientName);

  // ── Helpers internes ────────────────────────────────────────────────────────

  /** Adds or updates a patient in the list */
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

  /** Adds a tab after a successful DICOM load */
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
    addLog(`DICOM loaded — ${data.frameCount} frame(s), ${data.rows}×${data.cols} px.`, 'success');
  }, [addLog]);

  const addMp4Tab = useCallback((
    displayName: string,
    serverPath:  string,
    data:        DicomData,
  ) => {
    const label = displayName.replace(/\.[^.]+$/, '').slice(0, 20);
    const newTab: TabState = { ...makeDefaultTab(), label, patientName: 'MP4 Video', dicomPath: serverPath, isMp4: true, data };
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(newTab.id);
    setPatients(prev => upsertPatient(prev, 'MP4 Video', newTab.id));
    setActivePatientName('MP4 Video');
    addLog(`MP4 loaded — ${data.frameCount} frame(s), ${data.rows}×${data.cols} px.`, 'success');
  }, [addLog]);

  /** Loads a file (DICOM or MP4) from a batch result and returns the new tab's ID */
  const openBatchResultAsTab = useCallback(async (result: BatchResultToOpen): Promise<number> => {
    addLog(`Loading: ${result.name}`, 'info');

    if (result.isMp4) {
      // ── Cas MP4 ────────────────────────────────────────────────────────────
      let data: Awaited<ReturnType<typeof loadMp4>>;
      try {
        data = await loadMp4(result.serverPath);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (result.file && /introuvable|not found|no such file/i.test(msg)) {
          addLog(`MP4 temporary file expired — re-uploading ${result.name}…`, 'info');
          data = await loadMp4File(result.file);
        } else {
          throw err;
        }
      }
      const label = result.name.replace(/\.mp4$/i, '').slice(0, 20);
      const newTab: TabState = {
        ...makeDefaultTab(),
        label,
        patientName: 'MP4 Video',
        dicomPath:   result.serverPath,
        isMp4:       true,
        data,
        detectionsBy: result.detections?.length ? { original: result.detections } : {},
        resultsBy: result.risk ? {
          original: {
            riskText: `${result.risk.label} (${(result.risk.score * 100).toFixed(1)} %)`,
            riskFg:   /élevé|high/i.test(result.risk.label) ? '#f87171' : '#4ade80',
            detText:  `${result.detections?.reduce((a, fd) => a + fd.length, 0) ?? 0} lesion(s)`,
            detFg:    '#facc15',
          },
        } : {},
      };
      setTabs(prev => [...prev, newTab]);
      setPatients(prev => upsertPatient(prev, 'MP4 Video', newTab.id));
      setActivePatientName('MP4 Video');
      addLog(`MP4 loaded with results — ${data.frameCount} frame(s).`, 'success');
      return newTab.id;
    }

    // ── Cas DICOM ─────────────────────────────────────────────────────────────
    let data: Awaited<ReturnType<typeof loadDicom>>;
    try {
      data = await loadDicom(result.serverPath);
    } catch (err) {
      // Temp file expired — re-upload the original file if available
      const msg = err instanceof Error ? err.message : String(err);
      if (result.file && /introuvable|not found|no such file/i.test(msg)) {
        addLog(`Temporary file expired — re-uploading ${result.name}…`, 'info');
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
          detText:  `${result.detections?.reduce((a, fd) => a + fd.length, 0) ?? 0} lesion(s)`,
          detFg:    '#facc15',
        },
      } : {},
    };
    setTabs(prev => [...prev, newTab]);
    setPatients(prev => upsertPatient(prev, data.patientName, newTab.id));
    setActivePatientName(data.patientName);
    addLog(`DICOM loaded with results — ${data.frameCount} frame(s).`, 'success');
    return newTab.id;
    // Note: setActiveTabId is intentionally absent here.
    // The caller is responsible for activating the tab (multi or single batch case).
  }, [addLog]);

  /** Switches to an existing tab */
  const switchTab = useCallback((tabId: number) => {
    if (!tabsRef.current.some(t => t.id === tabId)) return;
    if (isPlaying) setIsPlaying(false);
    setActiveTabId(tabId);
    const patient = patientsRef.current.find(p => p.tabIds.includes(tabId));
    if (patient) setActivePatientName(patient.name);
  }, [isPlaying, setIsPlaying]);

  /** Closes a tab and selects the neighboring tab */
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

  /** Updates the active tab via a functional updater */
  const updateActiveTab = useCallback((updater: (t: TabState) => TabState) => {
    setTabs(prev => prev.map(t => t.id === activeTabId ? updater(t) : t));
  }, [activeTabId]);

  /** Updates any tab by its ID (e.g. injecting an analysis result) */
  const updateTabById = useCallback((tabId: number, updater: (t: TabState) => TabState) => {
    setTabs(prev => prev.map(t => t.id === tabId ? updater(t) : t));
  }, []);

  return {
    tabs, activeTabId, patients, activePatientName,
    activeTab, activeTabIdx, activePatientIdx,
    addTab, addMp4Tab, openBatchResultAsTab,
    switchTab, closeTab, updateActiveTab, updateTabById,
    setActiveTabId, setActivePatientName,
  };
}
