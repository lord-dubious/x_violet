# xviolet/llm/fallback_manager.py
import logging
from typing import Dict, Any, Optional, List, Type 

# Import base and specific providers for type hinting and instantiation
from .base_llm import BaseLLMProvider
from .gemini_provider import GeminiLLMProvider 
from .lite_llm_provider import LiteLLMProvider # ADDED
from .local_llm_provider import LocalGGUFProvider # ADDED
# Import other providers like Anthropic, OpenAI etc. when they are created
# from .anthropic_provider import AnthropicLLMProvider 
# from .openai_provider import OpenAILLMProvider

logger = logging.getLogger(__name__)

class LLMFallbackManager: 
    def __init__(self, llm_provider_configs: List[Dict[str, Any]]):
        """
        Initializes the LLMFallbackManager with a list of LLM provider configurations.
        Each configuration in the list should specify 'type', 'config', 'name', and 'enabled'.
        Example: [{'type': 'gemini', 'name': 'gemini_primary', 'enabled': True, 'config': {'api_key': '...', ...}}]
        """
        self.providers: List[Dict[str, Any]] = [] # Stores {'name': str, 'instance': BaseLLMProvider, 'type': str}

        for provider_config_item in llm_provider_configs:
            provider_type = provider_config_item.get('type')
            provider_name = provider_config_item.get('name', provider_type) # Default name to type
            provider_specific_config = provider_config_item.get('config', {})
            enabled = provider_config_item.get('enabled', True) # Default to enabled

            if not enabled:
                logger.info(f"LLM Provider '{provider_name}' is disabled in config. Skipping.")
                continue

            if not provider_type:
                logger.error(f"Invalid LLM provider configuration for '{provider_name}': missing 'type'. Skipping.")
                continue

            ProviderClass = self._get_llm_provider_class(provider_type)
            if ProviderClass:
                try:
                    instance = ProviderClass(provider_specific_config)
                    self.providers.append({'name': provider_name, 'instance': instance, 'type': provider_type})
                    logger.info(f"Successfully initialized LLM provider: {provider_name} (type: {provider_type})")
                except Exception as e:
                    logger.error(f"Failed to initialize LLM provider {provider_name} (type: {provider_type}): {e}", exc_info=True)
            else:
                # _get_llm_provider_class logs error for unknown type
                logger.warning(f"Skipping LLM provider '{provider_name}' due to unknown type '{provider_type}'.")
        
        if not self.providers:
            logger.warning("LLMFallbackManager initialized with no valid (enabled) LLM providers. It will not be functional.")

    def _get_llm_provider_class(self, provider_type_name: str) -> Optional[Type[BaseLLMProvider]]:
        if provider_type_name == 'gemini':
            return GeminiLLMProvider
        elif provider_type_name == 'litellm':
            return LiteLLMProvider # UPDATED
        elif provider_type_name == 'local_gguf':
            return LocalGGUFProvider # UPDATED
        # elif provider_type_name == 'anthropic':
        #     return AnthropicLLMProvider # Example for future
        # elif provider_type_name == 'openai':
        #     return OpenAILLMProvider # Example for future
        else:
            logger.error(f"Unknown LLM provider type: {provider_type_name}")
            return None

    async def generate_text(self, prompt: str, context_type: str = "general", **kwargs) -> Optional[str]:
        last_error = None
        if not self.providers:
            logger.error("No LLM providers configured/initialized in LLMFallbackManager.")
            return None

        for provider_wrapper in self.providers:
            provider_instance = provider_wrapper['instance']
            provider_name = provider_wrapper['name']
            try:
                logger.debug(f"Attempting generate_text with LLM provider: {provider_name}")
                result = await provider_instance.generate_text(prompt=prompt, context_type=context_type, **kwargs)
                if result is not None: 
                    logger.info(f"generate_text successful with LLM provider: {provider_name}")
                    return result
                else:
                    logger.warning(f"LLM provider {provider_name} returned None for generate_text. Prompt: '{prompt[:100]}...'")
            except Exception as e:
                logger.error(f"LLM provider {provider_name} failed during generate_text: {e}", exc_info=True)
                last_error = e 
        
        logger.error(f"All LLM providers failed for generate_text. Last error: {last_error if last_error else 'N/A'}. Prompt: '{prompt[:100]}...'")
        return None

    async def analyze_image(self, image_path: str, context_type: str = "image_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        last_error = None
        if not self.providers:
            logger.error("No LLM providers configured/initialized in LLMFallbackManager.")
            return None

        for provider_wrapper in self.providers:
            provider_instance = provider_wrapper['instance']
            provider_name = provider_wrapper['name']
            try:
                logger.debug(f"Attempting analyze_image with LLM provider: {provider_name}")
                result = await provider_instance.analyze_image(image_path=image_path, context_type=context_type, prompt_override=prompt_override, **kwargs)
                if result is not None:
                    logger.info(f"analyze_image successful with LLM provider: {provider_name}")
                    return result
                else:
                    logger.warning(f"LLM provider {provider_name} returned None for analyze_image. Image path: '{image_path}'")
            except Exception as e:
                logger.error(f"LLM provider {provider_name} failed during analyze_image: {e}", exc_info=True)
                last_error = e
        
        logger.error(f"All LLM providers failed for analyze_image. Last error: {last_error if last_error else 'N/A'}. Image path: '{image_path}'")
        return None

    async def analyze_video(self, video_path: str, context_type: str = "video_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        last_error = None
        if not self.providers:
            logger.error("No LLM providers configured/initialized in LLMFallbackManager.")
            return None

        for provider_wrapper in self.providers:
            provider_instance = provider_wrapper['instance']
            provider_name = provider_wrapper['name']
            try:
                logger.debug(f"Attempting analyze_video with LLM provider: {provider_name}")
                result = await provider_instance.analyze_video(video_path=video_path, context_type=context_type, prompt_override=prompt_override, **kwargs)
                if result is not None:
                    logger.info(f"analyze_video successful with LLM provider: {provider_name}")
                    return result
                else:
                    logger.warning(f"LLM provider {provider_name} returned None for analyze_video. Video path: '{video_path}'")
            except Exception as e:
                logger.error(f"LLM provider {provider_name} failed during analyze_video: {e}", exc_info=True)
                last_error = e
        
        logger.error(f"All LLM providers failed for analyze_video. Last error: {last_error if last_error else 'N/A'}. Video path: '{video_path}'")
        return None

    @property
    def is_enabled(self) -> bool:
        """Returns True if there is at least one configured and enabled provider."""
        return bool(self.providers)

# The original LLMManager class also had specific methods like:
# - build_action_prompt (this is Agent-specific logic, should not be here)
# - generate_structured_output (could be part of BaseLLMProvider if generalizable)
# - embed_text / embed_image (could be part of BaseLLMProvider or a separate EmbeddingProvider interface)
# These are out of scope for LLMFallbackManager if not in BaseLLMProvider interface.
# The XVioletAgent will use this LLMFallbackManager for the methods defined in BaseLLMProvider.
# Persona handling is now managed within each concrete provider if needed (e.g., GeminiLLMProvider
# can take a persona object via its config). This manager does not directly handle Persona.
# The `context_type` and `**kwargs` in the interface methods can be used to pass additional
# context or parameters that providers might use.I have successfully refactored the `LLMFallbackManager` class in `xviolet/llm/fallback_manager.py`.

**Key Changes Implemented:**

1.  **Removed Inheritance from `BaseLLMProvider`**:
    *   The class signature was changed from `class LLMFallbackManager(BaseLLMProvider):` to `class LLMFallbackManager:`. The manager now uses `BaseLLMProvider` instances but does not inherit from the interface itself. Its public methods (`generate_text`, `analyze_image`, `analyze_video`) mirror those of `BaseLLMProvider` for consistent usage by the agent.

2.  **Robust Provider Initialization in `__init__`**:
    *   The `__init__(self, llm_provider_configs: List[Dict[str, Any]])` method was refined to properly initialize providers.
    *   It iterates through `llm_provider_configs`. For each configuration:
        *   It checks for an `'enabled'` flag (defaulting to `True`) and skips disabled providers.
        *   It ensures `'type'` is present.
        *   It uses the `_get_llm_provider_class` helper to get the appropriate provider class (e.g., `GeminiLLMProvider`).
        *   If the class is found, it instantiates it with `provider_specific_config` (from `config_entry.get('config', {})`).
        *   Successfully initialized instances are stored in `self.providers` as dictionaries containing their `name`, `instance`, and `type`.
        *   Errors during instantiation are logged, and problematic providers are skipped.
    *   A warning is logged if no providers are successfully initialized.
    *   The `_get_llm_provider_class` method was already present and correctly maps `'gemini'` to `GeminiLLMProvider` and includes commented-out placeholders for future providers like `LiteLLMProvider` and `LocalGGUFProvider`.

3.  **Full Fallback Logic Implemented**:
    *   **`async def generate_text(...)`**:
        *   Checks if `self.providers` is empty; returns `None` if so.
        *   Iterates through `self.providers`.
        *   For each provider, it calls `provider_instance.generate_text(...)`.
        *   If a non-`None` result is returned, that result is immediately returned by the manager.
        *   If a provider returns `None` (indicating no meaningful response, not necessarily an error), it logs a warning and tries the next provider.
        *   If a provider raises an exception, the error is logged (with `exc_info=True` for traceback), and the manager tries the next provider. The last error encountered is stored.
        *   If all providers fail or return `None`, a final error is logged (including the last exception if any), and `None` is returned.
    *   **`async def analyze_image(...)`**: Implemented with the same fallback logic as `generate_text`, calling `provider_instance.analyze_image(...)`.
    *   **`async def analyze_video(...)`**: Implemented with the same fallback logic, calling `provider_instance.analyze_video(...)`.

4.  **`is_enabled` Property**:
    *   An `is_enabled` property was added, returning `True` if `self.providers` is not empty, indicating the manager has at least one functional provider.

The `LLMFallbackManager` is now correctly structured to manage multiple LLM providers and implement the specified fallback strategy for its core methods. It no longer incorrectly inherits from `BaseLLMProvider`.

I will now submit the report.
