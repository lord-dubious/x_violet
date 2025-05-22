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
from xviolet.persona import Persona # ADDED Persona import

logger = logging.getLogger("xviolet.agent")

class XVioletAgent:
    def __init__(self):
        self.config = config
        # self.llm = LLMManager() # LLMManager will be initialized later with provider configs
        self.twitter = TwitterClient()
        self.actions = ActionManager(self.twitter)
        self.used_media_set = load_used_media()
        self.current_new_tweet_context_docs = [] # Initialize context attribute

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
                generated_text = llm_result.get("text") # Initial reply/action text

                # Contextual Search for Replies
                if action == "reply" and generated_text and self.vector_store_manager:
                    original_tweet_text = processed_tweet_data.get('text')
                    if original_tweet_text:
                        try:
                            logger.info(f"Reply action: Searching vector store for context related to: '{original_tweet_text[:100]}...'")
                            # VectorStoreFallbackManager.search expects query_embedding.
                            # If it's text, it handles it for LocalVectorStore.
                            context_docs = await self.vector_store_manager.search(query_embedding=original_tweet_text, top_k=3)
                            if context_docs:
                                logger.info(f"Retrieved {len(context_docs)} context documents for reply:")
                                for doc in context_docs:
                                    logger.info(f"  - ID: {doc.get('id')}, Score: {doc.get('score')}, Text: {doc.get('text', '')[:100]}...")
                                # Store context_docs, e.g., self.current_reply_context = context_docs
                                # For now, just logging. This context would be used in a subsequent step
                                # to refine `generated_text` before dispatching.
                            else:
                                logger.info("No context documents found for this reply.")
                        except Exception as e_vs_search_reply:
                            logger.error(f"Error searching vector store for reply context: {e_vs_search_reply}", exc_info=True)
                
                # 4. Dispatch action (quote, reply, like, retweet)
                # Note: generated_text might be refined in a future step using context_docs before this dispatch.
                self.actions.dispatch(
                    action=action,
                    tweet_id=processed_tweet_data['id'], 
                    text=generated_text,
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
                logger.info("Starting post generation and scheduling cycle...")
                
                # Contextual Search Query for New Tweets
                if self.vector_store_manager:
                    query_text_for_new_tweet = "general relevant topics for social media" # Default
                    if self.persona and hasattr(self.persona, 'interests') and self.persona.interests:
                        # Ensure random is imported if not already at top of file
                        # import random # Should be at top of file
                        query_text_for_new_tweet = random.choice(self.persona.interests)
                        logger.info(f"New tweet context: Using persona interest '{query_text_for_new_tweet}' for vector search.")
                    else:
                        logger.info(f"New tweet context: Persona interests not available or empty, using default query '{query_text_for_new_tweet}'.")

                    try:
                        logger.debug(f"Searching vector store with query for new tweet context: '{query_text_for_new_tweet}'")
                        retrieved_docs_for_new_tweet = self.loop.run_until_complete(
                            self.vector_store_manager.search(query_embedding=query_text_for_new_tweet, top_k=3)
                        )
                        if retrieved_docs_for_new_tweet:
                            logger.info(f"Retrieved {len(retrieved_docs_for_new_tweet)} docs from VS for new tweet query '{query_text_for_new_tweet}':")
                            for doc_vs in retrieved_docs_for_new_tweet:
                                logger.info(f"  - ID: {doc_vs.get('id')}, Score: {doc_vs.get('score')}, Text: {doc_vs.get('text', '')[:100]}...")
                            self.current_new_tweet_context_docs = retrieved_docs_for_new_tweet
                        else:
                            logger.info(f"No documents found in VS for new tweet query: '{query_text_for_new_tweet}'")
                            self.current_new_tweet_context_docs = [] 
                    except Exception as e_vs_search_new:
                        logger.error(f"Error searching vector store for new tweet context: {e_vs_search_new}", exc_info=True)
                        self.current_new_tweet_context_docs = []
                else:
                    logger.info("Vector store manager not available, skipping context search for new tweets.")
                    self.current_new_tweet_context_docs = []

                scheduled_in_cycle_count = 0
                media_scheduled_in_cycle_count = 0
                
                # Reload used media set at the start of each cycle to pick up external changes if any
                # self.used_media_set = load_used_media() # Optional: consider if needed per cycle

                for _ in range(self.config.max_scheduled_tweets_total):
                    if scheduled_in_cycle_count >= self.config.max_scheduled_tweets_total:
                        logger.info("Reached max_scheduled_tweets_total for this cycle.")
                        break

                    selected_media_path = None
                    text_content = None
                    is_media_attempt = False

                    # Determine if a media tweet should be generated
                    if media_scheduled_in_cycle_count < self.config.max_scheduled_media_tweets and \
                       random.random() < self.config.media_tweet_probability:
                        is_media_attempt = True
                        logger.info("Attempting to schedule a media tweet.")
                        media_dir = Path(self.config.media_dir)
                        if media_dir.exists() and media_dir.is_dir():
                            available_media_files = [
                                p for p in media_dir.iterdir() 
                                if p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif')
                            ]
                            
                            unused_media_files = [
                                p for p in available_media_files 
                                if not is_media_used(os.path.basename(str(p)), self.used_media_set)
                            ]

                            if unused_media_files:
                                selected_media_path = str(random.choice(unused_media_files))
                                logger.info(f"Selected unused media: {selected_media_path}")
                                try:
                                    # Analyze image (ensure personality is used via context_type="post")
                                    text_content = self.llm.analyze_image(selected_media_path, context_type="post")
                                    if not text_content:
                                        logger.error(f"LLM failed to generate content for media {selected_media_path}. Skipping this media tweet slot.")
                                        # text_content remains None, selected_media_path is still set
                                        # This iteration will be skipped by the `if text_content:` block later
                                except Exception as e:
                                    logger.error(f"Error during LLM analysis for media {selected_media_path}: {e}. Skipping this media tweet slot.")
                                    text_content = None # Ensure text_content is None on LLM error
                                    # selected_media_path is still set
                            else:
                                logger.info("No unused image media found. Will attempt text tweet if possible.")
                                is_media_attempt = False # Cannot make a media tweet, selected_media_path remains None
                        else:
                            logger.warning(f"Media directory {self.config.media_dir} not found or not a directory. Skipping media tweet attempt.")
                            is_media_attempt = False # Cannot make a media tweet, selected_media_path remains None
                    
                    # Generate text-only tweet if it was decided from the start (not a media attempt)
                    if not is_media_attempt: # Only enter if it was never a media attempt or media selection failed (no path)
                        logger.info("Attempting to schedule a text-only tweet (not as a fallback for failed media analysis).")
                        try:
                            # Generate text (ensure personality is used via context_type="post")
                            text_content = self.llm.generate_text("Automated tweet from x_violet", context_type="post")
                            if not text_content:
                                logger.warning("Text generation failed for text-only tweet. Skipping this slot.")
                                # continue # Skip this iteration of the loop - text_content will be None, so it skips scheduling
                        except Exception as e:
                            logger.error(f"Error during text generation for text-only tweet: {e}")
                            text_content = None # Ensure text_content is None on error

                    # Schedule the tweet if text_content was successfully generated (either for media or text-only)
                    if text_content: # This condition now correctly skips if media analysis failed
                        try:
                            # If it was a media attempt but text_content is None (due to LLM failure for media),
                            # selected_media_path might still be set. We should only schedule if text_content is valid.
                            # The only way text_content is set for a media attempt is if LLM succeeded.
                            # If it's a text-only attempt, selected_media_path is None.
                            
                            current_media_to_schedule = selected_media_path if is_media_attempt and text_content else None

                            self.loop.run_until_complete(
                                self.twitter.schedule_tweet_from_agent(text=text_content, media_path=current_media_to_schedule)
                            )
                            logger.info(f"Successfully called schedule_tweet_from_agent for text: '{text_content[:50]}...' media: {current_media_to_schedule}")
                            scheduled_in_cycle_count += 1

                            if current_media_to_schedule: # Only if it was a successful media tweet
                                media_filename = os.path.basename(current_media_to_schedule)
                                mark_media_as_used(media_filename)
                                self.used_media_set.add(media_filename)
                                media_scheduled_in_cycle_count += 1
                                logger.info(f"Marked media {media_filename} as used. Total media scheduled this cycle: {media_scheduled_in_cycle_count}")
                        except Exception as e:
                            logger.error(f"Error scheduling tweet (text: '{text_content[:50]}...', media: {current_media_to_schedule}): {e}")
                    elif is_media_attempt and not text_content:
                        # This is the case where media analysis failed, and we logged an error.
                        # We explicitly do nothing more for this slot.
                        logger.info(f"Skipping scheduling for slot due to earlier media content generation failure for {selected_media_path}.")
                    else:
                        # This handles cases where text generation for a text-only tweet failed.
                        logger.info("No text_content available for this slot (e.g. text generation failed), nothing to schedule.")
                
                logger.info(f"Finished scheduling cycle. Total scheduled: {scheduled_in_cycle_count}, Media scheduled: {media_scheduled_in_cycle_count}.")
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
