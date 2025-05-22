# xviolet/llm/base_llm.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List # List was in the example, kept it.

class BaseLLMProvider(ABC):
    @abstractmethod
    def __init__(self, config: Dict[str, Any]):
        self.config_dict = config # Store the passed config dict
        # Common initialization if any, e.g., loading API keys, model names from config
        # Specific API key loading and client init should be in the concrete provider.
        pass

    @abstractmethod
    async def generate_text(self, prompt: str, context_type: str = "general", **kwargs) -> Optional[str]:
        """Generates text based on a prompt."""
        pass

    @abstractmethod
    async def analyze_image(self, image_path: str, context_type: str = "image_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        """Analyzes an image and returns a text description or caption."""
        pass

    @abstractmethod
    async def analyze_video(self, video_path: str, context_type: str = "video_analysis", prompt_override: Optional[str] = None, **kwargs) -> Optional[str]:
        """Analyzes a video and returns a text description or caption. Placeholder for now."""
        pass
