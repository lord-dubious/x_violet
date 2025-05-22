# xviolet/media_tracker.py
import os
import logging

logger = logging.getLogger(__name__)

USED_MEDIA_LOG_FILE = "data/used_media.txt"

def _ensure_data_directory():
    """Ensures the data directory for the log file exists."""
    data_dir = os.path.dirname(USED_MEDIA_LOG_FILE)
    if data_dir and not os.path.exists(data_dir): # Check data_dir is not empty string
        try:
            os.makedirs(data_dir, exist_ok=True) # exist_ok=True to avoid error if dir exists
            logger.info(f"Created data directory: {data_dir}")
        except OSError as e:
            logger.error(f"Could not create data directory {data_dir}: {e}")
            return False
    return True

def load_used_media() -> set:
    """
    Reads the used media log file and returns a set of filenames.
    Returns an empty set if the file doesn't exist or an error occurs.
    """
    if not _ensure_data_directory():
        return set() # Cannot proceed if data directory cannot be ensured

    if not os.path.exists(USED_MEDIA_LOG_FILE):
        logger.info(f"Used media log file {USED_MEDIA_LOG_FILE} not found. Returning empty set.")
        return set()
    try:
        with open(USED_MEDIA_LOG_FILE, 'r') as f:
            used_files = {line.strip() for line in f if line.strip()}
            logger.info(f"Loaded {len(used_files)} items from {USED_MEDIA_LOG_FILE}")
            return used_files
    except IOError as e:
        logger.error(f"Error loading used media log {USED_MEDIA_LOG_FILE}: {e}")
        return set()

def mark_media_as_used(filename: str):
    """
    Appends a filename to the used media log file.
    """
    if not _ensure_data_directory():
        logger.error(f"Cannot mark media as used; data directory {os.path.dirname(USED_MEDIA_LOG_FILE)} could not be ensured.")
        return

    try:
        with open(USED_MEDIA_LOG_FILE, 'a') as f:
            f.write(filename + '\n')
        logger.info(f"Marked media as used: {filename} in {USED_MEDIA_LOG_FILE}")
    except IOError as e:
        logger.error(f"Error marking media as used in {USED_MEDIA_LOG_FILE} for {filename}: {e}")

def is_media_used(filename: str, used_media_set: set) -> bool:
    """
    Checks if a filename is in the provided set of used media.
    """
    return filename in used_media_set

if __name__ == '__main__':
    # Example usage and basic test
    logging.basicConfig(level=logging.INFO)
    
    # Clean up existing log for fresh test run if needed
    if os.path.exists(USED_MEDIA_LOG_FILE):
        os.remove(USED_MEDIA_LOG_FILE)
        logger.info(f"Removed existing log file for testing: {USED_MEDIA_LOG_FILE}")

    # Test loading when file doesn't exist
    initial_set = load_used_media()
    logger.info(f"Initial used media set (should be empty): {initial_set}")
    assert not initial_set

    # Test marking media as used
    media_to_mark = ["image1.jpg", "video.mp4", "image2.png"]
    for media in media_to_mark:
        mark_media_as_used(media)

    # Test loading after marking
    current_set = load_used_media()
    logger.info(f"Current used media set: {current_set}")
    assert len(current_set) == len(media_to_mark)
    for media in media_to_mark:
        assert is_media_used(media, current_set)

    # Test checking unused media
    assert not is_media_used("new_image.gif", current_set)

    # Test marking another media
    mark_media_as_used("another_image.jpeg")
    final_set = load_used_media()
    logger.info(f"Final used media set: {final_set}")
    assert len(final_set) == len(media_to_mark) + 1
    assert is_media_used("another_image.jpeg", final_set)
    
    logger.info("Media tracker basic tests completed.")
