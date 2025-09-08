#!/usr/bin/env python3
"""
Test script for a single SKU
"""

from xero_price_updater import PartsPriceScraper
import logging

logging.basicConfig(level=logging.INFO)

def test_sku(sku):
    """Test scraping a single SKU"""
    
    print(f"\n{'='*50}")
    print(f"Testing SKU: {sku}")
    print('='*50)
    
    scraper = PartsPriceScraper(headless=False)  # Run with browser visible to see what's happening
    
    try:
        # Determine website based on SKU
        if sku.startswith('J'):
            print(f"This SKU should be searched on JustKampers")
            price = scraper.search_justkampers(sku)
            website = "JustKampers"
        else:
            print(f"This SKU should be searched on Heritage Parts Centre")
            price = scraper.search_heritage(sku)
            website = "Heritage Parts Centre"
        
        if price is not None:
            print(f"\n✅ SUCCESS: Found price £{price:.2f} on {website}")
        else:
            print(f"\n❌ FAILED: No price found on {website}")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
    
    finally:
        scraper.close_driver()
    
    return price

if __name__ == "__main__":
    # Test J21066 specifically
    test_sku("J21066")