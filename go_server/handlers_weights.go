// handlers_weights.go — Local provisioning of the STARHE AI model weights.
//
// The .pth checkpoints are not distributed with the plugin; the user supplies
// them from their own machine. These endpoints let the React UI (in any mode —
// browser or Electron) check which weights are present and upload a chosen
// .pth into WeightsDir under the canonical file name the pipeline expects.
//
//	GET  /starhe/weights/status  → [{id,name,file,present}, ...]
//	POST /starhe/weights/upload  → multipart {id, file} → writes the .pth
package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
)

// weightModel describes one AI model whose .pth weight the user provides.
// Single source of truth for the required weights (health.go derives the
// missing-checkpoint list from it); mirrors renderer/electron/weights.ts.
type weightModel struct {
	ID       string
	Name     string
	File     string
	SizeHint int64 // reference size, used only for a soft sanity warning
}

var weightModels = []weightModel{
	{ID: "risk", Name: "STARHE-RISK (C3D)", File: "best_acc_mean_cls_f1_epoch_14.pth", SizeHint: 312198292},
	{ID: "detect", Name: "STARHE-DETECT (RTMDet)", File: "best_coco_bbox_mAP_50_iter_2100.pth", SizeHint: 438998465},
}

func findWeightModel(id string) *weightModel {
	for i := range weightModels {
		if weightModels[i].ID == id {
			return &weightModels[i]
		}
	}
	return nil
}

// weightPresent reports whether the model's .pth sits in WeightsDir (>1 MB,
// which rules out a truncated or placeholder file).
func weightPresent(m weightModel) bool {
	fi, err := os.Stat(filepath.Join(cfg.WeightsDir, m.File))
	return err == nil && fi.Size() > 1_000_000
}

// GET /starhe/weights/status — per-model presence in WeightsDir.
func weightsStatusHandler(w http.ResponseWriter, r *http.Request) {
	type row struct {
		ID      string `json:"id"`
		Name    string `json:"name"`
		File    string `json:"file"`
		Present bool   `json:"present"`
	}
	out := make([]row, 0, len(weightModels))
	for _, m := range weightModels {
		out = append(out, row{ID: m.ID, Name: m.Name, File: m.File, Present: weightPresent(m)})
	}
	writeJSON(w, http.StatusOK, out)
}

// POST /starhe/weights/upload — multipart form {id, file} → writes the .pth
// into WeightsDir under the model's canonical name. Streams to a .part file
// then renames it, so a ~400 MB checkpoint is never held fully in memory and a
// failed upload never leaves a corrupt weight in place.
func weightsUploadHandler(w http.ResponseWriter, r *http.Request) {
	// Keep only small fields in memory; the large file part spills to a temp
	// file that we then stream to the destination.
	if err := r.ParseMultipartForm(16 << 20); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid form: " + err.Error()})
		return
	}

	id := r.FormValue("id")
	m := findWeightModel(id)
	if m == nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "unknown model id: " + id})
		return
	}

	f, _, err := r.FormFile("file")
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "missing 'file' field"})
		return
	}
	defer f.Close()

	if err := os.MkdirAll(cfg.WeightsDir, 0o755); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "cannot create weights dir: " + err.Error()})
		return
	}

	dest := filepath.Join(cfg.WeightsDir, m.File)
	tmp := dest + ".part"
	out, err := os.Create(tmp)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "cannot write weight: " + err.Error()})
		return
	}
	written, copyErr := io.Copy(out, f)
	closeErr := out.Close()
	if copyErr != nil || closeErr != nil {
		os.Remove(tmp)
		msg := "write failed"
		if copyErr != nil {
			msg = copyErr.Error()
		} else if closeErr != nil {
			msg = closeErr.Error()
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": msg})
		return
	}
	if written < 1_000_000 {
		os.Remove(tmp)
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "file too small to be a valid checkpoint"})
		return
	}
	if err := os.Rename(tmp, dest); err != nil {
		os.Remove(tmp)
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "cannot finalize weight: " + err.Error()})
		return
	}

	resp := map[string]any{"ok": true, "id": id, "file": m.File}
	if m.SizeHint > 0 {
		diff := float64(written-m.SizeHint) / float64(m.SizeHint)
		if diff < 0 {
			diff = -diff
		}
		if diff > 0.2 {
			resp["warning"] = fmt.Sprintf(
				"Unexpected size for %s (%d MB vs ~%d MB expected) — make sure this is the right checkpoint.",
				m.Name, written/1_000_000, m.SizeHint/1_000_000)
		}
	}
	writeJSON(w, http.StatusOK, resp)
}
