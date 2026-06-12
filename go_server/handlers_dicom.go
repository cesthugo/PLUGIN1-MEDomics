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
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
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
	var tmpToDelete string  // fichier temporaire à supprimer après traitement
	var originalName string  // nom original fourni par le navigateur (mode upload)

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

		// Lit le contenu en mémoire pour calculer le hash SHA-256
		fileBytes, err := io.ReadAll(f)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{
				"error": "erreur lecture fichier uploadé : " + err.Error(),
			})
			return
		}

		// Nom déterministe basé sur le contenu : même fichier → même chemin → cache hit
		hash := sha256.Sum256(fileBytes)
		hashStr := hex.EncodeToString(hash[:])[:24]
		tmpPath := filepath.Join(os.TempDir(), "starhe_upload_"+hashStr+".dcm")
		tmpToDelete = tmpPath

		// N'écrit que si le fichier n'existe pas encore (même contenu déjà présent)
		if _, statErr := os.Stat(tmpPath); os.IsNotExist(statErr) {
			if err := os.WriteFile(tmpPath, fileBytes, 0600); err != nil {
				writeJSON(w, http.StatusInternalServerError, map[string]string{
					"error": "erreur écriture fichier temporaire : " + err.Error(),
				})
				return
			}
		}

		dicomPath = tmpPath
		originalName = header.Filename

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

	// Timeout : 300 s pour les gros fichiers DICOM multi-frames (J2K Lossless lent à décoder)
	ctx, cancel := context.WithTimeout(r.Context(), 300*time.Second)
	defer cancel()

	args := []string{
		dicomPath,
		"--quality", strconv.Itoa(quality),
		"--max-dim", strconv.Itoa(maxDim),
	}

	cmd := pythonCmd(ctx, "dicom.loader_cli", args...)

	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	out, err := cmd.Output()
	if err != nil {
		// En cas d'erreur, nettoyer le temp si applicable
		if tmpToDelete != "" {
			os.Remove(tmpToDelete)
		}
		// loader_cli.py écrit l'erreur JSON+traceback sur stdout avant sys.exit(1).
		// On l'inclut dans la réponse pour que le client puisse afficher l'erreur réelle.
		errResp := map[string]string{
			"error":  "subprocess Python échoué : " + err.Error(),
			"stderr": stderr.String(),
		}
		if len(out) > 0 {
			errResp["stdout"] = string(out)
			// Si le JSON Python contient un champ "error", on l'expose directement.
			var pyErr map[string]string
			if jsonErr := json.Unmarshal(out, &pyErr); jsonErr == nil {
				if msg, ok := pyErr["error"]; ok {
					errResp["python_error"] = msg
				}
				if tb, ok := pyErr["traceback"]; ok {
					errResp["python_traceback"] = tb
				}
			}
		}
		writeJSON(w, http.StatusInternalServerError, errResp)
		return
	}

	// Si le fichier vient d'un upload multipart, injecter server_path dans le JSON
	// afin que le client React sache quel chemin envoyer à /starhe/analyze.
	if tmpToDelete != "" {
		var obj map[string]interface{}
		if err := json.Unmarshal(out, &obj); err == nil {
			obj["server_path"] = tmpToDelete
			if originalName != "" {
				obj["file_name"] = originalName
			}
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
