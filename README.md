# Xero Parts Price Updater

Automated price scraper for VW parts from JustKampers.com and Heritage Parts Centre. Updates prices in Xero export CSV files for mass import.

## Features

- Automatically identifies parts by SKU from item names
- Scrapes current prices from:
  - JustKampers.com (SKUs starting with 'J' or 'AC')
  - Heritage Parts Centre (all other SKUs)
- Handles SKU formatting variations (spaces, trailing slashes)
- Generates:
  - Updated CSV file ready for Xero import
  - Detailed price comparison report
  - Summary of changes, unchanged items, and errors

## Installation

1. Install Python 3.8 or higher
2. Install Chrome browser
3. Install ChromeDriver (download from https://chromedriver.chromium.org/)
4. Set up the project:

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Basic Usage

Run the main scraper on your Xero export:

```bash
python xero_price_updater.py
```

This will:
1. Read `xero_export.csv` from the current directory
2. Scrape current prices for all items
3. Generate:
   - `xero_import_YYYYMMDD_HHMMSS.csv` - Updated prices for Xero import
   - `price_update_report_YYYYMMDD_HHMMSS.txt` - Detailed comparison report

### Test Mode

To test with a small sample of items:

```bash
python test_price_scraper.py
```

This runs the scraper on 5 sample items to verify everything is working.

### Custom Files

To use custom input/output files, modify the file paths in `xero_price_updater.py`:

```python
input_file = "your_export.csv"
output_file = "your_import.csv"
update_report = "your_report.txt"
```

## CSV Format

The Xero export CSV must have these columns:
- `ItemCode` or `*ItemCode` - Unique item identifier
- `ItemName` - Description and SKU (e.g., "HEAT GASKET SET J21066")
- `SalesUnitPrice` - Current price

## SKU Format

The scraper extracts SKUs from the ItemName field:
- **JustKampers**: SKUs starting with 'J' or 'AC' (e.g., J21066, AC119119)
- **Heritage Parts**: All other SKUs (e.g., 113-105-245/F/GEN, 211-898-111/MP)

The SKU should be the last part of the ItemName, separated by a space.

## Output Files

### Updated CSV (`xero_import_*.csv`)
Ready for direct import into Xero with updated prices.

### Price Report (`price_update_report_*.txt`)
Contains:
- Summary statistics
- List of price changes (sorted by percentage change)
- Items where prices couldn't be found
- Items with unchanged prices

## Troubleshooting

### ChromeDriver Issues
If you get ChromeDriver errors:
1. Check Chrome browser is installed
2. Download matching ChromeDriver version
3. Add ChromeDriver to PATH or place in project directory

### Price Not Found
Common reasons:
- SKU format doesn't match website
- Product discontinued or out of stock
- Website structure changed

### Slow Performance
The scraper includes delays to avoid overwhelming servers. Processing 100 items takes approximately 2-3 minutes.

## Configuration

Edit `xero_price_updater.py` to adjust:
- `headless`: Set to `False` to see browser during scraping
- Request delays between items
- Logging level

## License

For internal business use only.