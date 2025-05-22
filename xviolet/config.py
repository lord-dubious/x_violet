"""
AgentConfig Loader for x_violet

Loads and validates all environment/config variables for the agent, supporting:
- Twitter credentials and client config
- LLM (Gemini) API/model config (with model variance)
- Persona file path
- Proxy config
- All agent variance for Eliza-style modularity

Exposes a single AgentConfig object for all modules to use.
"""
import os
from dotenv import load_dotenv
from typing import List
import json # Added json import
import logging # Added logging import

load_dotenv()

logger = logging.getLogger(__name__) # Added module-level logger

class AgentConfig:
    # Define default here for clarity or inside __init__ if preferred
    DEFAULT_LOCAL_DB_PATH = "data/vector_store.db" # Default path for the primary local store
    DEFAULT_VECTOR_STORE_CONFIGS = [
        {
            'name': 'local_default',
            'type': 'local',
            'config': {'db_path': os.getenv("LOCAL_VECTOR_DB_PATH", DEFAULT_LOCAL_DB_PATH)}
        }
    ]

    # --- Default LLM Provider Configurations ---
    DEFAULT_GEMINI_CONFIG = {
        'name': 'default_gemini', 'type': 'gemini', 'enabled': True,
        'config': {
            'api_key': os.getenv("GEMINI_API_KEY", ""), # Will use self.gemini_api_key if empty
            'text_model_name': os.getenv("GEMINI_TEXT_MODEL", "gemini-pro"),
            'vision_model_name': os.getenv("GEMINI_VISION_MODEL", "gemini-pro-vision"),
            # 'persona_object': self.persona_instance # Placeholder, persona init is later
        }
    }
    DEFAULT_LITELLM_CONFIG = {
        'name': 'default_litellm', 'type': 'litellm', 'enabled': False, # Disabled by default
        'config': {
            'model': os.getenv("LITELLM_MODEL", "gpt-3.5-turbo"), 
            'api_key': os.getenv("LITELLM_API_KEY", ""), # e.g., OPENAI_API_KEY
            'api_base': os.getenv("LITELLM_API_BASE", None), # e.g., for custom OpenAI-compatible endpoints
            'custom_llm_provider': os.getenv("LITELLM_CUSTOM_PROVIDER", None), # e.g., 'ollama' if model is 'ollama/mistral'
            'default_params': {'temperature': 0.7}
        }
    }
    DEFAULT_LOCAL_GGUF_CONFIG = {
        'name': 'default_local_gguf', 'type': 'local_gguf', 'enabled': False, # Disabled by default
        'config': {
            'model_path': os.getenv("LOCAL_GGUF_MODEL_PATH", "models/gguf/not_a_real_model.gguf"), # Placeholder
            'n_gpu_layers': int(os.getenv("LOCAL_GGUF_N_GPU_LAYERS", "0")),
            'n_ctx': int(os.getenv("LOCAL_GGUF_N_CTX", "2048")),
            'temperature': 0.7, # Default generation param
            'max_tokens': 512   # Default generation param
        }
    }
    # List of default LLM provider configurations
    DEFAULT_LLM_PROVIDER_CONFIGS = [
        DEFAULT_GEMINI_CONFIG, 
        DEFAULT_LITELLM_CONFIG, 
        DEFAULT_LOCAL_GGUF_CONFIG
    ]


    """
    Centralized config loader for all agent modules.
    Loads env vars, applies defaults, and type conversion.

    # --- ENVIRONMENT VARIABLES ---
    # ENV_NAME: Name of the current environment (dev, prod, etc)
    # CHARACTER_FILE: Path to persona/character JSON
    # GOOGLE_GENERATIVE_AI_API_KEY: Gemini API key
    # SMALL_GOOGLE_MODEL, MEDIUM_GOOGLE_MODEL, LARGE_GOOGLE_MODEL: LLM model names
    # EMBEDDING_GOOGLE_MODEL: Embedding model name
    # VISION_MODEL: Vision model name (for image/video analysis)
    # TWITTER_USER_AGENT: User-Agent string for all HTTP requests
    # SOCKS5_PROXY: Proxy string for all requests
    # ... (other Twitter/agent config)
    """
    def __init__(self):
        # --- ENV Name ---
        self.env_name = os.getenv("ENV_NAME", "dev")

        # --- Persona ---
        self.character_file = os.getenv("CHARACTER_FILE", "")

        # --- LLM (Gemini) ---
        self.gemini_api_key = os.getenv("GOOGLE_GENERATIVE_AI_API_KEY", "")
        self.small_model = os.getenv("SMALL_GOOGLE_MODEL", "gemini-2.0-flash-lite")
        self.medium_model = os.getenv("MEDIUM_GOOGLE_MODEL", "gemini-2.0-flash-lite")
        self.large_model = os.getenv("LARGE_GOOGLE_MODEL", "gemini-2.0-flash-thinking-exp-01-21")
        self.embedding_model = os.getenv("EMBEDDING_GOOGLE_MODEL", "gemini-embedding-exp-03-07")
        # Dimension of the embedding vector (default 1536 for Gemini embedding)
        self.embedding_dim = int(os.getenv("EMBEDDING_DIM", "1536"))
        self.vision_model = os.getenv("VISION_MODEL", "gemini-1.5-pro")

        # --- User-Agent ---
        self.user_agent = os.getenv("TWITTER_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

        # --- Twitter Credentials ---
        self.twitter_username = os.getenv("TWITTER_USERNAME", "")
        self.twitter_password = os.getenv("TWITTER_PASSWORD", "")
        self.twitter_email = os.getenv("TWITTER_EMAIL", "")
        self.twitter_2fa_secret = os.getenv("TWITTER_2FA_SECRET", "")
        self.twitter_ct0 = os.getenv("TWITTER_CT0", "")
        self.twitter_auth_token = os.getenv("TWITTER_AUTH_TOKEN", "")
        self.auth_delay_min = float(os.getenv("TWITTER_AUTH_DELAY_MIN", 2))
        self.auth_delay_max = float(os.getenv("TWITTER_AUTH_DELAY_MAX", 8))

        # --- Twitter Client Config ---
        self.dry_run = self._to_bool(os.getenv("TWITTER_DRY_RUN", "false"))
        self.max_tweet_length = int(os.getenv("MAX_TWEET_LENGTH", "280"))
        self.search_enable = self._to_bool(os.getenv("TWITTER_SEARCH_ENABLE", "false"))
        self.retry_limit = int(os.getenv("TWITTER_RETRY_LIMIT", "5"))
        self.poll_interval = int(os.getenv("TWITTER_POLL_INTERVAL", "120"))
        self.target_users = self._to_list(os.getenv("TWITTER_TARGET_USERS", ""))

        # --- Twitter Session/Cookie ---
        self.cookie_file = os.getenv("TWITTER_COOKIE_FILE", "cookies/cookies.json")
        # --- Authentication flow controls ---
        # Whether to attempt cookie-based fallback after credential login
        self.use_cookies = self._to_bool(os.getenv("TWITTER_USE_COOKIES", "true"))
        # Ensure user_agent retains default if not set
        self.twitter_user_agent = os.getenv("TWITTER_USER_AGENT", self.user_agent)
        self.twitter_proxy = os.getenv("TWITTER_PROXY", "")

        # --- Proxy ---
        self.socks5_proxy = os.getenv("SOCKS5_PROXY", "")
        # Route all outgoing HTTP/S traffic through proxy
        proxy_url = self.twitter_proxy or self.socks5_proxy
        if proxy_url:
            os.environ["HTTP_PROXY"] = proxy_url
            os.environ["HTTPS_PROXY"] = proxy_url

        # --- Advanced Twitter/Agent Controls ---
        self.enable_twitter_post_generation = self._to_bool(os.getenv("ENABLE_TWITTER_POST_GENERATION", "true"))
        self.post_interval_min = int(os.getenv("POST_INTERVAL_MIN", "120")) * 60  # minutes -> seconds
        self.post_interval_max = int(os.getenv("POST_INTERVAL_MAX", "600")) * 60
        self.enable_action_processing = self._to_bool(os.getenv("ENABLE_ACTION_PROCESSING", "true"))
        # Action processing interval in minutes -> seconds
        self.action_interval = int(os.getenv("ACTION_INTERVAL", "60")) * 60
        self.post_immediately = self._to_bool(os.getenv("POST_IMMEDIATELY", "false"))
        self.twitter_spaces_enable = self._to_bool(os.getenv("TWITTER_SPACES_ENABLE", "false"))
        self.max_actions_processing = int(os.getenv("MAX_ACTIONS_PROCESSING", "5"))
        self.action_timeline_type = os.getenv("ACTION_TIMELINE_TYPE", "home")
        # Media posting probability (0-1) and directory
        self.media_tweet_probability = float(os.getenv("MEDIA_TWEET_PROBABILITY", "0.3"))
        self.media_dir = os.getenv("MEDIA_DIR", "media")
        # Configure scheduler busy loop sleep interval (min/max)
        loop_min = os.getenv("LOOP_SLEEP_INTERVAL_MIN")
        loop_max = os.getenv("LOOP_SLEEP_INTERVAL_MAX")
        if loop_min is not None and loop_max is not None:
            self.loop_sleep_interval_min = float(loop_min)
            self.loop_sleep_interval_max = float(loop_max)
        else:
            default = float(os.getenv("LOOP_SLEEP_INTERVAL", "1"))
            self.loop_sleep_interval_min = default
            self.loop_sleep_interval_max = default
        
        # --- Scheduled Tweet Limits ---
        self.max_scheduled_tweets_total = int(os.getenv("MAX_SCHEDULED_TWEETS_TOTAL", "5"))
        self.max_scheduled_media_tweets = int(os.getenv("MAX_SCHEDULED_MEDIA_TWEETS", "2"))

        # --- Vector Store Configuration ---
        raw_vector_store_configs_json = os.getenv("VECTOR_STORE_CONFIGS_JSON")
        if raw_vector_store_configs_json:
            try:
                parsed_vs_configs = json.loads(raw_vector_store_configs_json)
                if isinstance(parsed_vs_configs, list):
                    self.vector_store_configs = parsed_vs_configs
                    logger.info(f"Loaded vector store configurations from VECTOR_STORE_CONFIGS_JSON: {self.vector_store_configs}")
                else:
                    logger.error("VECTOR_STORE_CONFIGS_JSON did not contain a valid JSON list. Using default vector store configuration.")
                    self.vector_store_configs = list(self.DEFAULT_VECTOR_STORE_CONFIGS) 
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in VECTOR_STORE_CONFIGS_JSON: {e}. Using default vector store configuration.")
                self.vector_store_configs = list(self.DEFAULT_VECTOR_STORE_CONFIGS)
        else:
            logger.info("VECTOR_STORE_CONFIGS_JSON not set. Using default vector store configuration.")
            self.vector_store_configs = list(self.DEFAULT_VECTOR_STORE_CONFIGS)

        if not self.vector_store_configs: # Check after attempting to load/default
            logger.warning("No vector store configurations available after processing. Vector store functionality may be impaired.")

        # --- LLM Provider Configurations ---
        # Update default Gemini config with potentially already loaded API key
        # This needs to be dynamic if self.gemini_api_key is set earlier.
        # For simplicity, GeminiLLMProvider itself can fall back to self.gemini_api_key from global config if not in its own dict.
        # Or, we ensure that the 'api_key' in DEFAULT_GEMINI_CONFIG correctly uses the loaded self.gemini_api_key.
        # Let's adjust DEFAULT_GEMINI_CONFIG to use self.gemini_api_key.
        # This requires DEFAULT_GEMINI_CONFIG to be defined *inside* __init__ or updated after self.gemini_api_key is set.
        # For class attribute definition, we can't directly use self.gemini_api_key.
        # So, we'll update the 'api_key' for the default gemini config if it's used.

        default_gemini_provider_cfg = {
            'name': 'default_gemini', 'type': 'gemini', 'enabled': True,
            'config': {
                'api_key': self.gemini_api_key, # Use the potentially loaded API key
                'text_model_name': self.small_model, # Use general model settings
                'vision_model_name': self.vision_model,
                # 'persona_object': self.persona_instance # Persona instance created later by agent
            }
        }
        # Reconstruct the full default list with the updated Gemini config
        current_default_llm_provider_configs = [
            default_gemini_provider_cfg,
            self.DEFAULT_LITELLM_CONFIG, # These are class attributes, access via self or AgentConfig
            self.DEFAULT_LOCAL_GGUF_CONFIG
        ]


        raw_llm_configs_json = os.getenv("LLM_PROVIDER_CONFIGS_JSON")
        if raw_llm_configs_json:
            try:
                loaded_llm_configs = json.loads(raw_llm_configs_json)
                if isinstance(loaded_llm_configs, list):
                    self.llm_provider_configs = loaded_llm_configs
                    logger.info(f"Loaded LLM provider configurations from LLM_PROVIDER_CONFIGS_JSON: {self.llm_provider_configs}")
                else:
                    logger.error("LLM_PROVIDER_CONFIGS_JSON is not a valid JSON list. Using dynamically constructed defaults.")
                    self.llm_provider_configs = list(current_default_llm_provider_configs)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in LLM_PROVIDER_CONFIGS_JSON: {e}. Using dynamically constructed default LLM configurations.")
                self.llm_provider_configs = list(current_default_llm_provider_configs)
        else:
            logger.info("LLM_PROVIDER_CONFIGS_JSON not set. Using dynamically constructed default LLM configurations.")
            self.llm_provider_configs = list(current_default_llm_provider_configs)
        
        if not self.llm_provider_configs:
            logger.warning("No LLM provider configurations available after processing. LLM functionality will be impaired.")


    def _to_bool(self, value: str) -> bool:
        return value.strip().lower() in ("1", "true", "yes", "on")

    def _to_list(self, value: str) -> List[str]:
        return [v.strip() for v in value.split(",") if v.strip()] if value else []

    def __repr__(self):
        return f"<AgentConfig persona={self.character_file} twitter={self.twitter_username} dry_run={self.dry_run}>"

# Singleton instance for all modules to import
config = AgentConfig()
