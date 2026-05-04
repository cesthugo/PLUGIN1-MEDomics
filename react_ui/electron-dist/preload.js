"use strict";
/**
 * electron/preload.ts — Script de preload Electron (contextBridge)
 *
 * Ce script tourne dans un contexte isolé entre le processus principal et
 * le renderer React. Il expose uniquement les méthodes listées dans
 * contextBridge.exposeInMainWorld(), rendant le renderer complètement isolé
 * de Node.js tout en lui donnant accès aux fonctionnalités natives nécessaires.
 *
 * Sécurité :
 *   - Le renderer ne peut invoquer que les méthodes déclarées ici
 *   - Aucun accès à ipcRenderer ou aux modules Node directement
 *   - Valider / filtrer les données côté main.ts si besoin
 */
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
electron_1.contextBridge.exposeInMainWorld('electronAPI', {
    /**
     * Ouvre un dialogue natif de sélection de fichiers DICOM.
     * Retourne un tableau de chemins absolus (vide si l'utilisateur annule).
     */
    openDicomFiles: () => electron_1.ipcRenderer.invoke('open-dicom-files'),
    /**
     * Base URL du serveur Go local.
     * Utilisée par api.ts pour construire les endpoints (API_BASE).
     */
    apiBase: 'http://localhost:8082',
});
