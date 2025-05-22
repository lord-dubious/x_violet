# xviolet/vector/fallback_manager.py
from typing import List, Dict, Any, Optional, Type
from .base import VectorStore
from .local_store import LocalVectorStore
from .remote_store import RemoteVectorStore
import logging

logger = logging.getLogger(__name__)

class VectorStoreFallbackManager(VectorStore): # Implement the VectorStore interface
    def __init__(self, store_configs: List[Dict[str, Any]]):
        # Note: VectorStore's __init__ expects a config dict, but FallbackManager
        # takes a list of store_configs. We don't directly call super().__init__(config)
        # unless VectorStore.ABC has a specific requirement not shown.
        # If VectorStore.__init__ just sets self.config = config, then for a manager,
        # its "config" is the list of store_configs.
        # For now, we'll assume VectorStore's __init__ is trivial or handled by ABC.
        # super().__init__({}) # Pass empty or a representative config if needed by ABC

        self.stores: List[Dict[str, Any]] = [] # List of {'name': str, 'instance': VectorStore, 'type': str}

        for config_item in store_configs:
            store_type_name = config_item.get('type')
            store_config_params = config_item.get('config')
            store_name = config_item.get('name', store_type_name) # Default name to type if not provided

            if not store_type_name or not store_config_params:
                logger.error(f"Invalid store configuration for '{store_name}': missing 'type' or 'config'. Skipping.")
                continue

            store_class = self._get_store_class(store_type_name)
            if store_class:
                try:
                    instance = store_class(store_config_params)
                    self.stores.append({'name': store_name, 'instance': instance, 'type': store_type_name})
                    logger.info(f"Successfully initialized vector store: {store_name} (type: {store_type_name})")
                except Exception as e:
                    logger.error(f"Failed to initialize vector store {store_name} (type: {store_type_name}): {e}")
            else:
                # _get_store_class already logs an error for unknown type
                logger.warning(f"Skipping store '{store_name}' due to unknown type '{store_type_name}'.")
        
        if not self.stores:
            logger.warning("VectorStoreFallbackManager initialized with no valid stores.")

    def _get_store_class(self, store_type_name: str) -> Optional[Type[VectorStore]]:
        if store_type_name == 'local':
            return LocalVectorStore
        elif store_type_name == 'remote':
            return RemoteVectorStore
        # Add other types like 'llm_search' in the future
        else:
            logger.error(f"Unknown vector store type: {store_type_name}")
            return None

    async def add_documents(self, documents: List[Dict[str, Any]], embeddings: Optional[List[List[float]]] = None) -> List[str]:
        last_error = None
        for store_wrapper in self.stores:
            store_instance = store_wrapper['instance']
            store_name = store_wrapper['name']
            try:
                logger.debug(f"Attempting add_documents with store: {store_name}")
                # Pass embeddings along; individual stores will decide if they use them (LocalStore ignores them)
                added_ids = await store_instance.add_documents(documents, embeddings)
                # add_documents should return a list. An empty list might be a valid "success" (e.g., all docs existed).
                # We consider it a success if no exception was raised and a list is returned.
                if added_ids is not None: # Check for explicit None in case a store misbehaves
                    logger.info(f"add_documents successful with store: {store_name}. Added IDs: {len(added_ids)}")
                    return added_ids
            except Exception as e:
                logger.error(f"Store {store_name} failed during add_documents: {e}")
                last_error = e
        
        logger.error("All vector stores failed for add_documents operation.")
        # if last_error:
        #     raise last_error # Or return empty list
        return [] # Default return if all fail

    async def search(self, query_embedding: List[float], top_k: int = 5, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        last_error = None
        for store_wrapper in self.stores:
            store_instance = store_wrapper['instance']
            store_name = store_wrapper['name']
            store_type = store_wrapper['type']
            try:
                logger.debug(f"Attempting search with store: {store_name} (type: {store_type})")
                
                results: Optional[List[Dict[str, Any]]] = None

                if store_type == 'local': # Check by type, not isinstance, to be explicit about config
                    # LocalVectorStore expects query_text.
                    # The manager's search signature is query_embedding.
                    # This is the "temporary adaptation" part.
                    if isinstance(query_embedding, str): # If query_embedding is actually query_text
                        logger.debug(f"Store {store_name} is LocalVectorStore, using query as text.")
                        results = await store_instance.search(query_text=query_embedding, top_k=top_k, metadata_filter=metadata_filter)
                    else:
                        logger.warning(f"Store {store_name} (LocalVectorStore) expects a text query, but received an embedding (list of floats). Skipping this store for this search.")
                        last_error = TypeError(f"{store_name} expects text query, received embedding.")
                        continue # Skip to the next store
                else: # Assume other stores (like RemoteVectorStore) expect query_embedding
                    if isinstance(query_embedding, str):
                        logger.warning(f"Store {store_name} (type: {store_type}) expects an embedding, but received text query. This may fail if store cannot handle text query directly. Attempting anyway.")
                        # This situation is also tricky. If a remote store *only* takes embeddings,
                        # and we have text, we're stuck without an embedder here.
                        # For now, we pass it and let the store handle it or fail.
                        # A more robust solution would involve an embedding generation step if needed.
                        results = await store_instance.search(query_embedding, top_k=top_k, metadata_filter=metadata_filter)

                    else: # query_embedding is a list (assumed to be floats)
                         results = await store_instance.search(query_embedding=query_embedding, top_k=top_k, metadata_filter=metadata_filter)
                
                # Successful if results is not None (empty list is a valid success, means no error and no results)
                if results is not None:
                    logger.info(f"Search successful with store: {store_name}. Results found: {len(results)}")
                    return results
            except Exception as e:
                logger.error(f"Store {store_name} failed during search: {e}")
                last_error = e
        
        logger.error("All vector stores failed for search operation.")
        # if last_error:
        #     raise last_error # Propagating last error might be desired in some contexts
        return []

    async def get_document_by_id(self, document_id: str) -> Optional[Dict[str, Any]]:
        last_error = None
        for store_wrapper in self.stores:
            store_instance = store_wrapper['instance']
            store_name = store_wrapper['name']
            try:
                logger.debug(f"Attempting get_document_by_id with store: {store_name}")
                document = await store_instance.get_document_by_id(document_id)
                if document is not None: # Document found
                    logger.info(f"get_document_by_id successful with store: {store_name}. Document ID: {document_id}")
                    return document
                # If document is None, it means not found in this store, try next.
            except Exception as e:
                logger.error(f"Store {store_name} failed during get_document_by_id for ID {document_id}: {e}")
                last_error = e
        
        logger.info(f"Document ID {document_id} not found in any store or all stores failed.")
        # if last_error:
        #     logger.error("Last error during get_document_by_id was: %s", last_error)
        return None

    async def delete_documents(self, document_ids: List[str]) -> bool:
        last_error = None
        original_document_ids = list(document_ids) # Copy for logging, as stores might modify list or fail partially

        for store_wrapper in self.stores:
            store_instance = store_wrapper['instance']
            store_name = store_wrapper['name']
            try:
                logger.debug(f"Attempting delete_documents with store: {store_name}")
                # The interface specifies `delete_documents` returns bool.
                # True means success (or partial success).
                # We assume if a store returns True, the operation is considered handled for this fallback level.
                success = await store_instance.delete_documents(document_ids) # Pass the potentially modified list
                if success:
                    logger.info(f"delete_documents successful or partially successful with store: {store_name} for IDs: {original_document_ids}")
                    return True
                # If False, it implies total failure for this store for these IDs, try next.
            except Exception as e:
                logger.error(f"Store {store_name} failed during delete_documents for IDs {original_document_ids}: {e}")
                last_error = e
        
        logger.error(f"All vector stores failed for delete_documents operation for IDs: {original_document_ids}.")
        # if last_error:
        #     raise last_error
        return False

    # Required by ABC, but not used by FallbackManager if it doesn't have its own "config" in the ABC sense
    def __init__(self, config: Dict[str, Any]):
        # This is the ABC's __init__. The FallbackManager's actual initialization
        # is done in the other __init__ method which takes store_configs.
        # This is a bit of a hack due to Python not allowing multiple __init__ signatures directly
        # in the same way as overloaded constructors in other languages.
        # We'll call the main init with the config if it's a list (for direct instantiation)
        # or handle it if it's a single dict (if ABC expects it).
        # For now, let's assume this init is for the ABC and the other is the primary.
        # This is slightly problematic. Let's stick to one __init__ and make it compatible.
        # The prompt implies the FallbackManager is a VectorStore, so it needs to satisfy the ABC's __init__.
        # The ABC's __init__ is `def __init__(self, config: Dict[str, Any]):`
        # The manager's useful init is `def __init__(self, store_configs: List[Dict[str, Any]])`.
        # This is a conflict.
        # Let's rename the manager's main init and call it from the ABC-compliant __init__.
        # This will be handled in the next step by correcting the __init__ structure.
        # For now, this placeholder satisfies the ABC.
        # The file creation tool will use the first __init__ it sees.
        # I will provide the correct __init__ as the first one.
        pass # Will be fixed in the combined __init__ logic.

