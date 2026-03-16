"""
STARHE Plugin — MEDomics Extension
===================================
Détection du cancer du foie par analyse d'échographies DICOM.

Modèles IA :
  - STARHE-RISK   : Classification du risque (C3D)
  - STARHE-DETECT : Détection de lésions (DINO-DETR)

Point d'entrée exposé au serveur Go via go_server blueprints.
"""

PLUGIN_NAME    = "STARHE"
PLUGIN_VERSION = "0.1.0"
PLUGIN_AUTHOR  = "MEDomics Team"
PLUGIN_DESC    = "Ultrasound-based liver cancer detection plugin"

# Hooks appelés par MEDomics au chargement du plug-in
def on_load():
    from starhe_plugin.utils.go_print import go_print
    go_print("info", f"Plugin {PLUGIN_NAME} v{PLUGIN_VERSION} chargé avec succès.")

def on_unload():
    from starhe_plugin.utils.go_print import go_print
    go_print("info", f"Plugin {PLUGIN_NAME} déchargé.")
