# xviolet/vector/local_store.py
import sqlite3
from pathlib import Path
import sqlite_vec 
from typing import List, Dict, Any, Optional
import logging

from .base import VectorStore
from xviolet.config import config # Global config for embedding settings

logger = logging.getLogger(__name__)

class LocalVectorStore(VectorStore):
    def __init__(self, config_dict: Dict[str, Any]):
        super().__init__(config_dict) 
        
        if 'db_path' not in config_dict:
            raise ValueError("LocalVectorStore config missing 'db_path'")
            
        self.db_path = Path(config_dict['db_path'])
        logger.info(f"Initializing LocalVectorStore with DB path: {self.db_path}")
        
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create parent directory for DB {self.db_path.parent}: {e}")
            raise

        try:
            self.db = sqlite3.connect(str(self.db_path))
            self.db.enable_load_extension(True)
            
            try:
                sqlite_vec.load(self.db)
                logger.info("Successfully loaded sqlite_vec extension.")
            except Exception as e: 
                logger.error(f"Failed to load sqlite_vec extension: {e}")
                raise RuntimeError(f"sqlite_vec extension failed to load, LocalVectorStore cannot function: {e}")
            
            try:
                self.db.load_extension("rembed0") 
                logger.info("Successfully loaded 'rembed0' SQLite extension.")
            except sqlite3.OperationalError as e:
                logger.warning(f"'rembed0' SQLite extension not found or failed to load: {e}. "
                               "Ensure it's compiled and available. sqlite-rembed provides rembed().")
        except sqlite3.Error as e:
            logger.error(f"SQLite error during DB connection or extension loading: {e}")
            raise 
        finally:
            if hasattr(self, 'db') and self.db:
                 self.db.enable_load_extension(False)

        self._register_rembed_client() # Check if rembed() is available
        self._create_tables()
        logger.info("LocalVectorStore initialized successfully.")

    def _register_rembed_client(self):
        try:
            model_name = config.embedding_model
            # No explicit client registration needed for sqlite-rembed usually,
            # it picks up config from env or compile-time.
            # This function now serves as a check.
            self.db.execute("SELECT rembed(?, ?)", (model_name, "test")).fetchone()
            logger.info(f"rembed() SQL function appears to be callable with model: {model_name}.")
        except sqlite3.OperationalError as e:
            logger.error(f"rembed() SQL function is not callable: {e}. "
                           "Ensure sqlite-rembed is correctly set up and the model name is valid.")
            # Depending on strictness, you might raise an error here if rembed is critical
            # raise RuntimeError(f"rembed() function not available: {e}") from e


    def _create_tables(self):
        try:
            embedding_dimension = config.embedding_dim 
            
            # Create the virtual vector table using sqlite_vec
            # This table will store embeddings and allow similarity search
            # Its rowid will be implicitly linked to interactions_meta.id
            self.db.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS interactions_vectors USING vec0(
                    embedding BLOB({embedding_dimension}) 
                );
            """)
            # Note: sqlite_vec's vec0 virtual table usually has a column for the vector.
            # The name 'embedding' is conventional. The type BLOB or TEXT depends on rembed output.
            # sqlite-rembed's C API suggests it deals with text representations for SQL.
            # If rembed() returns text, TEXT({embedding_dimension}) might be more appropriate.
            # However, BLOB is often used for raw vector data.
            # Given the original VectorInteractionStore used TEXT, let's stick to that for consistency for now.
            # Re-evaluating: sqlite_vec examples often use TEXT for the vector column with rembed.
            # Let's use TEXT for now, assuming rembed output is text-serializable.
            self.db.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS interactions_vectors_temp USING vec0(
                    vector TEXT({embedding_dimension}) 
                );
            """)
            self.db.execute("DROP TABLE IF EXISTS interactions_vectors_temp;") # Drop if recreate with different type
            self.db.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS interactions_vectors USING vec0(
                    embedding TEXT({embedding_dimension}) 
                );
            """)


            # Create a metadata table
            # 'id' here will be the integer ID, also used as rowid for interactions_vectors
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS interactions_meta (
                    id INTEGER PRIMARY KEY, 
                    original_id TEXT UNIQUE, 
                    content TEXT NOT NULL
                ) STRICT;
            """)
            self.db.commit()
            logger.info("Tables 'interactions_vectors' (virtual) and 'interactions_meta' checked/created.")
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            raise

    def has_interacted(self, int_doc_id: int) -> bool: # Changed to accept int_doc_id
        """Check if a document/interaction with the given integer ID exists."""
        try:
            cur = self.db.execute("SELECT 1 FROM interactions_meta WHERE id = ?", (int_doc_id,))
            return cur.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Error checking for interaction (int_id: {int_doc_id}): {e}")
            return False 

    async def add_documents(self, documents: List[Dict[str, Any]], embeddings: Optional[List[List[float]]] = None) -> List[str]:
        logger.info(f"Attempting to add {len(documents)} documents. This is a synchronous operation wrapped in async def.")
        if embeddings:
            logger.warning("Pre-computed embeddings were provided but are ignored by LocalVectorStore as it uses internal sqlite-rembed.")
        
        added_original_ids = []
        for doc in documents:
            original_doc_id_str = doc.get('id')
            doc_text = doc.get('text')

            if not original_doc_id_str or not doc_text:
                logger.warning(f"Skipping document with missing original_id or text: {doc}")
                continue
            
            try:
                # Attempt to use original_doc_id_str as integer if possible,
                # otherwise let SQLite assign a rowid and store original_id_str separately.
                # For simplicity and consistency with original VectorInteractionStore (tweet_id as int),
                # we'll require original_doc_id_str to be an integer string.
                int_doc_id = int(original_doc_id_str)
            except ValueError:
                logger.error(f"Document ID '{original_doc_id_str}' is not an integer string. Skipping add. "
                               "LocalVectorStore currently requires integer-convertible IDs.")
                continue
            
            if self.has_interacted(int_doc_id):
                logger.debug(f"Document with int_id {int_doc_id} (original: {original_doc_id_str}) already exists. Skipping add.")
                continue
            
            try:
                model = config.embedding_model 
                
                # Insert into metadata table first to get the rowid (which is int_doc_id here)
                self.db.execute(
                    "INSERT INTO interactions_meta(id, original_id, content) VALUES(?, ?, ?)",
                    (int_doc_id, original_doc_id_str, doc_text),
                )
                # Then insert into the vector table using the same rowid
                self.db.execute(
                    "INSERT INTO interactions_vectors(rowid, embedding) VALUES(?, rembed(?, ?))",
                    (int_doc_id, model, doc_text),
                )
                self.db.commit()
                added_original_ids.append(original_doc_id_str)
                logger.debug(f"Added document original_id: {original_doc_id_str} (as int_id: {int_doc_id})")
            except sqlite3.IntegrityError:
                logger.warning(f"Document int_id {int_doc_id} (original: {original_doc_id_str}) likely already exists (IntegrityError). Skipping.")
            except Exception as e:
                logger.error(f"Failed to add document original_id {original_doc_id_str} (int_id: {int_doc_id}): {e}")
        
        logger.info(f"Successfully added {len(added_original_ids)} out of {len(documents)} documents.")
        return added_original_ids

    async def search(self, query_text: str, top_k: int = 5, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        logger.warning("LocalVectorStore.search expects a text query (query_text), deviating from VectorStore interface (query_embedding). This is a synchronous operation wrapped in async def.")
        if metadata_filter:
            logger.warning("LocalVectorStore.search does not currently support metadata_filter.")
        
        results = []
        try:
            model = config.embedding_model 
            
            # The join is ON v.rowid = m.id, where m.id is now the integer PK.
            cur = self.db.execute(
                f"""
                SELECT m.original_id, m.content, v.distance
                FROM interactions_vectors v JOIN interactions_meta m ON v.rowid = m.id
                WHERE v.embedding MATCH rembed(?, ?) 
                ORDER BY v.distance
                LIMIT ?
                """,
                (model, query_text, top_k),
            )
            
            for row in cur.fetchall():
                # row[0] is m.original_id (string), row[1] is m.content, row[2] is v.distance
                results.append({'id': str(row[0]), 'text': row[1], 'score': row[2], 'metadata': {}})
            logger.info(f"Search for '{query_text[:50]}...' returned {len(results)} results.")
        except sqlite3.OperationalError as e:
             logger.error(f"Search failed for query '{query_text[:50]}...': {e}. This might be due to 'rembed0' or 'sqlite_vec' issues.")
        except Exception as e:
            logger.error(f"Search failed for query '{query_text[:50]}...': {e}")
        return results
        
    async def get_document_by_id(self, document_id_str: str) -> Optional[Dict[str, Any]]:
        logger.info(f"Attempting to get document by original_id: {document_id_str}. This is a synchronous operation.")
        try:
            # Query by original_id from interactions_meta
            cur = self.db.execute(
                "SELECT id, original_id, content FROM interactions_meta WHERE original_id = ?", (document_id_str,)
            )
            row = cur.fetchone()
            if row:
                # Return original_id as 'id' in the result, consistent with input
                return {'id': row[1], 'text': row[2], 'metadata': {}} 
            else:
                return None
        except Exception as e:
            logger.error(f"Failed to get document by original_id {document_id_str}: {e}")
            return None

    async def delete_documents(self, document_ids_str_list: List[str]) -> bool:
        logger.info(f"Attempting to delete {len(document_ids_str_list)} documents by original_id. This is a synchronous operation.")
        all_successful = True
        try:
            for original_id_str in document_ids_str_list:
                try:
                    # First, get the integer id from interactions_meta using original_id_str
                    cur_get_id = self.db.execute("SELECT id FROM interactions_meta WHERE original_id = ?", (original_id_str,))
                    id_row = cur_get_id.fetchone()

                    if not id_row:
                        logger.warning(f"No document found with original_id {original_id_str} to delete.")
                        continue # Skip if not found in meta, implies not in vector table either

                    int_doc_id = id_row[0]
                    
                    # Delete from interactions_meta using the integer id (PK)
                    cur_meta = self.db.execute("DELETE FROM interactions_meta WHERE id = ?", (int_doc_id,))
                    if cur_meta.rowcount == 0: # Should not happen if fetched above, but good check
                        logger.warning(f"Failed to delete from interactions_meta for int_id {int_doc_id} (original: {original_id_str}).")
                        all_successful = False
                        continue # If meta delete fails, maybe don't delete vector? Or proceed? For now, proceed.
                    
                    # Delete from interactions_vectors using the integer rowid
                    cur_vec = self.db.execute("DELETE FROM interactions_vectors WHERE rowid = ?", (int_doc_id,))
                    if cur_vec.rowcount == 0:
                        logger.warning(f"No vector found in interactions_vectors for rowid {int_doc_id} (original: {original_id_str}). This might be an inconsistency.")
                        # This could be okay if meta existed but vector didn't, but implies inconsistency
                        # all_successful = False # Optional: mark as not fully successful if vector part missing
                except sqlite3.Error as e:
                    logger.error(f"Failed to delete document with original_id {original_id_str}: {e}")
                    all_successful = False
            self.db.commit()
            logger.info("Deletion attempt completed.")
            return all_successful
        except Exception as e:
            logger.error(f"General error during batch deletion: {e}")
            return False

    def close(self):
        """Close the database connection."""
        if hasattr(self, 'db') and self.db:
            self.db.close()
            logger.info("Database connection closed.")

# Example usage for direct testing (not run during normal agent operation)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    class MockAgentConfig: # Renamed to avoid conflict with actual AgentConfig
        embedding_model = "mock-model-for-rembed" 
        gemini_api_key = "mock_api_key" # Not used by sqlite-rembed if pre-configured
        embedding_dim = 768 # Example, ensure this matches your rembed model output if testing real embeddings

    # Replace global config with mock for this test script
    from xviolet import config as global_agent_config
    original_config_embedding_model = global_agent_config.embedding_model
    original_config_gemini_api_key = global_agent_config.gemini_api_key
    original_config_embedding_dim = global_agent_config.embedding_dim
    
    global_agent_config.embedding_model = MockAgentConfig.embedding_model
    global_agent_config.gemini_api_key = MockAgentConfig.gemini_api_key
    global_agent_config.embedding_dim = MockAgentConfig.embedding_dim


    test_db_path = Path(__file__).parent / "test_local_store.db"
    if test_db_path.exists():
        test_db_path.unlink()

    store_config_dict = {'db_path': str(test_db_path)}
    vector_store = None # Initialize to None

    async def main_test_local_store(): # Renamed test function
        nonlocal vector_store # Allow assignment to outer scope variable
        vector_store = LocalVectorStore(store_config_dict)
        logger.info("--- Testing LocalVectorStore ---")

        docs_to_add = [
            {'id': '1001', 'text': 'The quick brown fox jumps over the lazy dog.'},
            {'id': '1002', 'text': 'Exploring the vastness of space and cosmic wonders.'},
            {'id': '1003', 'text': 'Artificial intelligence is reshaping industries.'},
            {'id': '1004', 'text': 'Another document about space exploration and planets.'},
            {'id': 'non_integer_id_string', 'text': 'This document has a non-integer string ID.'}, # Should be skipped
            {'id': '1005', 'text': 'A document about culinary arts.'},
        ]
        added_ids = await vector_store.add_documents(docs_to_add)
        logger.info(f"Added document original IDs: {added_ids}")
        assert '1001' in added_ids
        assert '1005' in added_ids
        assert 'non_integer_id_string' not in added_ids

        retrieved_doc = await vector_store.get_document_by_id('1001')
        logger.info(f"Retrieved doc '1001': {retrieved_doc}")
        assert retrieved_doc and retrieved_doc['text'] == docs_to_add[0]['text']
        assert retrieved_doc['id'] == '1001'

        missing_doc = await vector_store.get_document_by_id('9999')
        logger.info(f"Retrieved doc '9999' (should be None): {missing_doc}")
        assert missing_doc is None
        
        # This search will likely fail if rembed() isn't functional in the test environment
        # (e.g., if sqlite-rembed C extension isn't properly compiled/loaded with a model)
        logger.info("Attempting search (may return empty or fail if rembed() is not functional)...")
        search_query = "information about space"
        search_results = await vector_store.search(search_query, top_k=2)
        logger.info(f"Search results for '{search_query}': {search_results}")
        if not search_results:
             logger.warning("Search returned no results. This is expected if rembed() is not functional in the test env.")
        # Example assertion if rembed works:
        # if search_results: assert any(r['id'] == '1002' for r in search_results)

        # Test deletion
        delete_success = await vector_store.delete_documents(['1001', '1003', '8888']) # 2 existing, 1 non-existing
        logger.info(f"Deletion success status: {delete_success}")
        # `all_successful` is True if all operations attempted without SQLite error, even if some IDs not found.
        # Modify assertion based on desired strictness for "not found". Current logic returns True if no SQL errors.
        assert delete_success 
        
        assert await vector_store.get_document_by_id('1001') is None
        assert await vector_store.get_document_by_id('1003') is None
        assert await vector_store.get_document_by_id('1002') is not None # Should still be there

        logger.info("--- LocalVectorStore tests completed ---")

    import asyncio
    try:
        asyncio.run(main_test_local_store())
    finally:
        if vector_store:
            vector_store.close()
        if test_db_path.exists():
            test_db_path.unlink()
        # Restore global config
        global_agent_config.embedding_model = original_config_embedding_model
        global_agent_config.gemini_api_key = original_config_gemini_api_key
        global_agent_config.embedding_dim = original_config_embedding_dim
        logger.info("Test cleanup finished and global config restored.")
