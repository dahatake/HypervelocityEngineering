class DocstoreError(Exception):
    pass


class DocumentExistsError(DocstoreError):
    pass


class DocumentNotFoundError(DocstoreError):
    pass


class DocumentStore:
    """メモリ上の文書ストア。"""

    def __init__(self):
        self._docs = {}

    def create(self, doc_id, content):
        if doc_id in self._docs:
            raise DocumentExistsError(doc_id)
        self._docs[doc_id] = content

    def read(self, doc_id):
        try:
            return self._docs[doc_id]
        except KeyError:
            raise DocumentNotFoundError(doc_id) from None

    def update(self, doc_id, content):
        self.read(doc_id)
        self._docs[doc_id] = content

    def delete(self, doc_id):
        self.read(doc_id)
        del self._docs[doc_id]

    def list_ids(self):
        return sorted(self._docs)
