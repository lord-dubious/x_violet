"""
Main agent loop for x_violet: integrates LLM, persona, ActionManager, and TwitterClient.
- Handles polling, LLM-driven action selection, and dispatch.
- Avoids duplicate interactions using interactions.json
"""
import logging
import asyncio
import time
import random
from pathlib import Path
import os # Added os import
from xviolet.config import config
from xviolet.provider.llm import LLMManager
from xviolet.actions import ActionManager
from xviolet.client.twitter_client import TwitterClient
from xviolet.media_tracker import load_used_media, mark_media_as_used, is_media_used
from xviolet.vector.fallback_manager import VectorStoreFallbackManager
from xviolet.persona import Persona
from xviolet.scheduler import Scheduler # ADDED Scheduler import

logger = logging.getLogger("xviolet.agent")

class XVioletAgent:
    def __init__(self):
        self.config = config
        # self.llm = LLMManager() # LLMManager will be initialized later with provider configs
        self.twitter = TwitterClient()
        self.actions = ActionManager(self.twitter)
        self.used_media_set = load_used_media()
        # self.current_new_tweet_context_docs = [] # REMOVED as per cleanup task

        # Load Persona
        self.persona: Optional[Persona] = None
        if self.config.character_file and os.path.exists(self.config.character_file):
            try:
                self.persona = Persona(self.config.character_file)
                logger.info(f"Persona loaded successfully from {self.config.character_file}")
            except Exception as e:
                logger.error(f"Failed to load persona from {self.config.character_file}: {e}", exc_info=True)
        else:
            logger.warning(f"Persona file not configured or not found: {self.config.character_file}. Proceeding without persona.")

        # Initialize LLMManager (now LLMFallbackManager)
        # This was deferred from the original plan, but it's better to have it here.
        # The agent's LLMManager should use the LLM provider configs from AgentConfig.
        from xviolet.llm.fallback_manager import LLMFallbackManager as LLMManager_Fallback # Alias to avoid name clash
        try:
            logger.info("Initializing LLMFallbackManager...")
            # AgentConfig stores the list of dicts in self.config.llm_provider_configs
            self.llm = LLMManager_Fallback(llm_provider_configs=self.config.llm_provider_configs)
            logger.info("LLMFallbackManager initialized successfully.")
            if not self.llm.is_enabled: # Check if any providers were actually loaded
                 logger.warning("LLMFallbackManager has no enabled providers. LLM functionality will be offline.")
        except Exception as e:
            logger.error(f"Failed to initialize LLMFallbackManager: {e}", exc_info=True)
            self.llm = None # Set to None if initialization fails

        try:
            logger.info("Initializing VectorStoreFallbackManager...")
            manager_init_config = {'store_configs_list': self.config.vector_store_configs}
            self.vector_store_manager = VectorStoreFallbackManager(manager_init_config)
            logger.info("VectorStoreFallbackManager initialized successfully.")
        except Exception as e: 
            logger.error(f"Failed to initialize VectorStoreFallbackManager: {e}", exc_info=True)
            self.vector_store_manager = None
        
        # Initialize Scheduler
        try:
            logger.info("Initializing Scheduler...")
            self.scheduler = Scheduler(
                config=self.config,
                llm_manager=self.llm, # LLMFallbackManager instance
                vector_store_manager=self.vector_store_manager,
                twitter_client=self.twitter,
                persona=self.persona,
                used_media_set=self.used_media_set, # Pass the live set
                mark_media_as_used_func=mark_media_as_used # Pass the function
            )
            logger.info("Scheduler initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Scheduler: {e}", exc_info=True)
            self.scheduler = None

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    async def run_once(self):
        # 1. Fetch timeline/tweets to consider
        # Authenticate before polling - login() is async, so await it
        await self.twitter.login() # MODIFIED: Direct await
        timeline = await self.twitter.poll() # MODIFIED: Direct await
        # Limit number of tweets processed per cycle
        limit = self.config.max_actions_processing
        timeline = timeline[:limit]
        if not timeline:
            logger.info("No tweets to process.")
            return
        for tweet_obj in timeline: # tweet_obj is now a twikit.Tweet object
            try:
                user_obj = getattr(tweet_obj, 'author', None)
                if not user_obj:
                    logger.warning(f"Tweet object {getattr(tweet_obj, 'id', 'Unknown ID')} missing author. Skipping.")
                    continue

                # Reconstruct tweet dictionary for compatibility
                tweet_id_str = str(getattr(tweet_obj, 'id', None))
                tweet_text = getattr(tweet_obj, 'text', None)
                
                user_screen_name = getattr(user_obj, 'screen_name', None)
                if not user_screen_name: # Fallback to username if screen_name is not available
                    user_screen_name = getattr(user_obj, 'username', 'unknown_user')
                
                user_display_name = getattr(user_obj, 'name', 'Unknown User')

                # media_path is not provided by poll() in its current form
                media_path = None 
                
                # Determine conversation status
                # Assuming 'replied_to' or 'in_reply_to_status_id' or similar attribute indicates a reply
                # twikit.Tweet objects often have `in_reply_to_tweet_id` or similar
                conversation_flag = bool(getattr(tweet_obj, 'in_reply_to_tweet_id', None))

                processed_tweet_data = {
                    "id": tweet_id_str,
                    "text": tweet_text,
                    "user": {
                        "screen_name": user_screen_name,
                        "name": user_display_name,
                        # Add other user fields if build_action_prompt uses them:
                        "id": str(getattr(user_obj, 'id', None)), 
                    },
                    "media_path": media_path,
                    "conversation": conversation_flag,
                    "raw_tweet_obj": tweet_obj # Optional: include raw object if useful later
                }

                if not tweet_id_str or not tweet_text:
                    logger.warning(f"Could not extract essential data (ID or text) from tweet_obj: {tweet_obj}. Skipping.")
                    continue
                
                logger.debug(f"Processing tweet: ID {processed_tweet_data['id']}, Text: {processed_tweet_data['text']}")

                # 2. Build LLM prompt (persona, tweet, context, available actions)
                prompt = self.llm.build_action_prompt(
                    persona_path=self.config.character_file,
                    tweet=processed_tweet_data['text'],
                    user=processed_tweet_data['user'], # Pass the reconstructed user dictionary
                    available_actions=self.actions.SUPPORTED_ACTIONS,
                    context=processed_tweet_data # Pass the full reconstructed dict as context
                )
                # 3. Ask LLM to select action and generate text (if needed)
                llm_result = self.llm.generate_structured_output(prompt)
                action = llm_result.get("action")
                initial_generated_text = llm_result.get("text") # Renamed for clarity
                final_generated_text_for_dispatch = initial_generated_text # Start with the initial version

                # Contextual Search and Refinement for Replies
                if action == "reply" and initial_generated_text: # Check initial_generated_text before proceeding
                    reply_context_documents = []
                    if self.vector_store_manager:
                        original_tweet_text_for_context = processed_tweet_data.get('text')
                        if original_tweet_text_for_context:
                            try:
                                logger.info(f"Reply action: Searching VS for context related to: '{original_tweet_text_for_context[:100]}...'")
                                reply_context_documents = await self.vector_store_manager.search(
                                    query_embedding=original_tweet_text_for_context, # Manager handles text query for local store
                                    top_k=3
                                )
                                if reply_context_documents:
                                    logger.info(f"Retrieved {len(reply_context_documents)} context documents for reply:")
                                    for doc_idx, doc_vs in enumerate(reply_context_documents):
                                        logger.info(f"  CtxDoc-{doc_idx+1}: ID {doc_vs.get('id')}, Score {doc_vs.get('score')}, Text: {doc_vs.get('text', '')[:70]}...")
                                else:
                                    logger.info("No context documents found from VS for this reply.")
                            except Exception as e_vs_search_reply:
                                logger.error(f"Error searching vector store for reply context: {e_vs_search_reply}", exc_info=True)
                    
                    if reply_context_documents and self.llm and self.llm.is_enabled: # Check if llm is available
                        context_snippets = [doc.get('text', '') for doc in reply_context_documents if doc.get('text', '').strip()]
                        if context_snippets:
                            formatted_reply_context = "Contextual Information:\n" + "\n---\n".join(context_snippets)
                            
                            persona_name_for_prompt = (self.persona.name if self.persona and hasattr(self.persona, 'name') 
                                                       else 'an AI assistant')
                            
                            refinement_prompt = (
                                f"You are {persona_name_for_prompt}. Your task is to refine a draft Twitter reply based on the provided context and your persona.\n\n"
                                f"Context from related tweets/documents:\n{formatted_reply_context}\n\n"
                                f"Draft Reply to improve: \"{initial_generated_text}\"\n\n"
                                f"Instructions: Review the draft reply and the context. If the context provides relevant information "
                                f"or a better angle, refine the draft reply to be more contextual, engaging, and aligned with your persona. "
                                f"If the context is not helpful or the draft is already good, you can choose to keep the draft as is or make minimal changes. "
                                f"Output only the refined reply text, without any preamble."
                            )
                            logger.debug(f"Attempting to refine reply using context. Refinement prompt: {refinement_prompt[:300]}...")
                            try:
                                # self.llm is an instance of LLMFallbackManager
                                refined_text = await self.llm.generate_text(prompt=refinement_prompt, context_type="reply_refinement")
                                if refined_text and refined_text.strip() and refined_text.strip() != initial_generated_text:
                                    logger.info(f"Original reply draft: '{initial_generated_text}'. Refined reply: '{refined_text.strip()}'")
                                    final_generated_text_for_dispatch = refined_text.strip()
                                elif refined_text and refined_text.strip() == initial_generated_text:
                                    logger.info("Reply refinement resulted in the same text as original draft. Using original.")
                                else: # refined_text is None or empty
                                    logger.info("Reply refinement did not produce new text or was empty, using original draft.")
                            except Exception as e_refine:
                                logger.error(f"Error during reply refinement LLM call: {e_refine}. Using original draft.", exc_info=True)
                        else:
                            logger.info("No usable text snippets from context documents for reply refinement.")
                    elif not (self.llm and self.llm.is_enabled):
                        logger.warning("LLM manager not available or not enabled, skipping reply refinement.")

                # 4. Dispatch action (quote, reply, like, retweet)
                self.actions.dispatch(
                    action=action,
                    tweet_id=processed_tweet_data['id'], 
                    text=final_generated_text_for_dispatch, # Use the potentially refined text
                    media_path=processed_tweet_data['media_path'], 
                    conversation=processed_tweet_data['conversation'] 
                )

                # Add processed tweet to vector store (original tweet being replied to, or any other processed tweet)
                if self.vector_store_manager and processed_tweet_data.get('id') and processed_tweet_data.get('text'):
                    try:
                        document_to_add = {
                            "id": processed_tweet_data['id'], 
                            "text": processed_tweet_data['text']
                            # Potentially add more metadata from processed_tweet_data if store supports it
                        }
                        logger.debug(f"Adding document to vector store: {document_to_add['id']}")
                        added_ids = await self.vector_store_manager.add_documents([document_to_add])
                        if added_ids and processed_tweet_data['id'] in added_ids:
                            logger.info(f"Successfully added tweet {processed_tweet_data['id']} to vector store.")
                        else:
                             logger.warning(f"Failed to confirm addition of tweet {processed_tweet_data['id']} to vector store. Returned IDs: {added_ids}")
                    except Exception as e_vs_add:
                        logger.error(f"Error adding document {processed_tweet_data.get('id')} to vector store: {e_vs_add}", exc_info=True)

            except AttributeError as e:
                logger.error(f"Error processing tweet object attributes: {e}. Tweet Obj: {tweet_obj}")
                continue # Skip this tweet or handle error
            except Exception as e:
                logger.exception(f"An unexpected error occurred while processing tweet: {getattr(tweet_obj, 'id', 'Unknown ID')}. Error: {e}")
                continue


    def run(self, max_cycles: int = None):
        logger.info("Starting unified agent scheduler...")
        # Initialize next run times
        now = time.time()
        # Counter for test loop breaking
        cycles = 0
        next_action = now
        # Post scheduling: immediate first run or randomized interval
        if self.config.post_immediately:
            next_post = now
            # disable immediate flag for subsequent runs
            self.config.post_immediately = False
        else:
            next_post = now + random.uniform(self.config.post_interval_min, self.config.post_interval_max)
        while True:
            now = time.time()
            # Increment cycle and check max_cycles
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                logger.info(f"Reached max_cycles={max_cycles}, exiting loop.")
                break
            # Action processing (poll & dispatch) at configured interval
            if self.config.enable_action_processing and now >= next_action:
                logger.info("Running action processing cycle...")
                # self.twitter.login() is now called inside async run_once
                self.loop.run_until_complete(self.run_once()) # MODIFIED: Call async run_once
                next_action = now + self.config.action_interval
            
            # Post generation at configured interval
            if self.config.enable_twitter_post_generation and now >= next_post:
                logger.info("Agent: Initiating tweet scheduling cycle via Scheduler.")
                if self.scheduler and self.llm and self.llm.is_enabled: # Ensure LLM is also enabled
                    try:
                        # The vector store search for context and the main scheduling loop
                        # are now inside self.scheduler.run_schedule_cycle()
                        num_scheduled = self.loop.run_until_complete(self.scheduler.run_schedule_cycle())
                        logger.info(f"Agent: Scheduler completed cycle. Scheduled {num_scheduled} tweets.")
                    except Exception as e_scheduler_cycle:
                        logger.error(f"Agent: Error during scheduler cycle: {e_scheduler_cycle}", exc_info=True)
                elif not self.llm or not self.llm.is_enabled:
                    logger.warning("Agent: LLM is not available or not enabled. Skipping scheduling cycle.")
                else: # self.scheduler is None
                    logger.error("Agent: Scheduler not initialized. Skipping scheduling cycle.")
                
                next_post = now + random.uniform(self.config.post_interval_min, self.config.post_interval_max)
            sleep_interval = random.uniform(
                self.config.loop_sleep_interval_min,
                self.config.loop_sleep_interval_max
            )
            time.sleep(sleep_interval)

Agent = XVioletAgent  # Alias for compatibility

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = Agent()
    agent.run()
