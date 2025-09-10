#!/usr/bin/env python3
"""
Interactive Web Interface for Xero Price Updater
Real-time progress tracking for price scraping
"""

from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import csv
import os
import threading
from datetime import datetime
from xero_price_updater import PartsPriceScraper
import fast_scraper  # For testing mode
import logging
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for tracking progress
current_task = None
scraper_instance = None

class ScraperTask:
    def __init__(self):
        self.total_items = 0
        self.processed_items = 0
        self.updates = []
        self.errors = []
        self.unchanged = []
        self.status = "idle"
        self.current_item = ""
        self.output_file = ""
        self.report_file = ""
        
    def to_dict(self):
        return {
            'total_items': self.total_items,
            'processed_items': self.processed_items,
            'updates_count': len(self.updates),
            'errors_count': len(self.errors),
            'unchanged_count': len(self.unchanged),
            'status': self.status,
            'current_item': self.current_item,
            'progress_percent': (self.processed_items / self.total_items * 100) if self.total_items > 0 else 0
        }

@app.route('/')
def index():
    """Main page with upload form and progress display"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle CSV file upload"""
    global current_task, scraper_instance
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Please upload a CSV file'}), 400
    
    # Save uploaded file
    upload_path = os.path.join('uploads', file.filename)
    os.makedirs('uploads', exist_ok=True)
    file.save(upload_path)
    
    # Check if test mode is requested
    test_mode = request.form.get('test_mode', 'false') == 'true'
    
    # Start processing in background
    current_task = ScraperTask()
    if test_mode:
        logger.info("Starting in TEST MODE with fast scraper")
        thread = threading.Thread(target=process_csv_test, args=(upload_path,))
    else:
        logger.info("Starting in PRODUCTION MODE with real scraper")
        thread = threading.Thread(target=process_csv, args=(upload_path,))
    thread.start()
    
    return jsonify({'message': 'Processing started', 'filename': file.filename, 'mode': 'test' if test_mode else 'production'})

def process_csv_test(filepath):
    """Test mode - Fast processing with simulated prices"""
    global current_task
    
    try:
        current_task.status = "processing"
        socketio.emit('status_update', current_task.to_dict())
        
        # Read CSV
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            items = list(reader)
        
        current_task.total_items = len(items)
        socketio.emit('status_update', current_task.to_dict())
        
        # Process with fast scraper
        def progress_callback(i, total, item_code, item_name, current_price):
            current_task.current_item = f"{item_code}: {item_name}"
            current_task.processed_items = i
            
            socketio.emit('item_processing', {
                'item_code': item_code,
                'item_name': item_name,
                'current_price': current_price,
                'index': i,
                'total': total
            })
            
            socketio.emit('status_update', current_task.to_dict())
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"outputs/xero_import_test_{timestamp}.csv"
        report_file = f"outputs/price_update_test_{timestamp}.txt"
        os.makedirs('outputs', exist_ok=True)
        
        updates, errors, unchanged = fast_scraper.process_csv_fast(
            filepath, output_file, report_file, progress_callback
        )
        
        # Emit results
        for update in updates:
            socketio.emit('item_updated', {
                'item_code': update['ItemCode'],
                'item_name': update['ItemName'],
                'old_price': update['OldPrice'],
                'new_price': update['NewPrice'],
                'difference': update['Difference'],
                'difference_percent': update['DifferencePercent'],
                'source': update['Source'],
                'url': update.get('URL')
            })
        
        for error in errors:
            socketio.emit('item_error', {
                'item_code': error['ItemCode'],
                'item_name': error['ItemName'],
                'current_price': error['CurrentPrice'],
                'error': error['Error']
            })
        
        current_task.updates = updates
        current_task.errors = errors
        current_task.unchanged = unchanged
        current_task.status = "completed"
        current_task.output_file = os.path.basename(output_file)
        current_task.report_file = os.path.basename(report_file)
        
        socketio.emit('processing_complete', {
            'output_file': current_task.output_file,
            'report_file': current_task.report_file,
            'summary': current_task.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error in test processing: {e}")
        current_task.status = "error"
        socketio.emit('processing_error', {'error': str(e)})

def process_csv(filepath):
    """Process the CSV file and update prices"""
    global current_task, scraper_instance
    
    try:
        current_task.status = "processing"
        socketio.emit('status_update', current_task.to_dict())
        
        # Read CSV
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            items = list(reader)
        
        current_task.total_items = len(items)
        socketio.emit('status_update', current_task.to_dict())
        logger.info(f"Starting to process {current_task.total_items} items")
        
        # Initialize scraper
        scraper_instance = PartsPriceScraper(headless=True)
        
        # Process each item
        for i, item in enumerate(items, 1):
            if current_task.status == "cancelled":
                break
                
            item_code = item.get('ItemCode', item.get('*ItemCode', ''))
            item_name = item.get('ItemName', '')
            
            # Handle empty or invalid price values
            try:
                price_str = item.get('SalesUnitPrice', '0').strip()
                current_price = float(price_str) if price_str else 0.0
            except (ValueError, AttributeError):
                current_price = 0.0
            
            current_task.current_item = f"{item_code}: {item_name}"
            current_task.processed_items = i
            
            logger.info(f"Processing item {i}/{current_task.total_items}: {item_name}")
            
            # Emit progress update
            socketio.emit('item_processing', {
                'item_code': item_code,
                'item_name': item_name,
                'current_price': current_price,
                'index': i,
                'total': current_task.total_items
            })
            
            # Get new price with timeout protection
            try:
                new_price, source, url = scraper_instance.get_price(item_name)
            except Exception as e:
                logger.error(f"Error getting price for {item_name}: {e}")
                new_price = None
                source = "error"
                url = None
            
            if new_price is not None:
                price_diff = new_price - current_price
                price_diff_pct = (price_diff / current_price * 100) if current_price > 0 else 0
                
                result = {
                    'item_code': item_code,
                    'item_name': item_name,
                    'old_price': current_price,
                    'new_price': new_price,
                    'difference': price_diff,
                    'difference_percent': price_diff_pct,
                    'source': source,  # Keep the source name
                    'url': url  # Add URL as separate field
                }
                
                if abs(price_diff) > 0.01:
                    current_task.updates.append(result)
                    item['SalesUnitPrice'] = str(new_price)
                    socketio.emit('item_updated', result)
                else:
                    current_task.unchanged.append(result)
                    socketio.emit('item_unchanged', result)
            else:
                error_result = {
                    'item_code': item_code,
                    'item_name': item_name,
                    'current_price': current_price,
                    'error': 'Price not found'
                }
                current_task.errors.append(error_result)
                socketio.emit('item_error', error_result)
            
            socketio.emit('status_update', current_task.to_dict())
        
        # Save results
        if current_task.status != "cancelled":
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            current_task.output_file = f"xero_import_{timestamp}.csv"
            current_task.report_file = f"price_update_report_{timestamp}.txt"
            
            # Write updated CSV
            output_path = os.path.join('outputs', current_task.output_file)
            os.makedirs('outputs', exist_ok=True)
            
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = list(items[0].keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(items)
            
            # Write report
            report_path = os.path.join('outputs', current_task.report_file)
            write_report(report_path, current_task)
            
            current_task.status = "completed"
            socketio.emit('processing_complete', {
                'output_file': current_task.output_file,
                'report_file': current_task.report_file,
                'summary': current_task.to_dict()
            })
        
    except Exception as e:
        logger.error(f"Error processing CSV: {e}")
        current_task.status = "error"
        socketio.emit('processing_error', {'error': str(e)})
    
    finally:
        if scraper_instance:
            scraper_instance.close_driver()
            scraper_instance = None

def write_report(filepath, task):
    """Write the update report"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Price Update Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Summary:\n")
        f.write(f"Total items processed: {task.processed_items}\n")
        f.write(f"Prices updated: {len(task.updates)}\n")
        f.write(f"Prices unchanged: {len(task.unchanged)}\n")
        f.write(f"Errors: {len(task.errors)}\n\n")
        
        if task.updates:
            f.write("PRICE UPDATES:\n")
            f.write("-" * 80 + "\n")
            for update in sorted(task.updates, key=lambda x: abs(x['difference_percent']), reverse=True):
                f.write(f"\n{update['item_code']}: {update['item_name']}\n")
                f.write(f"  Source: {update['source']}\n")
                f.write(f"  Old Price: £{update['old_price']:.2f}\n")
                f.write(f"  New Price: £{update['new_price']:.2f}\n")
                f.write(f"  Difference: £{update['difference']:+.2f} ({update['difference_percent']:+.1f}%)\n")
        
        if task.errors:
            f.write("\n\nERRORS:\n")
            f.write("-" * 80 + "\n")
            for error in task.errors:
                f.write(f"\n{error['item_code']}: {error['item_name']}\n")
                f.write(f"  Current Price: £{error['current_price']:.2f}\n")
                f.write(f"  Error: {error['error']}\n")

@app.route('/status')
def get_status():
    """Get current processing status"""
    global current_task
    if current_task:
        return jsonify(current_task.to_dict())
    return jsonify({'status': 'idle'})

@app.route('/cancel', methods=['POST'])
def cancel_processing():
    """Cancel current processing"""
    global current_task
    if current_task:
        current_task.status = "cancelled"
        return jsonify({'message': 'Processing cancelled'})
    return jsonify({'message': 'No active task'})

@app.route('/download/<filename>')
def download_file(filename):
    """Download result files"""
    filepath = os.path.join('outputs', filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info('Client connected')
    if current_task:
        emit('status_update', current_task.to_dict())

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info('Client disconnected')

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5001, allow_unsafe_werkzeug=True)