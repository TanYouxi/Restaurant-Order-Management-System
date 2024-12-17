import tkinter as tk
from tkinter import ttk, messagebox
import time
import threading
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import pymysql
import plotly.express as px
from datetime import datetime, timedelta
from queue import PriorityQueue
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Order:
    """Class to represent an order with its details and processing status."""
    def __init__(self, order_id, arrival_time, task_time, table_number, dishes):
        self.order_id = order_id
        self.arrival_time = arrival_time
        self.task_time = task_time
        self.table_number = table_number
        self.dishes = dishes
        self.status = "Pending"
        self.actual_start_time = None
        self.actual_end_time = None
        self.wait_time = None

    def __lt__(self, other):
        """Enable comparison of orders based on arrival time for priority queue."""
        return self.arrival_time < other.arrival_time


def convert_to_datetime(seconds):
    """
    Convert seconds since midnight to a datetime object.
    This is useful for human-readable timestamps.
    """
    base_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return base_time + timedelta(seconds=int(seconds))


class ConcurrentProcessor:
    """Class to handle concurrent processing of orders using a thread pool."""
    def __init__(self, max_workers=3):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.lock = threading.Lock()
        self.order_queue = PriorityQueue()
        self.running_tasks = set()
        self.completed_orders = []
        self.is_running = False
        self.max_workers = max_workers
        self.start_time = time.time()
        self.total_wait_time = 0
        self.order_count = 0
        self.min_wait_time = float('inf')
        self.max_wait_time = 0
        self._stop_event = threading.Event()
        self.neworder_time = None

    def add_order(self, order):
        """Add orders to the processing queue"""
        self.order_queue.put((order.arrival_time, order.task_time, order))

    def process_task(self, order, update_callback, order_manager):
        """
        Process an individual order.
        Handles the order's status, timing, and database saving.
        """
        try:
            with self.lock:
                self.running_tasks.add(order.order_id)
                current_time = time.time()
                wait_time = current_time - (order.arrival_time + self.start_time)
                order.actual_start_time = current_time  # record  actual start time
                order.status = "Processing"  # update order status

                # update UI
                if update_callback:
                    update_callback(f"Started processing Order {order.order_id}\n")

            # Analog processing time
            processing_start = time.time()
            while time.time() - processing_start < order.task_time:
                if self._stop_event.is_set():
                    return
                time.sleep(0.1)

            with self.lock:
                order.actual_end_time = time.time()
                order.status = "Completed"
                order.wait_time = wait_time

                # Updated statistics
                if wait_time > 0:
                    self.total_wait_time += wait_time
                    self.order_count += 1
                    self.min_wait_time = min(self.min_wait_time, wait_time)
                    self.max_wait_time = max(self.max_wait_time, wait_time)

                self.completed_orders.append(order)
                self.running_tasks.remove(order.order_id)

                # Save to database
                try:
                    if order_manager:
                        order_manager.save_to_db(order)
                        update_callback(f"Order {order.order_id} saved to database\n")
                except Exception as e:
                    update_callback(f"Error saving order to database: {str(e)}\n")

                # Notification UI
                if update_callback:
                    update_callback(f"Completed Order {order.order_id} (Wait time: {wait_time:.2f}s)\n")

        except Exception as e:
            print(f"Error processing order {order.order_id}: {str(e)}")

    def run_concurrent(self, update_callback, order_manager):
        """Run the processor concurrently to handle incoming orders."""
        self._stop_event.clear()
        self.is_running = True
        self.start_time = time.time()
        self.neworder_time= time.time()

        def process_queue():
            """Continuously process orders from the queue."""
            while not self._stop_event.is_set():
                try:
                    if not self.order_queue.empty():
                        arrival_time, task_time, order = self.order_queue.get_nowait()
                        current_time = time.time() - self.start_time

                        if arrival_time <= current_time:
                            if len(self.running_tasks) < self.max_workers:
                                self.executor.submit(
                                    self.process_task,
                                    order,
                                    update_callback,
                                    order_manager
                                )
                            else:
                                self.order_queue.put((arrival_time, task_time, order))
                        else:
                            self.order_queue.put((arrival_time, task_time, order))
                    time.sleep(0.1)
                except Empty:
                    continue
                except Exception as e:
                    print(f"Error in process queue: {str(e)}")

        self.queue_thread = threading.Thread(target=process_queue)
        self.queue_thread.daemon = True
        self.queue_thread.start()

    def stop(self):
        """Stop the processor and clean up resources."""
        self._stop_event.set()
        self.is_running = False
        if hasattr(self, 'queue_thread'):
            self.queue_thread.join(timeout=1.0)
        self.executor.shutdown(wait=False)

    def get_statistics(self):
        """Obtaining processing statistics"""
        if self.order_count == 0:
            return {
                'avg_wait_time': 0,
                'min_wait_time': 0,
                'max_wait_time': 0,
                'total_orders': 0
            }

        return {
            'avg_wait_time': self.total_wait_time / self.order_count if self.order_count > 0 else 0,
            'min_wait_time': self.min_wait_time if self.min_wait_time != float('inf') else 0,
            'max_wait_time': self.max_wait_time,
            'total_orders': self.order_count
        }

class OrderManager:
    def __init__(self, db_params):
        # Initialize the OrderManager with database parameters and a concurrent processor
        self.db_params = db_params
        self.processor = ConcurrentProcessor(max_workers=3)
        self.orders = []
        try:
            # Attempt to set up the database
            self.setup_database()
        except Exception as e:
            # Log the error and display a warning if database setup fails
            logger.error(f"Database initialization error: {e}")
            messagebox.showwarning("Database Warning",
                                   "Unable to connect to database. System will work without database functionality.")

    def setup_database(self):
        # Creating the 'orders' table. If the table already exists, it will be dropped and recreated.
        try:
            conn = pymysql.connect(**self.db_params)
            try:
                with conn.cursor() as cursor:
                    cursor.execute("DROP TABLE IF EXISTS orders")
                    cursor.execute("""
                        CREATE TABLE orders (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            order_id INT,
                            table_number VARCHAR(50),
                            arrival_time DATETIME,
                            actual_start_time DATETIME,
                            actual_end_time DATETIME,
                            wait_time FLOAT,
                            dishes TEXT,
                            status VARCHAR(20)
                        )
                    """)
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            # Raise an exception if there is an error in setting up the database
            raise Exception(f"Database setup error: {e}")

    def save_to_db(self, order):
        #Save an order to the database by inserting its details into the 'orders' table.
        try:
            conn = pymysql.connect(**self.db_params)
            try:
                with conn.cursor() as cursor:
                    # Convert Unix timestamps to datetime objects
                    start_time = datetime.fromtimestamp(order.actual_start_time)
                    end_time = datetime.fromtimestamp(order.actual_end_time)
                    arrival_time = datetime.fromtimestamp(order.arrival_time + self.processor.start_time)
                    # SQL query to insert the order details
                    sql = """
                        INSERT INTO orders (
                            order_id, table_number, arrival_time,
                            actual_start_time, actual_end_time, 
                            wait_time, dishes, status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    # Execute the SQL query with the order's data
                    cursor.execute(sql, (
                        order.order_id,
                        order.table_number,
                        arrival_time,
                        start_time,
                        end_time,
                        order.wait_time,
                        ','.join(order.dishes), # Convert the list of dishes to a comma-separated string
                        order.status
                    ))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            # Log the error if the order could not be saved to the database
            logger.error(f"Database save error: {e}")

    def get_stats_from_db(self):
        """
        Retrieve statistics for orders from the database, grouped by table number.
        Statistics include average, minimum, and maximum wait times and total orders.
        """
        conn = None
        try:
            conn = pymysql.connect(**self.db_params)
            with conn.cursor() as cursor:
                # SQL query to calculate order statistics grouped by table number
                cursor.execute("""
                    SELECT 
                        table_number,
                        AVG(wait_time) as avg_wait_time,
                        COUNT(*) as total_orders,
                        MIN(wait_time) as min_wait_time,
                        MAX(wait_time) as max_wait_time
                    FROM orders
                    GROUP BY table_number
                """)
                stats = cursor.fetchall() # Fetch all results from the query
                return stats              # Return the statistics
        except Exception as e:
            # Log the error if the query fails and return an empty list
            logger.error(f"Database query error: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def add_order(self, order):
        # Add order to the order list and submit it to the concurrent processor for handling.
        self.orders.append(order)
        self.processor.add_order(order)


class OrderSchedulingGUI:
    def __init__(self, root):
        self.root = root
        self.menu = self.load_menu()  # load menu data

        # Database connection parameters
        db_params = {
            'host': 'localhost',
            'user': 'root',
            'password': 'tyx2004826',  # Database password (replace with your password)
            'database': 'restaurant_db',
            'port': 3306,
            'charset': 'utf8mb4'
        }

        # Initialize the order manager
        self.order_manager = OrderManager(db_params)
        self.order_id_counter = 1  # Counter for generating unique order IDs
        self.setup_gui()  # Set up the GUI layout


    def setup_gui(self):
        """set the GUI of the main window"""
        self.root.title("Restaurant Order Management System")  # Set window title
        self.root.geometry("1000x800")  # Set window size

        # Create main frames
        self.create_input_frame()  # Input section
        self.create_order_list_frame()  # Order list section
        self.create_control_frame()  # Control button section
        self.create_output_frame()  # Output display section

    def create_input_frame(self):
        """Create the order input section."""
        input_frame = ttk.LabelFrame(self.root, text="Order Input", padding="10")  # Group frame with title
        input_frame.pack(fill="x", padx=10, pady=5)

        # Table selection
        ttk.Label(input_frame, text="Table:").grid(row=0, column=0, padx=5)  # Label for table selection
        self.table_var = tk.StringVar()  # Variable to store selected table
        self.table_combo = ttk.Combobox(
            input_frame, textvariable=self.table_var,
            values=["Table 1", "Table 2", "Table 3","Table 4","Table 5","Table 6"],  # Options of the table
            state="readonly"  # Make the dropdown read-only
        )
        self.table_combo.grid(row=0, column=1, padx=5)
        self.table_combo.current(0)  # Set the default selection to the first value

        # Arrival time input field
        ttk.Label(input_frame, text="Arrival Time:").grid(row=0, column=2, padx=5)
        self.arrival_time_var = tk.StringVar()
        self.arrival_time_entry = ttk.Entry(
            input_frame, textvariable=self.arrival_time_var
        )
        self.arrival_time_entry.grid(row=0, column=3, padx=5)

        # Dish selection
        ttk.Label(input_frame, text="Dish:").grid(row=0, column=4, padx=5)
        self.dish_var = tk.StringVar()
        self.dish_combo = ttk.Combobox(
            input_frame, textvariable=self.dish_var,
            values=list(self.menu['dish_name']),
            state="readonly"
        )
        self.dish_combo.grid(row=0, column=5, padx=5)

        # Add order button
        ttk.Button(
            input_frame, text="Add Order",
            command=self.add_order
        ).grid(row=0, column=6, padx=5)

    def create_order_list_frame(self):
        """Create the section for displaying the current order list."""
        list_frame = ttk.LabelFrame(self.root, text="Current Orders", padding="10")
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Create treeview
        columns = ("ID", "Table", "Arrival", "Dish", "Status", "Wait Time")
        self.order_tree = ttk.Treeview(list_frame, columns=columns, show="headings")

        # Configure columns
        for col in columns:
            self.order_tree.heading(col, text=col)
            self.order_tree.column(col, width=100)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical",
            command=self.order_tree.yview
        )
        self.order_tree.configure(yscrollcommand=scrollbar.set)

        self.order_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def create_control_frame(self):
        """Create the control button section."""
        control_frame = ttk.Frame(self.root)  # Simple frame for buttons
        control_frame.pack(fill="x", padx=10, pady=5)

        # Start processing orders
        ttk.Button(
            control_frame, text="Start Processing",
            command=self.start_processing
        ).pack(side="left", padx=5)

        # Display statistics
        ttk.Button(
            control_frame, text="Show Statistics",
            command=self.show_statistics
        ).pack(side="left", padx=5)

        # Display Gantt chart
        ttk.Button(
            control_frame, text="Show Gantt Chart",
            command=self.show_gantt
        ).pack(side="left", padx=5)

    def create_output_frame(self):
        """Create the processing output display section."""
        output_frame = ttk.LabelFrame(self.root, text="Processing Output", padding="10")
        output_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Multi-line text box for displaying processing output
        self.output_text = tk.Text(output_frame, height=10)
        self.output_text.pack(fill="both", expand=True)

    def load_menu(self):
        """Load menu data from the Excel file"""
        try:
            # Attempt to load the menu data using pandas
            return pd.read_excel("menu.xlsx")
        #
        except FileNotFoundError:
            logger.error("Menu file not found")
            messagebox.showerror("Error", "Menu file not found!") # Display an error popup
            # Return default menu data if the file is missing
            return pd.DataFrame({
                'dish_name': ['Default Dish'],
                'cooking_time': [10],
                'price': [10.0]
            })

    def add_order(self):
        """Add a new order based on user input."""
        try:
          # If processing has not yet started,rival_time is based on Start Processing
            if not self.order_manager.processor.is_running:
              arrival_time = float(self.arrival_time_var.get())
            else:
              # If processing has already begun, arrival_time is based on Add Order + input arrival_time.
              arrival_time = time.time() - self.order_manager.processor.neworder_time + float(self.arrival_time_var.get())

            dish_name = self.dish_var.get()
            dish_info = self.menu[self.menu['dish_name'] == dish_name].iloc[0] # Retrieve dish information from the menu

            # Create an Order object
            order = Order(
                self.order_id_counter,
                arrival_time,
                dish_info['cooking_time'],
                self.table_var.get(),
                [dish_name]
            )

            # Add the order to the order manager
            self.order_manager.add_order(order)

            # Add to treeview
            self.order_tree.insert(
                "", "end",
                values=(
                    order.order_id,
                    order.table_number,
                    order.arrival_time,
                    dish_name,
                    order.status,
                    "Waiting"
                )
            )

            self.order_id_counter += 1  # Update the Treeview with the new order
            self.arrival_time_var.set("")  # Clear input of the arrival time filed

        except ValueError:
            messagebox.showerror("Error", "Please enter valid arrival time!")
        except Exception as e:
            messagebox.showerror("Error", f"Error adding order: {str(e)}")

    def start_processing(self):
        """Start processing orders and dynamically update the interface."""
        def update_callback(message):
            """
            Callback function to handle updates from the order processor.
            Dynamically updates the output text box and the Treeview order status.
            """
            self.output_text.insert(tk.END, message)  # Append message to the output text box
            self.output_text.see(tk.END)  # Automatically scroll to the latest message
            self.root.update_idletasks()  # Force update of the UI

            # Update order status in treeview
            if "Completed" in message:
                order_id = int(message.split()[2])  # Extract the order ID from the message
                for item in self.order_tree.get_children():
                    if int(self.order_tree.item(item)['values'][0]) == order_id:
                        values = list(self.order_tree.item(item)['values'])
                        values[4] = "Completed"
                        values[5] = f"{self.order_manager.processor.completed_orders[-1].wait_time:.2f}s"
                        self.order_tree.item(item, values=values)
                        break

        # Ensure that the order_manager parameter is passed
        self.order_manager.processor.run_concurrent(update_callback, self.order_manager)

    def show_statistics(self):
        """Display the order processing statistics in a separate window."""
        stats = self.order_manager.processor.get_statistics()
        db_stats = self.order_manager.get_stats_from_db()

        # Create a new window for statistics
        stats_window = tk.Toplevel()
        stats_window.title("Processing Statistics")
        stats_window.geometry("500x400")  # Increase window width

        # Create Treeview and set column widths
        tree = ttk.Treeview(stats_window, columns=('metric', 'value'), show='headings')
        tree.heading('metric', text='Metric')
        tree.heading('value', text='Value')

        # Set column widths and alignment
        tree.column('metric', width=300, anchor='w')  # Widen Metric columns, left-justified
        tree.column('value', width=150, anchor='center')  # Set Value column width, center-aligned

        # Current session stats
        tree.insert('', 'end', values=(
            'Current Session - Average Wait Time',
            f"{stats['avg_wait_time']:.2f}s"
        ))
        tree.insert('', 'end', values=(
            'Current Session - Min Wait Time',
            f"{stats['min_wait_time']:.2f}s"
        ))
        tree.insert('', 'end', values=(
            'Current Session - Max Wait Time',
            f"{stats['max_wait_time']:.2f}s"
        ))
        tree.insert('', 'end', values=(
            'Current Session - Total Orders',
            stats['total_orders']
        ))

        # Historical stats by table
        if db_stats:
            tree.insert('', 'end', values=('', ''))
            tree.insert('', 'end', values=(
                'Historical Stats by Table',
                ''
            ))
            for stat in db_stats:
                tree.insert('', 'end', values=(
                    f'Table {stat[0]} - Average Wait Time',
                    f"{stat[1]:.2f}s"
                ))
                tree.insert('', 'end', values=(
                    f'Table {stat[0]} - Total Orders',
                    stat[2]
                ))

        # Add a scrollbar
        scrollbar = ttk.Scrollbar(stats_window, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        # Use a pack layout so that the tree view fills the entire window
        tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")

        # Resize the window to fit the content
        stats_window.update()
        window_width = tree.winfo_reqwidth() + scrollbar.winfo_reqwidth() + 30
        window_height = min(400, tree.winfo_reqheight() + 50)
        stats_window.geometry(f"{window_width}x{window_height}")

        # Set the minimum window size
        stats_window.minsize(400, 300)

    def show_gantt(self):
        """Generate and display a Gantt chart for completed orders."""
        completed_orders = self.order_manager.processor.completed_orders
        if not completed_orders:
            # If no orders have been completed, show an information popup
            messagebox.showinfo("Info", "No completed orders to display")
            return

        task_data = []
        for order in completed_orders:
            # Convert timestamps using the actual current time
            start_time = datetime.fromtimestamp(order.actual_start_time)
            end_time = datetime.fromtimestamp(order.actual_end_time)

            # Append order details to task_data
            task_data.append({
                "Order": f"Order {order.order_id}",
                "Start": start_time,
                "End": end_time,
                "Table": order.table_number,
                "Dishes": ", ".join(order.dishes)
            })
        # Convert task data to a pandas DataFrame for visualization
        df = pd.DataFrame(task_data)

        # Use Plotly to generate a timeline (Gantt chart)
        fig = px.timeline(
            df,
            x_start="Start",
            x_end="End",
            y="Order",
            color="Table",
            title="Order Processing Timeline",
            labels={"Order": "Order ID", "Table": "Table Number"},
            hover_data=["Dishes"]
        )
        fig.show()  # Display the Gantt chart


# Main entry point
if __name__ == "__main__":
    root = tk.Tk()
    app = OrderSchedulingGUI(root)
    root.mainloop()