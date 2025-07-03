import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
import math
import logging
from pathlib import Path
import os

# Import the calculation engine
from app.services.calc_engine import AmazonRateCalculator, calculate_rates as calc_engine_calculate_rates

# Import the enhanced processing utilities
from app.services.utils_processing import (
    suggest_columns, 
    convert_weight_to_lbs, 
    standardize_service_level,
    clean_zip_codes
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('labl_iq.processor')

# Initialize the calculator once (singleton pattern)
calculator = AmazonRateCalculator()

def process_data(file_path: str, column_mapping: Dict[str, str]) -> pd.DataFrame:
    """
    Process the uploaded file with the provided column mapping
    
    Args:
        file_path: Path to the uploaded file
        column_mapping: Dictionary mapping required fields to actual column names
        
    Returns:
        Processed DataFrame with standardized column names
    """
    # Read file based on extension
    try:
        if file_path.endswith('.csv'):
            # Try different encodings and handle potential issues
            try:
                df = pd.read_csv(file_path, encoding='utf-8')
            except UnicodeDecodeError:
                # Try other encodings if UTF-8 fails
                try:
                    df = pd.read_csv(file_path, encoding='latin1')
                except Exception:
                    df = pd.read_csv(file_path, encoding='cp1252')
            
            # Check if DataFrame is empty or has no columns
            if df.empty or len(df.columns) == 0:
                logger.error(f"Empty DataFrame or no columns after reading {file_path}")
                raise ValueError(f"No data found in file: {file_path}")
        else:
            # For Excel files
            df = pd.read_excel(file_path)
        
        # Log column names for debugging
        logger.info(f"File columns: {df.columns.tolist()}")
        logger.info(f"Column mapping: {column_mapping}")
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {str(e)}", exc_info=True)
        raise ValueError(f"Error reading file: {str(e)}")
    
    # Create a new DataFrame with standardized column names
    processed_df = pd.DataFrame()
    
    # Map columns based on user selection
    for standard_name, file_column in column_mapping.items():
        if file_column in df.columns:
            processed_df[standard_name] = df[file_column]
        else:
            logger.warning(f"Column '{file_column}' not found in file, available columns: {df.columns.tolist()}")
    
    # Ensure all required columns exist
    required_columns = ["weight", "length", "width", "height", "from_zip", "to_zip", "carrier", "rate"]
    for col in required_columns:
        if col not in processed_df.columns:
            processed_df[col] = None
    
    # Convert numeric columns
    numeric_cols = ["weight", "length", "width", "height", "rate"]
    for col in numeric_cols:
        if col in processed_df.columns:
            processed_df[col] = pd.to_numeric(processed_df[col], errors='coerce')
    
    # Apply enhanced data processing
    
    # 1. Convert weight to pounds if needed
    if 'weight' in processed_df.columns:
        processed_df['weight'] = convert_weight_to_lbs(processed_df['weight'])
    
    # 2. Clean ZIP codes
    if 'from_zip' in processed_df.columns:
        processed_df['from_zip'] = clean_zip_codes(processed_df['from_zip'])
    if 'to_zip' in processed_df.columns:
        processed_df['to_zip'] = clean_zip_codes(processed_df['to_zip'])
    
    # 3. Standardize service level if present
    if 'service_level' in processed_df.columns:
        processed_df['service_level'] = standardize_service_level(processed_df['service_level'])
    
    return processed_df

def suggest_column_mapping(df: pd.DataFrame) -> Dict[str, str]:
    """
    Suggest column mappings based on header names.
    
    Args:
        df: DataFrame with the data to analyze
        
    Returns:
        Dict[str, str]: Suggested mapping of required fields to CSV columns
    """
    return suggest_columns(df)

def calculate_dimensional_weight(length: float, width: float, height: float, divisor: float = 139) -> float:
    """Calculate dimensional weight using the standard formula"""
    if not all(isinstance(x, (int, float)) and x > 0 for x in [length, width, height]):
        return 0
    
    dim_weight = (length * width * height) / divisor
    return math.ceil(dim_weight * 10) / 10  # Round up to nearest 0.1

def calculate_amazon_rate(
    weight: float, 
    length: float, 
    width: float, 
    height: float,
    from_zip: str,
    to_zip: str,
    service_level: str = 'standard',
    package_type: str = 'box',
    current_rate: float = None,
    fuel_surcharge_pct: float = 16.0,
    markup_pct: float = 10.0
) -> Dict[str, Any]:
    """
    Calculate Amazon shipping rate based on package dimensions and weight using the full calculation engine
    
    Args:
        weight: Package weight in pounds
        length, width, height: Package dimensions in inches
        from_zip, to_zip: Origin and destination ZIP codes
        service_level: Service level (standard, expedited, priority, next_day)
        package_type: Type of package (box, envelope, pak)
        current_rate: Current carrier rate for comparison
        fuel_surcharge_pct: Fuel surcharge percentage
        markup_pct: Markup percentage
        
    Returns:
        Dictionary with calculated rates and details
    """
    # Calculate dimensional weight
    dim_weight = calculate_dimensional_weight(length, width, height)
    
    # Use the greater of actual weight or dimensional weight
    billable_weight = max(weight, dim_weight) if weight and dim_weight else weight or dim_weight or 0
    
    # Update calculator criteria if needed
    calculator.update_criteria({
        'fuel_surcharge_percentage': fuel_surcharge_pct,
        'markup_percentage': markup_pct
    })
    
    # Create a shipment dictionary for the calculator
    shipment = {
        'shipment_id': 'CALC-1',
        'origin_zip': from_zip,
        'destination_zip': to_zip,
        'weight': weight,
        'billable_weight': billable_weight,
        'length': length,
        'width': width,
        'height': height,
        'package_type': package_type,
        'service_level': service_level,
        'carrier_rate': current_rate
    }
    
    # Calculate the rate using the full calculation engine
    result = calculator.calculate_shipment_rate(shipment)
    
    # Return a simplified result dictionary
    return {
        "billable_weight": billable_weight,
        "dim_weight": dim_weight,
        "zone": result.get('zone', 'Unknown'),
        "base_rate": result.get('base_rate', 0.0),
        "fuel_charge": result.get('fuel_surcharge', 0.0),
        "das_charge": result.get('das_surcharge', 0.0),
        "edas_charge": result.get('edas_surcharge', 0.0),
        "remote_charge": result.get('remote_surcharge', 0.0),
        "total_surcharges": result.get('total_surcharges', 0.0),
        "markup_amount": result.get('markup_amount', 0.0),
        "markup_percentage": result.get('markup_percentage', 0.0),
        "total_rate": result.get('final_rate', 0.0),
        "savings": result.get('savings', 0.0),
        "savings_percent": result.get('savings_percent', 0.0),
        "errors": result.get('errors', '')
    }

def calculate_rates(
    data: pd.DataFrame, 
    amazon_rate: float = 0.35, 
    fuel_surcharge: float = 0.05,
    markup_percent: float = 10.0,
    service_level: str = 'standard',
    calculation_criteria: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """
    Calculate Amazon rates for all packages and compare with current rates
    
    Args:
        data: Processed DataFrame with package information
        amazon_rate: Base Amazon rate per package (legacy parameter, not used with new engine)
        fuel_surcharge: Fuel surcharge percentage (as decimal)
        markup_percent: Markup percentage
        service_level: Service level (standard, expedited, priority, next_day)
        calculation_criteria: Dictionary with advanced calculation criteria
        
    Returns:
        List of dictionaries with rate comparison results
    """
    results = []
    logger.info(f"Starting rate calculation with {len(data)} rows")
    logger.info(f"Data columns: {data.columns.tolist()}")
    
    # Check if we have the minimal required data
    if 'weight' not in data.columns:
        logger.error("Weight column is missing from the dataset")
        # Create a dummy result to avoid empty results page
        return [{
            "package_id": "ERROR",
            "error_message": "Weight column is required but missing from your data",
            "weight": 0,
            "dimensions": "0x0x0",
            "from_zip": "N/A",
            "to_zip": "N/A",
            "carrier": "Unknown",
            "current_rate": 0,
            "amazon_rate": 0,
            "billable_weight": 0,
            "zone": "Unknown",
            "savings": 0,
            "savings_percent": 0,
            "errors": "Missing required weight data"
        }]
    
    # Convert fuel_surcharge from decimal to percentage if not provided in criteria
    fuel_surcharge_pct = fuel_surcharge * 100
    
    # Prepare criteria for calculator
    criteria = {
        'fuel_surcharge_percentage': fuel_surcharge_pct,
        'markup_percentage': markup_percent
    }
    
    # Update with advanced settings if provided
    if calculation_criteria:
        criteria.update(calculation_criteria)
    
    # Update calculator criteria
    calculator.update_criteria(criteria)
    
    # Fill missing values with defaults to avoid errors
    data_copy = data.copy()
    if 'from_zip' not in data_copy.columns or data_copy['from_zip'].isna().all():
        logger.warning("No origin ZIP codes found, using default")
        data_copy['from_zip'] = '10001'  # Default NYC ZIP
    
    # DO NOT set default destination ZIP - let calc_engine handle missing values
    # if 'to_zip' not in data_copy.columns or data_copy['to_zip'].isna().all():
    #     logger.warning("No destination ZIP codes found, using default")
    #     data_copy['to_zip'] = '60601'  # Default Chicago ZIP - This is explicitly excluded from DAS charges
    
    # Fill other missing values
    for col in ['length', 'width', 'height']:
        if col not in data_copy.columns or data_copy[col].isna().all():
            logger.warning(f"No {col} values found, using default of 10")
            data_copy[col] = 10  # Default dimension
    
    # Prepare shipments list for batch calculation
    shipments = []
    for idx, row in data_copy.iterrows():
        # Create a shipment dictionary with defaults for missing values
        
        # Handle 'from_zip' with proper validation
        from_zip = row.get('from_zip', '10001')
        if pd.isna(from_zip) or (isinstance(from_zip, str) and from_zip.strip() == ''):
            from_zip = '10001'  # Default NYC ZIP
        
        # Handle 'to_zip' - DO NOT set default destination ZIP
        to_zip = row.get('to_zip')
        # Leave null/empty destination ZIPs as they are - calc_engine will handle them
        # if pd.isna(to_zip) or (isinstance(to_zip, str) and to_zip.strip() == ''):
        #     to_zip = '60601'  # Default Chicago ZIP - This is explicitly excluded from DAS charges
        
        shipment = {
            'shipment_id': str(idx),
            'origin_zip': str(from_zip)[:5],
            'destination_zip': str(to_zip)[:5],
            'weight': float(row.get('weight', 1) or 1),  # Default to 1 if None or 0
            'length': float(row.get('length', 10) or 10),
            'width': float(row.get('width', 10) or 10),
            'height': float(row.get('height', 10) or 10),
            'package_type': 'box',  # Default to box
            'service_level': row.get('service_level', service_level) or service_level,  # Default to parameter if None
            'carrier_rate': float(row.get('rate', 0) or 0)
        }
        
        # Calculate dimensional weight
        dim_weight = calculate_dimensional_weight(
            shipment['length'], 
            shipment['width'], 
            shipment['height']
        )
        
        # Use the greater of actual weight or dimensional weight
        shipment['billable_weight'] = max(shipment['weight'], dim_weight) if shipment['weight'] and dim_weight else shipment['weight'] or dim_weight or 1.0
        
        shipments.append(shipment)
    
    logger.info(f"Prepared {len(shipments)} shipments for rate calculation")
    
    try:
        # Calculate rates in batch
        calculated_rates, stats = calc_engine_calculate_rates(shipments)
        logger.info(f"Successfully calculated rates for {len(calculated_rates)} shipments")
    except Exception as e:
        logger.error(f"Error in batch rate calculation: {str(e)}", exc_info=True)
        # Return error results
        return [{
            "package_id": "ERROR",
            "error_message": f"Rate calculation error: {str(e)}",
            "weight": 0,
            "dimensions": "0x0x0",
            "from_zip": "N/A",
            "to_zip": "N/A",
            "carrier": "Unknown",
            "current_rate": 0,
            "amazon_rate": 0,
            "billable_weight": 0,
            "zone": "Unknown",
            "savings": 0,
            "savings_percent": 0,
            "errors": str(e)
        }]
    
    # Process results
    for result in calculated_rates:
        # Format the result for the API response
        carrier = 'Unknown'
        try:
            if result.get('shipment_id', '').isdigit():
                idx = int(result.get('shipment_id', 0))
                if 'carrier' in data.columns and idx < len(data):
                    carrier = data.iloc[idx].get('carrier', 'Unknown')
                    if pd.isna(carrier):
                        carrier = 'Unknown'
        except Exception:
            pass
        
        # Handle possible NaN values in results
        def safe_value(value, default=0):
            """Return the value or default if it's NaN"""
            if pd.isna(value) or value is None or (isinstance(value, float) and math.isnan(value)):
                return default
            return value
        
        weight = safe_value(result.get('weight', 0))
        length = safe_value(result.get('length', 0))
        width = safe_value(result.get('width', 0))
        height = safe_value(result.get('height', 0))
        
        formatted_result = {
            "package_id": str(result.get('shipment_id', 'N/A')),
            "weight": weight,
            "dimensions": f"{length}x{width}x{height}",
            "from_zip": str(result.get('origin_zip', 'N/A')),
            "to_zip": str(result.get('destination_zip', 'N/A')),
            "carrier": carrier,
            "current_rate": safe_value(result.get('carrier_rate', 0)),
            "amazon_rate": safe_value(result.get('final_rate', 0)),
            "billable_weight": safe_value(result.get('billable_weight', 0)),
            "zone": result.get('zone', 'Unknown'),
            "base_rate": safe_value(result.get('base_rate', 0)),
            "fuel_surcharge": safe_value(result.get('fuel_surcharge', 0)),
            "das_surcharge": safe_value(result.get('das_surcharge', 0)),
            "edas_surcharge": safe_value(result.get('edas_surcharge', 0)),
            "remote_surcharge": safe_value(result.get('remote_surcharge', 0)),
            "total_surcharges": safe_value(result.get('total_surcharges', 0)),
            "markup_amount": safe_value(result.get('markup_amount', 0)),
            "markup_percentage": safe_value(result.get('markup_percentage', 0)),
            "savings": safe_value(result.get('savings', 0)),
            "savings_percent": safe_value(result.get('savings_percent', 0)),
            "errors": result.get('errors', '')
        }
        
        results.append(formatted_result)
    
    logger.info(f"Returning {len(results)} results")
    return results
