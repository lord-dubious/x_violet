# xviolet/cli_input.py
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def get_cli_scheduling_params() -> Dict[str, Any]:
    params: Dict[str, Any] = {} # Ensure params is typed
    print("\n--- Configure Scheduling Parameters ---")

    while True: # Loop for confirmation
        # Interval Unit
        while True:
            unit_raw = input("Enter scheduling interval unit (days, hours, minutes) [default: hours]: ").strip().lower()
            if not unit_raw:
                params['interval_unit'] = 'hours'
                break
            if unit_raw in ['days', 'd', 'day']:
                params['interval_unit'] = 'days'
                break
            elif unit_raw in ['hours', 'h', 'hour']:
                params['interval_unit'] = 'hours'
                break
            elif unit_raw in ['minutes', 'm', 'minute', 'min']:
                params['interval_unit'] = 'minutes'
                break
            else:
                print("Invalid unit. Please enter 'days', 'hours', or 'minutes'.")
        
        # Interval Value
        while True:
            default_interval_value = 6
            # Adjust default based on unit for user-friendliness, though final conversion is to seconds
            if params['interval_unit'] == 'days': default_interval_value = 1
            elif params['interval_unit'] == 'minutes': default_interval_value = 30

            val_raw = input(f"Enter scheduling interval value for {params['interval_unit']} (integer) [default: {default_interval_value}]: ").strip()
            if not val_raw:
                params['interval_value'] = default_interval_value
                break
            try:
                val_int = int(val_raw)
                if val_int > 0:
                    params['interval_value'] = val_int
                    break
                else:
                    print("Interval value must be a positive integer.")
            except ValueError:
                print("Invalid input. Please enter an integer.")

        # Total Tweets
        while True:
            val_raw = input("Enter total number of tweets to schedule per cycle (integer) [default: 5]: ").strip()
            if not val_raw:
                params['total_tweets'] = 5
                break
            try:
                val_int = int(val_raw)
                if val_int >= 0: 
                    params['total_tweets'] = val_int
                    break
                else:
                    print("Total tweets must be a non-negative integer.")
            except ValueError:
                print("Invalid input. Please enter an integer.")

        # Media Tweets
        while True:
            # Ensure total_tweets is accessed after it's set
            max_possible_media = params.get('total_tweets', 0) # Default to 0 if total_tweets not set (should not happen)
            default_media_tweets = min(2, max_possible_media)

            val_raw = input(f"Enter number of media tweets per cycle (0 to {max_possible_media}) [default: {default_media_tweets}]: ").strip()
            if not val_raw:
                params['media_tweets'] = default_media_tweets
                break
            try:
                val_int = int(val_raw)
                if 0 <= val_int <= max_possible_media:
                    params['media_tweets'] = val_int
                    break
                else:
                    print(f"Media tweets must be between 0 and {max_possible_media}.")
            except ValueError:
                print("Invalid input. Please enter an integer.")

        # Confirmation
        print("\n--- Scheduling Summary ---")
        print(f"- Interval: Every {params.get('interval_value', 'N/A')} {params.get('interval_unit', 'N/A')}")
        print(f"- Tweets per cycle: {params.get('total_tweets', 'N/A')}")
        print(f"- Media tweets per cycle: {params.get('media_tweets', 'N/A')}")
        
        confirm_raw = input("Proceed with these settings? (yes/no) [default: yes]: ").strip().lower()
        if not confirm_raw or confirm_raw in ['yes', 'y']:
            logger.info(f"CLI scheduling parameters confirmed: {params}")
            return params
        elif confirm_raw in ['no', 'n']:
            print("Re-entering scheduling parameters...")
        else:
            print("Invalid choice for confirmation. Re-entering scheduling parameters...")

if __name__ == '__main__':
    # Example of how to use the function
    logging.basicConfig(level=logging.INFO) # Basic logging for test
    cli_settings = get_cli_scheduling_params()
    print(f"\nFunction returned: {cli_settings}")
