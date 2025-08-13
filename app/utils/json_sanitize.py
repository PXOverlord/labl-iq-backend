import math
import numpy as np
import pandas as pd
from decimal import Decimal
from datetime import datetime, date

def is_nan_or_inf(x) -> bool:
    try:
        return (x is None) or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) \
            or (isinstance(x, np.floating) and (np.isnan(x) or np.isinf(x)))
    except Exception:
        return False

def deep_clean_json_safe(obj):
    if obj is None:
        return None
    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        return 0.0 if is_nan_or_inf(v) else v
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, Decimal):
        f = float(obj)
        return 0.0 if is_nan_or_inf(f) else f
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    try:
        if pd.isna(obj):
            return 0.0
    except Exception:
        pass
    if isinstance(obj, dict):
        return {str(k): deep_clean_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        cleaned = [deep_clean_json_safe(v) for v in obj]
        return cleaned if isinstance(obj, list) else list(cleaned)
    return obj

def contains_nan_inf(obj) -> bool:
    if obj is None:
        return False
    if isinstance(obj, (float, np.floating)):
        return is_nan_or_inf(obj)
    if isinstance(obj, dict):
        return any(contains_nan_inf(v) for v in obj.values())
    if isinstance(obj, (list, tuple, set)):
        return any(contains_nan_inf(v) for v in obj)
    return False
