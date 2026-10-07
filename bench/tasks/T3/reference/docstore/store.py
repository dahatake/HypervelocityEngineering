ROLE_RANK = {"viewer": 1, "editor": 2, "admin": 3}


class DocstoreError(Exception):
    pass


class DocumentExistsError(DocstoreError):
    pass


class DocumentNotFoundError(DocstoreError):
    pass


class PermissionDeniedError(DocstoreError):
    pass


class DocumentStore:
    """メモリ上の文書ストア。"""

    def __init__(self):
        self._docs = {}
        self._roles = {}

    def set_role(self, user, role, actor=None):
        if role not in ROLE_RANK:
            raise ValueError(role)
        if actor is not None:
            self._require(actor, "admin")
        self._roles[user] = role

    def get_role(self, user):
        return self._roles.get(user)

    def _require(self, user, minimum):
        if user is None:
            return
        role = self._roles.get(user)
        if role is None or ROLE_RANK[role] < ROLE_RANK[minimum]:
            raise PermissionDeniedError(user)

    def create(self, doc_id, content, user=None):
        self._require(user, "editor")
        if doc_id in self._docs:
            raise DocumentExistsError(doc_id)
        self._docs[doc_id] = content

    def read(self, doc_id, user=None):
        self._require(user, "viewer")
        try:
            return self._docs[doc_id]
        except KeyError:
            raise DocumentNotFoundError(doc_id) from None

    def update(self, doc_id, content, user=None):
        self._require(user, "editor")
        self.read(doc_id)
        self._docs[doc_id] = content

    def delete(self, doc_id, user=None):
        self._require(user, "admin")
        self.read(doc_id)
        del self._docs[doc_id]

    def list_ids(self, user=None):
        self._require(user, "viewer")
        return sorted(self._docs)
