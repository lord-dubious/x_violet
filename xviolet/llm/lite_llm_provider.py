# xviolet/llm/lite_llm_provider.py
import litellm
from litellm.exceptions import APIConnectionError, Timeout, RateLimitError, ServiceUnavailableError, APIError, InvalidRequestError
import logging
from typing import Dict, Any, Optional, List
import os # For image analysis to read file
import base64 # For image analysis

from .base_llm import BaseLLMProvider

logger = logging.getLogger(__name__)

class LiteLLMProvider(BaseLLMProvider):
    def __init__(self, config_dict: Dict[str, Any]): # Renamed config to config_dict to match base
        super().__init__(config_dict) # Calls BaseLLMProvider's __init__, sets self.config_dict
        self.model = self.config_dict.get('model')
        if not self.model:
            raise ValueError("LiteLLMProvider config missing 'model'. This is a required parameter.")
        
        self.api_key = self.config_dict.get('api_key')
        self.api_base = self.config_dict.get('api_base')
        # Allow setting custom_llm_provider for models like ollama/mistral if api_base is also set
        self.custom_llm_provider = self.config_dict.get('custom_llm_provider') 

        # Default parameters for LiteLLM calls, can be overridden by kwargs in methods
        self.default_litellm_params = self.config_dict.get('default_params', {})

        # LiteLLM also uses environment variables for keys (e.g., OPENAI_API_KEY).
        # If self.api_key is provided in config, it will be passed explicitly in calls.
        # If using a model that requires an API key not set as an environment variable
        # and not passed in config, calls might fail.

        log_params = {
            "model": self.model,
            "api_base": self.api_base if self.api_base else "Not set (using default or provider's default)",
            "custom_llm_provider": self.custom_llm_provider if self.custom_llm_provider else "Not set",
            "default_params_keys": list(self.default_litellm_params.keys())
        }
        logger.info(f"LiteLLMProvider initialized with params: {log_params}")
        if self.api_key:
            logger.info("API key provided in config and will be used explicitly.")
        else:
            logger.info("API key not provided in config; LiteLLM will rely on environment variables if needed.")


    async def generate_text(self, prompt: str, context_type: str = "general", **kwargs) -> Optional[str]:
        # context_type is not directly used by LiteLLM but is part of the interface.
        # It could be used for prompt engineering before this call if needed.
        messages = [{"role": "user", "content": prompt}]
        
        call_params = {
            "model": self.model,
            "messages": messages,
        }
        # Start with defaults, then override with provider-specific config defaults, then method-specific kwargs
        merged_params = {**self.default_litellm_params} 
        if self.custom_llm_provider: # For models like 'ollama/mistral', provider must be specified
            merged_params["custom_llm_provider"] = self.custom_llm_provider
        
        # Apply kwargs, which might override default_litellm_params or add new ones
        merged_params.update(kwargs) 
        call_params.update(merged_params)


        if self.api_key:
            call_params["api_key"] = self.api_key
        if self.api_base:
            call_params["api_base"] = self.api_base
        
        # Ensure "stream" is False unless explicitly requested, as it changes response format.
        if "stream" not in call_params:
            call_params["stream"] = False

        try:
            log_call_params = {k: v for k, v in call_params.items() if k != "messages"}
            log_call_params["messages_summary"] = messages[0]['content'][:70] + ('...' if len(messages[0]['content']) > 70 else '')
            logger.debug(f"Calling LiteLLM acompletion with params: {log_call_params}")

            response = await litellm.acompletion(**call_params)
            
            if response and response.choices and response.choices[0].message and response.choices[0].message.content:
                content = response.choices[0].message.content
                logger.info(f"LiteLLM generate_text successful for model {self.model}. Output length: {len(content)}")
                return content.strip()
            else:
                logger.warning(f"LiteLLM generate_text for model {self.model} returned empty or malformed response. Response: {response}")
                return None
        except (APIConnectionError, Timeout, RateLimitError, ServiceUnavailableError, APIError, InvalidRequestError) as e:
            logger.error(f"LiteLLM API error during generate_text for model {self.model}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error during LiteLLM generate_text for model {self.model}: {e}", exc_info=True)
            return None

    async def analyze_image(self, image_path: str, context_type: str = "image_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        # Check if the configured model is known to be multimodal and supported by LiteLLM's image input
        # This is a simplified check; LiteLLM's support can vary.
        is_multimodal_model = "vision" in self.model or "v" in self.model.lower() or "llava" in self.model.lower()

        if not is_multimodal_model:
            logger.warning(f"LiteLLMProvider.analyze_image: Model '{self.model}' may not support image analysis or is not configured for it. Skipping.")
            return None

        if not os.path.exists(image_path):
            logger.error(f"Image file not found at path: {image_path}")
            return None

        try:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            image_url = f"data:image/jpeg;base64,{base64_image}" # Assuming JPEG, adjust if other types common

            text_prompt = prompt_override or "Describe this image."
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ]
            
            call_params = {
                "model": self.model,
                "messages": messages,
            }
            merged_params = {**self.default_litellm_params}
            if self.custom_llm_provider:
                 merged_params["custom_llm_provider"] = self.custom_llm_provider
            merged_params.update(kwargs)
            call_params.update(merged_params)

            if self.api_key:
                call_params["api_key"] = self.api_key
            if self.api_base:
                call_params["api_base"] = self.api_base
            
            if "stream" not in call_params:
                call_params["stream"] = False

            log_call_params = {k:v for k,v in call_params.items() if k != "messages"}
            log_call_params["messages_summary"] = f"Text: {text_prompt[:50]}..., Image: {image_path}"
            logger.debug(f"Calling LiteLLM acompletion (image analysis) with params: {log_call_params}")

            response = await litellm.acompletion(**call_params)

            if response and response.choices and response.choices[0].message and response.choices[0].message.content:
                content = response.choices[0].message.content
                logger.info(f"LiteLLM analyze_image successful for model {self.model}. Output length: {len(content)}")
                return content.strip()
            else:
                logger.warning(f"LiteLLM analyze_image for model {self.model} returned empty or malformed response for {image_path}. Response: {response}")
                return None

        except (APIConnectionError, Timeout, RateLimitError, ServiceUnavailableError, APIError, InvalidRequestError) as e:
            logger.error(f"LiteLLM API error during analyze_image for model {self.model}, image {image_path}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error during LiteLLM analyze_image for model {self.model}, image {image_path}: {e}", exc_info=True)
            return None

    async def analyze_video(self, video_path: str, context_type: str = "video_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        logger.warning("LiteLLMProvider.analyze_video is not currently supported. Video analysis often requires specialized models and handling beyond typical LiteLLM text/image focus.")
        return None
