# Restaurant Order Management System

## Project Overview
A Python-based restaurant order management system featuring concurrent order processing, database integration, and real-time visualization capabilities.

## System Features
* Real-time order management and tracking
* Configurable concurrent order processing
* Interactive GUI based on tkinter
* Order statistics and visualization using Plotly
* MySQL database integration for order history
* Gantt chart visualization for order processing timeline
* Real-time order status updates
* Table-based order management
* Menu management through Excel integration

## Requirements
* Python 3.8 or higher
* MySQL Server 5.7 or higher
* PyCharm IDE
* DataGrip for database management and visualization
* Python packages:
  - pandas
  - pymysql
  - plotly
  - openpyxl

## Installation Steps

1. Open Project in PyCharm
* Open PyCharm
* Select File -> Open -> Choose project folder
* PyCharm will automatically detect and prompt to create virtual environment

2. Install Python Dependencies in PyCharm Terminal
```bash
# Install required packages
pip install pandas pymysql plotly openpyxl
```

3. Database Configuration

Use DataGrip to create the database and table by executing the following SQL commands:
```sql
CREATE DATABASE IF NOT EXISTS restaurant_db;
USE restaurant_db;
CREATE TABLE IF NOT EXISTS orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    table_number VARCHAR(50) NOT NULL,
    arrival_time FLOAT NOT NULL,
    actual_start_time FLOAT,
    actual_end_time FLOAT,
    wait_time FLOAT,
    dishes TEXT NOT NULL,
    status VARCHAR(20)
);
```

4. Database Connection Configuration
Update the following configuration in `Order_Management_System.py`:
```python
# In OrderSchedulingGUI class's __init__ method
def __init__(self, root):
    self.root = root
    self.menu = self.load_menu()
    
    db_params = {
        'host': 'localhost',
        'user': 'your_username',
        'password': 'your_password',
        'database': 'restaurant_db',
        'port': 3306,
        'charset': 'utf8mb4'
    }
    
    self.order_manager = OrderManager(db_params)
```

## Usage Guide

### Adding Orders
1. Select table number from dropdown menu
2. Enter arrival time (in seconds)
3. Select dish from menu
4. Click "Add Order" to add the order

### Processing Orders
1. Click "Start Processing" to begin order processing
2. System will process orders concurrently based on arrival time
3. Processing output window will display order status updates

### Viewing Statistics
1. Click "Show Statistics" to view processing metrics
2. Statistics include:
   * Average wait time
   * Minimum wait time
   * Maximum wait time
   * Total order count
   * Historical statistics by table

### Viewing Gantt Chart in GUI
Click "Show Gantt Chart" to view the order processing timeline, displaying:
* Processing time period for each order
* Table assignment (distinguished by different colors)
* Detailed order information:
  - Table Number
  - Start Time
  - End Time
  - Order ID
  - Dish Information

### Database Analysis in DataGrip
Access and analyze order data directly in DataGrip:

1. View Data:
   * Open DataGrip and connect to restaurant_db
   * Navigate to orders table
   * View all order records and their details

2. Create Visualizations:
   * Click the Chart icon in the query results toolbar
   * Choose visualization type from the available chart options
   
3. Customize Chart Settings:
   * Categories: Group data by table_number, group, etc.
   * Values: Select metrics to analyze (wait_time, order counts, min, max, etc.)
   * Chart Type: Choose from various visualization options
   * Additional Settings:
     - Adjust chart layout (stacked/horizontal)
   
4. Available Metrics for Analysis:
   * Wait times by table
   * Order processing durations
   * Order status distribution

5. Export Options:
   * Download charts as images
   * Export data for external analysis

## Project Structure
```
restaurant_system/
│
├── Order_Management_System.py  # Main program file
├── menu.xlsx                  # Menu data file (provided)
└── README.md                  # Project documentation
```

## Troubleshooting

### Database Connection Issues
* Verify MySQL server is running
* Check database credentials configuration
* Ensure database and tables are correctly created in DataGrip
* Validate database connection parameters

### Menu File Issues
* Ensure using the provided `menu.xlsx` file
* Do not modify menu file structure (maintain dish_name and cooking_time columns)

### GUI Issues
* Ensure all dependencies are correctly installed
* Run the program in PyCharm rather than directly from command line

