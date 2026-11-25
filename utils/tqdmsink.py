from tqdm import tqdm


# --- Define the tqdm sink. ---
class TqdmSink:
    def write(self, message):
        # tqdm.write prints safely above the progress bar without disrupting it.
        message = message.strip()
        if message:  # Avoid blank lines.
            tqdm.write(message)
    def flush(self):
        pass  # tqdm.write handles flushing.
