# xviolet/llm/local_llm.py
from llama_cpp import Llama
import logging
from typing import Dict, Any, Optional, List
import os
import asyncio # For running sync llama-cpp calls in executor

from .base_llm import BaseLLMProvider

logger = logging.getLogger(__name__)

class LocalGGUFProvider(BaseLLMProvider):
    def __init__(self, config_dict: Dict[str, Any]): # Renamed config to config_dict
        super().__init__(config_dict) # Calls BaseLLMProvider's __init__, sets self.config_dict
        
        self.model_path = self.config_dict.get('model_path')
        if not self.model_path or not os.path.exists(self.model_path):
            # Log before raising to ensure it's captured if error handling above is generic
            logger.error(f"LocalGGUFProvider config missing or invalid 'model_path': {self.model_path}")
            raise ValueError(f"LocalGGUFProvider config missing or invalid 'model_path': {self.model_path}")

        # Llama constructor parameters from config
        self.n_gpu_layers = self.config_dict.get('n_gpu_layers', 0) # Default: 0 (CPU only)
        self.n_ctx = self.config_dict.get('n_ctx', 2048) # Context window
        self.verbose_llama = self.config_dict.get('verbose', False) # llama-cpp verbose

        # Parameters for generation, can be overridden by kwargs in generate_text
        self.temperature = self.config_dict.get('temperature', 0.7)
        self.max_tokens = self.config_dict.get('max_tokens', 512)
        self.top_p = self.config_dict.get('top_p', 0.95)
        self.top_k = self.config_dict.get('top_k', 40)
        # Add other relevant Llama params as needed from self.config_dict for generation

        self.llm: Optional[Llama] = None # Initialize llm attribute

        logger.info(f"Initializing LocalGGUFProvider with model: {self.model_path}")
        logger.info(f"  n_gpu_layers: {self.n_gpu_layers}, n_ctx: {self.n_ctx}, verbose: {self.verbose_llama}")
        logger.info(f"  Default generation params: temp={self.temperature}, max_tokens={self.max_tokens}, top_p={self.top_p}, top_k={self.top_k}")

        try:
            self.llm = Llama(
                model_path=self.model_path,
                n_gpu_layers=self.n_gpu_layers,
                n_ctx=self.n_ctx,
                verbose=self.verbose_llama
                # Other Llama __init__ params can be added here from self.config_dict if needed
            )
            logger.info(f"Successfully loaded GGUF model from: {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load GGUF model from {self.model_path}: {e}", exc_info=True)
            # self.llm remains None, methods should check this
            # Optionally re-raise or handle as a critical failure for the provider
            raise ValueError(f"Could not load GGUF model: {e}") from e


    async def generate_text(self, prompt: str, context_type: str = "general", **kwargs) -> Optional[str]:
        # context_type is part of the interface, not directly used here unless for specific prompt engineering
        if not self.llm:
            logger.error("LocalGGUFProvider: GGUF model not loaded or failed to initialize.")
            return None

        # Prepare parameters for create_completion, allowing overrides from kwargs
        # Default values are taken from instance attributes set during __init__
        current_temp = kwargs.get('temperature', self.temperature)
        current_max_tokens = kwargs.get('max_tokens', self.max_tokens)
        current_top_p = kwargs.get('top_p', self.top_p)
        current_top_k = kwargs.get('top_k', self.top_k)
        # Add other create_completion params from kwargs or self.config_dict as needed
        # e.g., stop sequences, presence_penalty, frequency_penalty

        # Construct the messages payload for Llama.create_completion
        # It expects a list of messages, similar to OpenAI API.
        # For a simple prompt, it's usually:
        messages = [
            {"role": "user", "content": prompt}
        ]
        # If a system prompt is desired, it can be added:
        # system_prompt = self.config_dict.get('system_prompt') # Or from persona logic
        # if system_prompt:
        # messages.insert(0, {"role": "system", "content": system_prompt})

        # Parameters for the create_completion call
        completion_params = {
            "messages": messages,
            "temperature": current_temp,
            "max_tokens": current_max_tokens,
            "top_p": current_top_p,
            "top_k": current_top_k,
            # "stop": ["\n", "User:"], # Example stop sequences
        }
        
        # Remove None values from params if Llama complains, or ensure defaults are always set.
        # For example, if max_tokens is -1 for unlimited, ensure that's handled if Llama expects None or positive int.
        # llama-cpp typically expects positive for max_tokens, or defaults if not given.

        log_call_params = {k:v for k,v in completion_params.items() if k != "messages"}
        log_call_params["messages_summary"] = messages[-1]['content'][:70] + ('...' if len(messages[-1]['content']) > 70 else '')
        logger.debug(f"Calling GGUF model create_completion with params: {log_call_params}")

        try:
            loop = asyncio.get_event_loop()
            
            # Define the synchronous blocking function to be run in the executor
            def _create_completion_sync():
                return self.llm.create_completion(**completion_params)

            completion = await loop.run_in_executor(None, _create_completion_sync)
            
            if completion and completion['choices'] and completion['choices'][0]['message'] and \
               completion['choices'][0]['message']['content']:
                text_content = completion['choices'][0]['message']['content']
                logger.info(f"GGUF model generated text successfully. Length: {len(text_content)}")
                return text_content.strip()
            else:
                logger.warning(f"GGUF model text generation returned empty or malformed response: {completion}")
                return None
        except Exception as e:
            logger.error(f"Error during GGUF model text generation: {e}", exc_info=True)
            return None

    async def analyze_image(self, image_path: str, context_type: str = "image_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        logger.warning(f"LocalGGUFProvider.analyze_image: Operation not supported by most GGUF models. Model: {self.model_path}. Image path: {image_path}")
        # If self.llm is a LLaVA model, specific handling would be needed here.
        # For generic GGUF, this is not supported.
        return None

    async def analyze_video(self, video_path: str, context_type: str = "video_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        logger.warning(f"LocalGGUFProvider.analyze_video: Operation not supported by GGUF models. Model: {self.model_path}. Video path: {video_path}")
        return None

# Example of how this provider might be configured in agent_config.py (for context):
# DEFAULT_LLM_PROVIDER_CONFIGS = [
#     {
#         'name': 'local_gguf_main',
#         'type': 'local_gguf', # This type name would be registered in LLMFallbackManager
#         'enabled': True,
#         'config': {
#             'model_path': '/path/to/your/model.gguf', # Critical: User must provide this
#             'n_gpu_layers': 0, # Or number of layers to offload if GPU supported & compiled
#             'n_ctx': 4096,
#             'temperature': 0.6,
#             'max_tokens': 1024,
#             'verbose': False
#         }
#     },
#     # ... other providers like gemini or litellm
# ]
