// health.go — Health check of the plugin's dependencies
//
// At startup, the server logs the resolved paths (PythonExe, WeightsDir),
// checks for the presence of the .pth checkpoints and tests in the background
// that the venv's critical Python modules are importable.
//
// GET /health reflects the actual state:
//
//	{"status":"ok"}
//	{"status":"degraded","missing":["best_acc_...pth"],"python_error":"ModuleNotFoundError: ..."}
//
// This lets the UI warn the user BEFORE launching an analysis doomed to
// fail (missing weights, incomplete venv).
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// requiredWeights — checkpoints required by both STARHE models.
var requiredWeights = []string{
	"best_acc_mean_cls_f1_epoch_14.pth",   // STARHE-RISK (C3D / mmaction2)
	"best_coco_bbox_mAP_50_iter_2100.pth", // STARHE-DETECT (RTMDet)
}

// criticalImports — Python modules without which the pipeline cannot run.
// Reproduces the pipeline's actual imports (including the exact C3D import
// used by _c3d_runner.py, which validates mmaction2 + its venv patches).
const criticalImports = "import numpy, pydicom, torch, mmengine, prepUS; " +
	"from mmaction.models.backbones.c3d import C3D"

type healthState struct {
	mu        sync.Mutex
	pythonOK  bool
	pythonErr string
	checked   bool // true once the Python check has completed
}

var health healthState

// missingWeights returns the checkpoints missing from WeightsDir.
// Recomputed on every call (a simple stat): weights downloaded mid-session
// flip /health back to "ok" without a restart.
func missingWeights() []string {
	missing := []string{}
	for _, name := range requiredWeights {
		if _, err := os.Stat(filepath.Join(cfg.WeightsDir, name)); err != nil {
			missing = append(missing, name)
		}
	}
	return missing
}

// runStartupCheck logs the resolved configuration then runs the Python
// import check in the background (import torch = several seconds,
// don't block the HTTP server startup).
func runStartupCheck() {
	log.Printf("PythonExe  : %s", cfg.PythonExe)
	log.Printf("WeightsDir : %s", cfg.WeightsDir)
	if m := missingWeights(); len(m) > 0 {
		log.Printf("ATTENTION — checkpoints manquants : %v (lancez scripts/download_models.py)", m)
	} else {
		log.Printf("Checkpoints IA : OK (%d fichiers)", len(requiredWeights))
	}

	go func() {
		// PyInstaller bundle mode: dependencies are embedded, nothing to check.
		if cfg.WorkerBin != "" {
			health.mu.Lock()
			health.pythonOK, health.checked = true, true
			health.mu.Unlock()
			return
		}

		var errMsg string
		if _, err := os.Stat(cfg.PythonExe); err != nil {
			errMsg = "python du venv introuvable : " + cfg.PythonExe
		} else {
			start := time.Now()
			cmd := exec.Command(cfg.PythonExe, "-c", criticalImports)
			cmd.Dir = cfg.PythonModPath
			cmd.Env = append(os.Environ(), "PYTHONPATH="+cfg.PythonModPath, "PYTHONUTF8=1")
			if out, err := cmd.CombinedOutput(); err != nil {
				errMsg = lastNonEmptyLine(string(out))
				if errMsg == "" {
					errMsg = err.Error()
				}
			} else {
				log.Printf("Venv Python : OK — imports critiques vérifiés en %s", time.Since(start).Round(time.Millisecond))
			}
		}

		health.mu.Lock()
		health.pythonOK = errMsg == ""
		health.pythonErr = errMsg
		health.checked = true
		health.mu.Unlock()

		if errMsg != "" {
			log.Printf("ATTENTION — venv Python incomplet : %s (lancez scripts/setup.sh)", errMsg)
		}
	}()
}

// lastNonEmptyLine extracts the last non-empty line of an output —
// for a Python traceback, that is the final error message
// (e.g. "ModuleNotFoundError: No module named 'mmaction'").
func lastNonEmptyLine(s string) string {
	lines := strings.Split(strings.TrimSpace(s), "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		if l := strings.TrimSpace(lines[i]); l != "" && !strings.HasPrefix(l, "warnings.warn") {
			return l
		}
	}
	return ""
}

// healthHandler — GET /health. Always 200 (the server responds), but the
// body exposes the actual dependency state so the UI can warn the user.
func healthHandler(w http.ResponseWriter, r *http.Request) {
	missing := missingWeights()

	health.mu.Lock()
	pythonOK, pythonErr, checked := health.pythonOK, health.pythonErr, health.checked
	health.mu.Unlock()

	resp := map[string]any{"status": "ok"}
	if len(missing) > 0 || (checked && !pythonOK) {
		resp["status"] = "degraded"
		if len(missing) > 0 {
			resp["missing"] = missing
		}
		if checked && !pythonOK {
			resp["python_error"] = pythonErr
		}
	} else if !checked {
		// The Python check is still running — the server is reachable,
		// don't block the UI startup because of it.
		resp["python_check"] = "pending"
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp) //nolint:errcheck
}
