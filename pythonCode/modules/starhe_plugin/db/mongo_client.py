"""
db/mongo_client.py — Persistence of STARHE results in MongoDB
===================================================================
Schema of a result document:
{
  "_id"                  : ObjectId,
  "file_path"            : str,       → source .dcm path (cache key)
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
    """Normalizes a path to POSIX separators so that the MongoDB
    cache key is identical regardless of the source OS."""
    return str(PurePosixPath(p))


def _get_collection() -> Collection:
    """Opens a MongoDB connection and returns the STARHE collection."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        # Test the connection immediately
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
    Inserts (or replaces) a result document in MongoDB.
    If a document with the same file_path already exists, it is replaced.

    Returns the _id (str) of the inserted/replaced document, or None if
    MongoDB is unreachable (the pipeline continues without persistence).
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
    Returns the result document associated with this DICOM file and mode, or None.
    If analysis_mode is None, returns the first result found.
    Returns None if MongoDB is unreachable.
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
    """Fetches a result document by its _id (str)."""
    from bson import ObjectId
    col = _get_collection()
    doc = col.find_one({"_id": ObjectId(doc_id)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def list_results(limit: int = 50) -> list[dict]:
    """
    Returns the last N results sorted by descending date.
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
    """Deletes the result document associated with a file. Returns True if deleted."""
    col = _get_collection()
    res = col.delete_one({"file_path": file_path})
    deleted = res.deleted_count > 0
    go_print("info", f"mongo_client : {file_path} {'supprimé' if deleted else 'introuvable'}.")
    return deleted
