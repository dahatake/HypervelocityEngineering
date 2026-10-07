import json
import os
from datetime import datetime, timedelta

MAX_BYTES = 65536


class DraftError(Exception):
    pass


class DraftNotFoundError(DraftError):
    pass


class DraftTooLargeError(DraftError):
    pass


class DraftStore:
    def __init__(self, path, retention_days=30, clock=None):
        self._path = path
        self._retention = timedelta(days=retention_days)
        self._clock = clock or datetime.now
        self._data = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._write()

    def _write(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)

    def _expired(self, rec):
        return self._clock() - datetime.fromisoformat(rec["saved_at"]) >= self._retention

    @staticmethod
    def _key(user, form_id):
        return json.dumps([user, form_id])

    def save(self, user, form_id, data):
        if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
            raise DraftTooLargeError(form_id)
        self._data[self._key(user, form_id)] = {
            "user": user, "form_id": form_id, "data": data,
            "saved_at": self._clock().isoformat(),
        }
        self._write()

    def _live(self, user, form_id):
        rec = self._data.get(self._key(user, form_id))
        if rec is None or self._expired(rec):
            raise DraftNotFoundError(form_id)
        return rec

    def resume(self, user, form_id):
        return self._live(user, form_id)["data"]

    def list_drafts(self, user):
        return sorted(r["form_id"] for r in self._data.values()
                      if r["user"] == user and not self._expired(r))

    def submit(self, user, form_id):
        rec = self._live(user, form_id)
        del self._data[self._key(user, form_id)]
        self._write()
        return rec["data"]

    def purge_expired(self):
        dead = [k for k, r in self._data.items() if self._expired(r)]
        for k in dead:
            del self._data[k]
        self._write()
        return len(dead)
