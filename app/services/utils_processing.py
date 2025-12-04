"""
Labl IQ Rate Analyzer - Data Processing Utilities

This module provides utility functions for data processing in the Labl IQ Rate Analyzer.
It includes:
1. Column mapping suggestions based on common column names
2. Weight unit conversion (oz, g to lbs)
3. Service level standardization

Date: May 2, 2025
"""

import re
import pandas as pd
import logging
from typing import Dict, List, Any, Optional, Union

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('labl_iq.utils_processing')

# Define constants for column mapping
COLUMN_ALIAS_MAP = {
    # Weight column aliases
    "weight": [
        "weight", "wt", "package weight", "pkg weight", "pkg wt", "parcel weight",
        "actual weight", "shipment weight", "item weight", "weight (lbs)", 
        "weight (oz)", "weight (g)", "weight in lbs", "weight in oz", "weight in g"
    ],
    
    # Dimension column aliases
    "length": [
        "length", "len", "package length", "pkg length", "pkg len", "parcel length",
        "l", "dim l", "dimension l", "length (in)", "length in inches", "dim1"
    ],
    "width": [
        "width", "wid", "package width", "pkg width", "pkg wid", "parcel width",
        "w", "dim w", "dimension w", "width (in)", "width in inches", "dim2"
    ],
    "height": [
        "height", "hgt", "package height", "pkg height", "pkg hgt", "parcel height",
        "h", "dim h", "dimension h", "height (in)", "height in inches", "dim3"
    ],
    
    # ZIP code column aliases
    "from_zip": [
        "from zip", "origin zip", "origin postal", "origin code", "ship from zip",
        "sender zip", "source zip", "from postal code", "origin postal code", "o zip",
        "origin", "from", "shipper zip", "shipper postal", "origin zip code", "from zip code"
    ],
    "to_zip": [
        "to zip", "dest zip", "destination zip", "destination postal", "destination code",
        "ship to zip", "recipient zip", "target zip", "to postal code", "destination postal code",
        "d zip", "destination", "to", "consignee zip", "consignee postal", "destination zip code", "to zip code"
    ],
    
    # Carrier column aliases
    "carrier": [
        "carrier", "shipping carrier", "shipper", "shipping company", "shipping service",
        "courier", "delivery service", "shipping provider", "logistics provider"
    ],
    
    # Rate column aliases
    "rate": [
        "rate", "cost", "price", "charge", "fee", "shipping cost", "shipping rate",
        "shipping price", "shipping charge", "shipping fee", "postage", "postage cost",
        "carrier rate", "carrier cost", "carrier price", "carrier charge", "carrier fee"
    ],
    
    # Service level column aliases
    "service_level": [
        "service level", "service", "shipping level", "shipping service", "delivery service",
        "delivery type", "shipping type", "service type", "delivery speed", "shipping speed",
        "delivery option", "shipping option", "service option"
    ],
    
    # Package type column aliases
    "package_type": [
        "package type", "pkg type", "parcel type", "shipment type", "container type",
        "packaging", "package", "container", "box type", "envelope type"
    ]
}

# Define constants for service level standardization
STANDARD_SERVICE_LEVEL_MAP = {
    # Standard service
    "standard": ["standard", "std", "regular", "ground", "normal", "basic", "economy", "eco"],
    
    # Expedited service
    "expedited": ["expedited", "exp", "express", "2day", "2-day", "second day", "2nd day", 
                 "two day", "2 day", "fast", "quick", "rapid"],
    
    # Priority service
    "priority": ["priority", "prio", "3day", "3-day", "third day", "3rd day", "three day", "3 day"],
    
    # Next day service
    "next_day": ["next day", "next-day", "overnight", "next", "1day", "1-day", "first day", 
                "1st day", "one day", "1 day", "nextday", "urgent", "same day"]
}

def suggest_columns(df: pd.DataFrame) -> Dict[str, str]:
    """
    Suggest column mappings based on header names.
    
    Args:
        df: DataFrame with the data to analyze
        
    Returns:
        Dict[str, str]: Suggested mapping of required fields to CSV columns
    """
    if df.empty or len(df.columns) == 0:
        logger.warning("Empty DataFrame provided for column mapping suggestion")
        return {}
        
    suggested_mapping = {}
    headers = [str(col).lower() for col in df.columns]
    
    # For each target field, try to find a matching column
    for field_key, aliases in COLUMN_ALIAS_MAP.items():
        # Try to find exact matches first
        exact_matches = [header for idx, header in enumerate(df.columns) 
                        if headers[idx] in aliases]
        
        if exact_matches:
            suggested_mapping[field_key] = exact_matches[0]
            continue
            
        # Try to find partial matches
        partial_matches = []
        for idx, header in enumerate(df.columns):
            header_norm = re.sub(r'[^a-zA-Z0-9]', '', headers[idx])
            
            # Check if any alias is contained in the normalized header
            for alias in aliases:
                alias_norm = re.sub(r'[^a-zA-Z0-9]', '', alias)
                if alias_norm in header_norm or header_norm in alias_norm:
                    partial_matches.append(header)
                    break
        
        if partial_matches:
            suggested_mapping[field_key] = partial_matches[0]
            continue
            
        # Try more flexible matching for specific fields
        if field_key in ['from_zip', 'to_zip']:
            # Special case for ZIP codes - look for origin/destination or from/to
            prefix = 'from' if field_key == 'from_zip' else 'to'
            alt_prefix = 'origin' if field_key == 'from_zip' else 'destination'
            
            for idx, header in enumerate(df.columns):
                header_lower = headers[idx]
                if (prefix in header_lower or alt_prefix in header_lower) and ('zip' in header_lower or 'code' in header_lower or 'postal' in header_lower):
                    suggested_mapping[field_key] = header
                    break
        
        # Special case for dimensions
        elif field_key in ['length', 'width', 'height']:
            dimension_abbr = field_key[0].lower()  # l, w, h
            for idx, header in enumerate(df.columns):
                header_lower = headers[idx]
                if dimension_abbr == header_lower or f"dim{dimension_abbr}" in header_lower or f"{dimension_abbr}dim" in header_lower:
                    suggested_mapping[field_key] = header
                    break
    
    # Map common field name variations
    field_variations = {
        'weight': ['wt', 'weight', 'package weight', 'pkg wt'],
        'length': ['len', 'length', 'l', 'dim1'],
        'width': ['wid', 'width', 'w', 'dim2'],
        'height': ['hgt', 'height', 'h', 'dim3'],
        'from_zip': ['origin', 'origin zip', 'from zip', 'ship from', 'from'],
        'to_zip': ['dest', 'destination', 'destination zip', 'to zip', 'ship to', 'to'],
        'carrier': ['carrier', 'shipper', 'shipping company'],
        'rate': ['cost', 'price', 'rate', 'amount', 'charge', 'fee']
    }
    
    # Try one more pass with simplified matching
    for field, variations in field_variations.items():
        if field not in suggested_mapping:
            for col in df.columns:
                col_lower = col.lower()
                if any(var in col_lower for var in variations):
                    suggested_mapping[field] = col
                    break
    
    # Map standard field names if they exist exactly
    standard_fields = {
        'weight': 'weight',
        'length': 'length',
        'width': 'width',
        'height': 'height',
        'from_zip': 'from_zip',
        'to_zip': 'to_zip',
        'carrier': 'carrier',
        'rate': 'rate'
    }
    
    for field, std_name in standard_fields.items():
        if field not in suggested_mapping and std_name in df.columns:
            suggested_mapping[field] = std_name
    
    # Add simple case-insensitive matching for common field names
    simple_mappings = {
        'weight': ['weight', 'Weight', 'WEIGHT'],
        'length': ['length', 'Length', 'LENGTH'],
        'width': ['width', 'Width', 'WIDTH'],
        'height': ['height', 'Height', 'HEIGHT'],
        'from_zip': ['origin', 'Origin', 'ORIGIN', 'from_zip', 'from zip'],
        'to_zip': ['destination', 'Destination', 'DESTINATION', 'to_zip', 'to zip'],
        'carrier': ['carrier', 'Carrier', 'CARRIER'],
        'rate': ['rate', 'Rate', 'RATE', 'cost', 'Cost', 'COST', 'price', 'Price', 'PRICE']
    }
    
    for field, variations in simple_mappings.items():
        if field not in suggested_mapping:
            for col in df.columns:
                if col in variations:
                    suggested_mapping[field] = col
                    break
    
    logger.info(f"Suggested column mapping: {suggested_mapping}")
    return suggested_mapping

def convert_weight_to_lbs(weight_series: pd.Series, unit_series: Optional[pd.Series] = None) -> pd.Series:
    """
    Convert weight values to pounds (lbs) from various units.
    
    Args:
        weight_series: Series containing weight values
        unit_series: Optional series containing unit information
        
    Returns:
        pd.Series: Weight values converted to pounds
    """
    # Create a copy to avoid modifying the original
    converted_weights = weight_series.copy()
    
    # If we have a unit series, use it for conversion
    if unit_series is not None:
        for idx, unit in unit_series.items():
            if pd.isna(unit) or pd.isna(converted_weights[idx]):
                continue
                
            unit = str(unit).lower().strip()
            
            # Convert based on unit
            if unit in ['oz', 'ounce', 'ounces']:
                converted_weights[idx] = converted_weights[idx] / 16.0
            elif unit in ['g', 'gram', 'grams']:
                converted_weights[idx] = converted_weights[idx] / 453.592
            # Assume pounds for other units or if unit is 'lb', 'lbs', 'pound', 'pounds'
    else:
        # Without explicit unit information, try to infer from column name or data patterns
        column_name = weight_series.name.lower() if hasattr(weight_series, 'name') and weight_series.name else ""
        
        # Check if column name contains unit information
        if 'lb' in column_name or 'pound' in column_name:
            logger.info(f"Detected pound unit in column name: {column_name}, no conversion needed")
            # Already in pounds, no conversion needed
        elif 'oz' in column_name or 'ounce' in column_name:
            logger.info(f"Detected ounce unit in column name: {column_name}, converting to pounds")
            converted_weights = converted_weights / 16.0
        elif 'kg' in column_name:
            logger.info(f"Detected kilogram unit in column name: {column_name}, converting to pounds")
            converted_weights = converted_weights * 2.20462
        elif 'g' in column_name:
            logger.info(f"Detected gram unit in column name: {column_name}, converting to pounds")
            converted_weights = converted_weights / 453.592
        else:
            # Try to infer from data patterns if column name doesn't help
            if converted_weights.median() > 100:  # Typical packages are rarely over 100 lbs
                logger.info("Detected possible gram values based on magnitude, converting to pounds")
                converted_weights = converted_weights / 453.592
            elif converted_weights.median() > 10 and converted_weights.median() < 50:
                # This range could be ounces for small packages
                logger.info("Detected possible ounce values based on magnitude, converting to pounds")
                converted_weights = converted_weights / 16.0
            # Otherwise assume it's already in pounds
    
    return converted_weights

def standardize_service_level(service_level_series: pd.Series) -> pd.Series:
    """
    Standardize service level values to a consistent set.
    
    Args:
        service_level_series: Series containing service level values
        
    Returns:
        pd.Series: Standardized service level values
    """
    # Create a copy to avoid modifying the original
    standardized_levels = service_level_series.copy()
    
    # Create a reverse mapping for easier lookup
    reverse_map = {}
    for standard, aliases in STANDARD_SERVICE_LEVEL_MAP.items():
        for alias in aliases:
            reverse_map[alias] = standard
    
    # Apply standardization
    for idx, level in service_level_series.items():
        if pd.isna(level):
            standardized_levels[idx] = "standard"  # Default to standard
            continue
            
        level_str = str(level).lower().strip()
        
        # Check for exact match in reverse map
        if level_str in reverse_map:
            standardized_levels[idx] = reverse_map[level_str]
            continue
            
        # Check for partial matches
        level_norm = re.sub(r'[^a-zA-Z0-9]', '', level_str)
        matched = False
        
        for alias, standard in reverse_map.items():
            alias_norm = re.sub(r'[^a-zA-Z0-9]', '', alias)
            if alias_norm in level_norm or level_norm in alias_norm:
                standardized_levels[idx] = standard
                matched = True
                break
                
        # Default to standard if no match found
        if not matched:
            standardized_levels[idx] = "standard"
            logger.warning(f"Unknown service level '{level}', defaulting to 'standard'")
    
    return standardized_levels

def clean_zip_codes(zip_series: pd.Series) -> pd.Series:
    """
    Clean and standardize ZIP codes.
    
    Args:
        zip_series: Series containing ZIP code values
        
    Returns:
        pd.Series: Cleaned ZIP code values
    """
    # Create a copy to avoid modifying the original
    cleaned_zips = zip_series.copy()
    
    # Apply cleaning to each value
    for idx, zip_code in zip_series.items():
        if pd.isna(zip_code):
            continue
            
        # Ensure value is a string
        zip_str = str(zip_code)
        
        # Remove any non-alphanumeric characters
        zip_clean = re.sub(r'[^a-zA-Z0-9]', '', zip_str)
        
        # For US ZIP codes, ensure it's 5 digits
        if len(zip_clean) > 5 and zip_clean.isdigit():
            zip_clean = zip_clean[:5]  # Truncate to first 5 digits
        elif len(zip_clean) < 5 and zip_clean.isdigit():
            zip_clean = zip_clean.zfill(5)  # Pad with leading zeros
            
        cleaned_zips[idx] = zip_clean
    
    return cleaned_zips
