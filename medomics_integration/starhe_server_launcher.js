/**
 * starhe_main_electron.js — Ajouts au processus principal Electron de MEDomics
 *
 * Ce module gère le cycle de vie du serveur Go STARHE standalone,
 * qui est un processus séparé du serveur Go MEDomics principal.
 *
 * Le serveur Go MEDomics proxifie les routes /starhe/* vers ce serveur
 * (voir starhe_blueprint.go).
 *
 * ── Installation dans MEDomics ──────────────────────────────────────────────
 *
 * Dans MEDomics/main/main.js (ou main/index.js) :
 *
 *   const { startStarheServer, stopStarheServer } = require('./starhe_server_launcher')
 *
 *   // Dans app.whenReady() ou là où vous démarrez les serveurs :
 *   startStarheServer()
 *
 *   // Dans app.on('before-quit', ...) :
 *   stopStarheServer()
 *
 * ── Structure des fichiers requis ───────────────────────────────────────────
 *
 * En développement, les chemins relatifs pointent vers le repo PLUGIN1-MEDomics.
 * En production (app packagée), les fichiers doivent être copiés dans les
 * ressources de l'app via electron-builder extraResources :
 *
 *   {
 *     "from": "../PLUGIN1-MEDomics/go_server/go_server",  // binaire Go
 *     "to":   "starhe/go_server"
 *   },
 *   {
 *     "from": "../PLUGIN1-MEDomics/pythonCode",
 *     "to":   "starhe/pythonCode"
 *   }
 */

const path = require('path')
const { spawn } = require('child_process')
const { app } = require('electron')

// Port dédié au serveur Go STARHE (distinct du port MEDomics principal)
const STARHE_SERVER_PORT = 8082

let _starheProcess = null

/**
 * Démarre le serveur Go STARHE en arrière-plan.
 * Idempotent : si déjà démarré, ne fait rien.
 */
function startStarheServer() {
  if (_starheProcess) return

  const isDev = !app.isPackaged
  const binaryName = process.platform === 'win32' ? 'go_server.exe' : 'go_server'

  // Chemins selon le mode (dev / production packagée)
  const binaryPath = isDev
    ? path.join(__dirname, '..', '..', 'PLUGIN1-MEDomics', 'go_server', binaryName)
    : path.join(process.resourcesPath, 'starhe', binaryName)

  const pythonModPath = isDev
    ? path.join(__dirname, '..', '..', 'PLUGIN1-MEDomics', 'pythonCode', 'modules')
    : path.join(process.resourcesPath, 'starhe', 'pythonCode', 'modules')

  // Le serveur Go lit PORT et PYTHON_MOD_PATH depuis l'environnement
  const env = {
    ...process.env,
    PORT: String(STARHE_SERVER_PORT),
    PYTHON_MOD_PATH: pythonModPath,
  }

  _starheProcess = spawn(binaryPath, [], {
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  _starheProcess.stdout.on('data', (d) =>
    console.log('[STARHE Go]', d.toString().trim()),
  )
  _starheProcess.stderr.on('data', (d) =>
    console.error('[STARHE Go ERR]', d.toString().trim()),
  )
  _starheProcess.on('exit', (code) => {
    console.log('[STARHE Go] exit', code)
    _starheProcess = null
  })

  console.log(`[STARHE Go] Démarrage sur port ${STARHE_SERVER_PORT}`)
}

/**
 * Arrête proprement le serveur Go STARHE.
 * À appeler dans app.on('before-quit').
 */
function stopStarheServer() {
  if (_starheProcess) {
    _starheProcess.kill()
    _starheProcess = null
    console.log('[STARHE Go] Arrêté')
  }
}

module.exports = { startStarheServer, stopStarheServer, STARHE_SERVER_PORT }
