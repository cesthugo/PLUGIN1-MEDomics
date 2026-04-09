// starhe_blueprint.go — Blueprint MEDomics pour le plugin STARHE
//
// Ce fichier est destiné à être intégré dans le serveur Go de MEDomics :
//   MEDomics/go_server/blueprints/starhe/starhe.go
//
// Ajoutez ensuite dans MEDomics/go_server/main.go :
//   import Starhe "go_module/blueprints/starhe"
//   Starhe.AddHandleFunc()
//
// Le blueprint enregistre les routes suivantes :
//   POST  starhe/analyze/   → lance le pipeline STARHE via run_starhe.py
//   POST  starhe/progress/  → récupère la progression d'un job STARHE
package starhe

import (
	"log"

	Utils "go_module/src"
)

var prePath = "starhe"

// AddHandleFunc enregistre les routes STARHE dans le serveur HTTP MEDomics.
func AddHandleFunc() {
	Utils.CreateHandleFunc(prePath+"/analyze/", handleAnalyze)
	Utils.CreateHandleFunc(prePath+"/progress/", handleProgress)
}

// handleAnalyze lance le pipeline STARHE complet sur un fichier DICOM.
//
// json_param attendu (envoyé depuis le frontend MEDomics) :
//
//	{
//	    "dicom_path":           "/chemin/vers/fichier.dcm",
//	    "anon_mode":            "hash",
//	    "run_detection":        true,
//	    "back_scan_conversion": true,
//	    "backscan_width":       512,
//	    "backscan_height":      512,
//	    "patient_id":           "optionnel"
//	}
//
// Le script Python run_starhe.py :
//   1. Localise le venv STARHE (starhe_plugin/.venv/)
//   2. Lance pipeline.py en subprocess
//   3. Traduit le protocole GO_PRINT → MEDomics (progress/response)
func handleAnalyze(jsonConfig string, id string) (string, error) {
	log.Println("STARHE: lancement de l'analyse...", id)
	response, err := Utils.StartPythonScripts(
		jsonConfig,
		"../pythonCode/modules/starhe/run_starhe.py",
		id,
	)
	Utils.RemoveIdFromScripts(id)
	if err != nil {
		log.Println("STARHE: erreur pipeline —", err.Error())
		return "", err
	}
	return response, nil
}

// handleProgress retourne la progression courante du job STARHE.
// Utilisé par le frontend MEDomics pour interroger l'état via polling.
func handleProgress(jsonConfig string, id string) (string, error) {
	Utils.Mu.Lock()
	script, ok := Utils.Scripts[id]
	Utils.Mu.Unlock()
	if !ok {
		return "{\"now\":0,\"currentLabel\":\"Job introuvable\"}", nil
	}
	return script.Progress, nil
}
