#!/usr/bin/env python3
"""
Labl IQ Rate Analyzer - Calculation Engine Module

This module handles the rate calculations for the Labl IQ Rate Analyzer.
It provides functionality for:
1. Determining shipping zones based on origin and destination ZIP codes
2. Identifying applicable surcharges (like DAS) based on destination ZIP codes
3. Calculating base shipping rates based on weight, dimensions, and zone
4. Applying applicable surcharges (DAS, fuel, etc.)
5. Applying user-configured discounts and markups
6. Calculating margins compared to current rates

Date: April 22, 2025
"""

import os
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Any, Optional, Tuple, Union, Set
import bisect
import math
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('labl_iq.calc_engine')

def _sanitize_result_row(row):
    """Sanitize a result row to ensure JSON compliance"""
    if isinstance(row, dict):
        return {k: _sanitize_result_row(v) for k, v in row.items()}
    elif isinstance(row, list):
        return [_sanitize_result_row(item) for item in row]
    elif isinstance(row, float) and (np.isnan(row) or np.isinf(row)):
        return 0.0
    elif str(row).lower() == 'nan' or str(row).lower() == 'inf':
        return 0.0
    else:
        return row

def _to_num(value, default=0.0):
    """Convert value to number, handling NaN and None"""
    if pd.isna(value) or value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def _coalesce_num(*values, default=0.0):
    """Return first non-NaN, non-None value, or default"""
    for value in values:
        if not pd.isna(value) and value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                continue
    return default

class CalculationError(Exception):
    """Base exception for all calculation errors."""
    pass

class ReferenceDataError(CalculationError):
    """Exception raised when reference data cannot be loaded or is invalid."""
    pass

class ZoneLookupError(CalculationError):
    """Exception raised when zone lookup fails."""
    pass

class RateCalculationError(CalculationError):
    """Exception raised when rate calculation fails."""
    pass

class AmazonRateCalculator:
    """
    Main class for calculating Amazon shipping rates.
    
    This class handles the entire rate calculation process:
    1. Loading reference data (zone matrix, DAS zips, rate tables)
    2. Determining shipping zones
    3. Calculating base rates
    4. Applying surcharges
    5. Applying discounts and markups
    6. Calculating margins
    """
    
    def __init__(self, template_path: str = None):
        """
        Initialize the AmazonRateCalculator.
        
        Args:
            template_path: Path to the Excel template with reference data
        """
        # If template_path is not provided, use the default path
        if template_path is None:
            # Use a path relative to this file
            current_dir = os.path.abspath(os.path.dirname(__file__))
            template_path = os.path.join(current_dir, 'reference_data', '2025 Labl IQ Rate Analyzer Template.xlsx')
            logger.info(f"Using default template path: {template_path}")
        
        # Check if template_path is a file path or just a filename
        self.template_path = template_path
        if not os.path.isfile(template_path):
            # Try to locate the file in common locations
            current_dir = os.path.abspath(os.path.dirname(__file__))
            possible_paths = [
                os.path.join(current_dir, template_path),
                os.path.join(current_dir, 'reference_data', template_path),
                os.path.join(current_dir, 'data', template_path),
                os.path.join(os.path.dirname(current_dir), template_path),
                template_path
            ]
            
            for path in possible_paths:
                if os.path.isfile(path):
                    self.template_path = path
                    break
        
        self.zone_matrix = None
        self.das_zips = None
        self.das_zips_dict = {}
        self.edas_zips_dict = {}
        self.remote_zips_dict = {}
        self.rate_table = None
        self.criteria = None
        self.criteria_values = {}
        
        # Load reference data
        self.load_reference_data()
        
    def load_reference_data(self) -> None:
        """
        Load reference data from the Excel template.
        
        This includes:
        - UPS Zone matrix for origin-destination ZIP code pairs
        - Amazon DAS ZIP codes for delivery area surcharges
        - Amazon Rates for base shipping rates
        - Criteria for discount/markup calculations and other parameters
        
        Raises:
            ReferenceDataError: If reference data cannot be loaded or is invalid
        """
        try:
            logger.info(f"Loading reference data from {self.template_path}")
            
            # Load UPS Zone matrix
            self.zone_matrix = pd.read_excel(
                self.template_path, 
                sheet_name='UPS Zone matrix_April 2024'
            )
            
            # Validate zone matrix structure
            if self.zone_matrix.shape[0] < 2 or self.zone_matrix.shape[1] < 2:
                raise ReferenceDataError("Zone matrix must have at least 2 rows and 2 columns")
            
            # Set the first column as index (origin ZIPs)
            self.zone_matrix.set_index('Unnamed: 0', inplace=True)
            
            # Convert all values to numeric, replacing non-numeric with NaN
            self.zone_matrix = self.zone_matrix.apply(pd.to_numeric, errors='coerce')
            
            # Validate that we have valid zones
            invalid_zones = self.zone_matrix.isna().sum().sum()
            if invalid_zones > 0:
                logger.warning(f"Found {invalid_zones} invalid zones in matrix")
            
            # Ensure index contains origin ZIPs and columns contain destination ZIPs
            if not all(str(x).isdigit() for x in self.zone_matrix.index):
                raise ReferenceDataError("First column must contain origin ZIP prefixes")
            
            if not all(str(x).isdigit() for x in self.zone_matrix.columns):
                raise ReferenceDataError("Column headers must contain destination ZIP prefixes")
            
            logger.info(f"Loaded UPS Zone matrix with shape {self.zone_matrix.shape}")
            
            # Clean the zone matrix to fix invalid values
            self.clean_zone_matrix()
            
            # Load Amazon DAS ZIP codes
            self.das_zips = pd.read_excel(
                self.template_path,
                sheet_name='Amazon DAS Zips and Types'
            )
            
            # Clean up DAS zips data
            # Create separate dictionaries for each surcharge type
            self.das_zips_dict = {}
            self.edas_zips_dict = {}
            self.remote_zips_dict = {}
            
            # Process ZIP codes by type
            for _, row in self.das_zips.iterrows():
                if pd.notna(row.iloc[0]):
                    zip_code = str(row.iloc[0]).strip()
                    
                    # Skip header rows
                    if zip_code == "Zipcode" or not zip_code.isdigit():
                        continue
                        
                    # Standardize ZIP code format (5 digits)
                    zip_code = zip_code.zfill(5)[:5]
                    
                    # Store by surcharge type
                    das_col = 1  # "Do DAS, EDAS or RAS apply?" column
                    edas_col = 2  # "EDAS" column
                    remote_col = 3  # "Remote Area in Continental US" column
                    
                    self.das_zips_dict[zip_code] = str(row.iloc[das_col]).strip() == "Yes"
                    self.edas_zips_dict[zip_code] = str(row.iloc[edas_col]).strip() == "Yes"
                    self.remote_zips_dict[zip_code] = str(row.iloc[remote_col]).strip() == "Yes"
            
            logger.info(f"Loaded {len(self.das_zips_dict)} DAS ZIP codes")
            logger.info(f"Loaded {len(self.edas_zips_dict)} EDAS ZIP codes")
            logger.info(f"Loaded {len(self.remote_zips_dict)} Remote ZIP codes")
            
            # Load Amazon Rates
            self.rate_table = pd.read_excel(
                self.template_path,
                sheet_name='Amazon Rates',
                skiprows=2  # Skip the first two rows
            )
            
            # Rename columns
            self.rate_table.columns = ['Cntr', 'Rate Type', 'lbs', '1', '2', '3', '4', '5', '6', '7', '8']
            
            # Clean up rate table
            # Convert weight breaks to numeric
            self.rate_table['lbs'] = pd.to_numeric(self.rate_table['lbs'], errors='coerce')
            
            # Convert rate columns to numeric
            for col in self.rate_table.columns:
                if col not in ['Cntr', 'Rate Type', 'lbs']:
                    self.rate_table[col] = pd.to_numeric(self.rate_table[col], errors='coerce')
            
            logger.info(f"Loaded Amazon Rates with {len(self.rate_table)} weight breaks")
            
            # Load Criteria
            self.criteria = pd.read_excel(
                self.template_path,
                sheet_name='Criteria',
                header=None
            )
            
            # Extract key criteria values
            self.extract_criteria_values()
            
            # Add default service level markups if not loaded from file
            if 'service_level_markups' not in self.criteria_values:
                self.criteria_values['service_level_markups'] = {
                    'standard': 0.0,
                    'expedited': 0.0,
                    'priority': 0.0,
                    'next_day': 0.0
                }

            logger.info("Successfully loaded all reference data")
            
        except Exception as e:
            logger.error(f"Failed to load reference data: {str(e)}")
            raise ReferenceDataError(f"Failed to load reference data: {str(e)}")
    
    def extract_criteria_values(self) -> None:
        """
        Extract and validate criteria values from the 'Criteria' sheet.
        """
        try:
            # Default values for criteria
            self.criteria_values = {
                'origin_zip': '10001',  # NYC ZIP (changed from 46307)
                'fuel_surcharge': 0.0,
                'fuel_surcharge_percentage': 16.0,
                'das_surcharge': 1.98,
                'edas_surcharge': 3.92,
                'remote_surcharge': 14.15,
                'dim_divisor': 139.0,
                'discount_percent': 0.0,
                'markup_percentage': 10.0
            }
            
            # Extract values by exact match on first column
            for idx, row in self.criteria.iterrows():
                if pd.isna(row[0]):
                    continue
                    
                key = str(row[0]).strip()
                if key == "Client Origin Zip":
                    value = str(row[1]).strip()
                    # Check for 'nan' string and other invalid values
                    if value.lower() == 'nan' or value == '' or pd.isna(row[1]):
                        self.criteria_values['origin_zip'] = '10001'  # Use default NYC ZIP
                        logger.warning("Invalid origin ZIP in Excel, using default NYC ZIP (10001)")
                    else:
                        self.criteria_values['origin_zip'] = value
                elif key == "Fuel Surcharge":
                    try:
                        value = float(row[1])
                        if pd.isna(value):
                            logger.warning("Invalid Fuel Surcharge in Excel, using default 0.0")
                        else:
                            self.criteria_values['fuel_surcharge'] = value
                    except (ValueError, TypeError):
                        logger.warning("Invalid Fuel Surcharge in Excel, using default 0.0")
                elif key == "DAS Surcharge":
                    try:
                        value = float(row[1])
                        if pd.isna(value):
                            logger.warning("Invalid DAS Surcharge in Excel, using default 1.98")
                        else:
                            self.criteria_values['das_surcharge'] = value
                    except (ValueError, TypeError):
                        logger.warning("Invalid DAS Surcharge in Excel, using default 1.98")
                elif key == "EDAS Surcharge":
                    try:
                        value = float(row[1])
                        if pd.isna(value):
                            logger.warning("Invalid EDAS Surcharge in Excel, using default 3.92")
                        else:
                            self.criteria_values['edas_surcharge'] = value
                    except (ValueError, TypeError):
                        logger.warning("Invalid EDAS Surcharge in Excel, using default 3.92")
                elif key == "Remote Area Surcharge":
                    try:
                        value = float(row[1])
                        if pd.isna(value):
                            logger.warning("Invalid Remote Area Surcharge in Excel, using default 14.15")
                        else:
                            self.criteria_values['remote_surcharge'] = value
                    except (ValueError, TypeError):
                        logger.warning("Invalid Remote Area Surcharge in Excel, using default 14.15")
                elif key == "Dimensional Weight Divisor":
                    try:
                        value = float(row[1])
                        if pd.isna(value):
                            logger.warning("Invalid Dimensional Weight Divisor in Excel, using default 139.0")
                        else:
                            self.criteria_values['dim_divisor'] = value
                    except (ValueError, TypeError):
                        logger.warning("Invalid Dimensional Weight Divisor in Excel, using default 139.0")
            
            # Set default values for any missing criteria
            if 'origin_zip' not in self.criteria_values:
                self.criteria_values['origin_zip'] = None
            if 'fuel_surcharge' not in self.criteria_values:
                self.criteria_values['fuel_surcharge'] = 0.0
            if 'fuel_surcharge_percentage' not in self.criteria_values:
                self.criteria_values['fuel_surcharge_percentage'] = 16.0
            if 'das_surcharge' not in self.criteria_values:
                self.criteria_values['das_surcharge'] = 1.98
            if 'edas_surcharge' not in self.criteria_values:
                self.criteria_values['edas_surcharge'] = 3.92
            if 'remote_surcharge' not in self.criteria_values:
                self.criteria_values['remote_surcharge'] = 14.15
            if 'dim_divisor' not in self.criteria_values:
                self.criteria_values['dim_divisor'] = 139.0
            
            # Set default values for discount/markup
            self.criteria_values['discount_percent'] = 0.0
            self.criteria_values['markup_percentage'] = 0.0
            
            # Ensure no negative values
            for key in ['fuel_surcharge', 'das_surcharge', 'edas_surcharge', 'remote_surcharge']:
                if self.criteria_values[key] < 0:
                    logger.warning(f"{key} cannot be negative, setting to 0")
                    self.criteria_values[key] = 0.0
            
            if self.criteria_values['dim_divisor'] <= 0:
                logger.warning("Dimensional weight divisor must be positive, using default value of 139.0")
                self.criteria_values['dim_divisor'] = 139.0
            
            logger.info(f"Extracted criteria values: {self.criteria_values}")
            
        except Exception as e:
            logger.error(f"Failed to extract criteria values: {str(e)}")
            # Set default values if extraction fails
            self.criteria_values = {
                'origin_zip': '10001',  # NYC ZIP (changed from 46307)
                'fuel_surcharge': 0.0,
                'fuel_surcharge_percentage': 16.0,
                'das_surcharge': 1.98,
                'edas_surcharge': 3.92,
                'remote_surcharge': 14.15,
                'dim_divisor': 139.0,
                'discount_percent': 0.0,
                'markup_percentage': 0.0
            }
    
    def normalize_zip(self, zip_code: Any) -> str:
        """Normalize an input ZIP/postal code to a 5-character US ZIP when possible."""
        if zip_code is None:
            return ""

        # Handle pandas NaN and numpy NaN
        try:
            if pd.isna(zip_code):
                return ""
        except TypeError:
            # Non-numeric values raise here, ignore
            pass

        # Numeric inputs (int/float) coming from Excel often lose leading zeros
        if isinstance(zip_code, (int, float)):
            if isinstance(zip_code, float):
                if math.isnan(zip_code) or math.isinf(zip_code):
                    return ""
                zip_code = int(round(zip_code))
            normalized = str(int(zip_code)).zfill(5)[:5]
            return normalized

        # Fallback to string processing
        zip_str = str(zip_code).strip()
        if not zip_str or zip_str.lower() == 'nan':
            return ""

        # Remove whitespace and hyphen separators (ZIP+4 etc.)
        zip_str = zip_str.replace(' ', '').replace('-', '')

        digits_only = ''.join(ch for ch in zip_str if ch.isdigit())
        if digits_only:
            return digits_only.zfill(5)[:5]

        # For international codes retain uppercase string so callers can detect
        return zip_str.upper()

    def standardize_zip(self, zip_code: str) -> str:
        """
        Standardize ZIP code format to 3-digit prefix.

        Args:
            zip_code: ZIP code to standardize

        Returns:
            str: Standardized 3-digit ZIP prefix, "INT" for international, or "000" for invalid
        """
        # Handle None, NaN, empty string, and 'nan' string cases
        if zip_code is None or pd.isna(zip_code) or (isinstance(zip_code, str) and (zip_code.strip() == '' or zip_code.lower() == 'nan')):
            logger.warning(f"Invalid ZIP code: {zip_code}")
            return "000"  # Return placeholder prefix for missing data
        
        # Ensure input is a string
        zip_code = str(zip_code)
        
        # Clean the input by removing any whitespace and hyphens
        zip_code = zip_code.strip().replace(' ', '').replace('-', '')
        
        # Skip further processing if empty after cleaning
        if not zip_code:
            logger.warning("Empty ZIP code after cleaning")
            return "000"
        
        # Canadian postal codes (e.g., E3G7P6) or other international formats
        # Only identify as international if it contains letters (but isn't just 'nan')
        if any(c.isalpha() for c in zip_code) and zip_code.lower() != 'nan':
            logger.debug(f"International postal code detected: {zip_code}")
            return "INT"
        
        # Extract digits for any alphanumeric codes
        zip_digits = ''.join(filter(str.isdigit, zip_code))
        
        # Validate the digits
        if not zip_digits:
            logger.debug(f"No digits found in ZIP code: {zip_code}")
            return "000"  # Return placeholder for invalid data
        
        # Get the first 3 digits (or pad with zeros if needed)
        if len(zip_digits) < 3:
            zip_digits = zip_digits.zfill(3)
        
        # Return the 3-digit prefix as a string
        return zip_digits[:3]

    def validate_zone_matrix(self) -> None:
        """
        Validate the zone matrix structure and content.
        
        Raises:
            ReferenceDataError: If zone matrix is invalid
        """
        if self.zone_matrix is None or self.zone_matrix.empty:
            raise ReferenceDataError("Zone matrix is empty or not loaded")
        
        if self.zone_matrix.shape[0] < 2 or self.zone_matrix.shape[1] < 2:
            raise ReferenceDataError("Zone matrix must have at least 2 rows and 2 columns")
        
        # Convert all values to numeric, replacing non-numeric with NaN
        self.zone_matrix = self.zone_matrix.apply(pd.to_numeric, errors='coerce')
        
        # Check for invalid zones
        invalid_zones = self.zone_matrix.isna().sum().sum()
        total_cells = self.zone_matrix.size
        valid_cells = total_cells - invalid_zones
        invalid_pct = invalid_zones / total_cells * 100
        valid_pct = valid_cells / total_cells * 100
        
        if invalid_zones > 0:
            if invalid_zones > total_cells * 0.1:  # If > 10% are invalid
                logger.warning(f"Found {invalid_zones} invalid zones ({invalid_pct:.1f}%) in matrix of size {total_cells}")
                logger.warning("This is normal for sparse zone matrices where not all ZIP prefix combinations have defined zones")
            else:
                logger.info(f"Found {invalid_zones} invalid zones ({invalid_pct:.1f}%) in matrix")
            
            logger.info(f"Valid zones: {valid_cells} ({valid_pct:.1f}%)")

    def clean_zone_matrix(self) -> None:
        """
        Clean the zone matrix by fixing invalid zone values.
        
        This method:
        1. Replaces invalid zone values (like 45.0) with zone 8
        2. Ensures all zones are integers between 1-8
        3. Handles NaN values appropriately
        """
        try:
            logger.info("Cleaning zone matrix data...")
            
            # Convert all values to numeric, replacing non-numeric with NaN
            self.zone_matrix = self.zone_matrix.apply(pd.to_numeric, errors='coerce')
            
            # Count invalid zones before cleaning
            invalid_zones_mask = (self.zone_matrix < 1) | (self.zone_matrix > 8)
            invalid_count = invalid_zones_mask.sum().sum()
            
            if invalid_count > 0:
                logger.info(f"Found {invalid_count} invalid zone values, replacing with zone 8")
                
                # Replace invalid zones with zone 8
                self.zone_matrix = self.zone_matrix.where(
                    (self.zone_matrix >= 1) & (self.zone_matrix <= 8),
                    8
                )
            
            # Ensure all valid zones are integers
            self.zone_matrix = self.zone_matrix.round().astype('Int64')
            
            logger.info("Zone matrix cleaning completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to clean zone matrix: {str(e)}")
            raise ReferenceDataError(f"Failed to clean zone matrix: {str(e)}")

    def get_zone(self, origin_zip: str, dest_zip: str) -> int:
        """
        Determine the shipping zone based on origin and destination ZIP codes.
        
        Simplified implementation with robust error handling and default fallbacks.
        
        Args:
            origin_zip: Origin ZIP code
            dest_zip: Destination ZIP code
            
        Returns:
            int: Shipping zone (1-8, defaults to 8 for errors/international)
        """
        try:
            # Convert inputs to strings
            origin_zip_str = str(origin_zip).strip()
            dest_zip_str = str(dest_zip).strip()
            
            # Handle international destinations (contain letters)
            if any(c.isalpha() for c in dest_zip_str):
                logger.debug(f"International destination detected: {dest_zip_str}")
                return 8
            
            # Standardize ZIP codes to 3-digit prefixes
            origin_prefix = self.standardize_zip(origin_zip_str)
            dest_prefix = self.standardize_zip(dest_zip_str)
            
            # Handle special cases from standardize_zip
            if origin_prefix in ["INT", "000"] or dest_prefix in ["INT", "000"]:
                logger.debug(f"Invalid or international ZIP detected: origin={origin_prefix}, dest={dest_prefix}")
                return 8
            
            # Convert matrix indices and columns to strings for consistent lookup
            matrix_index_str = [str(idx) for idx in self.zone_matrix.index]
            matrix_columns_str = [str(col) for col in self.zone_matrix.columns]
            
            # Find origin index
            origin_idx = None
            if origin_prefix in matrix_index_str:
                origin_idx = self.zone_matrix.index[matrix_index_str.index(origin_prefix)]
            else:
                # Use client origin as fallback if available
                if self.criteria_values.get('origin_zip'):
                    client_origin_prefix = self.standardize_zip(str(self.criteria_values['origin_zip']))
                    if client_origin_prefix in matrix_index_str:
                        origin_idx = self.zone_matrix.index[matrix_index_str.index(client_origin_prefix)]
                
                # If still not found, use first available origin
                if origin_idx is None and len(self.zone_matrix.index) > 0:
                    origin_idx = self.zone_matrix.index[0]
                    logger.debug(f"Using default origin {origin_idx} for {origin_prefix}")
            
            # Find destination index
            dest_idx = None
            if dest_prefix in matrix_columns_str:
                dest_idx = self.zone_matrix.columns[matrix_columns_str.index(dest_prefix)]
            
            # If either index not found, default to zone 8
            if origin_idx is None or dest_idx is None:
                logger.debug(f"ZIP prefix not found in matrix: origin={origin_prefix}, dest={dest_prefix}")
                return 8
            
            # Get zone value from matrix
            zone = self.zone_matrix.loc[origin_idx, dest_idx]
            
            # Validate zone value
            if pd.isna(zone) or not (1 <= zone <= 8):
                logger.debug(f"Invalid zone value {zone} for {origin_zip} to {dest_zip}")
                return 8
            
            return int(zone)
            
        except Exception as e:
            logger.warning(f"Zone lookup error for {origin_zip} to {dest_zip}: {str(e)}")
            return 8
    
    def is_das_zip(self, zip_code: Any) -> bool:
        """Return True when the destination qualifies for a DAS surcharge."""
        normalized = self.normalize_zip(zip_code)
        if not normalized:
            # Historically treat missing/unknown as surcharge-eligible to stay conservative
            return True
        if not normalized.isdigit():
            # International / alphanumeric postal codes
            return True
        return self.das_zips_dict.get(normalized, False)

    def is_edas_zip(self, zip_code: Any) -> bool:
        """Return True when the destination qualifies for an extended DAS surcharge."""
        normalized = self.normalize_zip(zip_code)
        if not normalized or not normalized.isdigit():
            return False
        return self.edas_zips_dict.get(normalized, False)

    def is_remote_zip(self, zip_code: Any) -> bool:
        """Return True when the destination qualifies for a remote area surcharge."""
        normalized = self.normalize_zip(zip_code)
        if not normalized:
            return False
        if not normalized.isdigit():
            # Non-US / alphanumeric postal codes considered remote
            return True
        return self.remote_zips_dict.get(normalized, False)
    
    def get_base_rate(self, weight: float, zone: int, package_type: str = 'box') -> float:
        """
        Get the base shipping rate based on weight, zone, and package type.
        
        Args:
            weight: Weight in pounds
            zone: Shipping zone
            package_type: Type of package ('box', 'envelope', 'pak', 'custom')
            
        Returns:
            float: Base shipping rate
            
        Raises:
            RateCalculationError: If rate calculation fails
        """
        try:
            # Ensure package_type is a string
            if package_type is None:
                package_type = 'box'
                
            # Handle case where package_type might be a number/float
            if isinstance(package_type, (int, float)):
                logger.warning(f"Invalid package_type: {package_type} (numeric type), using 'box' instead")
                package_type_str = 'box'
            else:
                try:
                    package_type_str = str(package_type).lower().strip()
                except (AttributeError, TypeError):
                    # Handle case where package_type is not string-convertible
                    logger.warning(f"Invalid package_type: {package_type}, using 'box' instead")
                    package_type_str = 'box'
            
            # Convert zone to string for column lookup
            zone_col = str(zone)
            
            # Filter rate table by package type
            if package_type_str == 'envelope':
                rate_rows = self.rate_table[self.rate_table['Cntr'] == 'Letters']
            else:
                rate_rows = self.rate_table[self.rate_table['Cntr'] == 'Pkg']
            
            if rate_rows.empty:
                raise RateCalculationError(f"No rates found for package type {package_type_str}")
            
            # Check if zone column exists
            if zone_col not in rate_rows.columns:
                raise RateCalculationError(f"Zone {zone} not found in rate table")
            
            # Get weight breaks
            weight_breaks = rate_rows['lbs'].tolist()
            
            # Find the appropriate weight break
            idx = bisect.bisect_right(weight_breaks, weight)
            if idx == 0:
                # Weight is less than the smallest weight break
                idx = 1
            elif idx > len(weight_breaks) - 1:
                # Weight is greater than the largest weight break
                idx = len(weight_breaks) - 1
            
            # Get the rate for the weight break and zone
            rate = rate_rows.iloc[idx-1][zone_col]
            
            # Validate the rate
            if pd.isna(rate) or rate <= 0:
                raise RateCalculationError(f"Invalid rate for weight {weight}, zone {zone}, package type {package_type_str}")
            
            return float(rate)
            
        except AttributeError as e:
            # Handle specific attribute errors (likely "lower" method on float)
            error_msg = f"Package type error: {str(e)}"
            logger.error(error_msg)
            raise RateCalculationError(error_msg)
        except Exception as e:
            if not isinstance(e, RateCalculationError):
                logger.error(f"Rate calculation failed: {str(e)}")
                raise RateCalculationError(f"Rate calculation failed: {str(e)}")
            raise
    
    def apply_discounts_and_markups(self, base_rate: float, surcharges: Dict[str, float],
                               service_level: str) -> Dict[str, float]:
        """
        Apply service-level markups to the rate (base + all surcharges).
        Note: Markups are applied based on service level.

        Args:
            base_rate: The base shipping rate.
            surcharges: Dictionary of calculated surcharges.
            service_level: The service level for the shipment.

        Returns:
            Dictionary containing the final rate and markup percentage used.
        """
        try:
            # Calculate rate including all surcharges
            rate_with_surcharges = base_rate + surcharges.get('total_surcharges', 0.0)
            
            # More detailed logging for debugging
            logger.info(f"Checking for markup - Current criteria values: {self.criteria_values}")
            
            # IMPORTANT: Check for general markup percentage first, then fall back to service-specific
            default_markup_key = 'markup_percentage'
            markup_key = f"{service_level}_markup"
            
            if default_markup_key in self.criteria_values and self.criteria_values[default_markup_key] is not None:
                markup_pct = float(self.criteria_values[default_markup_key])
                logger.info(f"Using default markup percentage: {markup_pct}%")
            elif markup_key in self.criteria_values and self.criteria_values[markup_key] is not None:
                markup_pct = float(self.criteria_values[markup_key])
                logger.info(f"Using service-specific markup for {service_level}: {markup_pct}%")
            else:
                markup_pct = 0.0
                logger.warning(f"No markup found for {service_level}, using 0%")
            
            # Convert percentage to decimal (e.g., 10% -> 0.10)
            markup_decimal = float(markup_pct) / 100.0
            
            # Apply markup
            markup_amount = rate_with_surcharges * markup_decimal
            final_rate = rate_with_surcharges + markup_amount
            
            logger.info(f"Rate calculation: Base={base_rate}, Surcharges={surcharges.get('total_surcharges', 0.0)}, Markup={markup_pct}%, Final={final_rate}")
            
            return {
                'markup_percentage': markup_pct,
                'markup_amount': round(markup_amount, 2),
                'final_rate': round(final_rate, 2)
            }
            
        except Exception as e:
            logger.error(f"Error applying markups: {str(e)}")
            
            # Fallback to safe values
            return {
                'markup_percentage': 0.0,
                'markup_amount': 0.0,
                'final_rate': round(base_rate + surcharges.get('total_surcharges', 0.0), 2)
            }
    
    def apply_surcharges(self, base_rate: float, dest_zip: str, weight: float, package_type: str) -> Dict[str, float]:
        """
        Apply applicable surcharges to the base rate.
        
        Args:
            base_rate: Base shipping rate
            dest_zip: Destination ZIP code
            weight: Weight in pounds
            package_type: Type of package
            
        Returns:
            Dict[str, float]: Dictionary with surcharge details
        """
        surcharges = {
            'fuel_surcharge': 0.0,
            'das_surcharge': 0.0,
            'edas_surcharge': 0.0,
            'remote_surcharge': 0.0,
            'total_surcharges': 0.0
        }
        
        try:
            # Apply fuel surcharge (convert percentage to decimal)
            fuel_pct = self.criteria_values.get('fuel_surcharge_percentage', 16.0)
            # Convert percentage to decimal (e.g., 16% -> 0.16)
            fuel_decimal = float(fuel_pct) / 100.0
            
            # Apply fuel surcharge to base rate
            fuel_amount = base_rate * fuel_decimal
            surcharges['fuel_surcharge'] = round(fuel_amount, 2)
            
            dest_zip_str = str(dest_zip) if dest_zip is not None else ""
            normalized_zip = self.normalize_zip(dest_zip_str)

            if not normalized_zip:
                logger.info(f"Empty, nan, or invalid destination ZIP code: '{dest_zip}', skipping all surcharges except fuel")
                surcharges['total_surcharges'] = surcharges['fuel_surcharge']
                return surcharges

            # Skip further surcharge processing for default ZIP codes we're using as placeholders
            if normalized_zip in ['10001', '60601']:
                logger.info(f"Using default city ZIP {dest_zip_str}, only applying fuel surcharge")
                # No DAS charges for default ZIPs
                surcharges['total_surcharges'] = surcharges['fuel_surcharge']
                return surcharges

            # Get ZIP prefix for surcharge rules
            try:
                zip_prefix = self.standardize_zip(dest_zip_str)
            except Exception as e:
                logger.error(f"Error getting ZIP prefix for {dest_zip_str}: {str(e)}")
                zip_prefix = "000"  # Use a safe default value
            
            # Skip surcharges for invalid/placeholder ZIP codes
            if zip_prefix == "000":
                logger.info(f"Invalid/missing ZIP code prefix for {dest_zip_str}, skipping surcharges")
                surcharges['total_surcharges'] = surcharges['fuel_surcharge']
                return surcharges
            
            # Check if this ZIP code requires delivery area surcharge
            if self.is_das_zip(normalized_zip):
                surcharges['das_surcharge'] = self.criteria_values.get('das_surcharge', 1.98)
                logger.info(f"Applied DAS to ZIP: {normalized_zip}")

            # Check if it's an extended DAS ZIP
            # Use standardized 5-digit ZIP for EDAS lookup
            if zip_prefix != "INT" and zip_prefix != "000":  # Skip for international or invalid
                if self.is_edas_zip(normalized_zip):
                    surcharges['edas_surcharge'] = self.criteria_values.get('edas_surcharge', 3.92)
                    logger.info(f"Applied EDAS to ZIP: {normalized_zip}")
            
            # Apply remote surcharge only in very specific cases:
            apply_remote = False
            remote_reason = ""
            
            # Case 1: Genuine international destinations with letters (not 'nan')
            if zip_prefix == "INT" and any(c.isalpha() for c in dest_zip_str) and dest_zip_str.lower() != 'nan':
                apply_remote = True
                remote_reason = "international"
            # Case 2: Known Alaska/Hawaii ZIPs 
            elif zip_prefix.isdigit() and (
                (zip_prefix.startswith('995') or zip_prefix.startswith('996') or zip_prefix.startswith('997') or 
                 zip_prefix.startswith('998') or zip_prefix.startswith('999') or  # Alaska
                 zip_prefix.startswith('967') or zip_prefix.startswith('968'))   # Hawaii
            ):
                apply_remote = True
                remote_reason = "Alaska/Hawaii"
            # Case 3: Truly documented remote areas
            elif self.is_remote_zip(normalized_zip):
                apply_remote = True
                remote_reason = "remote area in ZIP database"
            
            # Apply remote surcharge if qualified
            if apply_remote:
                surcharges['remote_surcharge'] = self.criteria_values.get('remote_surcharge', 14.15)
                logger.info(f"Applied Remote surcharge to {remote_reason} ZIP: {dest_zip_str}")
            
            # Calculate total surcharges
            surcharges['total_surcharges'] = round(
                surcharges['fuel_surcharge'] + 
                surcharges['das_surcharge'] + 
                surcharges['edas_surcharge'] + 
                surcharges['remote_surcharge'], 
                2
            )
            
            return surcharges
            
        except Exception as e:
            logger.error(f"Error applying surcharges: {str(e)}")
            # Return the default surcharges with at least the fuel surcharge
            try:
                # Attempt to still calculate fuel surcharge even if other surcharges fail
                fuel_pct = self.criteria_values.get('fuel_surcharge_percentage', 16.0)
                fuel_decimal = float(fuel_pct) / 100.0
                surcharges['fuel_surcharge'] = round(base_rate * fuel_decimal, 2)
                surcharges['total_surcharges'] = surcharges['fuel_surcharge']
            except Exception:
                pass
            return surcharges
    
    def calculate_margin(self, final_rate: float, current_rate: float = None) -> Dict[str, float]:
        """
        Calculate margin compared to current rate.
        
        Args:
            final_rate: Final calculated rate
            current_rate: Current rate being paid (if available)
            
        Returns:
            Dict[str, float]: Dictionary with margin details
        """
        margin = {
            'carrier_rate': current_rate,
            'savings': 0.0,
            'savings_percent': 0.0
        }
        
        # Calculate savings if current rate is available
        if current_rate is not None and current_rate > 0:
            margin['savings'] = current_rate - final_rate
            margin['savings_percent'] = (margin['savings'] / current_rate) * 100
        
        return margin
    
    def calculate_shipment_rate(self, shipment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate the complete rate for a single shipment.
        
        Args:
            shipment: Dictionary with shipment details
            
        Returns:
            Dict[str, Any]: Dictionary with complete rate details
            
        Raises:
            CalculationError: If rate calculation fails
        """
        # Initialize default result with error indicators
        default_result = {
            'shipment_id': shipment.get('shipment_id', ''),
            'origin_zip': shipment.get('origin_zip', ''),
            'destination_zip': shipment.get('destination_zip', ''),
            'weight': _to_num(shipment.get('weight'), default=0.0),
            'billable_weight': _to_num(shipment.get('billable_weight', shipment.get('weight', 0.0)), default=0.0),
            'package_type': shipment.get('package_type', 'box'),
            'zone': 'Error',
            'base_rate': 0.0,
            'fuel_surcharge': 0.0,
            'das_surcharge': 0.0,
            'edas_surcharge': 0.0,
            'remote_surcharge': 0.0,
            'total_surcharges': 0.0,
            'discount_amount': 0.0,
            'markup_amount': 0.0,
            'markup_percentage': 0.0,
            'final_rate': 0.0,
            'carrier_rate': _to_num(shipment.get('carrier_rate'), default=0.0),
            'savings': 0.0,
            'savings_percent': 0.0,
            'service_level': shipment.get('service_level', 'standard'),
            'errors': ''
        }
        
        try:
            # Extract shipment details
            origin_zip = shipment.get('origin_zip')
            dest_zip = shipment.get('destination_zip')
            weight = shipment.get('weight')
            package_type = shipment.get('package_type', 'box')
            current_rate = shipment.get('carrier_rate')
            service_level = shipment.get('service_level', 'standard')
            
            # Immediate validation and replacement of missing values
            # Handle missing or invalid destination ZIP right away
            if not dest_zip or pd.isna(dest_zip) or (isinstance(dest_zip, str) and (dest_zip.strip() == '' or dest_zip.lower() == 'nan')):
                dest_zip = '60601'  # Chicago ZIP - domestic ZIP code explicitly excluded from DAS charges
                default_result['destination_zip'] = dest_zip
                logger.warning(f"Missing destination ZIP in shipment, using default domestic: {dest_zip}")

            # Handle missing origin ZIP
            if not origin_zip or pd.isna(origin_zip) or (isinstance(origin_zip, str) and (origin_zip.strip() == '' or origin_zip.lower() == 'nan')):
                origin_zip = self.criteria_values.get('origin_zip', '10001')  # Default to NYC
                default_result['origin_zip'] = origin_zip
                logger.warning(f"Missing origin ZIP, using default: {origin_zip}")

            # Use billable_weight if provided, otherwise use weight
            rating_weight = shipment.get('billable_weight', weight)
            
            # Validate required fields with detailed error handling
            missing_fields = []
            if not origin_zip or pd.isna(origin_zip) or (isinstance(origin_zip, str) and origin_zip.strip() == ''):
                missing_fields.append('origin_zip')
                # Use default origin_zip from criteria values
                origin_zip = self.criteria_values.get('origin_zip', '10001')
                logger.warning(f"Missing origin ZIP, using default: {origin_zip}")
            
            if not dest_zip or pd.isna(dest_zip) or (isinstance(dest_zip, str) and dest_zip.strip() == ''):
                missing_fields.append('destination_zip')
                # Use default dest_zip of Chicago (60601)
                dest_zip = '60601'  # Chicago ZIP - domestic US ZIP explicitly excluded from DAS charges
                logger.warning(f"Missing destination ZIP in shipment, using default domestic: {dest_zip}")
            
            if not rating_weight or pd.isna(rating_weight) or rating_weight <= 0:
                missing_fields.append('weight/billable_weight')
                # Use a safe default weight
                rating_weight = 1.0
                logger.warning(f"Missing or invalid weight, using default: {rating_weight}")
            
            if missing_fields:
                logger.warning(f"Shipment missing required fields: {missing_fields}")
                default_result['errors'] = f"Missing required fields: {', '.join(missing_fields)}"
            
            # Check if zone is already provided in the shipment data
            provided_zone = shipment.get('zone')
            if provided_zone is not None:  # zone can be 0, so just check for not None
                # Use the zone provided by the frontend (from CSV)
                zone = provided_zone
                logger.info(f"Using provided zone from CSV: {zone}")
                default_result['zone'] = zone
            else:
                # Handle Canadian/international postal codes
                is_international = False
                dest_zip_str = str(dest_zip)
                
                if any(c.isalpha() for c in dest_zip_str):
                    is_international = True
                    logger.info(f"Processing international destination: {dest_zip_str}")
                    # Set zone to 8 for international
                    zone = 8
                    default_result['zone'] = zone
                else:
                    try:
                        # Get regular zone for domestic shipments (only if not provided)
                        zone = self.get_zone(origin_zip, dest_zip)
                        default_result['zone'] = zone
                        logger.info(f"Calculated zone from ZIP codes: {zone}")
                    except Exception as e:
                        logger.error(f"Zone lookup failed: {str(e)}")
                        zone = 8  # Default to zone 8 for any failures
                        default_result['zone'] = zone
                        default_result['errors'] = f"Zone lookup error: {str(e)}"
            
            # Get base rate
            try:
                base_rate = self.get_base_rate(rating_weight, zone, package_type)
                default_result['base_rate'] = base_rate
                
                # Apply surcharges
                try:
                    surcharges = self.apply_surcharges(base_rate, dest_zip, rating_weight, package_type)
                    default_result.update({
                        'fuel_surcharge': surcharges['fuel_surcharge'],
                        'das_surcharge': surcharges['das_surcharge'],
                        'edas_surcharge': surcharges['edas_surcharge'],
                        'remote_surcharge': surcharges['remote_surcharge'],
                        'total_surcharges': surcharges['total_surcharges']
                    })
                    
                    # Apply discounts and markups
                    try:
                        pricing = self.apply_discounts_and_markups(base_rate, surcharges, service_level)
                        default_result['final_rate'] = pricing['final_rate']
                        default_result['markup_percentage'] = pricing['markup_percentage']
                        default_result['markup_amount'] = pricing['markup_amount']
                        
                        # Calculate margin if carrier_rate is provided
                        if current_rate is not None:
                            try:
                                margin = self.calculate_margin(pricing['final_rate'], current_rate)
                                default_result.update({
                                    'savings': margin['savings'],
                                    'savings_percent': margin['savings_percent']
                                })
                            except Exception as e:
                                logger.warning(f"Margin calculation failed: {str(e)}")
                                default_result['errors'] = f"Margin calculation error: {str(e)}"
                        
                    except Exception as e:
                        logger.warning(f"Discount/markup application failed: {str(e)}")
                        default_result['errors'] = f"Discount/markup error: {str(e)}"
                    
                except Exception as e:
                    logger.warning(f"Surcharge application failed: {str(e)}")
                    default_result['errors'] = f"Surcharge error: {str(e)}"
                
            except Exception as e:
                logger.warning(f"Base rate calculation failed: {str(e)}")
                default_result['errors'] = f"Base rate error: {str(e)}"
            
            # If we got this far with no errors, sanitize and return the result
            sanitized_result = _sanitize_result_row(default_result)
            return sanitized_result
            
        except Exception as e:
            logger.error(f"Shipment rate calculation failed: {str(e)}")
            default_result['errors'] = f"Calculation error: {str(e)}"
            sanitized_error_result = _sanitize_result_row(default_result)
            return sanitized_error_result
    
    def calculate_rates(self, shipments: List[Dict[str, Any]], 
                       discount_percent: float = None, 
                       markup_percent: float = None) -> List[Dict[str, Any]]:
        """
        Calculate rates for multiple shipments.
        
        Args:
            shipments: List of dictionaries with shipment details
            discount_percent: Optional discount percentage override
            markup_percent: Optional markup percentage override
            
        Returns:
            List[Dict[str, Any]]: List of dictionaries with complete rate details
        """
        results = []
        errors = []
        
        for i, shipment in enumerate(shipments):
            try:
                result = self.calculate_shipment_rate(shipment)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to calculate rate for shipment {shipment.get('shipment_id', 'N/A')}: {str(e)}", exc_info=True)
                # Create a result dictionary with error indicators for all expected columns
                error_result = {
                    'shipment_id': shipment.get('shipment_id', 'N/A'),
                    'origin_zip': shipment.get('origin_zip', 'N/A'),
                    'destination_zip': shipment.get('destination_zip', 'N/A'),
                    'weight': _to_num(shipment.get('weight'), default=0.0),
                    'dim_weight': 0.0,
                    'billable_weight': _to_num(shipment.get('billable_weight'), default=0.0),
                    'rating_weight': 0.0,
                    'package_type': shipment.get('package_type', 'N/A'),
                    'service_level': shipment.get('service_level', 'N/A'),
                    'zone': 'Error',
                    'base_rate': 0.0,
                    'fuel_surcharge': 0.0,
                    'das_surcharge': 0.0,
                    'edas_surcharge': 0.0,
                    'remote_surcharge': 0.0,
                    'total_surcharges': 0.0,
                    'discount_amount': 0.0,
                    'markup_percent': 0.0,
                    'final_rate': 0.0,
                    'carrier_rate': _to_num(shipment.get('carrier_rate'), default=0.0),
                    'savings': 0.0,
                    'savings_percent': 0.0,
                    'errors': f"Calculation Error: {e}"
                }
                results.append(error_result)
        
        if errors:
            logger.warning(f"Completed with {len(errors)} errors: {errors}")
        
        logger.info(f"Calculated rates for {len(results)} shipments")
        return results
    
    def get_summary_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get summary statistics for the calculated rates.
        
        Args:
            results: List of dictionaries with rate details
            
        Returns:
            Dict[str, Any]: Summary statistics
        """
        # Filter out results with errors
        valid_results = [r for r in results if 'error' not in r]

        def _safe_sum(iterable):
            total = 0.0
            for v in iterable:
                x = _to_num(v, default=0.0)
                try:
                    if math.isfinite(x):
                        total += x
                except Exception:
                    # For environments without math.isfinite on this type, coerce to float
                    try:
                        xf = float(x)
                        if not (np.isnan(xf) or np.isinf(xf)):
                            total += xf
                    except Exception:
                        pass
            return total

        if not valid_results:
            return {
                'total_shipments': 0,
                'total_base_rate': 0,
                'total_surcharges': 0,
                'total_final_rate': 0,
                'total_savings': 0,
                'avg_base_rate': 0,
                'avg_final_rate': 0,
                'avg_savings_percent': 0
            }

        stats = {
            'total_shipments': len(valid_results),
            'total_base_rate': _safe_sum(r.get('base_rate') for r in valid_results),
            'total_surcharges': _safe_sum(r.get('total_surcharges') for r in valid_results),
            'total_final_rate': _safe_sum(r.get('final_rate') for r in valid_results),
            'total_savings': _safe_sum(r.get('savings') for r in valid_results if _to_num(r.get('carrier_rate'), 0.0) > 0),
            'avg_base_rate': 0.0,
            'avg_final_rate': 0.0,
            'avg_savings_percent': 0.0
        }
        if stats['total_shipments'] > 0:
            stats['avg_base_rate'] = stats['total_base_rate'] / stats['total_shipments']
            stats['avg_final_rate'] = stats['total_final_rate'] / stats['total_shipments']
        savings_denominator = len([r for r in valid_results if _to_num(r.get('carrier_rate'), 0.0) > 0])
        if savings_denominator > 0:
            stats['avg_savings_percent'] = _safe_sum(
                r.get('savings_percent', 0.0) for r in valid_results if _to_num(r.get('carrier_rate'), 0.0) > 0
            ) / savings_denominator

        # Sanitize stats to ensure JSON compliance
        sanitized_stats = _sanitize_result_row(stats)
        return sanitized_stats

    def update_criteria(self, criteria: Dict[str, Any]) -> None:
        """
        Update calculation criteria.
        
        Args:
            criteria: Dictionary of criteria values
        """
        if not criteria:
            logger.warning("Empty criteria provided, using defaults")
            return
            
        # Log the update
        logger.info(f"Updating criteria with: {criteria}")
        
        # Always ensure origin_zip is set to NYC (10001) if not explicitly provided
        if 'origin_zip' not in criteria or not criteria['origin_zip']:
            criteria['origin_zip'] = '10001'  # Default to NYC ZIP
        
        # Handle potential naming inconsistencies
        if 'fuel_surcharge_percentage' in criteria and 'fuel_surcharge' not in criteria:
            criteria['fuel_surcharge'] = criteria['fuel_surcharge_percentage'] / 100.0  # Convert to decimal
        elif 'fuel_surcharge' in criteria and 'fuel_surcharge_percentage' not in criteria:
            criteria['fuel_surcharge_percentage'] = criteria['fuel_surcharge'] * 100.0  # Convert to percentage
        
        # Explicitly handle markup_percentage
        if 'markup_percentage' in criteria:
            try:
                markup_value = float(criteria['markup_percentage'])
                criteria['markup_percentage'] = markup_value
                logger.info(f"Setting markup_percentage to {markup_value}%")
            except (ValueError, TypeError):
                logger.warning(f"Invalid markup_percentage value: {criteria['markup_percentage']}, using default 10.0%")
                criteria['markup_percentage'] = 10.0
            else:
                logger.info("No markup_percentage provided in criteria, keeping current value")
        
        # Convert surcharge values to proper types
        surcharge_fields = [
            'das_surcharge', 'edas_surcharge', 'remote_surcharge', 
            'markup_percentage', 'fuel_surcharge_percentage'
        ]
        
        for field in surcharge_fields:
            if field in criteria:
                try:
                    criteria[field] = float(criteria[field])
                except (ValueError, TypeError):
                    logger.warning(f"Could not convert {field} value '{criteria[field]}' to float, using default")
                    if field in self.criteria_values:
                        criteria[field] = self.criteria_values[field]
                    else:
                        # Set sensible defaults for missing values
                        defaults = {
                            'das_surcharge': 1.98,
                            'edas_surcharge': 3.92,
                            'remote_surcharge': 14.15,
                            'markup_percentage': 0.0,
                            'fuel_surcharge_percentage': 16.0
                        }
                        criteria[field] = defaults.get(field, 0.0)
            
        # Process service level markups if provided
        if 'service_level_markups' in criteria:
            service_markups = criteria['service_level_markups']
            if isinstance(service_markups, dict):
                # Update individual service level markups in criteria
                for service, markup in service_markups.items():
                    criteria[f'{service}_markup'] = float(markup)
        
        # Create a service_level_markups dict if not present but individual markups are
        service_levels = ['standard', 'expedited', 'priority', 'next_day']
        has_individual_markups = any(f'{level}_markup' in criteria for level in service_levels)
        
        if has_individual_markups and 'service_level_markups' not in criteria:
            criteria['service_level_markups'] = {}
            for level in service_levels:
                key = f'{level}_markup'
                if key in criteria:
                    criteria['service_level_markups'][level] = float(criteria[key])
                elif key in self.criteria_values:
                    criteria['service_level_markups'][level] = float(self.criteria_values[key])
                else:
                    # Default values for service level markups
                    defaults = {
                        'standard_markup': 0.0,
                        'expedited_markup': 10.0,
                        'priority_markup': 15.0,
                        'next_day_markup': 25.0
                    }
                    criteria['service_level_markups'][level] = defaults.get(f'{level}_markup', 0.0)
                    
        # Store the updated criteria
        self.criteria_values.update(criteria)
        
        # Log the final criteria
        logger.info(f"Updated criteria: {self.criteria_values}")
        
        # Validate any changes that need validation
        if 'dim_divisor' in criteria:
            try:
                self.criteria_values['dim_divisor'] = float(criteria['dim_divisor'])
            except (ValueError, TypeError):
                logger.warning(f"Invalid dim_divisor value: {criteria['dim_divisor']}, using default 139.0")
                self.criteria_values['dim_divisor'] = 139.0
                
        if 'min_billable_weight' in criteria:
            try:
                self.criteria_values['min_billable_weight'] = float(criteria['min_billable_weight'])
            except (ValueError, TypeError):
                logger.warning(f"Invalid min_billable_weight value: {criteria['min_billable_weight']}, using default 1.0")
                self.criteria_values['min_billable_weight'] = 1.0


def calculate_rates(shipments: List[Dict[str, Any]], 
                   template_path: str = None,
                   discount_percent: float = None, 
                   markup_percent: float = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Calculate Amazon shipping rates for a list of shipments.
    
    Args:
        shipments: List of dictionaries with shipment details
        template_path: Path to the Excel template with reference data
        discount_percent: Optional discount percentage override
        markup_percent: Optional markup percentage override
        
    Returns:
        Tuple[List[Dict[str, Any]], Dict[str, Any]]: Calculated rates and summary statistics
    """
    calculator = AmazonRateCalculator(template_path)
    results = calculator.calculate_rates(shipments, discount_percent, markup_percent)
    stats = calculator.get_summary_stats(results)
    
    return results, stats
