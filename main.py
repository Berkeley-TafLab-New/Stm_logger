import serial
import csv
from datetime import datetime
import re
import threading
import sys
import time

COM_PORT = 'COM17'
BAUD_RATE = 115200
CSV_FILENAME = 'serial_log.csv'

# Expected CSV header based on your STM32 code
EXPECTED_HEADER = ['AccX', 'AccY', 'AccZ', 'GyroX', 'GyroY', 'GyroZ', 'Roll', 'Pitch', 'YawIMU',
                   'MagX', 'MagY', 'MagZ', 'Lat', 'Lon', 'Alt', 'Speed', 'Course', 'Sats',
                   'PDOP', 'HDOP', 'VDOP']

# Logging control variables
csv_message_count = 0
last_summary_time = time.time()

def is_numeric(s):
    """Check if string can be converted to float or int"""
    try:
        float(s)
        return True
    except ValueError:
        return False

def is_csv_data_line(line):
    """
    Determine if a line contains CSV sensor data
    """
    # Remove any leading/trailing whitespace and control characters
    cleaned_line = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', line.strip())
    
    # Skip obvious non-data lines
    if any(keyword in cleaned_line.lower() for keyword in 
           ['hello', 'error', 'system', 'baud', 'find', 'sensor', 'connection', 'boot', 
            'rudder', 'propeller', 'zero', 'unknown', 'command']):
        return False
    
    # Check if line looks like CSV data
    parts = cleaned_line.split(',')
    
    # Should have approximately the right number of fields
    if len(parts) < 15 or len(parts) > 25:
        return False
    
    # Most parts should be numeric
    numeric_count = sum(1 for part in parts if is_numeric(part.strip()))
    if numeric_count < len(parts) * 0.8:  # At least 80% should be numeric
        return False
    
    return True

def clean_csv_line(line):
    """
    Clean and extract CSV data from a line
    """
    # Remove control characters and clean the line
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', line.strip())
    
    # Split by comma and clean each part
    parts = [part.strip() for part in cleaned.split(',')]
    
    # Try to find the start of valid numeric data
    for i in range(len(parts)):
        candidate_parts = parts[i:]
        if len(candidate_parts) >= len(EXPECTED_HEADER):
            # Check if we have enough numeric values
            numeric_parts = []
            for j, part in enumerate(candidate_parts[:len(EXPECTED_HEADER)]):
                if is_numeric(part):
                    numeric_parts.append(part)
                else:
                    break
            
            if len(numeric_parts) >= len(EXPECTED_HEADER):
                return numeric_parts[:len(EXPECTED_HEADER)]
    
    return None

def command_sender(ser):
    """
    Thread function to handle user input and send commands to STM32
    """
    print("\n" + "="*60)
    print("COMMAND INTERFACE - Available commands:")
    print("  Rudder control: [ (left), ] (right)")
    print("  Propeller: f (forward), s (stop), 0 (reset)")
    print("  Other: hello, setzero, auto, nauto, setzerouart")
    print("  Type 'quit' to exit")
    print("="*60)
    
    while True:
        try:
            command = input("Enter command: ").strip()
            if command.lower() == 'quit':
                print("Exiting...")
                break
            elif command:
                # Send command with carriage return (as expected by STM32)
                ser.write((command + '\r').encode('utf-8'))
                print(f"[SENT] {command}")
        except KeyboardInterrupt:
            print("\nCommand interface stopped.")
            break
        except Exception as e:
            print(f"Error sending command: {e}")

def main():
    global csv_message_count, last_summary_time
    
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"Connected to {COM_PORT} at {BAUD_RATE} baud.")
        print("=" * 50)
        print("CSV data logging to file (summary every 15 seconds)")
        print("Debug messages shown below:")
        print("=" * 50)
    except Exception as e:
        print(f"Failed to open serial port: {e}")
        return

    header_written = False

    # Start command sender thread
    command_thread = threading.Thread(target=command_sender, args=(ser,), daemon=True)
    command_thread.start()

    with open(CSV_FILENAME, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)

        try:
            while True:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='replace').strip()

                    # Skip completely empty lines
                    if not line:
                        continue

                    # Check if this line contains the CSV header
                    if 'AccX,AccY,AccZ' in line and not header_written:
                        writer.writerow(['Timestamp'] + EXPECTED_HEADER)
                        header_written = True
                        print("[CSV Header detected and written to file]")
                        continue
                    
                    # Skip repeated headers
                    if 'AccX,AccY,AccZ' in line and header_written:
                        continue

                    # Check if this is CSV sensor data
                    if is_csv_data_line(line):
                        cleaned_data = clean_csv_line(line)
                        if cleaned_data:
                            timestamp = datetime.now()
                            writer.writerow([timestamp.isoformat()] + cleaned_data)
                            file.flush()  # Ensure data is written immediately
                            
                            csv_message_count += 1
                            
                            # Show summary every 15 seconds
                            current_time = time.time()
                            if current_time - last_summary_time >= 15:
                                print(f"[CSV] Received {csv_message_count} messages in the last 15 seconds")
                                csv_message_count = 0
                                last_summary_time = current_time
                        else:
                            print(f"[CSV Parse Error] {line}")
                    else:
                        # This is a debug/status/response message - show on console
                        print(f"[STM32] {line}")

        except KeyboardInterrupt:
            print("\n" + "=" * 50)
            print(f"Logging stopped by user. Final count: {csv_message_count} messages")
        except Exception as e:
            print(f"Error during logging: {e}")
        finally:
            ser.close()
            print("Serial port closed.")

if __name__ == '__main__':
    main()
