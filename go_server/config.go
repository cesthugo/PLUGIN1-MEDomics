// config.go — Configuration du serveur STARHE
//
// Toutes les valeurs peuvent être surchargées via variables d'environnement.
// Exemple :
//
//	$env:PORT = "9090"
//	$env:STARHE_PYTHON_EXE = "C:\Python313\python.exe"
package main

import "os"

type appConfig struct {
	// Réseau
	Port string

	// Python
	PythonExe     string // Chemin absolu vers python.exe du venv
	PythonModPath string // Dossier racine des modules Python (contient starhe_plugin/)

	// MongoDB
	MongoURI        string
	MongoDatabase   string
	MongoCollection string
}

var cfg = appConfig{
	Port: envOr("PORT", "8080"),

	PythonExe: envOr(
		"STARHE_PYTHON_EXE",
		`F:\STAGE\PROJET\PLUGIN1-MEDomics\pythonCode\modules\starhe_plugin\.venv\Scripts\python.exe`,
	),
	PythonModPath: envOr(
		"STARHE_PYTHON_PATH",
		`F:\STAGE\PROJET\PLUGIN1-MEDomics\pythonCode\modules`,
	),

	MongoURI:        envOr("MONGO_URI", "mongodb://localhost:27017/"),
	MongoDatabase:   envOr("MONGO_DB", "medomics"),
	MongoCollection: envOr("MONGO_COLL", "starhe_results"),
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
