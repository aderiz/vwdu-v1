#!/usr/bin/env python3
"""
Xero Parts Price Updater
Scrapes prices from JustKampers.com and Heritage Parts Centre
Updates prices in Xero export CSV file
"""

import csv
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from decimal import Decimal
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PartsPriceScraper:
    """Scraper for parts prices from JustKampers and Heritage Parts Centre"""
    
    def __init__(self, headless: bool = True):
        """Initialize the scraper with Chrome options"""
        self.options = Options()
        if headless:
            self.options.add_argument('--headless=new')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option('useAutomationExtension', False)
        self.options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        self.driver = None
        
    def start_driver(self):
        """Start the Chrome driver"""
        if not self.driver:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=self.options)
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(5)
    
    def close_driver(self):
        """Close the Chrome driver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def extract_sku_from_name(self, item_name: str) -> Tuple[str, str]:
        """
        Extract SKU and description from item name
        Returns: (description, sku)
        """
        # Split by last space to separate SKU from description
        parts = item_name.rsplit(' ', 1)
        if len(parts) == 2:
            description, sku = parts
            # Clean up SKU - remove trailing slashes and spaces
            sku = sku.strip().rstrip('/')
            return description.strip(), sku
        return item_name, ""
    
    def determine_website(self, sku: str) -> str:
        """Determine which website to search based on SKU prefix"""
        if sku.startswith('J'):
            return 'justkampers'
        else:
            return 'heritage'
    
    def search_justkampers(self, sku: str) -> Optional[float]:
        """
        Search for a part on JustKampers.com
        Returns the price if found, None otherwise
        """
        try:
            self.start_driver()
            
            # Clean SKU for search
            search_sku = sku.strip()
            search_sku_normalized = search_sku.upper()
            
            # Search URL
            search_url = f"https://www.justkampers.com/catalogsearch/result/?q={search_sku}"
            logger.info(f"Searching JustKampers for SKU: {search_sku}")
            
            self.driver.get(search_url)
            time.sleep(2)  # Wait for JavaScript to load
            
            # Handle cookie popup if present
            try:
                cookie_button = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'ACCEPT') or contains(text(), 'accept') or contains(@class, 'accept') or contains(@id, 'accept')]"))
                )
                cookie_button.click()
                logger.info("Accepted cookies on JustKampers")
                time.sleep(1)
            except:
                pass  # Cookie popup might not appear or already accepted
            
            # Wait for page to load and check for products
            time.sleep(3)  # Allow page to load
            
            # Look for product items
            products = self.driver.find_elements(By.CSS_SELECTOR, "div.product-item")
            
            if not products:
                logger.warning(f"No products found for {search_sku} on JustKampers")
                return None
            
            logger.info(f"Found {len(products)} products on JustKampers")
            
            # Check each product for matching SKU
            for product in products:
                try:
                    # Look for SKU in the amlabel-text div (where JustKampers shows the SKU)
                    sku_labels = product.find_elements(By.CSS_SELECTOR, "div.amlabel-text")
                    product_sku = ""
                    
                    for label in sku_labels:
                        label_text = label.text.strip()
                        if label_text:
                            product_sku = label_text
                            logger.info(f"Found SKU label: {product_sku}")
                            break
                    
                    # Check if this is our SKU (case-insensitive)
                    if product_sku.upper() == search_sku_normalized:
                        logger.info(f"Found matching product with SKU {product_sku}")
                        
                        # Extract price from this product
                        price_selectors = [
                            "span.price",
                            "span[data-price-type='finalPrice']",
                            "div.price-box span.price",
                            "span.price-wrapper span.price"
                        ]
                        
                        for selector in price_selectors:
                            try:
                                price_element = product.find_element(By.CSS_SELECTOR, selector)
                                
                                # Try getting price from data attribute first
                                price_amount = price_element.get_attribute('data-price-amount')
                                if price_amount:
                                    price = float(price_amount)
                                    logger.info(f"Found price £{price} for {search_sku} on JustKampers (from data attribute)")
                                    return price
                                
                                # Otherwise get from text
                                price_text = price_element.text
                                if price_text:
                                    price_match = re.search(r'[\d,]+\.?\d*', price_text)
                                    if price_match:
                                        price = float(price_match.group().replace(',', ''))
                                        logger.info(f"Found price £{price} for {search_sku} on JustKampers")
                                        return price
                            except NoSuchElementException:
                                continue
                        
                        # If no price found in listing, try clicking through to product page
                        try:
                            product_link = product.find_element(By.CSS_SELECTOR, "a.product-item-photo, a.product-item-link")
                            product_link.click()
                            time.sleep(2)
                            
                            # Try to get price from product page
                            for selector in price_selectors:
                                try:
                                    price_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                                    price_text = price_element.text
                                    
                                    price_match = re.search(r'[\d,]+\.?\d*', price_text)
                                    if price_match:
                                        price = float(price_match.group().replace(',', ''))
                                        logger.info(f"Found price £{price} for {search_sku} on JustKampers (product page)")
                                        return price
                                except NoSuchElementException:
                                    continue
                        except:
                            pass
                        
                        logger.warning(f"Product found but no price for {search_sku} on JustKampers")
                        return None
                        
                except Exception as e:
                    logger.debug(f"Error checking product: {e}")
                    continue
            
            logger.warning(f"No exact match found for {search_sku} on JustKampers")
            return None
            
        except Exception as e:
            logger.error(f"Error searching JustKampers for {sku}: {e}")
            return None
    
    def search_heritage(self, sku: str) -> Optional[float]:
        """
        Search for a part on Heritage Parts Centre
        Returns the price if found, None otherwise
        """
        try:
            self.start_driver()
            
            # Clean SKU for search - Heritage sometimes has different formatting
            search_sku = sku.strip().rstrip('/')
            # Remove spaces that might be in Heritage SKUs (make case-insensitive)
            search_sku_normalized = search_sku.replace(' ', '').replace('/', '').upper()
            
            # Search URL
            search_url = f"https://www.heritagepartscentre.com/uk/catalogsearch/result/?q={search_sku}"
            logger.info(f"Searching Heritage for SKU: {search_sku}")
            
            self.driver.get(search_url)
            time.sleep(3)  # Wait for JavaScript to load
            
            # Handle cookie popup if present (Cookiebot)
            try:
                # Try to click the OK/Accept button on the Cookiebot dialog
                cookie_button = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.ID, "CybotCookiebotDialogBodyLevelButtonAccept"))
                )
                cookie_button.click()
                logger.info("Accepted cookies on Heritage (Cookiebot)")
                time.sleep(1)
            except:
                try:
                    # Alternative: try other cookie accept buttons
                    cookie_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'OK') or contains(text(), 'Accept')]")
                    cookie_button.click()
                    logger.info("Accepted cookies on Heritage")
                    time.sleep(1)
                except:
                    pass  # Cookie popup might not appear or already accepted
            
            # Wait for search results
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "products-grid"))
                )
            except TimeoutException:
                logger.warning(f"No search results found for {search_sku} on Heritage")
                return None
            
            # Additional wait for content to fully load
            time.sleep(2)
            
            # Find products in search results  
            products = self.driver.find_elements(By.CSS_SELECTOR, "div.product-item-info")
            
            if not products:
                # Try alternative selectors
                products = self.driver.find_elements(By.CSS_SELECTOR, "li.product-item")
                if not products:
                    products = self.driver.find_elements(By.CSS_SELECTOR, "article.product-item-info")
            
            logger.info(f"Found {len(products)} products to check")
            
            for i, product in enumerate(products):
                try:
                    # Check SKU in product info - multiple possible locations
                    sku_text = ""
                    sku_selectors = [
                        "div.product__sku mark",  # This is what Heritage uses
                        "div.product-item-sku",
                        "span.sku",
                        "div.sku",
                        "span[itemprop='sku']"
                    ]
                    
                    for selector in sku_selectors:
                        try:
                            sku_element = product.find_element(By.CSS_SELECTOR, selector)
                            sku_text = sku_element.text.strip()
                            if sku_text:
                                logger.info(f"Found SKU in product {i}: {sku_text}")
                                break
                        except:
                            continue
                    
                    # Also check in product name/title
                    if not sku_text:
                        try:
                            title = product.find_element(By.CSS_SELECTOR, "a.product-item-link, h2.product-name").text
                            if search_sku in title:
                                sku_text = search_sku
                        except:
                            pass
                    
                    product_sku = sku_text
                    
                    # Normalize for comparison (case-insensitive)
                    product_sku_normalized = product_sku.replace(' ', '').replace('/', '').upper()
                    search_normalized = search_sku_normalized
                    
                    if product_sku_normalized == search_normalized:
                        # Found exact match, get price
                        price_selectors = [
                            "span.price-wrapper[data-price-including-tax] span.price",  # Heritage's exact selector
                            "span[itemprop='lowPrice']",  # Alternative Heritage selector
                            "span.price:not(:empty)",
                            "span[data-price-type='finalPrice'] span.price",
                            "div.price-box span[data-price-amount]",
                            "span.price-wrapper span.price",
                            "div.price-final_price span.price",
                            "span.regular-price span.price"
                        ]
                        
                        for selector in price_selectors:
                            try:
                                price_element = product.find_element(By.CSS_SELECTOR, selector)
                                
                                # Try getting text first
                                price_text = price_element.text
                                
                                # If text is empty, try getting attribute values
                                if not price_text:
                                    # Check parent element for data-price-including-tax attribute
                                    parent = price_element.find_element(By.XPATH, "..")
                                    price_text = parent.get_attribute('data-price-including-tax')
                                    if not price_text:
                                        price_text = price_element.get_attribute('data-price-amount')
                                    if not price_text:
                                        price_text = price_element.get_attribute('content')
                                    if not price_text:
                                        price_text = price_element.get_attribute('innerText')
                                
                                if price_text:
                                    # Extract numeric price
                                    price_match = re.search(r'[\d,]+\.?\d*', str(price_text))
                                    if price_match:
                                        price = float(price_match.group().replace(',', ''))
                                        if price > 0:  # Make sure we have a valid price
                                            logger.info(f"Found price £{price} for {search_sku} on Heritage")
                                            return price
                            except Exception as e:
                                logger.debug(f"Price extraction error with {selector}: {e}")
                                continue
                        
                        # If no price found in list, try clicking through to product page
                        product_link = product.find_element(By.CSS_SELECTOR, "a.product-item-link")
                        product_link.click()
                        time.sleep(2)
                        
                        # Try to get price from product page
                        for selector in price_selectors:
                            try:
                                price_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                                price_text = price_element.text
                                
                                price_match = re.search(r'[\d,]+\.?\d*', price_text)
                                if price_match:
                                    price = float(price_match.group().replace(',', ''))
                                    logger.info(f"Found price £{price} for {search_sku} on Heritage (product page)")
                                    return price
                            except NoSuchElementException:
                                continue
                        
                except Exception as e:
                    logger.debug(f"Error checking product: {e}")
                    continue
            
            logger.warning(f"No exact match found for {search_sku} on Heritage")
            return None
            
        except Exception as e:
            logger.error(f"Error searching Heritage for {sku}: {e}")
            return None
    
    def get_price(self, item_name: str) -> Tuple[Optional[float], str]:
        """
        Get price for an item based on its name and SKU
        Returns: (price, source_website)
        """
        description, sku = self.extract_sku_from_name(item_name)
        
        if not sku:
            logger.warning(f"No SKU found in item name: {item_name}")
            return None, "unknown"
        
        website = self.determine_website(sku)
        
        if website == 'justkampers':
            price = self.search_justkampers(sku)
            return price, 'JustKampers'
        else:
            price = self.search_heritage(sku)
            return price, 'Heritage Parts Centre'


def process_xero_export(input_file: str, output_file: str, update_file: str):
    """
    Process the Xero export file and update prices
    
    Args:
        input_file: Path to the original Xero export CSV
        output_file: Path to save the updated CSV for Xero import
        update_file: Path to save the price comparison report
    """
    scraper = PartsPriceScraper(headless=True)
    
    try:
        # Read the input CSV
        with open(input_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            items = list(reader)
        
        # Prepare update report
        updates = []
        errors = []
        unchanged = []
        
        # Process each item
        total_items = len(items)
        logger.info(f"Processing {total_items} items...")
        
        for i, item in enumerate(items, 1):
            item_code = item.get('ItemCode', item.get('*ItemCode', ''))
            item_name = item.get('ItemName', '')
            current_price = float(item.get('SalesUnitPrice', 0))
            
            logger.info(f"[{i}/{total_items}] Processing: {item_name}")
            
            # Get new price
            new_price, source = scraper.get_price(item_name)
            
            if new_price is not None:
                price_diff = new_price - current_price
                price_diff_pct = (price_diff / current_price * 100) if current_price > 0 else 0
                
                if abs(price_diff) > 0.01:  # Price changed
                    updates.append({
                        'ItemCode': item_code,
                        'ItemName': item_name,
                        'OldPrice': current_price,
                        'NewPrice': new_price,
                        'Difference': price_diff,
                        'DifferencePercent': price_diff_pct,
                        'Source': source
                    })
                    # Update the item's price
                    item['SalesUnitPrice'] = str(new_price)
                else:
                    unchanged.append({
                        'ItemCode': item_code,
                        'ItemName': item_name,
                        'Price': current_price,
                        'Source': source
                    })
            else:
                errors.append({
                    'ItemCode': item_code,
                    'ItemName': item_name,
                    'CurrentPrice': current_price,
                    'Error': 'Price not found'
                })
            
            # Add a small delay to avoid overwhelming the servers
            time.sleep(1)
        
        # Write the updated CSV for Xero import
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = list(items[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(items)
        
        # Write the update report
        with open(update_file, 'w', newline='', encoding='utf-8') as f:
            f.write(f"Price Update Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Summary:\n")
            f.write(f"Total items processed: {total_items}\n")
            f.write(f"Prices updated: {len(updates)}\n")
            f.write(f"Prices unchanged: {len(unchanged)}\n")
            f.write(f"Errors: {len(errors)}\n\n")
            
            if updates:
                f.write("PRICE UPDATES:\n")
                f.write("-" * 80 + "\n")
                for update in sorted(updates, key=lambda x: abs(x['DifferencePercent']), reverse=True):
                    f.write(f"\n{update['ItemCode']}: {update['ItemName']}\n")
                    f.write(f"  Source: {update['Source']}\n")
                    f.write(f"  Old Price: £{update['OldPrice']:.2f}\n")
                    f.write(f"  New Price: £{update['NewPrice']:.2f}\n")
                    f.write(f"  Difference: £{update['Difference']:+.2f} ({update['DifferencePercent']:+.1f}%)\n")
            
            if errors:
                f.write("\n\nERRORS (prices not found):\n")
                f.write("-" * 80 + "\n")
                for error in errors:
                    f.write(f"\n{error['ItemCode']}: {error['ItemName']}\n")
                    f.write(f"  Current Price: £{error['CurrentPrice']:.2f}\n")
                    f.write(f"  Error: {error['Error']}\n")
            
            if unchanged:
                f.write("\n\nUNCHANGED PRICES:\n")
                f.write("-" * 80 + "\n")
                for item in unchanged:
                    f.write(f"{item['ItemCode']}: {item['ItemName']} - £{item['Price']:.2f} ({item['Source']})\n")
        
        logger.info(f"Processing complete!")
        logger.info(f"Updated CSV saved to: {output_file}")
        logger.info(f"Update report saved to: {update_file}")
        
        return updates, errors, unchanged
        
    finally:
        scraper.close_driver()


if __name__ == "__main__":
    # File paths
    input_file = "xero_export.csv"
    output_file = f"xero_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    update_report = f"price_update_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    # Process the files
    updates, errors, unchanged = process_xero_export(input_file, output_file, update_report)
    
    # Print summary
    print("\n" + "=" * 50)
    print("PRICE UPDATE SUMMARY")
    print("=" * 50)
    print(f"Total items processed: {len(updates) + len(errors) + len(unchanged)}")
    print(f"Prices updated: {len(updates)}")
    print(f"Prices unchanged: {len(unchanged)}")
    print(f"Errors (not found): {len(errors)}")
    print(f"\nOutput files:")
    print(f"  - Xero import file: {output_file}")
    print(f"  - Update report: {update_report}")