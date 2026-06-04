import pandas as pd
import os
# The caching pattern — professional habit
def load_data(url: str, local_path: str) -> pd.DataFrame:
    """Load from URL, save locally. On next run, use local copy."""

    if os.path.exists(local_path):  # already downloaded?
        print(f'Loading from cache: {local_path}')
        return pd.read_csv(local_path)

    print(f'Downloading from {url}...')
    df = pd.read_csv(url)

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    df.to_csv(local_path, index=False)  # save for next time

    print(f'Saved to {local_path}')
    return df