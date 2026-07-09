"""
STARHE Plugin — MEDomics Extension
===================================
Liver cancer detection through DICOM ultrasound analysis.

AI models:
  - STARHE-RISK   : Risk classification (C3D)
  - STARHE-DETECT : Lesion detection (DINO-DETR)

Entry point exposed to the Go server via go_server blueprints.
"""

PLUGIN_NAME    = "STARHE"
PLUGIN_VERSION = "0.1.0"
PLUGIN_AUTHOR  = "MEDomics Team"
PLUGIN_DESC    = "Ultrasound-based liver cancer detection plugin"

# Hooks called by MEDomics when the plug-in is loaded
def on_load():
    from starhe_plugin.utils.go_print import go_print
    go_print("info", f"Plugin {PLUGIN_NAME} v{PLUGIN_VERSION} chargé avec succès.")

def on_unload():
    from starhe_plugin.utils.go_print import go_print
    go_print("info", f"Plugin {PLUGIN_NAME} déchargé.")
