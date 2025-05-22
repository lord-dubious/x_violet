# xviolet/scheduler.py
import asyncio
import logging
import random
import os
from pathlib import Path # Needed for media directory operations
from typing import List, Dict, Any, Optional, Set, Callable 

# Type hints for dependencies (actual imports not strictly needed here if only for type hinting)
# from xviolet.config import AgentConfig 
# from xviolet.llm.fallback_manager import LLMFallbackManager 
# from xviolet.vector.fallback_manager import VectorStoreFallbackManager
# from xviolet.client.twitter_client import TwitterClient
# from xviolet.persona import Persona
from xviolet.media_tracker import is_media_used # Only need is_media_used directly for path checks

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self,
                 config, #: AgentConfig,
                 llm_manager, #: LLMFallbackManager,
                 vector_store_manager, #: VectorStoreFallbackManager,
                 twitter_client, #: TwitterClient,
                 persona, #: Optional[Persona],
                 used_media_set: Set[str],
                 mark_media_as_used_func: Callable[[str], None]):
        
        self.config = config
        self.llm = llm_manager
        self.vector_store = vector_store_manager
        self.twitter = twitter_client
        self.persona = persona
        self.used_media_set = used_media_set # This is a reference to the agent's set
        self.mark_media_as_used = mark_media_as_used_func
        # self.loop = asyncio.get_event_loop() # Not needed if all calls are await from async method

        logger.info("Scheduler initialized.")

    async def run_schedule_cycle(self) -> int:
        logger.info("Scheduler: Starting new tweet scheduling cycle.")
        scheduled_in_this_cycle = 0
        media_scheduled_this_cycle = 0
        
        # 1. Get context for new tweets for this cycle
        current_new_tweet_context_docs = []
        query_text_for_new_tweet = "general relevant topics for social media" # Default
        
        if self.persona and hasattr(self.persona, 'interests') and self.persona.interests:
            query_text_for_new_tweet = random.choice(self.persona.interests)
            logger.info(f"Scheduler: Using persona interest '{query_text_for_new_tweet}' for VS search.")
        else:
            logger.info(f"Scheduler: Persona interests not available or empty, using default VS query '{query_text_for_new_tweet}'.")

        if self.vector_store:
            try:
                logger.debug(f"Scheduler: Searching VS with query: '{query_text_for_new_tweet}'")
                # The FallbackManager's search method expects query_embedding, but handles text for local store.
                retrieved_docs = await self.vector_store.search(query_embedding=query_text_for_new_tweet, top_k=3)
                if retrieved_docs:
                    logger.info(f"Scheduler: Retrieved {len(retrieved_docs)} docs from VS for query '{query_text_for_new_tweet}'.")
                    current_new_tweet_context_docs = retrieved_docs
                else:
                    logger.info(f"Scheduler: No documents found in VS for query: '{query_text_for_new_tweet}'")
            except Exception as e_vs_search:
                logger.error(f"Scheduler: Error searching vector store: {e_vs_search}", exc_info=True)
        else:
            logger.info("Scheduler: Vector store manager not available, skipping context search.")
        
        formatted_context_for_cycle = ""
        if current_new_tweet_context_docs:
            context_snippets = [doc.get('text', '') for doc in current_new_tweet_context_docs if doc.get('text', '').strip()]
            if context_snippets:
                formatted_context_for_cycle = "Contextual Information:\n" + "\n---\n".join(context_snippets) + "\n\n"
                logger.debug(f"Scheduler: Using formatted context for this cycle's LLM prompts: {formatted_context_for_cycle[:200]}...")

        # --- Transplanted Tweet Generation Loop ---
        for _ in range(self.config.max_scheduled_tweets_total):
            if scheduled_in_this_cycle >= self.config.max_scheduled_tweets_total:
                logger.info(f"Scheduler: Reached max_scheduled_tweets_total ({self.config.max_scheduled_tweets_total}) for this cycle.")
                break

            selected_media_path = None
            text_content = None
            is_media_attempt = False

            if media_scheduled_this_cycle < self.config.max_scheduled_media_tweets and \
               random.random() < self.config.media_tweet_probability:
                is_media_attempt = True
                logger.info("Scheduler: Attempting to schedule a media tweet.")
                media_dir = Path(self.config.media_dir) # Use Path for directory operations
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
                        logger.info(f"Scheduler: Selected unused media: {selected_media_path}")
                        try:
                            base_caption_prompt = "Analyze the following image and generate a tweet caption for it, reflecting your persona."
                            prompt_for_image_analysis = f"{formatted_context_for_cycle}Based on the context above (if any) and your persona, analyze the image and generate a suitable tweet caption:" if formatted_context_for_cycle else base_caption_prompt
                            
                            text_content = await self.llm.analyze_image(
                                selected_media_path, 
                                context_type="post",
                                prompt_override=prompt_for_image_analysis
                            )
                            if not text_content:
                                logger.error(f"Scheduler: LLM failed to generate caption for media {selected_media_path}. Skipping this media tweet slot.")
                        except Exception as e:
                            logger.error(f"Scheduler: Error during LLM caption generation for media {selected_media_path}: {e}. Skipping.", exc_info=True)
                            text_content = None 
                    else:
                        logger.info("Scheduler: No unused image media found for a media tweet attempt.")
                        is_media_attempt = False 
                else:
                    logger.warning(f"Scheduler: Media directory {self.config.media_dir} not found or not a directory. Skipping media tweet attempt.")
                    is_media_attempt = False
            
            if not is_media_attempt: 
                logger.info("Scheduler: Attempting to schedule a text-only tweet.")
                base_topic_for_llm = query_text_for_new_tweet
                prompt_for_text_generation = f"Based on your persona, generate a tweet about: {base_topic_for_llm}."
                if formatted_context_for_cycle:
                    prompt_for_text_generation = f"{formatted_context_for_cycle}Based on the context above (if any) and your persona, generate a tweet about: {base_topic_for_llm}."
                
                try:
                    text_content = await self.llm.generate_text(prompt=prompt_for_text_generation, context_type="post")
                    if not text_content:
                        logger.warning(f"Scheduler: Text generation failed for topic: {base_topic_for_llm}. Skipping this slot.")
                except Exception as e:
                    logger.error(f"Scheduler: Error during text generation for topic '{base_topic_for_llm}': {e}", exc_info=True)
                    text_content = None 

            if text_content:
                try:
                    current_media_to_schedule = selected_media_path if is_media_attempt and text_content else None
                    
                    # schedule_tweet_from_agent is async, so await it
                    await self.twitter.schedule_tweet_from_agent(text=text_content, media_path=current_media_to_schedule)
                    
                    logger.info(f"Scheduler: Successfully called schedule_tweet_from_agent for text: '{text_content[:50]}...' media: {current_media_to_schedule}")
                    scheduled_in_this_cycle += 1

                    if current_media_to_schedule:
                        media_filename = os.path.basename(current_media_to_schedule)
                        self.mark_media_as_used(media_filename) # Call the passed function
                        self.used_media_set.add(media_filename) # Update the referenced set
                        media_scheduled_this_cycle += 1
                        logger.info(f"Scheduler: Marked media {media_filename} as used. Total media scheduled this cycle: {media_scheduled_this_cycle}")
                except Exception as e_sched:
                    logger.error(f"Scheduler: Error scheduling tweet (text: '{text_content[:50]}...', media: {current_media_to_schedule}): {e_sched}", exc_info=True)
            elif is_media_attempt and not text_content:
                logger.info(f"Scheduler: Skipping scheduling for slot due to earlier media content generation failure for {selected_media_path}.")
            else:
                logger.info("Scheduler: No text_content available for this slot (e.g. text generation failed), nothing to schedule.")
        # --- End of transplanted logic ---

        logger.info(f"Scheduler: Cycle finished. Total scheduled: {scheduled_in_this_cycle}, Media scheduled: {media_scheduled_this_cycle}.")
        return scheduled_in_this_cycle
