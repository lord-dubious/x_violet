"""
Persona loader for x_violet.
Loads and parses the character persona (holly.json) and provides helpers for LLM and agent logic.
"""
import os
from dotenv import load_dotenv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class Persona:
    def __init__(self, character_path: Optional[str] = None):
        """
        Loads the persona from the provided character JSON file.
        If no path is given, checks the CHARACTER_FILE env variable, then defaults to x_violet/character/holly.json relative to the repo root.
        """
        # Load .env if not already loaded
        load_dotenv()
        env_character_path = os.getenv("CHARACTER_FILE")

        # Priority: argument > env > default
        if character_path:
            resolved_path = Path(character_path)
        elif env_character_path:
            resolved_path = Path(env_character_path)
        else:
            resolved_path = Path("character/holly.json")

        # Always resolve relative paths from the current working directory
        if not resolved_path.is_absolute():
            resolved_path = (Path(os.getcwd()) / resolved_path).resolve()
        self.character_file_path = resolved_path
        print(f"[Persona Loader] Resolved persona file path: {self.character_file_path}")

        if not self.character_file_path.exists():
            raise FileNotFoundError(f"Character file not found: {self.character_file_path}")

        try:
            with open(self.character_file_path, encoding="utf-8-sig") as f:
                raw = f.read()
                # Remove leading/trailing whitespace or blank lines that might cause issues
                raw = raw.lstrip()
                try:
                    self.data = json.loads(raw)
                except json.JSONDecodeError as e:
                    # Print a snippet of the raw content for debugging
                    snippet = '\n'.join(raw.splitlines()[:10])
                    raise ValueError(
                        f"Error decoding JSON from {self.character_file_path}: {e}\n"
                        f"First 10 lines of file:\n{snippet}"
                    )
        except Exception as e:
            raise IOError(f"Error reading character file {self.character_file_path}: {e}")

    @property
    def name(self) -> str:
        return self.data.get("name", "Unknown Persona")

    @property
    def bio(self) -> List[str]:
        return self.data.get("bio", [])

    @property
    def system(self) -> str:
        """The core system prompt defining the roleplay character."""
        return self.data.get("system", "Act as a helpful AI assistant.")

    @property
    def lore(self) -> List[str]:
        return self.data.get("lore", [])

    @property
    def style(self) -> Dict[str, List[str]]:
        """Style guidelines for different contexts (all, chat, post)."""
        return self.data.get("style", {})

    @property
    def adjectives(self) -> List[str]:
        return self.data.get("adjectives", [])

    @property
    def topics(self) -> List[str]:
        return self.data.get("topics", [])

    @property
    def message_examples(self) -> List[Any]:
        """Few-shot examples for chat interactions."""
        return self.data.get("messageExamples", [])

    @property
    def post_examples(self) -> List[str]:
        """Few-shot examples for creating posts."""
        return self.data.get("postExamples", [])

    def get_style_guidelines(self, context: str = "all") -> List[str]:
        """Get style guidelines for a specific context ('all', 'chat', 'post')."""
        return self.style.get(context, self.style.get("all", []))

    def persona_summary(self) -> str:
        """
        Returns a concise summary string of the persona for basic context.
        Includes name, system prompt overview, and key adjectives.
        """
        summary = f"You are {self.name}. Your core instruction is: '{self.system}'. "
        if self.adjectives:
            summary += f"Key personality traits: {', '.join(self.adjectives)}. "
        return summary.strip()

    def get_full_context_for_llm(self, context_type: str = "chat") -> str:
        """
        Generates a comprehensive context string suitable for priming an LLM.
        Includes system prompt, bio, lore, relevant style, adjectives, and topics.

        Args:
            context_type: 'chat' or 'post' to tailor style guidelines and examples.
        """
        context_parts = [f"## Roleplay Instructions for {self.name}"]
        context_parts.append(f"**Core System Prompt:** {self.system}")

        if self.bio:
            bio_str = "\n- ".join(self.bio)
            context_parts.append(f"**Bio Snippets:**\n- {bio_str}")
        if self.lore:
            lore_str = "\n- ".join(self.lore)
            context_parts.append(f"**Key Lore/Background:**\n- {lore_str}")
        if self.adjectives:
            adj_str = ", ".join(self.adjectives)
            context_parts.append(f"**Personality Adjectives:** {adj_str}")
        if self.topics:
            topic_str = ", ".join(self.topics)
            context_parts.append(f"**Common Topics:** {topic_str}")

        style_rules = self.get_style_guidelines("all") + self.get_style_guidelines(context_type)
        # Remove duplicates while preserving order if necessary (simple list conversion is fine here)
        unique_style_rules = list(dict.fromkeys(style_rules))
        if unique_style_rules:
            style_str = "\n- ".join(unique_style_rules)
            context_parts.append(f"**Style Guidelines ({context_type}):**\n- {style_str}")

        # Add relevant examples
        if context_type == "chat" and self.message_examples:
            context_parts.append("\n**Example Chat Interactions:**")
            for i, example in enumerate(self.message_examples):
                chat_str = f"Example {i+1}:"
                # Ensure example is a list of dicts with 'user' and 'content'
                if isinstance(example, list):
                    for turn in example:
                        if isinstance(turn, dict) and 'user' in turn and 'content' in turn and 'text' in turn['content']:
                            user = turn['user']
                            text = turn['content']['text']
                            # Indent each line of the turn for clarity
                            chat_str += f"\n  {user}: {text}"
                context_parts.append(chat_str)

        elif context_type == "post" and self.post_examples:
            post_examples_str = "\n- ".join(self.post_examples)
            context_parts.append(f"\n**Example Posts:**\n- {post_examples_str}")

        return "\n\n".join(context_parts)
