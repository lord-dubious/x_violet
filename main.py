#!/usr/bin/env python3
"""
Entrypoint for x_violet agent. Run this script to start the bot.
"""
import logging
import colorlog  # For colorful logs

from xviolet.agent import Agent


def setup_logging():
    # Configure root logger with colorized output
    root = logging.getLogger()
    root.handlers.clear()
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    root.addHandler(handler)
    root.setLevel(logging.INFO)

# Use a specific logger for main, if preferred, or root logger is fine for simple script.
logger = logging.getLogger("xviolet.main") # Or just use logging.info directly

def main():
    setup_logging() # Existing logging setup
    logger.info("Starting x_violet agent...")

    # Get scheduling parameters from CLI
    try:
        from xviolet.cli_input import get_cli_scheduling_params
        from xviolet.config import config as agent_config # Use a distinct alias if needed, or direct 'config'

        logger.info("Requesting scheduling parameters from user via CLI...")
        cli_scheduling_params = get_cli_scheduling_params()
        
        if cli_scheduling_params: 
            agent_config.update_scheduling_params_from_cli(cli_scheduling_params)
            logger.info("AgentConfig updated with CLI scheduling parameters.")
        else:
            # This case might not be reachable if get_cli_scheduling_params always returns a dict or loops
            logger.info("No CLI scheduling parameters provided or process cancelled. Using default/env config.")
    except Exception as e:
        logger.error(f"Error obtaining or applying CLI scheduling parameters: {e}. Agent will use default/env config for scheduling.", exc_info=True)
        # Agent will proceed with default/env scheduling config loaded by AgentConfig.__init__

    # Initialize and run the agent
    # The Agent's __init__ will now use the potentially updated 'config' object
    try:
        logger.info("Initializing and running the agent...")
        agent = Agent()
        agent.run()
    except KeyboardInterrupt:
        logger.info("Agent run interrupted by user (KeyboardInterrupt). Exiting.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during agent execution: {e}", exc_info=True)
    finally:
        logger.info("x_violet agent shutting down.")


if __name__ == "__main__":
    main()
