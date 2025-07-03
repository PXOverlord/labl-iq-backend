"""
Labl IQ Rate Analyzer - Profiles Management Module

This module handles the saving and loading of column mapping profiles.
It provides functionality for:
1. Saving column mapping profiles to JSON files
2. Loading saved profiles
3. Listing available profiles

Date: May 5, 2025
"""

import os
import json
import logging
from typing import Dict, List, Optional
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('labl_iq.profiles')

# Define the profiles directory
PROFILES_DIR = Path(__file__).parent.parent / "data" / "profiles"

# Ensure the profiles directory exists
if not PROFILES_DIR.exists():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created profiles directory: {PROFILES_DIR}")

def save_profile(profile_name: str, column_mapping: Dict[str, str]) -> bool:
    """
    Save a column mapping profile to a JSON file.
    
    Args:
        profile_name: Name of the profile
        column_mapping: Dictionary mapping required fields to actual column names
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Sanitize profile name for use as a filename
        profile_filename = profile_name.replace(" ", "_").lower() + ".json"
        profile_path = PROFILES_DIR / profile_filename
        
        # Save the profile
        with open(profile_path, 'w') as f:
            json.dump({
                "name": profile_name,
                "mapping": column_mapping
            }, f, indent=2)
        
        logger.info(f"Saved profile '{profile_name}' to {profile_path}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to save profile '{profile_name}': {str(e)}")
        return False

def load_profile(profile_name: str) -> Optional[Dict[str, str]]:
    """
    Load a column mapping profile from a JSON file.
    
    Args:
        profile_name: Name of the profile
        
    Returns:
        Optional[Dict[str, str]]: Column mapping dictionary if successful, None otherwise
    """
    try:
        # Sanitize profile name for use as a filename
        profile_filename = profile_name.replace(" ", "_").lower() + ".json"
        profile_path = PROFILES_DIR / profile_filename
        
        # Check if the profile exists
        if not profile_path.exists():
            logger.warning(f"Profile '{profile_name}' not found at {profile_path}")
            return None
        
        # Load the profile
        with open(profile_path, 'r') as f:
            profile_data = json.load(f)
        
        logger.info(f"Loaded profile '{profile_name}' from {profile_path}")
        return profile_data.get("mapping", {})
    
    except Exception as e:
        logger.error(f"Failed to load profile '{profile_name}': {str(e)}")
        return None

def list_profiles() -> List[Dict[str, str]]:
    """
    List all available column mapping profiles.
    
    Returns:
        List[Dict[str, str]]: List of profile information dictionaries
    """
    try:
        profiles = []
        
        # Get all JSON files in the profiles directory
        for file_path in PROFILES_DIR.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    profile_data = json.load(f)
                
                profiles.append({
                    "id": file_path.stem,
                    "name": profile_data.get("name", file_path.stem),
                    "fields": len(profile_data.get("mapping", {}))
                })
            except Exception as e:
                logger.warning(f"Failed to read profile from {file_path}: {str(e)}")
        
        logger.info(f"Found {len(profiles)} profiles")
        return profiles
    
    except Exception as e:
        logger.error(f"Failed to list profiles: {str(e)}")
        return []

def delete_profile(profile_name: str) -> bool:
    """
    Delete a column mapping profile.
    
    Args:
        profile_name: Name of the profile
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Sanitize profile name for use as a filename
        profile_filename = profile_name.replace(" ", "_").lower() + ".json"
        profile_path = PROFILES_DIR / profile_filename
        
        # Check if the profile exists
        if not profile_path.exists():
            logger.warning(f"Profile '{profile_name}' not found at {profile_path}")
            return False
        
        # Delete the profile
        os.remove(profile_path)
        
        logger.info(f"Deleted profile '{profile_name}' from {profile_path}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to delete profile '{profile_name}': {str(e)}")
        return False
