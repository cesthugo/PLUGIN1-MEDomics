// handlers_dicom.go — Endpoints supplémentaires pour le service DICOM (chargement frames)
//
// POST /starhe/dicom/load   → charge un DICOM via Python et retourne toutes les frames en JPEG base64
//   Accept deux formats :
//     - multipart/form-data  : champ "file" (upload navigateur), paramètres "quality" et "max_dim"
//     - application/json     : {"dicom_path":"...","quality":70,"max_dim":640} (Electron / CLI)
// DELETE /starhe/cache      → supprime le cache MongoDB d'un fichier par path (?path=...)
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/bson"
)

// ── POST /starhe/dicom/load ────────────────────────────────────────────────
//
// Accepte deux formats :
//
//  1. multipart/form-data (upload navigateur) :
//     champ "file"     → octets du fichier DICOM
//     champ "quality"  → int optionnel (défaut 70)
//     champ "max_dim"  → int optionnel (défaut 640)
//
//  2. application/json (Electron / saisie chemin) :
//     { "dicom_path": "/chemin/absolu/fichier.dcm", "quality": 70, "max_dim": 640 }
//
// Réponse : JSON retourné directement par loader_cli.py.
func dicomLoadHandler(w http.ResponseWriter, r *http.Request) {
	quality := 70
	maxDim  := 640
	var dicomPath string
	var tmpToDelete string // fichier temporaire à supprimer après traitement

	ct := r.Header.Get("Content-Type")

	if strings.Contains(ct, "multipart/form-data") {
		// ── Mode upload navigateur ──────────────────────────────────────────
		// Limite à 500 MB en mémoire (les DICOM multi-frames peuvent être lourds)
		if err := r.ParseMultipartForm(500 << 20); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "impossible de parser le formulaire : " + err.Error(),
			})
			return
		}

		f, header, err := r.FormFile("file")
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "champ 'file' manquant dans le formulaire",
			})
			return
		}
		defer f.Close()

		// Écriture dans un fichier temporaire (suffixe .dcm pour que pydicom l'accepte)
		tmp, err := os.CreateTemp("", "starhe_upload_*.dcm")
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{
				"error": "impossible de créer le fichier temporaire : " + err.Error(),
			})
			return
		}
		tmpToDelete = tmp.Name()

		if _, err := io.Copy(tmp, f); err != nil {
			tmp.Close()
			os.Remove(tmpToDelete)
			writeJSON(w, http.StatusInternalServerError, map[string]string{
				"error": "erreur écriture fichier temporaire : " + err.Error(),
			})
			return
		}
		tmp.Close()

		dicomPath = tmp.Name()
		_ = header // nom original disponible si besoin

		// Paramètres optionnels depuis le formulaire
		if v := r.FormValue("quality"); v != "" {
			if n, err := strconv.Atoi(v); err == nil {
				quality = n
			}
		}
		if v := r.FormValue("max_dim"); v != "" {
			if n, err := strconv.Atoi(v); err == nil {
				maxDim = n
			}
		}

	} else {
		// ── Mode JSON (Electron / saisie chemin) ───────────────────────────
		var req struct {
			DicomPath string `json:"dicom_path"`
			Quality   int    `json:"quality"`
			MaxDim    int    `json:"max_dim"`
		}
		req.Quality = quality
		req.MaxDim  = maxDim

		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "corps de requête JSON invalide : " + err.Error(),
			})
			return
		}
		if req.DicomPath == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "dicom_path est requis",
			})
			return
		}
		if _, err := os.Stat(req.DicomPath); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "fichier dicom_path introuvable : " + req.DicomPath,
			})
			return
		}
		dicomPath = req.DicomPath
		if req.Quality > 0 { quality = req.Quality }
		if req.MaxDim  > 0 { maxDim  = req.MaxDim  }
	}

	// En mode upload : conserve le fichier temp — il sera utilisé par /starhe/analyze.
	// Il est supprimé via DELETE /starhe/cache?path=<server_path>.
	// (pas de defer os.Remove ici)

	// Borne les paramètres
	if quality < 1 || quality > 95 { quality = 70  }
	if maxDim  < 64 || maxDim > 4096 { maxDim = 640 }

	// Timeout généreux : 120 s pour les gros fichiers DICOM multi-frames
	ctx, cancel := context.WithTimeout(r.Context(), 120*time.Second)
	defer cancel()

	args := []string{
		"-m", "starhe_plugin.dicom.loader_cli",
		dicomPath,
		"--quality", strconv.Itoa(quality),
		"--max-dim", strconv.Itoa(maxDim),
	}

	cmd := exec.CommandContext(ctx, cfg.PythonExe, args...)
	cmd.Dir = cfg.PythonModPath
	cmd.Env = append(os.Environ(),
		"PYTHONPATH="+cfg.PythonModPath,
		"PYTHONUTF8=1",
	)

	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	out, err := cmd.Output()
	if err != nil {
		// En cas d'erreur, nettoyer le temp si applicable
		if tmpToDelete != "" {
			os.Remove(tmpToDelete)
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{
			"error":  "subprocess Python échoué : " + err.Error(),
			"stderr": stderr.String(),
		})
		return
	}

	// Si le fichier vient d'un upload multipart, injecter server_path dans le JSON
	// afin que le client React sache quel chemin envoyer à /starhe/analyze.
	if tmpToDelete != "" {
		var obj map[string]interface{}
		if err := json.Unmarshal(out, &obj); err == nil {
			obj["server_path"] = tmpToDelete
			if patched, err := json.Marshal(obj); err == nil {
				out = patched
			}
		}
	}

	// Transmet le JSON au client
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	w.Write(out) //nolint:errcheck
}

// ── DELETE /starhe/cache ───────────────────────────────────────────────────
//
// Paramètre URL : ?path=<dicom_path_absolu>
//
// Supprime les documents MongoDB dont le champ "file_path" correspond au chemin fourni.
func deleteCacheHandler(w http.ResponseWriter, r *http.Request) {
	path := r.URL.Query().Get("path")
	if path == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "paramètre 'path' requis",
		})
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	result, err := collection().DeleteMany(ctx, bson.D{{Key: "file_path", Value: path}})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{
			"error": err.Error(),
		})
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"deleted": result.DeletedCount,
		"path":    path,
	})
}
