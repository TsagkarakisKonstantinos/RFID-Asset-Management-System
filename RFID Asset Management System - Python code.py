import serial
import threading
import tkinter as tk
from tkinter import messagebox, Menu
import os
import sys
import time
import mysql.connector


# Check the password of the intro screen
def check_password():
    correct_password = 'test'
    entered_password = password_entry.get()

    if entered_password == correct_password:
        # Destroy the intro window if the correct password is entered
        intro_window.destroy()
        # Set the flag to indicate the correct password is entered
        password_correct.set(True)
    else:
        messagebox.showerror("Incorrect Password", "Please enter the correct password.")


# Create the intro window
intro_window = tk.Tk()
intro_window.title("RFID Management System - Login Screen")
intro_window.geometry("400x150")

intro_label = tk.Label(intro_window, text="Please enter the correct password to continue:")
intro_label.pack(pady=10)

password_entry = tk.Entry(intro_window, show="*", width=20)
password_entry.pack(pady=5)

submit_button = tk.Button(intro_window, text="Submit", command=check_password)
submit_button.pack(pady=10)

# Create a BooleanVar to store whether the correct password is entered
password_correct = tk.BooleanVar()

# Start the intro window main event loop
intro_window.mainloop()


# mySQL Database connection parameters
host = "localhost"
user = "kotsos"
password = "kotsospro99"
database = "rfid_management_system"

# Attempt to establish a connection to the database
connection = mysql.connector.connect(
    host=host,
    user=user,
    password=password,
    database=database
)

# Create a cursor to interact with the database
cursor = connection.cursor()


# Define the serial port and baud rate for communication with Arduino
serial_port = 'COM3'
baud_rate = 115200

# Fetch com_port and room values from the com_port_mapping database table
com_port_mapping = {}

cursor.execute("SELECT com_port, room FROM com_port_mapping")

for com_port, room in cursor.fetchall():
    com_port_mapping[com_port] = room

com_port = serial_port
room = com_port_mapping.get(com_port)


# Connect to Arduino through serial port
arduino = serial.Serial(serial_port, baud_rate)

# Event to signal when to stop reading data from Arduino
stop_event = threading.Event()

# Minimum interval (in seconds) between consecutive transfers of the same tag between listboxes
min_transfer_interval = 3

# Dictionary to track timestamps of tag transfers
last_transfer_times = {}

# Global variables to store the last detected tag and the timer object
last_detected_tag = None
last_detection_timer = None

# Global variable to store the timer identifier
last_detection_timer_id = ""
is_timer_active = False

# Create a variable to store the last detected data
last_detected_data = ""


# Define different tag color configurations (for different RSSI levels)
listbox_tag_configurations = {
    "green": {"foreground": "black", "background": "green"},
    "yellow": {"foreground": "black", "background": "yellow"},
    "orange": {"foreground": "black", "background": "orange"},
    "red": {"foreground": "black", "background": "red"},
    "black": {"foreground": "black", "background": "white"},
}


data_thread = None  # Declare data_thread as a global variable at the module level


# Start the data reading thread (button: Start)
def start_data_reading():
    # Start receiving data from the Arduino.
    start_button.config(state=tk.DISABLED)
    stop_event.clear()
    global data_thread
    data_thread = threading.Thread(target=data_reading)
    data_thread.start()


# Handle program exit and clean up resources. (button: Exit)
def on_exit():
    confirm = messagebox.askokcancel("Exit Confirmation", "Are you sure you want to exit?")
    if confirm:
        root.destroy()
        stop_event.set()
        arduino.close()
        # Wait for the data thread to finish (if running)
        if 'data_thread' in globals() and data_thread is not None and data_thread.is_alive():
            data_thread.join()
        # Close the database connection
        connection.close()
        sys.exit()


# Read data from the Arduino and update the GUI accordingly.
def data_reading():
    global last_detected_tag, last_detection_timer_id, is_timer_active, room, last_detected_data

    while not stop_event.is_set():
        data = arduino.readline().decode().strip()
        data = data.split(",")
        data = [d.strip() for d in data]

        # Check if the data list is empty
        if not data:
            continue  # Continue to read the next data

        last_detected_data = ', '.join(data)  # Save the last detected data as a string

        if len(data) >= 2:
            rssi = int(data[0])
            tag_value = data[1]

            # Update the gui with the received tags
            update_gui(tag_value, rfids_listbox3)

            # Call the update_listbox4 function to update the data reading console with the detected tag data
            update_listbox4()

            # Call the check_rssi function to handle RSSI-based automatic tag transfers and font color configuration
            check_rssi(rssi, tag_value)

            # Reset the timer whenever a tag is detected
            if is_timer_active:
                root.after_cancel(last_detection_timer_id)
            start_no_tag_timer()  # Start the new timer for no tag detection

            # Update the last detected tag
            last_detected_tag = tag_value


# Update the listbox4 data console with detected arduino data.
def update_listbox4():
    global last_detected_data
    if last_detected_data:
        rfids_listbox4.insert(tk.END, last_detected_data)
        rfids_listbox4.see(tk.END)  # Scroll to the bottom to show new data


# Update the GUI with RFID data and add it to the appropriate listbox and database table.
def update_gui(data, listbox):
    global room
    # Check if the tag is in the 'all_tags' table
    select_query = "SELECT * FROM all_tags WHERE tag = %s"
    cursor.execute(select_query, (data,))
    row = cursor.fetchone()

    if row:
        # If the tag exists in the table, get its ID from the table
        tag_id = row[0]

        # Check if the data is already in the listbox to avoid duplicates
        if not any(data in item for item in listbox.get(0, tk.END)):
            # Check if the tag exists in the 'inside_tags' database table
            inside_query = "SELECT * FROM inside_tags WHERE tag = %s"
            cursor.execute(inside_query, (data, ))
            inside_row = cursor.fetchone()

            if inside_row is not None:
                # Only insert if the tag is in the "correct" room
                if inside_row[1] == selected_room:
                    listbox.insert(tk.END, f"{data} - tag{tag_id} detected. From Reader: {com_port}")
            else:
                # Tag is not inside the correct room, so check if it's in the 'outside_tags' table
                outside_query = "SELECT * FROM outside_tags WHERE tag = %s"
                cursor.execute(outside_query, (data,))
                outside_row = cursor.fetchone()

                if outside_row is None:
                    # Since the tag is not inside and not already in the 'outside_tags' table, insert it to outside
                    insert_outside_query = "INSERT INTO outside_tags (tag) VALUES (%s)"
                    cursor.execute(insert_outside_query, (data,))
                    connection.commit()

                    listbox.insert(tk.END, f"{data} - tag{tag_id} detected. From Reader: {com_port}")
                elif outside_row is not None:
                    listbox.insert(tk.END, f"{data} - tag{tag_id} detected. From Reader: {com_port}")

    else:
        # If the tag is new, add it to the 'all_tags' table
        insert_query = "INSERT INTO all_tags (tag) VALUES (%s)"
        values = (data,)
        cursor.execute(insert_query, values)
        connection.commit()

        # Fetch the newly inserted row to get its ID
        cursor.execute(select_query, (data,))
        row = cursor.fetchone()
        tag_id = row[0]

        # Check if the tag exists in the 'inside_tags' database table
        inside_query = "SELECT * FROM inside_tags WHERE tag = %s"
        cursor.execute(inside_query, (data,))
        inside_row = cursor.fetchone()

        if inside_row is not None:
            # Only insert if the tag is in the "correct" room
            if inside_row[1] == selected_room:
                listbox.insert(tk.END, f"{data} - tag{tag_id} detected. From Reader: {com_port}")
        else:
            # Tag is not inside the "correct" room, so check if it's in the 'outside_tags' table
            outside_query = "SELECT * FROM outside_tags WHERE tag = %s"
            cursor.execute(outside_query, (data,))
            outside_row = cursor.fetchone()

            if outside_row is None:
                # Since the tag is not inside and not already in the 'outside_tags' table, insert it to outside
                insert_outside_query = "INSERT INTO outside_tags (tag) VALUES (%s)"
                cursor.execute(insert_outside_query, (data,))
                connection.commit()

                listbox.insert(tk.END, f"{data} - tag{tag_id} registered. From Reader: {com_port}")
            elif outside_row is not None:
                listbox.insert(tk.END, f"{data} - tag{tag_id} detected. From Reader: {com_port}")

    # Ensure the listbox scrolls to the last item
    listbox.yview(tk.END)
    # Update the listboxes to reflect the changes
    update_listboxes()


# Update the GUI listboxes to always display the current RFID data.
def update_listboxes():
    global selected_room, room

    # Clear the listboxes
    rfids_listbox1.delete(0, tk.END)
    rfids_listbox2.delete(0, tk.END)

    # Fetch data from the 'all_tags' table
    select_query = "SELECT * FROM all_tags"
    cursor.execute(select_query)
    all_tags_data = cursor.fetchall()

    # Initialize counters for each room
    room1_count = 0
    room2_count = 0
    room3_count = 0

    # Update the listboxes with the fetched data
    for row in all_tags_data:
        tag_id = row[0]
        tag_value = row[1]

        # Check if the tag exists in the 'inside_tags' database table
        inside_query = "SELECT * FROM inside_tags WHERE tag = %s"
        cursor.execute(inside_query, (tag_value,))
        inside_row = cursor.fetchone()

        if inside_row:
            inside_tag, inside_room = inside_row[0], inside_row[1]

            if inside_room == "ROOM1":
                room1_count += 1
            elif inside_room == "ROOM2":
                room2_count += 1
            elif inside_room == "ROOM3":
                room3_count += 1

            if inside_room == selected_room:
                # Display the tag in rfids_listbox2 if room matches selected_room
                rfids_listbox2.insert(tk.END, f"{tag_value} - tag{tag_id}")

        else:
            # Check if the tag is in 'outside_tags' table
            outside_query = "SELECT * FROM outside_tags WHERE tag = %s"
            cursor.execute(outside_query, (tag_value,))
            outside_row = cursor.fetchone()

            if outside_row:
                # Display the tag in the outside tags listbox
                rfids_listbox1.insert(tk.END, f"{tag_value} - tag{tag_id}")

                # Increment the counters based on the tag's room
                outside_room_query = "SELECT room FROM inside_tags WHERE tag = %s"
                cursor.execute(outside_room_query, (tag_value,))
                outside_room = cursor.fetchone()

                if outside_room == "ROOM1":
                    room1_count += 1
                elif outside_room == "ROOM2":
                    room2_count += 1
                elif outside_room == "ROOM3":
                    room3_count += 1

    # Update the room counters text label
    room1_tags_label.config(text=f"ROOM 1: {room1_count} tags")
    room2_tags_label.config(text=f"ROOM 2: {room2_count} tags")
    room3_tags_label.config(text=f"ROOM 3: {room3_count} tags")


# Check the RSSI value of a detected tag and transfer it to the other listbox if criteria is met, with its updated font.
def check_rssi(rssi, tag_value):
    global last_transfer_times, room
    font_color = None

    if tag_value is None:
        return

    # Check if the tag_value exists in the 'outside_tags' database table
    outside_query = "SELECT * FROM outside_tags WHERE tag = %s"
    cursor.execute(outside_query, (tag_value,))
    outside_row = cursor.fetchone()

    # Get the current font color of the tag in the listbox
    tag_listbox = rfids_listbox1 if outside_row is not None else rfids_listbox2

    # Fetch the tag_id from the 'all_tags' table in the database
    cursor.execute("SELECT tag_id FROM all_tags WHERE tag = %s", (tag_value,))
    result = cursor.fetchone()
    if result:
        tag_id = result[0]
    else:
        tag_id = None

    # Find the index of the tag in the listbox based on the tag_value and tag_id
    if tag_id is not None:
        try:
            tag_index = tag_listbox.get(0, tk.END).index(f"{tag_value} - tag{tag_id}")
        except ValueError:
            tag_index = None
    else:
        tag_index = None

    current_font_color = font_color

    # Only update the font color in the listbox if it's different from the current color
    if font_color != current_font_color and room == selected_room and tag_index is not None:
        tag_listbox.itemconfig(tag_index, background=font_color)

    if rssi >= -45:
        font_color = "green"

        current_time = time.monotonic()
        transfer_time = last_transfer_times.get(tag_value, 0)

        # Check if enough time has passed since the last transfer of this tag
        if current_time - transfer_time >= min_transfer_interval:
            # Check if the tag exists in the 'inside_tags' database table with a specific room
            inside_query = "SELECT * FROM inside_tags WHERE tag = %s AND room = %s"
            cursor.execute(inside_query, (tag_value, room))
            inside_row = cursor.fetchone()
            if inside_row is not None:
                inside_row_room = inside_row[1]
            else:
                inside_row_room = None

            # Check if the tag_value exists in the 'outside_tags' database table
            outside_query = "SELECT * FROM outside_tags WHERE tag = %s"
            cursor.execute(outside_query, (tag_value,))
            outside_row = cursor.fetchone()

            # Perform the transfer based on the presence of the tag in the database tables
            if inside_row:
                # Transferring from inside to outside
                delete_query = "DELETE FROM inside_tags WHERE tag = %s"
                cursor.execute(delete_query, (tag_value,))
                connection.commit()

                insert_query = "INSERT INTO outside_tags (tag) VALUES (%s)"
                cursor.execute(insert_query, (tag_value,))
                connection.commit()

            elif outside_row:
                # Transferring from outside to inside
                delete_query = "DELETE FROM outside_tags WHERE tag = %s"
                cursor.execute(delete_query, (tag_value,))
                connection.commit()

                insert_query = "INSERT INTO inside_tags (tag, room) VALUES (%s, %s)"
                cursor.execute(insert_query, (tag_value, room))
                connection.commit()

            if inside_row_room != room and outside_row is None:
                log_transfer_info(tag_value, 10)  # 10 assigned for room mismatch
            else:
                log_transfer_info(tag_value, rssi)

            # Update the last transferred tag timestamp
            last_transfer_times[tag_value] = current_time

            update_listboxes()

    elif rssi >= -50:
        font_color = "yellow"
    elif rssi >= -55:
        font_color = "orange"
    elif rssi >= -60:
        font_color = "red"
    elif rssi < -60:
        font_color = "black"

    # Check if the tag_value exists in the 'outside_tags' database table
    outside_query = "SELECT * FROM outside_tags WHERE tag = %s"
    cursor.execute(outside_query, (tag_value,))
    outside_row = cursor.fetchone()

    # Check if the tag_value exists in the 'inside_tags' database table
    inside_query = "SELECT * FROM inside_tags WHERE tag = %s"
    cursor.execute(inside_query, (tag_value,))
    inside_row = cursor.fetchone()

    tag_listbox = rfids_listbox1 if outside_row is not None else rfids_listbox2

    # Fetch the tag_id from the 'all_tags' table in the database
    cursor.execute("SELECT tag_id FROM all_tags WHERE tag = %s", (tag_value,))
    result = cursor.fetchone()
    if result:
        tag_id = result[0]
    else:
        tag_id = None

    # Find the index of the tag in the listbox based on the tag_value and tag_id
    if tag_id is not None:
        try:
            tag_index = tag_listbox.get(0, tk.END).index(f"{tag_value} - tag{tag_id}")
        except ValueError:
            tag_index = None
    else:
        tag_index = None

    # Only update the font color in the listbox if the tag is in the correct room and is visible in the listbox
    if inside_row is not None or room == selected_room:
        font_color = listbox_tag_configurations.get(font_color)
        if font_color and tag_index is not None:
            tag_listbox.itemconfig(tag_index, **font_color)
    elif outside_row is not None:
        font_color = listbox_tag_configurations.get(font_color)
        if font_color and tag_index is not None:
            tag_listbox.itemconfig(tag_index, **font_color)

    return


def log_transfer_info(tag_value, rssi):
    current_time = time.strftime("%H:%M:%S")
    # Fetch the tag_id from the 'all_tags' table in the database
    cursor.execute("SELECT tag_id FROM all_tags WHERE tag = %s", (tag_value,))
    result = cursor.fetchone()
    if result:
        tag_id = result[0]
    else:
        tag_id = None

    if rssi < 0:
        # Rssi value provided meaning it is an automatic transfer
        message = f"{current_time} - Transferring tag{tag_id} with RSSI: {rssi}"
        rfids_listbox3.insert(tk.END, message)
        rfids_listbox3.yview(tk.END)  # Scroll to the bottom of the listbox to show the latest message
    elif rssi == 0:
        # Rssi = 0 meaning it was called from the manual transfer tag function
        message = f"{current_time} - tag{tag_id} has been manually transferred."
        rfids_listbox3.insert(tk.END, message)
        rfids_listbox3.yview(tk.END)  # Scroll to the bottom of the listbox to show the latest message
    elif rssi == 10:
        # Called for room mismatch
        message = f"{current_time} - tag{tag_id} is inside another room, can't perform transfer."
        rfids_listbox3.insert(tk.END, message)
        rfids_listbox3.yview(tk.END)  # Scroll to the bottom of the listbox to show the latest message


# Timer for the no_tag_detected function
def start_no_tag_timer():
    global last_detection_timer_id, is_timer_active
    last_detection_timer_id = root.after(2000, no_tag_detected)  # 2sec = 2000ms
    is_timer_active = True


# Function to be called when no tag is detected for a set time
def no_tag_detected():
    global last_detection_timer_id, last_detected_tag, is_timer_active
    current_time = time.strftime("%H:%M:%S")

    # Reset the timer identifier
    last_detection_timer_id = ""

    if last_detected_tag is None:
        # The timer expired, but no tag has been detected during the interval
        pass
    else:
        # Change the font color of the last detected tag to black
        # Check if the tag_value exists in the 'outside_tags' database table
        outside_query = "SELECT * FROM outside_tags WHERE tag = %s"
        cursor.execute(outside_query, (last_detected_tag,))
        outside_row = cursor.fetchone()

        tag_listbox = rfids_listbox1 if outside_row is not None else rfids_listbox2

        try:
            # Fetch the tag_id from the 'all_tags' table in the database
            cursor.execute("SELECT tag_id FROM all_tags WHERE tag = %s", (last_detected_tag,))
            result = cursor.fetchone()
            if result:
                tag_id = result[0]
            else:
                tag_id = None

            if tag_id is not None:
                tag_index = tag_listbox.get(0, tk.END).index(f"{last_detected_tag} - tag{tag_id}")
                tag_listbox.itemconfig(tag_index, foreground="black", background="white")

        except ValueError:
            # Handle the case when the tag is not found in the listbox
            pass

    rfids_listbox3.insert(tk.END, f"{current_time} - No tag is being detected.")
    rfids_listbox3.yview(tk.END)  # Scroll to the bottom of the listbox to show the latest message
    # Reset the timer status flag
    is_timer_active = False


# Handle double-click event on listbox items and show RFID info in a message box.
def on_double_click(event):
    selected_listbox = None
    index = None
    # Determine the source listbox based on the selected item
    selection = rfids_listbox1.curselection()
    if selection:
        index = selection[0]
        selected_listbox = rfids_listbox1
    else:
        selection = rfids_listbox2.curselection()
        if selection:
            index = selection[0]
            selected_listbox = rfids_listbox2

    if selected_listbox is not None:
        selected_item = selected_listbox.get(index)
        rfid_value = selected_item.split(" - ")[0]
        rfid_tag_id = selected_item.split(" - ")[1]

        inside_query = "SELECT * FROM inside_tags WHERE tag = %s"
        cursor.execute(inside_query, (rfid_value,))
        inside_row = cursor.fetchone()

        # Determine the location based on the selected listbox
        if selected_listbox == rfids_listbox1:
            location = "Outside any room"
        else:
            location = inside_row[1]

        # Show a message box with the RFID value, tag id and location
        messagebox.showinfo("Tag Info", f"The selected RFID value is: {rfid_value}\nLocation: {location}\nWith tag id: {rfid_tag_id}")


# Manual Transfer of RFID tags between 'Inside the room' and 'Outside the room' listboxes.
def transfer_tag():
    global last_transfer_times

    selected_listbox = None
    destination_listbox = None
    index = None

    # Determine the source and destination listboxes based on the selected item
    selection = rfids_listbox1.curselection()
    if selection:
        index = selection[0]
        selected_listbox = rfids_listbox1
        destination_listbox = rfids_listbox2
    else:
        selection = rfids_listbox2.curselection()
        if selection:
            index = selection[0]
            selected_listbox = rfids_listbox2
            destination_listbox = rfids_listbox1

    if selected_listbox is None:
        # If no tag is selected, display a message in the GUI console
        messagebox.showinfo("Warning", "Please select a tag first.")
        return

    # Get the selected tag from the source listbox
    selected_tag = selected_listbox.get(index)

    if selected_tag not in last_transfer_times:
        last_transfer_times[selected_tag] = 0  # Assign 0 to indicate a manual transfer

    # Check if the selected tag has the expected format (tag_value - tagX)
    tag_parts = selected_tag.split(" - ")
    if len(tag_parts) == 2:
        tag_value, tag_id = tag_parts[0], tag_parts[1]

        # Update the destination listbox and remove the selected tag from the source listbox
        destination_listbox.insert(tk.END, selected_tag)
        selected_listbox.delete(index)

        # Check if the tag_value exists in the 'inside_tags' database table
        inside_query = "SELECT * FROM inside_tags WHERE tag = %s"
        cursor.execute(inside_query, (tag_value,))
        inside_row = cursor.fetchone()

        # Check if the tag_value exists in the 'outside_tags' database table
        outside_query = "SELECT * FROM outside_tags WHERE tag = %s"
        cursor.execute(outside_query, (tag_value,))
        outside_row = cursor.fetchone()

        # Perform the transfer based on the presence of the tag in the database tables
        if inside_row:
            # Delete the tag from inside_tags table
            delete_query = "DELETE FROM inside_tags WHERE tag = %s"
            cursor.execute(delete_query, (tag_value,))
            connection.commit()

            # Insert the tag into outside_tags table
            insert_query = "INSERT INTO outside_tags (tag) VALUES (%s)"
            cursor.execute(insert_query, (tag_value,))
            connection.commit()

            # Log the transfer in the "Data console" listbox
            log_transfer_info(tag_value, 0)

        elif outside_row:
            # Delete the tag from outside_tags table
            delete_query = "DELETE FROM outside_tags WHERE tag = %s"
            cursor.execute(delete_query, (tag_value,))
            connection.commit()

            # Insert the tag into inside_tags table with the correct room
            insert_query = "INSERT INTO inside_tags (tag, room) VALUES (%s, %s)"
            cursor.execute(insert_query, (tag_value, room))
            connection.commit()

            # Log the transfer in the "Data console" listbox
            log_transfer_info(tag_value, 0)

    # Update the listboxes to reflect the changes
    update_listboxes()


# Function to clear the cursor selection in the listboxes
def clear_selection():
    rfids_listbox1.selection_clear(0, tk.END)
    rfids_listbox2.selection_clear(0, tk.END)


# Function to remove all saved tags from listboxes and database tables.
def reset_tags():
    # Check if there are any tags in the listboxes
    cursor.execute("SELECT COUNT(*) FROM all_tags")
    result = cursor.fetchone()
    if result[0] == 0:
        messagebox.showinfo("No RFID Tags Detected", "There is no need to reset the tags.")
        return

    # Fetch the number of tags before the removal from the 'all_tags' table
    cursor.execute("SELECT COUNT(*) FROM all_tags")
    result = cursor.fetchone()
    tags_before_removal = result[0]

    # Display a confirmation dialog box to ask for user confirmation
    response = messagebox.askokcancel("Confirmation Warning", "Are you sure you want to reset all tags? This action cannot be undone.")
    if response:
        # Clear all database tables
        truncate_query = "TRUNCATE TABLE all_tags"
        cursor.execute(truncate_query)
        connection.commit()

        truncate_query = "TRUNCATE TABLE inside_tags"
        cursor.execute(truncate_query)
        connection.commit()

        truncate_query = "TRUNCATE TABLE outside_tags"
        cursor.execute(truncate_query)
        connection.commit()

        # Clear the listboxes
        rfids_listbox1.delete(0, tk.END)
        rfids_listbox2.delete(0, tk.END)
        rfids_listbox3.delete(0, tk.END)
        rfids_listbox4.delete(0, tk.END)

        # Update the listboxes to reflect the changes (show empty listboxes)
        update_listboxes()

        # Fetch the number of tags after the removal from the 'all_tags' table
        cursor.execute("SELECT COUNT(*) FROM all_tags")
        result = cursor.fetchone()
        tags_after_removal = tags_before_removal - result[0]

        # Log the removal of the tags in the "Data console" listbox
        current_time = time.strftime("%H:%M:%S")
        rfids_listbox3.insert(tk.END, f"{current_time} - Database tables and app GUI have been reset.")
        rfids_listbox3.insert(tk.END, f"{current_time} - Number of tags removed: {tags_after_removal}")
        rfids_listbox3.yview(tk.END)  # Scroll to the bottom of the listbox to show the latest message
    else:
        # If the user cancels the operation, do nothing
        pass


def on_room_selection(event):
    global selected_room
    selected_room = selected_room_var.get()

    if selected_room:
        message = f"{selected_room} has been selected from the dropdown menu."
        rfids_listbox3.insert(tk.END, message)
        rfids_listbox3.yview(tk.END)  # Scroll to the bottom of the listbox to show the latest message
        update_listboxes()


# Function to handle the About menu bar option
def show_about_info():
    messagebox.showinfo("About", "RFID Management System\nVersion 1.0\n© 2023 IHU\nDeveloped by Tsagkarakis Konstantinos and Iordanidis Xristos")


# Function to set up the menu bar
def setup_menu():
    global com_port, room
    menu_bar = Menu(root)

    # File menu
    file_menu = Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label="File", menu=file_menu)

    # View menu
    view_menu = Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label="View", menu=view_menu)
    # Add submenu items from the com_port_mapping dictionary
    # for com_port, room in com_port_mapping.items():
    #    view_menu.add_command(label=f"{com_port} - {room}")

    # Edit menu
    edit_menu = Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label="Edit", menu=edit_menu)
    # Settings menu
    settings_menu = Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label="Settings", menu=settings_menu)

    # Help menu
    help_menu = Menu(menu_bar, tearoff=0)
    help_menu.add_command(label="About", command=show_about_info)
    menu_bar.add_cascade(label="Help", menu=help_menu)

    # Exit menu
    exit_menu = tk.Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label="Exit", menu=exit_menu)
    exit_menu.add_command(label="Exit", command=on_exit)

    # Configure the root window to use the menu_bar
    root.config(menu=menu_bar)


# Check if the correct password was entered before proceeding to create the main GUI
if password_correct.get():
    # Setup for the main GUI window
    root = tk.Tk()
    setup_menu()

    # Labels and listboxes setup for the GUI
    # Outside Listbox
    header_label1 = tk.Label(root, text="Outside the room", font=("Helvetica", 16, "bold"))
    header_label1.grid(row=0, column=0, pady=(10, 5), sticky="w")

    rfids_listbox1 = tk.Listbox(root, width=15, height=10)
    rfids_listbox1.grid(row=1, column=0, padx=(10, 5), pady=5, sticky="nsew")

    scrollbar1 = tk.Scrollbar(root, command=rfids_listbox1.yview)
    scrollbar1.grid(row=1, column=0, sticky='nse')

    # Inside Listbox
    header_label2 = tk.Label(root, text="Inside the room", font=("Helvetica", 16, "bold"))
    header_label2.grid(row=0, column=1, pady=(10, 5), sticky="w")

    rfids_listbox2 = tk.Listbox(root, width=55, height=10)
    rfids_listbox2.grid(row=1, column=1, padx=(5, 10), pady=5, sticky="nsew")

    scrollbar2 = tk.Scrollbar(root, command=rfids_listbox2.yview)
    scrollbar2.grid(row=1, column=1, sticky='nse')

    # Create a label for viewing_room, port header
    viewing_room_label = tk.Label(root, text=f"(Selected reader {com_port} for: {room})", font=("Helvetica", 10, "italic"))
    viewing_room_label.grid(row=0, column=1, columnspan=2, padx=120)

    # Console listbox
    header_label3 = tk.Label(root, text="GUI Data console:", font=("Helvetica", 10, "bold"))
    header_label3.grid(row=2, column=0, pady=(10, 5), sticky="w")

    rfids_listbox3 = tk.Listbox(root, width=60, height=6)
    rfids_listbox3.grid(row=3, column=0, padx=(5, 10), pady=5, sticky="nsew")

    scrollbar3 = tk.Scrollbar(root, command=rfids_listbox3.yview)
    scrollbar3.grid(row=3, column=0, sticky='nse')

    # Data reading listbox
    header_label4 = tk.Label(root, text="Arduino detected tags:", font=("Helvetica", 10, "bold"))
    header_label4.grid(row=2, column=1, pady=(10, 5), sticky="w")

    rfids_listbox4 = tk.Listbox(root, width=55, height=6)
    rfids_listbox4.grid(row=3, column=1, padx=(5, 10), pady=5, sticky="nsew")

    scrollbar4 = tk.Scrollbar(root, command=rfids_listbox4.yview)
    scrollbar4.grid(row=3, column=1, sticky='nse')

    rfids_listbox1.configure(yscrollcommand=scrollbar1.set)
    rfids_listbox2.configure(yscrollcommand=scrollbar2.set)
    rfids_listbox3.configure(yscrollcommand=scrollbar3.set)
    rfids_listbox4.configure(yscrollcommand=scrollbar4.set)

    root.columnconfigure(0, weight=1)
    root.columnconfigure(1, weight=1)

    # GUI Buttons config
    exit_button = tk.Button(root, text="Exit", command=on_exit, height=1, width=4, fg="red")
    exit_button.grid(row=4, column=1, pady=(10, 10), padx=100)

    start_button = tk.Button(root, text="Start", command=start_data_reading, height=1, width=4, fg="green")
    start_button.grid(row=4, column=0, pady=(10, 10), padx=10)

    transfer_button = tk.Button(root, text="Transfer tag", command=transfer_tag, height=1, width=10, fg="purple")
    transfer_button.grid(row=3, column=2, pady=(50, 10), padx=(0, 100))

    clear_selection_button = tk.Button(root, text="Clear Cursor Selection", command=clear_selection, height=1, width=18, fg="blue")
    clear_selection_button.grid(row=3, column=2, pady=(0, 80), padx=(0, 0))

    reset_tags_button = tk.Button(root, text="Reset Tags", command=reset_tags, height=1, width=10, fg="brown")
    reset_tags_button.grid(row=3, column=2, pady=(50, 10), padx=(100, 0))

    # Initialize the selected_room variable with the default value
    selected_room = room
    # Create a variable to store the selected room
    selected_room_var = tk.StringVar(value=selected_room)

    # Dropdown menu to select the room
    room_label = tk.Label(root, text="Select Room to view:")
    room_label.grid(row=0, column=2, pady=(10, 5), padx=(0, 100))

    room_dropdown = tk.OptionMenu(root, selected_room_var, "ROOM1", "ROOM2", "ROOM3", command=on_room_selection)
    room_dropdown.grid(row=0, column=2, pady=(10, 5), padx=(110, 0))

    # Create label widgets to display the number of tags in each room
    room_counters_label = tk.Label(root, text="Room Counters", font=("Helvetica", 8, "bold"))
    room_counters_label.grid(row=1, column=2, padx=10, pady=(0, 40), sticky="w")

    room1_tags_label = tk.Label(root, text="ROOM 1: 0 tags")
    room1_tags_label.grid(row=1, column=2, padx=10, sticky="w")

    room2_tags_label = tk.Label(root, text="ROOM 2: 0 tags")
    room2_tags_label.grid(row=1, column=2, padx=10, pady=(40, 0), sticky="w")

    room3_tags_label = tk.Label(root, text="ROOM 3: 0 tags")
    room3_tags_label.grid(row=1, column=2, padx=10, pady=(80, 0), sticky="w")

    # GUI window config
    root.title("RFID Management System")
    root.geometry("1280x420")

    root.protocol("WM_DELETE_WINDOW", on_exit)
    rfids_listbox1.bind("<Double-Button-1>", on_double_click)
    rfids_listbox2.bind("<Double-Button-1>", on_double_click)

    # Call the update_listboxes function at the start of the program to populate the listboxes on each launch.
    update_listboxes()

    # Connected to sql database
    rfids_listbox3.insert(tk.END, f"Connected to mySQL database: {database}...")

    # Start the main GUI event loop
    root.mainloop()
