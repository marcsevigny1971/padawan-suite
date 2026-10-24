# -*- coding: utf-8 -*-
"""
facteur_boite — boîtes aux lettres SQL pour Facteur (Projet Padawan).

Deux modes :
  A) Pont PHP HTTPS (recommandé) : Facteur appelle facteur_boite.php, requêtes signées HMAC.
  B) MySQL direct (pymysql), optionnel.

Identifiants MySQL : jamais en clair dans FTP_HOME ni dans le code.
Stockés via DPAPI (Windows) / PLAIN1 (tests Linux) dans %LOCALAPPDATA%\\Padawan\\Facteur\\
ou dans le dossier --data pour les tests.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import socket
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS incoming (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  created_at DATETIME NOT NULL,
  expire_at DATETIME NOT NULL,
  source VARCHAR(64) NOT NULL DEFAULT '',
  action VARCHAR(64) NOT NULL,
  params JSON NOT NULL,
  sig CHAR(64) NOT NULL,
  uuid CHAR(32) NOT NULL,
  statut ENUM('en_attente','en_cours','traite','refuse') NOT NULL DEFAULT 'en_attente',
  tentative INT NOT NULL DEFAULT 0,
  verrou_par VARCHAR(128) DEFAULT NULL,
  verrou_at DATETIME DEFAULT NULL,
  raison TEXT NULL,
  UNIQUE KEY uq_incoming_uuid (uuid),
  KEY idx_incoming_statut (statut, expire_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS traites (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  incoming_id BIGINT NULL,
  uuid CHAR(32) NOT NULL,
  action VARCHAR(64) NOT NULL,
  params JSON NULL,
  resultat TEXT NULL,
  statut VARCHAR(32) NOT NULL,
  traite_at DATETIME NOT NULL,
  machine VARCHAR(128) NOT NULL DEFAULT '',
  UNIQUE KEY uq_traites_uuid (uuid),
  KEY idx_traites_at (traite_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def machine_id() -> str:
    return (socket.gethostname() or "pc")[:120]


def creds_path(data_dir: str, default_data_dir: str) -> str:
    """Fichier chiffré des identifiants (hors FTP_HOME en usage normal)."""
    la = os.environ.get("LOCALAPPDATA", "").strip()
    if la and os.path.abspath(data_dir) == os.path.abspath(default_data_dir):
        d = os.path.join(la, "Padawan", "Facteur")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "boites_sql_creds.dpapi")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "boites_sql_creds.dpapi")


class CredsStore:
    """Dict {boite_id: {host, port, user, password, database}} protégé DPAPI."""

    def __init__(self, path: str, protect_fn, unprotect_fn, is_win: bool) -> None:
        self.path = path
        self._protect = protect_fn
        self._unprotect = unprotect_fn
        self.is_win = is_win
        self._cache: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if not os.path.isfile(self.path):
            self._cache = {}
            return self._cache
        with open(self.path, "rb") as f:
            blob = f.read()
        if blob.startswith(b"DPAPI1"):
            raw = self._unprotect(blob[6:])
        elif blob.startswith(b"PLAIN1"):
            raw = blob[6:]
        else:
            raise RuntimeError("fichier d'identifiants illisible")
        self._cache = json.loads(raw.decode("utf-8"))
        return self._cache

    def save(self, data: Dict[str, Any]) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        if self.is_win:
            blob = b"DPAPI1" + self._protect(raw)
        else:
            blob = b"PLAIN1" + raw
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, self.path)
        self._cache = data

    def get(self, boite_id: str) -> Dict[str, Any]:
        return dict(self.load().get(boite_id) or {})

    def set(self, boite_id: str, creds: Dict[str, Any]) -> None:
        d = self.load()
        d[boite_id] = {
            "host": str(creds.get("host") or ""),
            "port": int(creds.get("port") or 3306),
            "user": str(creds.get("user") or ""),
            "password": str(creds.get("password") or ""),
            "database": str(creds.get("database") or ""),
        }
        self.save(d)

    def delete(self, boite_id: str) -> None:
        d = self.load()
        d.pop(boite_id, None)
        self.save(d)


def default_boite() -> Dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:8],
        "nom": "Boîte SQL",
        "actif": False,
        "intervalle": 30,
        "horaire": {"actif": False, "debut": "00:00", "fin": "23:59", "jours": list(range(7))},
        "mode": "pont",  # pont | mysql
        "pont_url": "",  # https://.../facteur_boite.php
        "note": "",
    }


# ---------- MySQL direct ----------
def _pymysql():
    try:
        import pymysql  # type: ignore
        return pymysql
    except ImportError as ex:
        raise RuntimeError("pymysql absent — pip install --user pymysql") from ex


def mysql_connect(creds: Dict[str, Any]):
    pymysql = _pymysql()
    return pymysql.connect(
        host=creds.get("host") or "127.0.0.1",
        port=int(creds.get("port") or 3306),
        user=creds.get("user") or "",
        password=creds.get("password") or "",
        database=creds.get("database") or "",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=15,
        read_timeout=60,
        write_timeout=60,
    )


def mysql_create_schema(creds: Dict[str, Any]) -> str:
    con = mysql_connect(creds)
    try:
        with con.cursor() as cur:
            for stmt in SCHEMA_SQL.split(";"):
                s = stmt.strip()
                if s:
                    cur.execute(s)
        con.commit()
        return "tables incoming + traites OK"
    finally:
        con.close()


def mysql_test(creds: Dict[str, Any]) -> str:
    con = mysql_connect(creds)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
            cur.execute("SHOW TABLES LIKE 'incoming'")
            has = cur.fetchone() is not None
        return "connexion OK" + (" (tables présentes)" if has else " (tables absentes — crée-les)")
    finally:
        con.close()


def _row_to_cmd(row: Dict[str, Any]) -> Dict[str, Any]:
    params = row.get("params")
    if isinstance(params, (bytes, bytearray)):
        params = params.decode("utf-8", "replace")
    if isinstance(params, str):
        params = json.loads(params) if params else {}
    if not isinstance(params, dict):
        params = {}
    # ts / expire depuis les DATETIME
    def _ts(v) -> int:
        if isinstance(v, dt.datetime):
            return int(v.timestamp())
        if isinstance(v, str):
            try:
                return int(dt.datetime.fromisoformat(v.replace(" ", "T")).timestamp())
            except ValueError:
                return int(time.time())
        return int(time.time())
    return {
        "v": 1,
        "id": row["uuid"],
        "ts": _ts(row.get("created_at")),
        "expire": _ts(row.get("expire_at")),
        "action": row["action"],
        "params": params,
        "sig": (row.get("sig") or "").lower(),
        "_incoming_id": row["id"],
        "_source": row.get("source") or "",
    }


def mysql_claim_pending(creds: Dict[str, Any], limit: int = 20) -> List[Dict[str, Any]]:
    """Verrouille et retourne des commandes en_attente (ou expirees a refuser)."""
    mid = machine_id()
    con = mysql_connect(creds)
    out: List[Dict[str, Any]] = []
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT * FROM incoming WHERE statut='en_attente' "
                "ORDER BY id ASC LIMIT %s FOR UPDATE",
                (int(limit),),
            )
            rows = list(cur.fetchall() or [])
            now = dt.datetime.now().replace(microsecond=0)
            for row in rows:
                cur.execute(
                    "UPDATE incoming SET statut='en_cours', tentative=tentative+1, "
                    "verrou_par=%s, verrou_at=%s WHERE id=%s AND statut='en_attente'",
                    (mid, now, row["id"]),
                )
                if cur.rowcount == 1:
                    row["statut"] = "en_cours"
                    out.append(_row_to_cmd(row))
        con.commit()
        return out
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def mysql_finish(creds: Dict[str, Any], cmd: Dict[str, Any], statut: str, resultat: str) -> None:
    """Déplace vers traites (transaction) ; uuid UNIQUE empêche le double traitement."""
    mid = machine_id()
    iid = cmd.get("_incoming_id")
    uid = str(cmd.get("id") or "")
    con = mysql_connect(creds)
    try:
        with con.cursor() as cur:
            cur.execute(
                "INSERT INTO traites (incoming_id, uuid, action, params, resultat, statut, traite_at, machine) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (iid, uid, cmd.get("action"), json.dumps(cmd.get("params") or {}, ensure_ascii=False),
                 (resultat or "")[:4000], statut, dt.datetime.now().replace(microsecond=0), mid),
            )
            if iid:
                cur.execute(
                    "UPDATE incoming SET statut=%s, raison=%s WHERE id=%s",
                    (statut if statut in ("traite", "refuse") else "traite", (resultat or "")[:1000], iid),
                )
        con.commit()
    except Exception as ex:
        con.rollback()
        # doublon uuid = deja traite ailleurs
        if "Duplicate" in str(ex) or "1062" in str(ex):
            return
        raise
    finally:
        con.close()


def mysql_list_recent(creds: Dict[str, Any], n: int = 30) -> Tuple[List[Dict], List[Dict]]:
    con = mysql_connect(creds)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT id, uuid, action, statut, created_at, expire_at, source, raison "
                        "FROM incoming ORDER BY id DESC LIMIT %s", (n,))
            inc = list(cur.fetchall() or [])
            cur.execute("SELECT id, uuid, action, statut, traite_at, machine, LEFT(resultat,200) AS resultat "
                        "FROM traites ORDER BY id DESC LIMIT %s", (n,))
            tr = list(cur.fetchall() or [])
        return inc, tr
    finally:
        con.close()


def mysql_purge(creds: Dict[str, Any], days: int = 30) -> str:
    con = mysql_connect(creds)
    try:
        with con.cursor() as cur:
            cur.execute("DELETE FROM traites WHERE traite_at < (NOW() - INTERVAL %s DAY)", (int(days),))
            n1 = cur.rowcount
            cur.execute(
                "DELETE FROM incoming WHERE statut IN ('traite','refuse') "
                "AND created_at < (NOW() - INTERVAL %s DAY)",
                (int(days),),
            )
            n2 = cur.rowcount
        con.commit()
        return f"purgé : {n1} traités, {n2} incoming"
    finally:
        con.close()


def mysql_insert_command(creds: Dict[str, Any], cmd: Dict[str, Any], source: str = "test") -> int:
    """Insertion directe (tests / page PHP équivalente)."""
    con = mysql_connect(creds)
    try:
        with con.cursor() as cur:
            created = dt.datetime.fromtimestamp(int(cmd["ts"])).replace(microsecond=0)
            expire = dt.datetime.fromtimestamp(int(cmd["expire"])).replace(microsecond=0)
            cur.execute(
                "INSERT INTO incoming (created_at, expire_at, source, action, params, sig, uuid, statut) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'en_attente')",
                (created, expire, source, cmd["action"],
                 json.dumps(cmd.get("params") or {}, ensure_ascii=False),
                 cmd["sig"], cmd["id"]),
            )
            iid = cur.lastrowid
        con.commit()
        return int(iid)
    finally:
        con.close()


# ---------- Pont PHP (HTTPS + HMAC) ----------
def bridge_canonical(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def bridge_sign(payload: Dict[str, Any], key: bytes) -> str:
    return hmac.new(key, bridge_canonical(payload), hashlib.sha256).hexdigest()


def bridge_call(url: str, key: bytes, action: str, extra: Optional[Dict[str, Any]] = None,
                timeout: float = 30) -> Dict[str, Any]:
    import urllib.request
    import urllib.error
    body: Dict[str, Any] = {
        "action": action,
        "ts": int(time.time()),
        "nonce": uuid.uuid4().hex,
        "machine": machine_id(),
    }
    if extra:
        body.update(extra)
    body["sig"] = bridge_sign({k: v for k, v in body.items() if k != "sig"}, key)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "Facteur-Padawan/1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as ex:
        raw = ex.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {ex.code}: {raw[:300]}") from ex
    except Exception as ex:
        raise RuntimeError(f"pont PHP : {ex}") from ex
    try:
        out = json.loads(raw)
    except json.JSONDecodeError as ex:
        raise RuntimeError(f"réponse JSON invalide : {raw[:200]}") from ex
    if not out.get("ok"):
        raise RuntimeError(out.get("error") or "erreur pont")
    return out


def bridge_create_schema(url: str, key: bytes) -> str:
    return str(bridge_call(url, key, "create_schema").get("message") or "OK")


def bridge_test(url: str, key: bytes) -> str:
    r = bridge_call(url, key, "ping")
    return str(r.get("message") or "ping OK")


def bridge_claim_pending(url: str, key: bytes, limit: int = 20) -> List[Dict[str, Any]]:
    r = bridge_call(url, key, "list_pending", {"limit": int(limit)})
    items = r.get("items") or []
    out = []
    for row in items:
        out.append(_row_to_cmd(row) if "uuid" in row else row)
    return out


def bridge_finish(url: str, key: bytes, cmd: Dict[str, Any], statut: str, resultat: str) -> None:
    bridge_call(url, key, "mark_done", {
        "incoming_id": cmd.get("_incoming_id"),
        "uuid": cmd.get("id"),
        "cmd_action": cmd.get("action"),  # ne pas écraser action=mark_done
        "params": cmd.get("params") or {},
        "statut": statut,
        "resultat": (resultat or "")[:4000],
    })


# ---------- Orchestration d'une boîte ----------
def fetch_pending(boite: Dict[str, Any], creds: Dict[str, Any], key: bytes) -> List[Dict[str, Any]]:
    mode = boite.get("mode") or "pont"
    if mode == "mysql":
        return mysql_claim_pending(creds, 20)
    url = (boite.get("pont_url") or "").strip()
    if not url:
        raise RuntimeError("URL du pont PHP manquante")
    return bridge_claim_pending(url, key, 20)


def finish_command(boite: Dict[str, Any], creds: Dict[str, Any], key: bytes,
                   cmd: Dict[str, Any], statut: str, resultat: str) -> None:
    mode = boite.get("mode") or "pont"
    if mode == "mysql":
        mysql_finish(creds, cmd, statut, resultat)
    else:
        bridge_finish((boite.get("pont_url") or "").strip(), key, cmd, statut, resultat)



def export_cle_php(key: bytes, out_path: str) -> str:
    """Écrit facteur_cle.php (clé hex) à déposer avec les pages PHP."""
    hexkey = key.hex()
    lines = [
        "<?php",
        "/** Généré par Facteur — ne pas publier ni committer. */",
        "declare(strict_types=1);",
        "if (basename($_SERVER['SCRIPT_FILENAME'] ?? '') === basename(__FILE__)) {",
        "    http_response_code(404); exit;",
        "}",
        f"$FACTEUR_KEY_HEX = '{hexkey}';",
        "",
    ]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    return out_path


def export_web_pack(key: bytes, dest_dir: str, test_suffix: str = "") -> Dict[str, str]:
    """Copie web/ + génère facteur_cle.php et le nom aléatoire de la page test."""
    import shutil
    import secrets
    import string
    if not test_suffix:
        test_suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    os.makedirs(dest_dir, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    src_web = os.path.join(here, "web")
    written: Dict[str, str] = {}
    if os.path.isdir(src_web):
        for name in os.listdir(src_web):
            if name.startswith("."):
                continue
            if name == "facteur_test_TEMPLATE.php":
                continue
            if name.startswith("facteur_test_") and name.endswith(".php"):
                continue  # on regénère un suffixe propre
            src = os.path.join(src_web, name)
            if os.path.isfile(src):
                dst = os.path.join(dest_dir, name)
                shutil.copy2(src, dst)
                written[name] = dst
    # config: copy exemple → config if absent
    ex = os.path.join(dest_dir, "facteur_boite_config.exemple.php")
    cfg = os.path.join(dest_dir, "facteur_boite_config.php")
    if os.path.isfile(ex) and not os.path.isfile(cfg):
        shutil.copy2(ex, cfg)
        written["facteur_boite_config.php"] = cfg
    cle = export_cle_php(key, os.path.join(dest_dir, "facteur_cle.php"))
    written["facteur_cle.php"] = cle
    tpl = os.path.join(src_web, "facteur_test_TEMPLATE.php")
    final_name = f"facteur_test_{test_suffix}.php"
    final = os.path.join(dest_dir, final_name)
    if os.path.isfile(tpl):
        shutil.copy2(tpl, final)
        written[final_name] = final
    written["_test_suffix"] = test_suffix
    written["_test_page"] = final_name
    note = os.path.join(dest_dir, "LISEZMOI-DEPLOIEMENT.txt")
    with open(note, "w", encoding="utf-8") as f:
        f.write(
            "Déploiement Boîte SQL Facteur\n"
            "==============================\n\n"
            "1) Remplis SEULEMENT $LOCAL_DB_PASS dans facteur_boite_config.php\n"
            "   (hôte localhost, user marcsevigny, base test déjà préremplis).\n"
            "   Option : $LOCAL_DB_INCLUDE vers un fichier de connexion existant.\n\n"
            "2) Dépose ce dossier en HTTPS sur ton serveur.\n\n"
            f"3) Page TEST (notifier seulement, pas de mot de passe) : {final_name}\n"
            "   Ne publie pas cette URL.\n\n"
            "4) Dans Facteur > Boîtes SQL : mode Pont, URL = …/facteur_boite.php\n"
            "   Aucun mot de passe MySQL sur le PC.\n\n"
            "5) facteur_cle.php = clé HMAC générée par Facteur — ne pas partager.\n"
        )
    written["LISEZMOI-DEPLOIEMENT.txt"] = note
    return written
