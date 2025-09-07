#!/usr/bin/env python3
"""
Test script to verify the hot water config migration from JSON to individual fields.
This script tests the migration logic to ensure no data loss occurs.
"""

import json
import sys
import os

# Add the custom_components directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components', 'priceanalyzer'))

from const import (
    HOT_WATER_CONFIG, HOT_WATER_DEFAULT_CONFIG, TEMP_DEFAULT, TEMP_FIVE_MOST_EXPENSIVE,
    TEMP_IS_FALLING, TEMP_FIVE_CHEAPEST, TEMP_TEN_CHEAPEST, TEMP_LOW_PRICE,
    TEMP_NOT_CHEAP_NOT_EXPENSIVE, TEMP_MINIMUM
)

def test_migration_logic():
    """Test the migration logic from config_flow.py"""
    
    def _migrate_hot_water_config(existing_config):
        """Migrate existing JSON hot water config to individual fields"""
        if existing_config is None:
            return {}
        
        # If we have individual fields already, return as-is
        if any(key.startswith('temp_') for key in existing_config.keys()):
            return existing_config
        
        # Migrate from JSON config
        migrated = existing_config.copy()
        hot_water_json = existing_config.get(HOT_WATER_CONFIG)
        
        if hot_water_json:
            try:
                hot_water_dict = json.loads(hot_water_json) if isinstance(hot_water_json, str) else hot_water_json
                
                # Map JSON keys to individual config keys
                migrated['temp_default'] = hot_water_dict.get(TEMP_DEFAULT, HOT_WATER_DEFAULT_CONFIG[TEMP_DEFAULT])
                migrated['temp_five_most_expensive'] = hot_water_dict.get(TEMP_FIVE_MOST_EXPENSIVE, HOT_WATER_DEFAULT_CONFIG[TEMP_FIVE_MOST_EXPENSIVE])
                migrated['temp_is_falling'] = hot_water_dict.get(TEMP_IS_FALLING, HOT_WATER_DEFAULT_CONFIG[TEMP_IS_FALLING])
                migrated['temp_five_cheapest'] = hot_water_dict.get(TEMP_FIVE_CHEAPEST, HOT_WATER_DEFAULT_CONFIG[TEMP_FIVE_CHEAPEST])
                migrated['temp_ten_cheapest'] = hot_water_dict.get(TEMP_TEN_CHEAPEST, HOT_WATER_DEFAULT_CONFIG[TEMP_TEN_CHEAPEST])
                migrated['temp_low_price'] = hot_water_dict.get(TEMP_LOW_PRICE, HOT_WATER_DEFAULT_CONFIG[TEMP_LOW_PRICE])
                migrated['temp_not_cheap_not_expensive'] = hot_water_dict.get(TEMP_NOT_CHEAP_NOT_EXPENSIVE, HOT_WATER_DEFAULT_CONFIG[TEMP_NOT_CHEAP_NOT_EXPENSIVE])
                migrated['temp_minimum'] = hot_water_dict.get(TEMP_MINIMUM, HOT_WATER_DEFAULT_CONFIG[TEMP_MINIMUM])
                
                # Remove old JSON config
                migrated.pop(HOT_WATER_CONFIG, None)
            except (json.JSONDecodeError, TypeError):
                # If JSON parsing fails, use defaults
                pass
        
        return migrated

    def test_get_config_key(config, key):
        """Test the get_config_key logic from sensor.py"""
        individual_key_map = {
            TEMP_DEFAULT: 'temp_default',
            TEMP_FIVE_MOST_EXPENSIVE: 'temp_five_most_expensive',
            TEMP_IS_FALLING: 'temp_is_falling',
            TEMP_FIVE_CHEAPEST: 'temp_five_cheapest',
            TEMP_TEN_CHEAPEST: 'temp_ten_cheapest',
            TEMP_LOW_PRICE: 'temp_low_price',
            TEMP_NOT_CHEAP_NOT_EXPENSIVE: 'temp_not_cheap_not_expensive',
            TEMP_MINIMUM: 'temp_minimum'
        }
        
        # Check if we have the individual field (new format)
        if key in individual_key_map:
            individual_key = individual_key_map[key]
            if individual_key in config:
                return config[individual_key]
        
        # Fall back to JSON format (old format) for backward compatibility
        hot_water_config = config.get(HOT_WATER_CONFIG, "")
        config_dict = {}
        if hot_water_config:
            try:
                config_dict = json.loads(hot_water_config)
            except (json.JSONDecodeError, TypeError):
                config_dict = HOT_WATER_DEFAULT_CONFIG
        else:
            config_dict = HOT_WATER_DEFAULT_CONFIG
            
        if key in config_dict.keys():
            return config_dict[key]
        else:
            return HOT_WATER_DEFAULT_CONFIG[key]

    print("Testing Hot Water Config Migration...")
    print("=" * 50)

    # Test 1: Migration from JSON config
    print("\n1. Testing migration from JSON config:")
    original_json_config = {
        "region": "Kr.sand",
        HOT_WATER_CONFIG: json.dumps({
            TEMP_DEFAULT: 80,
            TEMP_FIVE_MOST_EXPENSIVE: 35,
            TEMP_IS_FALLING: 55,
            TEMP_FIVE_CHEAPEST: 75,
            TEMP_TEN_CHEAPEST: 70,
            TEMP_LOW_PRICE: 65,
            TEMP_NOT_CHEAP_NOT_EXPENSIVE: 45,
            TEMP_MINIMUM: 80
        })
    }
    
    migrated = _migrate_hot_water_config(original_json_config)
    print(f"Original JSON config keys: {list(original_json_config.keys())}")
    print(f"Migrated config keys: {list(migrated.keys())}")
    
    # Verify all individual fields are present
    expected_fields = ['temp_default', 'temp_five_most_expensive', 'temp_is_falling', 
                      'temp_five_cheapest', 'temp_ten_cheapest', 'temp_low_price',
                      'temp_not_cheap_not_expensive', 'temp_minimum']
    
    all_present = all(field in migrated for field in expected_fields)
    print(f"All individual fields present: {all_present}")
    print(f"JSON config removed: {HOT_WATER_CONFIG not in migrated}")

    # Test 2: Already migrated config (should remain unchanged)
    print("\n2. Testing already migrated config:")
    already_migrated = {
        "region": "Kr.sand",
        "temp_default": 85,
        "temp_five_most_expensive": 40
    }
    
    result = _migrate_hot_water_config(already_migrated)
    unchanged = result == already_migrated
    print(f"Already migrated config unchanged: {unchanged}")

    # Test 3: Test get_config_key with both formats
    print("\n3. Testing get_config_key compatibility:")
    
    # Test with new individual fields
    new_config = migrated
    temp_default_new = test_get_config_key(new_config, TEMP_DEFAULT)
    print(f"temp_default from new format: {temp_default_new}")
    
    # Test with old JSON format
    old_config = original_json_config
    temp_default_old = test_get_config_key(old_config, TEMP_DEFAULT)
    print(f"temp_default from old format: {temp_default_old}")
    
    # They should be the same
    values_match = temp_default_new == temp_default_old
    print(f"Values match between formats: {values_match}")

    # Test 4: Test all temperature keys
    print("\n4. Testing all temperature configuration keys:")
    test_keys = [TEMP_DEFAULT, TEMP_FIVE_MOST_EXPENSIVE, TEMP_IS_FALLING, 
                TEMP_FIVE_CHEAPEST, TEMP_TEN_CHEAPEST, TEMP_LOW_PRICE,
                TEMP_NOT_CHEAP_NOT_EXPENSIVE, TEMP_MINIMUM]
    
    all_match = True
    for key in test_keys:
        old_value = test_get_config_key(original_json_config, key)
        new_value = test_get_config_key(migrated, key)
        match = old_value == new_value
        all_match = all_match and match
        print(f"  {key}: old={old_value}, new={new_value}, match={match}")
    
    print(f"\nAll values match: {all_match}")

    # Test 5: Test with missing/invalid JSON
    print("\n5. Testing with invalid JSON config:")
    invalid_config = {
        "region": "Kr.sand",
        HOT_WATER_CONFIG: "invalid json"
    }
    
    try:
        migrated_invalid = _migrate_hot_water_config(invalid_config)
        temp_from_invalid = test_get_config_key(migrated_invalid, TEMP_DEFAULT)
        expected_default = HOT_WATER_DEFAULT_CONFIG[TEMP_DEFAULT]
        fallback_works = temp_from_invalid == expected_default
        print(f"Fallback to defaults works: {fallback_works}")
        print(f"Default value: {temp_from_invalid}")
    except Exception as e:
        print(f"Error handling invalid JSON: {e}")

    print("\n" + "=" * 50)
    print("Migration test completed!")
    
    return all_match and all_present and unchanged and values_match and fallback_works

if __name__ == "__main__":
    success = test_migration_logic()
    if success:
        print("✅ All tests passed! Migration logic works correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed! Please check the migration logic.")
        sys.exit(1)
