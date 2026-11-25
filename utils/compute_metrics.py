import numpy as np

def compute_overall_passk(results):
    """
    Compute pass@k over the entire dataset.
    
    Args:
        results: list[list[float]]
            Each item contains one task's pass@k results, such as [x, y, z].

            
    Returns:
        list[float]
            Each item is the aggregate pass@k result for the corresponding k.
    """
    results = np.array(results)  # Convert to a NumPy array for vectorized processing.
    overall = results.mean(axis=0)  # Average across all tasks.
    return overall.tolist()

