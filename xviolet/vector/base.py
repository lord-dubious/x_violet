# xviolet/vector/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class VectorStore(ABC):
    """
    Abstract base class for a vector store.
    """

    @abstractmethod
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the vector store with given configuration.
        Config might include paths, API keys, model names, etc.
        """
        pass

    @abstractmethod
    async def add_documents(self, documents: List[Dict[str, Any]], embeddings: Optional[List[List[float]]] = None) -> List[str]:
        """
        Add documents to the vector store.
        'documents' is a list of dictionaries, each representing a document with metadata.
        Each document should have an 'id' and 'text' field at minimum.
        'embeddings' (optional) are pre-computed embeddings for the documents.
        If embeddings are not provided, the method should generate them using an appropriate model.
        Should return a list of document IDs that were successfully added/updated.
        """
        pass

    @abstractmethod
    async def search(self, query_embedding: List[float], top_k: int = 5, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for similar documents.
        'query_embedding' is the embedding of the query text.
        'top_k' is the number of similar documents to return.
        'metadata_filter' (optional) allows filtering results based on document metadata.
        Should return a list of documents, each including its content, metadata, and similarity score.
        """
        pass
    
    @abstractmethod
    async def get_document_by_id(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a document by its ID.
        Returns the document dictionary or None if not found.
        """
        pass

    @abstractmethod
    async def delete_documents(self, document_ids: List[str]) -> bool:
        """
        Delete documents by their IDs.
        Returns True if deletion was successful (or partially successful), False otherwise.
        """
        pass

    # Optional: A method to get client or configuration, useful for fallback manager or diagnostics
    # def get_client_config(self) -> Dict[str, Any]:
    #     """ Returns underlying client or configuration details. """
    #     return {}
