"""
db/mongo_client.py — Persistance des résultats STARHE dans MongoDB
===================================================================
Schéma d'un document résultat :
{
  "_id"                  : ObjectId,
  "file_path"            : str,       → chemin .dcm source (clé de cache)
  "processed_at"         : ISO-8601,
  "num_frames"           : int,
  "roi"                  : [x0, y0, x1, y1],
  "risk"                 : { "score": float, "label": str },
  "detections_per_frame" : [ [{"bbox": [...], "score": float, "label": str}, ...], ... ],
  "anon_mode"            : str,       → "hash" | "remove" | "none"
  "analysis_mode"        : str        → "original" | "backscan" | "crop"
}
"""

from __future__ import annotations

import datetime
from pathlib import PurePosixPath
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure

from starhe_plugin.config import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION
from starhe_plugin.utils.go_print import go_print


def _normalize_path(p: str) -> str:
    """Normalise un chemin vers des séparateurs POSIX pour que la clé
    de cache MongoDB soit identique quel que soit l'OS d'origine."""
    return str(PurePosixPath(p))


def _get_collection() -> Collection:
    """Ouvre une connexion MongoDB et retourne la collection STARHE."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        # Teste la connexion immédiatement
        client.admin.command("ping")
        return client[MONGO_DB_NAME][MONGO_COLLECTION]
    except ConnectionFailure as e:
        go_print("error", f"MongoDB inaccessible : {e}")
        raise


def save_result(file_path: str,
                num_frames: int,
                roi: list[int],
                risk: dict | None,
                detections_per_frame: list[list[dict]],
                anon_mode: str = "none",
                analysis_mode: str = "original") -> str | None:
    """
    Insère (ou remplace) un document de résultat dans MongoDB.
    Si un document avec le même file_path existe déjà, il est remplacé.

    Retourne l'_id (str) du document inséré/remplacé, ou None si
    MongoDB est inaccessible (le pipeline continue sans persistence).
    """
    try:
        col = _get_collection()
        file_path = _normalize_path(file_path)
        doc: dict[str, Any] = {
            "file_path"            : file_path,
            "processed_at"         : datetime.datetime.utcnow().isoformat() + "Z",
            "num_frames"           : num_frames,
            "roi"                  : roi,
            "detections_per_frame" : detections_per_frame,
            "anon_mode"            : anon_mode,
            "analysis_mode"        : analysis_mode,
        }
        if risk is not None:
            doc["risk"] = risk
        result = col.replace_one(
            {"file_path": file_path, "analysis_mode": analysis_mode},
            doc, upsert=True)
        doc_id = str(result.upserted_id) if result.upserted_id else "(updated)"
        go_print("info", f"mongo_client : résultat sauvegardé (_id={doc_id}).")
        return doc_id
    except Exception as exc:
        go_print("warning", f"MongoDB indisponible — résultat non sauvegardé : {exc}")
        return None


def find_by_file(file_path: str, analysis_mode: str | None = None) -> dict | None:
    """
    Retourne le document de résultat associé à ce fichier DICOM et mode, ou None.
    Si analysis_mode est None, retourne le premier résultat trouvé.
    Retourne None si MongoDB est inaccessible.
    """
    try:
        col = _get_collection()
        query = {"file_path": _normalize_path(file_path)}
        if analysis_mode is not None:
            query["analysis_mode"] = analysis_mode
        doc = col.find_one(query)
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception as exc:
        go_print("warning", f"MongoDB indisponible — recherche impossible : {exc}")
        return None


def get_result(doc_id: str) -> dict | None:
    """Récupère un document résultat par son _id (str)."""
    from bson import ObjectId
    col = _get_collection()
    doc = col.find_one({"_id": ObjectId(doc_id)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def list_results(limit: int = 50) -> list[dict]:
    """
    Retourne les N derniers résultats triés par date décroissante.
    """
    col = _get_collection()
    cursor = col.find({}, {"_id": 1, "file_path": 1, "processed_at": 1,
                           "risk": 1, "detections": 1}) \
                .sort("processed_at", -1) \
                .limit(limit)
    docs = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        docs.append(doc)
    return docs


def delete_result(file_path: str) -> bool:
    """Supprime le document résultat associé à un fichier. Retourne True si supprimé."""
    col = _get_collection()
    res = col.delete_one({"file_path": file_path})
    deleted = res.deleted_count > 0
    go_print("info", f"mongo_client : {file_path} {'supprimé' if deleted else 'introuvable'}.")
    return deleted
