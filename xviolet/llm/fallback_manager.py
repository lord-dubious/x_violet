# xviolet/llm/fallback_manager.py
import logging
from typing import Dict, Any, Optional, List, Type # Added Type for _get_store_class hint

# Import base and specific providers for type hinting and instantiation
from .base_llm import BaseLLMProvider
from .gemini_provider import GeminiLLMProvider 
# Import other providers like Anthropic, OpenAI etc. when they are created
# from .anthropic_provider import AnthropicLLMProvider 
# from .openai_provider import OpenAILLMProvider

logger = logging.getLogger(__name__)

class LLMFallbackManager(BaseLLMProvider): # Will implement the same interface
    def __init__(self, llm_provider_configs: List[Dict[str, Any]]):
        """
        Initializes the LLMFallbackManager with a list of LLM provider configurations.
        Each configuration in the list should specify 'type' and 'config' for the provider.
        Example: [{'type': 'gemini', 'name': 'gemini_primary', 'config': {'api_key': '...', ...}}]
        """
        # The FallbackManager itself doesn't have a single 'config' in the BaseLLMProvider sense.
        # Its configuration *is* the list of providers.
        # We call super().__init__ with a representative or empty dict if BaseLLMProvider's __init__ needs it.
        super().__init__({'manager_name': 'LLMFallbackManager', 'provider_configs': llm_provider_configs})

        self.providers: List[Dict[str, Any]] = [] # Stores {'name': str, 'instance': BaseLLMProvider, 'type': str}

        for provider_config_item in llm_provider_configs:
            provider_type_name = provider_config_item.get('type')
            provider_specific_config = provider_config_item.get('config')
            provider_name = provider_config_item.get('name', provider_type_name)

            if not provider_type_name or provider_specific_config is None:
                logger.error(f"Invalid LLM provider configuration for '{provider_name}': missing 'type' or 'config'. Skipping.")
                continue

            provider_class = self._get_provider_class(provider_type_name)
            if provider_class:
                try:
                    instance = provider_class(provider_specific_config)
                    self.providers.append({'name': provider_name, 'instance': instance, 'type': provider_type_name})
                    logger.info(f"Successfully initialized LLM provider: {provider_name} (type: {provider_type_name})")
                except Exception as e:
                    logger.error(f"Failed to initialize LLM provider {provider_name} (type: {provider_type_name}): {e}", exc_info=True)
            else:
                logger.warning(f"Skipping LLM provider '{provider_name}' due to unknown type '{provider_type_name}'.")
        
        if not self.providers:
            logger.warning("LLMFallbackManager initialized with no valid LLM providers. It will not be functional.")

    def _get_provider_class(self, provider_type_name: str) -> Optional[Type[BaseLLMProvider]]:
        if provider_type_name == 'gemini':
            return GeminiLLMProvider
        # elif provider_type_name == 'anthropic':
        #     return AnthropicLLMProvider # Example for future
        # elif provider_type_name == 'openai':
        #     return OpenAILLMProvider # Example for future
        else:
            logger.error(f"Unknown LLM provider type: {provider_type_name}")
            return None

    async def generate_text(self, prompt: str, context_type: str = "general", **kwargs) -> Optional[str]:
        if not self.providers:
            logger.error("No LLM providers available in LLMFallbackManager for generate_text.")
            return None
        
        # For now, placeholder: try the first provider. Full fallback logic in Step 7.
        first_provider_wrapper = self.providers[0]
        provider_instance = first_provider_wrapper['instance']
        provider_name = first_provider_wrapper['name']
        logger.debug(f"LLMFallbackManager attempting generate_text with first provider: {provider_name}")
        try:
            return await provider_instance.generate_text(prompt, context_type, **kwargs)
        except Exception as e:
            logger.error(f"Provider {provider_name} failed in generate_text: {e}", exc_info=True)
            # In full implementation, would try next provider here.
            return None # Placeholder: return None if first fails

    async def analyze_image(self, image_path: str, context_type: str = "image_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        if not self.providers:
            logger.error("No LLM providers available in LLMFallbackManager for analyze_image.")
            return None

        # For now, placeholder: try the first provider.
        first_provider_wrapper = self.providers[0]
        provider_instance = first_provider_wrapper['instance']
        provider_name = first_provider_wrapper['name']
        logger.debug(f"LLMFallbackManager attempting analyze_image with first provider: {provider_name}")
        try:
            return await provider_instance.analyze_image(image_path, context_type, prompt_override, **kwargs)
        except Exception as e:
            logger.error(f"Provider {provider_name} failed in analyze_image: {e}", exc_info=True)
            return None

    async def analyze_video(self, video_path: str, context_type: str = "video_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        if not self.providers:
            logger.error("No LLM providers available in LLMFallbackManager for analyze_video.")
            return None
            
        # For now, placeholder: try the first provider.
        first_provider_wrapper = self.providers[0]
        provider_instance = first_provider_wrapper['instance']
        provider_name = first_provider_wrapper['name']
        logger.debug(f"LLMFallbackManager attempting analyze_video with first provider: {provider_name}")
        try:
            return await provider_instance.analyze_video(video_path, context_type, prompt_override, **kwargs)
        except Exception as e:
            logger.error(f"Provider {provider_name} failed in analyze_video: {e}", exc_info=True)
            return None

    # Other methods that were in the original LLMManager but are not part of BaseLLMProvider
    # (like generate_structured_output, embed_text, build_action_prompt) are not included here
    # as this class is now primarily a fallback manager for the BaseLLMProvider interface.
    # If those methods are needed at the manager level, the BaseLLMProvider interface would need to be extended,
    # or they would be handled by a different component.

    # Example: If build_action_prompt was to be kept, it would need access to persona,
    # which is no longer directly part of this manager's init.
    # It would need to be passed in or handled differently.
    # For this refactor step, we focus only on the BaseLLMProvider interface methods.

    @property
    def is_enabled(self) -> bool:
        """Returns True if there is at least one configured provider."""
        return bool(self.providers)

# The original LLMManager class also had specific methods like:
# - build_action_prompt (moved to XVioletAgent as it's agent-specific logic)
# - generate_structured_output (could be part of BaseLLMProvider if generalizable)
# - embed_text / embed_image (could be part of BaseLLMProvider or a separate EmbeddingProvider interface)
# For this refactor, these are out of scope for LLMFallbackManager if not in BaseLLMProvider.
# The XVioletAgent will eventually use this LLMFallbackManager.
# Any helper methods previously in LLMManager that were specific to agent logic
# (e.g., using self.persona to build prompts) will either need the LLM providers
# themselves to handle persona (passed via config) or the agent will manage persona prompt
# templating before calling the LLM manager.
# The GeminiLLMProvider was adapted to take persona via its config.
# This LLMFallbackManager does not directly know about Persona; it just dispatches to providers.
# The `context_type` and `**kwargs` in the interface methods can be used to pass additional
# context or parameters that providers might use, including persona-related details if needed.
# The original global `config` and `Persona` imports are removed as they are not directly used by the manager.
# Imports like `google.genai` are also removed as they are provider-specific.
# `proxy_manager` import is also removed. Proxy settings should be part of provider config.
# `dotenv` import is also removed.
# The original file had `logging.basicConfig`. This is application-wide and should ideally be configured
# at the application entry point, not in a library module. Removing it from here.
# The `DEFAULT_API_KEY_ENV_VAR` and `DEFAULT_MODEL_NAME` constants were Gemini-specific and removed.
# Safety settings comment also removed as it's provider-specific.
# All Gemini-specific code is now in gemini_provider.py.
# This file is now lean and focused on being a fallback manager for BaseLLMProvider instances.
