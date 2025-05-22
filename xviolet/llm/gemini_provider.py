# xviolet/llm/gemini_provider.py
import logging
import os
from typing import Dict, Any, Optional

from .base_llm import BaseLLMProvider
# Assuming Persona might be passed via config or initialized if path is in config
# from ..persona import Persona # This creates a circular dependency if BaseLLMProvider is in ..llm
# For now, let's assume persona handling is simplified or persona context is passed in kwargs if needed.
# The original LLMManager took a Persona object. We'll try to replicate that if config allows.

try:
    from google import genai
    from google.genai import types as genai_types # Renamed to avoid conflict
except ImportError:
    genai = None
    genai_types = None

logger = logging.getLogger(__name__)

class GeminiLLMProvider(BaseLLMProvider):
    def __init__(self, config_dict: Dict[str, Any]):
        super().__init__(config_dict) # Sets self.config_dict

        self.api_key = self.config_dict.get("api_key")
        self.text_model_name = self.config_dict.get("text_model_name", "gemini-1.5-flash-latest")
        self.vision_model_name = self.config_dict.get("vision_model_name", "gemini-1.5-pro") # Default from vision_model in old config
        
        # Persona handling: For now, assume persona object is passed in config_dict if used
        # This is a simplification; a more robust solution might involve a PersonaManager.
        self.persona = self.config_dict.get("persona_object", None) # Example key

        self.client = None
        self.text_model = None
        self.vision_model = None

        if not genai:
            logger.error("Google Generative AI SDK (google.generativeai) not installed. GeminiLLMProvider cannot function.")
            return

        if not self.api_key:
            logger.error("Gemini API key not provided in config. GeminiLLMProvider disabled.")
            return

        # Proxy handling (simplified, assumes proxy URL is in config_dict if needed)
        proxy_url = self.config_dict.get("proxy_url")
        if proxy_url:
            # Note: Modifying os.environ here might have wider effects.
            # Consider passing proxy to client if API supports it directly.
            os.environ['HTTP_PROXY'] = proxy_url
            os.environ['HTTPS_PROXY'] = proxy_url
            logger.info(f"Routing Gemini API traffic via proxy: {proxy_url}")
        
        try:
            # Configuring the SDK with the API key
            genai.configure(api_key=self.api_key)
            # In the new genai SDK, client is often implicit after configure.
            # We initialize models directly.
            self.text_model = genai.GenerativeModel(self.text_model_name)
            self.vision_model = genai.GenerativeModel(self.vision_model_name)
            logger.info(f"GeminiLLMProvider configured successfully for text model: {self.text_model_name} and vision model: {self.vision_model_name}")
            self.client = True # Indicate client is configured (though it's not a client object anymore)
        except Exception as e:
            logger.error(f"Failed to configure Gemini models: {e}")
            self.client = None # Reset to indicate failure

    @property
    def is_enabled(self) -> bool:
        return self.client is not None and self.text_model is not None

    async def generate_text(self, prompt: str, context_type: str = "general", **kwargs) -> Optional[str]:
        # dry_run handling: Check if 'dry_run' is in self.config_dict and True
        if self.config_dict.get('dry_run', False):
            logger.info(f"[DRY RUN] GeminiLLMProvider.generate_text: returning prompt fallback for '{prompt}'")
            return f"[DRY_RUN_GEMINI] {prompt}"

        if not self.is_enabled:
            logger.error("GeminiLLMProvider is not enabled. Cannot generate text.")
            return None

        full_prompt = prompt
        # Simplified persona handling: if persona object exists and has get_full_context_for_llm
        if self.persona and hasattr(self.persona, 'get_full_context_for_llm'):
            persona_context = self.persona.get_full_context_for_llm(context_type=context_type)
            full_prompt = f"{persona_context}\n\n---\n\n**Current Task/Prompt:**\n{prompt}"
            logger.debug(f"Generating text with full prompt (persona context type: {context_type}):\n{full_prompt[:500]}...")
        else:
            logger.debug("Generating text with prompt (no/incomplete persona):\n%s...", prompt[:500])
        
        # Default generation_config from original LLMManager
        generation_config_params = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
        }
        generation_config_params.update(kwargs.get("generation_config", {})) # Allow overriding via kwargs
        
        try:
            # Use the pre-initialized model
            response = await self.text_model.generate_content_async(
                full_prompt,
                generation_config=genai_types.GenerationConfig(**generation_config_params)
            )
            if hasattr(response, 'text') and response.text:
                logger.info(f"Gemini generated text successfully (length: {len(response.text)}).")
                return response.text.strip()
            else:
                logger.warning("Gemini returned empty or blocked response for text generation.")
                # Log candidate and finish reason if available for debugging
                if response.candidates and response.candidates[0].finish_reason:
                     logger.warning(f"Finish Reason: {response.candidates[0].finish_reason.name}")
                if response.prompt_feedback:
                    logger.warning(f"Prompt Feedback: {response.prompt_feedback}")
                return None
        except Exception as e:
            logger.error(f"Error during Gemini text generation: {e}", exc_info=True)
            return None

    async def analyze_image(self, image_path: str, context_type: str = "image_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        if self.config_dict.get('dry_run', False):
            logger.info(f"[DRY RUN] GeminiLLMProvider.analyze_image: returning placeholder for '{image_path}'")
            return f"[DRY_RUN_GEMINI_VISION] Image at {image_path}"

        if not self.is_enabled or not self.vision_model:
            logger.error("GeminiLLMProvider is not enabled or vision model not set. Cannot analyze image.")
            return None

        image_prompt = prompt_override or "Describe the image." # Use prompt_override as the main prompt
        
        full_prompt_parts = []
        # Simplified persona handling
        if self.persona and hasattr(self.persona, 'get_full_context_for_llm'):
            persona_context = self.persona.get_full_context_for_llm(context_type=context_type)
            full_prompt_parts.append(f"{persona_context}\n\n---\n\n**Current Task/Prompt:**\n{image_prompt}")
        else:
            full_prompt_parts.append(image_prompt)

        generation_config_params = kwargs.get("generation_config", {})

        try:
            if not os.path.exists(image_path):
                logger.error(f"Image file not found at path: {image_path}")
                return None

            with open(image_path, "rb") as f:
                image_bytes = f.read()
            
            # Determine MIME type based on file extension (simplified)
            ext = os.path.splitext(image_path)[1].lower()
            mime_type = f"image/{ext[1:]}" if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'] else "image/png" # Default to png
            if ext == ".jpg": mime_type = "image/jpeg"


            image_part = genai_types.Part(inline_data=genai_types.Blob(data=image_bytes, mime_type=mime_type))
            full_prompt_parts.insert(0, image_part) # Image part first usually

            response = await self.vision_model.generate_content_async(
                full_prompt_parts, # List of parts: image and text
                generation_config=genai_types.GenerationConfig(**generation_config_params) if generation_config_params else None
            )
            if hasattr(response, 'text') and response.text:
                logger.info(f"Gemini analyzed image {image_path} successfully.")
                return response.text.strip()
            else:
                logger.warning(f"Gemini returned empty or blocked response for image analysis of {image_path}.")
                if response.candidates and response.candidates[0].finish_reason:
                     logger.warning(f"Finish Reason: {response.candidates[0].finish_reason.name}")
                if response.prompt_feedback:
                    logger.warning(f"Prompt Feedback: {response.prompt_feedback}")
                return None
        except Exception as e:
            logger.error(f"Error during Gemini image analysis for {image_path}: {e}", exc_info=True)
            return None

    async def analyze_video(self, video_path: str, context_type: str = "video_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        logger.warning("GeminiLLMProvider.analyze_video is not yet implemented.")
        # Placeholder for future implementation.
        # Would involve similar logic to analyze_image but with video_part.
        # Example:
        # video_part = genai_types.Part(inline_data=genai_types.Blob(data=video_bytes, mime_type='video/mp4'))
        # response = await self.vision_model.generate_content_async([video_part, full_prompt_text_part])
        return None
