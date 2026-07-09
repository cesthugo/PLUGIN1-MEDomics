// hooks/usePipelineSSE.ts — SSE stream of the STARHE analysis
//
// Consumes the SSE events of /starhe/analyze and dispatches:
//  - progress  → update of the detection label
//  - result    → final results (risk + detections_per_frame)
//  - error     → message d'erreur

import { useCallback, useRef, useState } from 'react';
import { streamAnalysis, type AnalyzeRequest } from '../api';
import type { Detection, AnalysisResult, LogLevel, SSEPayload } from '../types';
import { RISK_HIGH_FG, RISK_LOW_FG, WARN_FG, SUCCESS_FG, SBAR_MUTED } from '../colors';

export type AnalysisStatus = 'idle' | 'running' | 'done' | 'error';

export interface PipelineResult {
  detectionsPerFrame: Detection[][];
  result: AnalysisResult;
}

export interface PipelineSSEState {
  status:   AnalysisStatus;
  progress: string | null;   // texte de progression
  startAnalysis: (req: AnalyzeRequest) => void;
  cancelAnalysis: () => void;
  lastResult: PipelineResult | null;
}

export function usePipelineSSE(
  addLog: (msg: string, level: LogLevel) => void,
): PipelineSSEState {
  const [status,     setStatus]     = useState<AnalysisStatus>('idle');
  const [progress,   setProgress]   = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<PipelineResult | null>(null);

  const abortRef = useRef<(() => void) | null>(null);

  const cancelAnalysis = useCallback(() => {
    abortRef.current?.();
    abortRef.current = null;
    setStatus('idle');
    setProgress(null);
  }, []);

  const startAnalysis = useCallback((req: AnalyzeRequest) => {
    if (abortRef.current) abortRef.current();

    setStatus('running');
    setLastResult(null);
    setProgress('Starting analysis…');
    addLog('Starting STARHE analysis (SSE stream)…', 'info');

    // What the user requested — used to filter the SSE events
    // (the backend may return RISK data even if it was not requested,
    //  e.g. a cached MongoDB result)
    const runRisk      = req.runRisk      ?? true;
    const runDetection = req.runDetection ?? true;

    let finalDetections: Detection[][] | null = null;
    let finalResult:     AnalysisResult  | null = null;
    // Business error emitted by Python (level "error") and reception of
    // the final "result" event — without this, onDone committed an
    // empty result with "done" status even when the pipeline had crashed.
    let pipelineError: string | null = null;
    let gotResult     = false;
    let committed     = false;

    // An analysis can finish as soon as the requested models have responded
    const isComplete = () =>
      (!runRisk      || finalResult?.riskText !== undefined && finalResult.riskText !== '…') &&
      (!runDetection || finalDetections !== null);

    const commitResult = () => {
      committed = true;
      setLastResult({
        detectionsPerFrame: finalDetections ?? [],
        result: finalResult ?? { riskText: '', riskFg: SBAR_MUTED, detText: '', detFg: SBAR_MUTED },
      });
      setStatus('done');
      setProgress(null);
    };

    const onEvent = (payload: SSEPayload) => {
      const msg = payload.message ?? '';
      const lvl = (payload.level ?? 'info') as string;
      const logLvl = (['info','success','warning','error'] as const).includes(lvl as LogLevel)
        ? (lvl as LogLevel) : 'info';

      addLog(msg, logLvl);

      if (lvl === 'progress' || lvl === 'info') {
        setProgress(msg);
      }

      if (lvl === 'error') {
        pipelineError = msg || 'Erreur pipeline (voir logs serveur)';
      }
      if (lvl === 'result') {
        gotResult = true;
      }

      // Risk extraction — ignored if the mode does not include it
      if (runRisk && payload.data?.risk) {
        const risk = payload.data.risk;
        const score = (risk.score ?? risk.risk_score ?? 0) as number;
        const label = (risk.label ?? risk.risk_label ?? '—') as string;
        const riskFg  = /élevé|high/i.test(label) ? RISK_HIGH_FG : RISK_LOW_FG;
        const riskText = `${label}  (${(score * 100).toFixed(1)} %)`;
        if (!finalResult) finalResult = { riskText, riskFg, detText: '…', detFg: SBAR_MUTED };
        else finalResult = { ...finalResult, riskText, riskFg };
      }

      // Final detection extraction — ignored if the mode does not include it
      if (runDetection && payload.data?.detections_per_frame) {
        finalDetections = payload.data.detections_per_frame as Detection[][];
        const nDet = finalDetections.filter(d => d.length > 0).length;
        const total = finalDetections.length;
        const detFg  = nDet > 0 ? WARN_FG : SUCCESS_FG;
        const detText = `${nDet}/${total} frame(s) with lesion(s)`;
        finalResult = finalResult
          ? { ...finalResult, detText, detFg }
          : { riskText: '', riskFg: SBAR_MUTED, detText, detFg };
      }

      if ((lvl as string) === 'result' && isComplete()) {
        commitResult();
      }
    };

    const onDone = () => {
      // Python business error (level "error") or stream ended without any
      // "result" event → error status, without committing a false result.
      if (pipelineError || !gotResult) {
        const msg = pipelineError ?? 'Pipeline terminé sans résultat (crash Python ?)';
        addLog(`Erreur analyse : ${msg}`, 'error');
        setStatus('error');
        setProgress(null);
        return;
      }
      if (!committed) commitResult();
      addLog('Analysis complete.', 'success');
    };

    const onError = (err: Error) => {
      addLog(`Erreur analyse : ${err.message}`, 'error');
      setStatus('error');
      setProgress(null);
    };

    abortRef.current = streamAnalysis(req, onEvent, onDone, onError);
  }, [addLog]);

  return { status, progress, startAnalysis, cancelAnalysis, lastResult };
}
