import os
import json
import re as re_module
import secrets
import threading
from datetime import datetime, timezone, timedelta
import dotenv

dotenv.load_dotenv()

DB_TYPE = os.getenv("DB_TYPE").strip().lower()


def _gen_id() -> str:
    return secrets.token_hex(12)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _matches_filter(doc: dict, filter_dict: dict) -> bool:
    for key, condition in filter_dict.items():
        doc_val = doc.get(key)

        if isinstance(condition, dict):
            for op, operand in condition.items():
                if op == "$regex":
                    pattern = operand.get("$regex") if isinstance(operand, dict) else operand
                    opts = operand.get("$options", "") if isinstance(operand, dict) else ""
                    flags = 0
                    if "i" in opts:
                        flags |= re_module.IGNORECASE
                    if not re_module.search(pattern, str(doc_val or ""), flags):
                        return False
                elif op == "$ne":
                    if doc_val == operand:
                        return False
                elif op == "$in":
                    if doc_val not in operand:
                        return False
                elif op == "$nin":
                    if doc_val in operand:
                        return False
                elif op == "$exists":
                    exists = key in doc and doc[key] is not None
                    if bool(operand) != exists:
                        return False
                else:
                    raise NotImplementedError(f"フィルタ演算子 {op} は未対応です")
        else:
            if doc_val != condition:
                return False
    return True


def _apply_updates(doc: dict, update_dict: dict):
    for op, fields in update_dict.items():
        if op == "$set":
            for k, v in fields.items():
                doc[k] = v
        elif op == "$addToSet":
            for k, v in fields.items():
                current = doc.get(k)
                if not isinstance(current, list):
                    current = []
                if v not in current:
                    current.append(v)
                doc[k] = current
        elif op == "$pull":
            for k, v in fields.items():
                current = doc.get(k)
                if isinstance(current, list) and v in current:
                    current.remove(v)
                    doc[k] = current


if DB_TYPE == "mongodb":
    from pymongo import MongoClient
    from bson import ObjectId

    MONGO_URI = os.getenv("MONGO_URI")
    DB_NAME = os.getenv("DB_NAME")

    _client = MongoClient(MONGO_URI)
    _mongo_db = _client[DB_NAME]
    _mongo_users = _mongo_db["Users"]
    _mongo_memos = _mongo_db["Memos"]
    _mongo_roles = _mongo_db["Roles"]

    _mongo_users.create_index("code", unique=True)
    _mongo_users.create_index("username", unique=True)

    class _MongoCollection:
        def __init__(self, col):
            self._col = col

        def _fix_id(self, d):
            if d is not None and "_id" in d and isinstance(d["_id"], str):
                d = dict(d)
                try:
                    d["_id"] = ObjectId(d["_id"])
                except Exception:
                    pass
            return d

        def find_one(self, filter_dict=None):
            return self._col.find_one(self._fix_id(filter_dict or {}))

        def find(self, filter_dict=None):
            return self._col.find(self._fix_id(filter_dict or {}))

        def insert_one(self, doc):
            return self._col.insert_one(doc)

        def insert_many(self, docs):
            return self._col.insert_many(docs)

        def update_one(self, filter_dict, update_dict):
            return self._col.update_one(self._fix_id(filter_dict), update_dict)

        def update_many(self, filter_dict, update_dict):
            return self._col.update_many(self._fix_id(filter_dict), update_dict)

        def delete_one(self, filter_dict):
            return self._col.delete_one(self._fix_id(filter_dict))

        def count_documents(self, filter_dict=None):
            return self._col.count_documents(self._fix_id(filter_dict or {}))

        def create_index(self, field, **kwargs):
            return self._col.create_index(field, **kwargs)

        def cleanup_expired(self):
            pass

    users_col = _MongoCollection(_mongo_users)
    memos_col = _MongoCollection(_mongo_memos)
    roles_col = _MongoCollection(_mongo_roles)


elif DB_TYPE == "sqlite":
    import sqlite3

    SQLITE_PATH = os.getenv("SQLITE_PATH")

    _local = threading.local()

    def _get_conn():
        if not hasattr(_local, "conn") or _local.conn is None:
            _local.conn = sqlite3.connect(SQLITE_PATH)
            _local.conn.row_factory = sqlite3.Row
            _local.conn.execute("PRAGMA journal_mode=WAL")
        return _local.conn

    _init_conn = sqlite3.connect(SQLITE_PATH)
    _init_conn.execute("PRAGMA journal_mode=WAL")
    _init_conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            collection TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT
        )
    """)
    _init_conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_collection ON documents(collection)")
    _init_conn.commit()
    _init_conn.close()

    class _JsonCollection:
        def __init__(self, name, ttl_seconds=None):
            self.name = name
            self._ttl_seconds = ttl_seconds

        def _deserialize(self, row):
            if row is None:
                return None
            doc = json.loads(row["data"])
            doc["_id"] = row["id"]
            if row["created_at"] and "createdAt" not in doc:
                doc["createdAt"] = row["created_at"]
            return doc

        def _all_docs(self):
            conn = _get_conn()
            rows = conn.execute(
                "SELECT id, data, created_at FROM documents WHERE collection = ? ORDER BY rowid",
                (self.name,)
            ).fetchall()
            return [self._deserialize(r) for r in rows]

        def _save(self, doc):
            conn = _get_conn()
            doc_id = doc.pop("_id", _gen_id())
            created_at = doc.pop("createdAt", None) or _now_iso()
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO documents (id, collection, data, created_at) VALUES (?, ?, ?, ?)",
                (doc_id, self.name, json.dumps(doc, ensure_ascii=False), created_at)
            )
            conn.commit()
            doc["_id"] = doc_id
            doc["createdAt"] = created_at
            return doc_id

        def _delete(self, doc_id):
            conn = _get_conn()
            conn.execute(
                "DELETE FROM documents WHERE id = ? AND collection = ?",
                (doc_id, self.name)
            )
            conn.commit()

        def find_one(self, filter_dict=None):
            filter_dict = filter_dict or {}
            for doc in self._all_docs():
                if _matches_filter(doc, filter_dict):
                    return doc
            return None

        def find(self, filter_dict=None):
            return _JsonCursor(self, filter_dict or {})

        def insert_one(self, doc):
            return self._save(dict(doc))

        def insert_many(self, docs):
            ids = []
            for doc in docs:
                ids.append(self._save(dict(doc)))
            return ids

        def update_one(self, filter_dict, update_dict):
            doc = self.find_one(filter_dict)
            if doc:
                _apply_updates(doc, update_dict)
                self._save(doc)

        def update_many(self, filter_dict, update_dict):
            for doc in self._all_docs():
                if _matches_filter(doc, filter_dict):
                    _apply_updates(doc, update_dict)
                    self._save(doc)

        def delete_one(self, filter_dict):
            doc = self.find_one(filter_dict)
            if doc:
                self._delete(doc["_id"])

        def count_documents(self, filter_dict=None):
            filter_dict = filter_dict or {}
            return sum(1 for _ in self._all_docs() if _matches_filter(_, filter_dict))

        def create_index(self, field, **kwargs):
            expire = kwargs.get("expireAfterSeconds")
            if expire:
                self._ttl_seconds = expire

        def cleanup_expired(self):
            if not self._ttl_seconds:
                return
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._ttl_seconds)
            conn = _get_conn()
            rows = conn.execute(
                "SELECT id, data, created_at FROM documents WHERE collection = ?",
                (self.name,)
            ).fetchall()
            for row in rows:
                created = _parse_iso(row["created_at"])
                if created and created < cutoff:
                    conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
            conn.commit()

    class _JsonCursor:
        def __init__(self, collection, filter_dict):
            self.collection = collection
            self.filter_dict = filter_dict
            self._sort = None
            self._limit = None
            self._skip = None

        def sort(self, key, direction):
            self._sort = (key, direction)
            return self

        def limit(self, n):
            self._limit = n
            return self

        def skip(self, n):
            self._skip = n
            return self

        def __iter__(self):
            docs = [d for d in self.collection._all_docs()
                    if _matches_filter(d, self.filter_dict)]

            if self._sort:
                key, direction = self._sort
                reverse = direction < 0
                docs.sort(key=lambda d: d.get(key, "") or "", reverse=reverse)

            skip = self._skip or 0
            limit = self._limit or len(docs)
            return iter(docs[skip:skip + limit])

    users_col = _JsonCollection("users")
    memos_col = _JsonCollection("memos")
    roles_col = _JsonCollection("roles")


elif DB_TYPE in ("postgresql", "postgres", "psql"):
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor

    POSTGRESQL_URL = os.getenv("POSTGRESQL_URL")
    _pg_pool = pool.ThreadedConnectionPool(1, 10, POSTGRESQL_URL)

    def _get_conn():
        return _pg_pool.getconn()

    def _put_conn(conn):
        _pg_pool.putconn(conn)

    _tmp = _get_conn()
    _tmp.autocommit = True
    cur = _tmp.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            collection TEXT NOT NULL,
            data JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_collection ON documents(collection)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_collection_data ON documents USING GIN (collection, data jsonb_path_ops)")
    cur.close()
    _put_conn(_tmp)

    class _PgJsonCollection:
        def __init__(self, name, ttl_seconds=None):
            self.name = name
            self._ttl_seconds = ttl_seconds

        def _all_docs(self):
            conn = _get_conn()
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(
                    "SELECT id, data, created_at FROM documents WHERE collection = %s ORDER BY created_at",
                    (self.name,)
                )
                rows = cur.fetchall()
                cur.close()
                result = []
                for row in rows:
                    doc = dict(row["data"])
                    doc["_id"] = row["id"]
                    if row["created_at"] and "createdAt" not in doc:
                        doc["createdAt"] = row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"]
                    result.append(doc)
                return result
            finally:
                _put_conn(conn)

        def _save(self, doc):
            conn = _get_conn()
            try:
                doc_id = doc.pop("_id", _gen_id())
                created_at = doc.pop("createdAt", None) or _now_iso()
                if isinstance(created_at, datetime):
                    created_at_str = created_at.isoformat()
                else:
                    created_at_str = created_at

                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO documents (id, collection, data, created_at)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, created_at = EXCLUDED.created_at""",
                    (doc_id, self.name, json.dumps(doc, ensure_ascii=False), created_at_str)
                )
                cur.close()
                conn.commit()
                doc["_id"] = doc_id
                doc["createdAt"] = created_at_str
                return doc_id
            finally:
                _put_conn(conn)

        def _delete(self, doc_id):
            conn = _get_conn()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM documents WHERE id = %s AND collection = %s",
                            (doc_id, self.name))
                cur.close()
                conn.commit()
            finally:
                _put_conn(conn)

        def find_one(self, filter_dict=None):
            filter_dict = filter_dict or {}
            for doc in self._all_docs():
                if _matches_filter(doc, filter_dict):
                    return doc
            return None

        def find(self, filter_dict=None):
            return _PgJsonCursor(self, filter_dict or {})

        def insert_one(self, doc):
            return self._save(dict(doc))

        def insert_many(self, docs):
            ids = []
            for doc in docs:
                ids.append(self._save(dict(doc)))
            return ids

        def update_one(self, filter_dict, update_dict):
            doc = self.find_one(filter_dict)
            if doc:
                _apply_updates(doc, update_dict)
                self._save(doc)

        def update_many(self, filter_dict, update_dict):
            for doc in self._all_docs():
                if _matches_filter(doc, filter_dict):
                    _apply_updates(doc, update_dict)
                    self._save(doc)

        def delete_one(self, filter_dict):
            doc = self.find_one(filter_dict)
            if doc:
                self._delete(doc["_id"])

        def count_documents(self, filter_dict=None):
            filter_dict = filter_dict or {}
            return sum(1 for _ in self._all_docs() if _matches_filter(_, filter_dict))

        def create_index(self, field, **kwargs):
            expire = kwargs.get("expireAfterSeconds")
            if expire:
                self._ttl_seconds = expire

        def cleanup_expired(self):
            if not self._ttl_seconds:
                return
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._ttl_seconds)
            conn = _get_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM documents WHERE collection = %s AND created_at IS NOT NULL AND created_at < %s",
                    (self.name, cutoff)
                )
                cur.close()
                conn.commit()
            finally:
                _put_conn(conn)

    class _PgJsonCursor:
        def __init__(self, collection, filter_dict):
            self.collection = collection
            self.filter_dict = filter_dict
            self._sort = None
            self._limit = None
            self._skip = None

        def sort(self, key, direction):
            self._sort = (key, direction)
            return self

        def limit(self, n):
            self._limit = n
            return self

        def skip(self, n):
            self._skip = n
            return self

        def __iter__(self):
            docs = [d for d in self.collection._all_docs()
                    if _matches_filter(d, self.filter_dict)]
            if self._sort:
                key, direction = self._sort
                docs.sort(key=lambda d: d.get(key, "") or "", reverse=direction < 0)
            skip = self._skip or 0
            limit = self._limit or len(docs)
            return iter(docs[skip:skip + limit])

    users_col = _PgJsonCollection("users")
    memos_col = _PgJsonCollection("memos")
    roles_col = _PgJsonCollection("roles")

else:
    raise ValueError(
        f"DB_TYPE に未対応の値が指定されています: {DB_TYPE!r}  "
        f"（指定可能: mongodb / sqlite / postgresql）"
    )


memos_col.create_index("createdAt", expireAfterSeconds=86400)

memos_col.update_many(
    {"createdAt": {"$exists": False}},
    {"$set": {"createdAt": _now_iso()}}
)

if DB_TYPE != "mongodb":
    memos_col.cleanup_expired()
