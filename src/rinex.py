import subprocess
import threading
import os
import serial
from datetime import datetime
import requests
import dropbox
import math
import firebase_admin
from firebase_admin import credentials, db
import tkinter as tk
from tkinter import font
import time

# PPLS
cred = credentials.Certificate(
    "/home/ronny/gps-geodesi/asset/ppls-shift-firebase-adminsdk-61y26-a26269269d.json"
)
firebase_admin.initialize_app(
    cred,
    {
        "databaseURL": "https://ppls-shift-default-rtdb.asia-southeast1.firebasedatabase.app/"  # Replace with your database URL
    },
)

# Configuration parameters
device_port = "/dev/ttyGPS"
baud_rate = "115200"
output_raw_file = "/home/ronny/gps-geodesi/output.ubx"
output_rinex_file = "/home/ronny/gps-geodesi/output.obs"
output_rinex_file_nav = "/home/ronny/gps-geodesi/output.nav"

ref = db.reference("Realtime")
data = ref.child("base").get()
NTRIP_SERVER = data["ntrip"]
# NTRIP_SERVER = "ntrips://:792eke@caster.emlid.com:2101/MP17657"
# DROPBOX PARAMETER
auth_code = "tydj37Ufg54AAAAAAAAAf8-wu05VAM_49_4-jKINzi8"
redirect_uri = "http://localhost:8080/"
app_key = "aarre6i5rftqn5i"
app_secret = "rpyy84iee1grtod"
refresh_token = "aPyJmpqx6k4AAAAAAAAAAWDX6ZTPoe-vp65ZVp67ZQhX1fZA5wRaeRr3zK6sZOkV"


def geodetic_to_ecef(lat, lon, alt):
    # WGS84 constants
    a = 6378137.0  # Semi-major axis in meters
    f = 1 / 298.257223563  # Flattening
    e2 = f * (2 - f)  # Square of eccentricity

    # Convert latitude and longitude to radians
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    # Prime vertical radius of curvature
    N = a / math.sqrt(1 - e2 * math.sin(lat_rad) ** 2)

    # ECEF coordinates
    X = (N + alt) * math.cos(lat_rad) * math.cos(lon_rad)
    Y = (N + alt) * math.cos(lat_rad) * math.sin(lon_rad)
    Z = (N * (1 - e2) + alt) * math.sin(lat_rad)

    return X, Y, Z


def to_ubx_bytes(value):
    return int(value).to_bytes(4, byteorder="little", signed=True)


def send_ubx_message(ser, message):
    ser.write(message)
    print(f"Sent: {message.hex()}")


def collect_raw_data(duration, ntrip):
    """
    Collect raw GNSS data from ZED-F9P using RTKLIB's str2str.
    """
    print("Collecting raw data from ZED-F9P...")
    str2str_command = [
        f"str2str",
        "-in",
        f"{device_port}",
        "-out",
        ntrip,
        "-out",
        f"file://{output_raw_file}",
        "-msg",
        "1003,1004,1005,1011,1012,1019,1020,1045,1044,1046,1074,1084,1094,1124,1077,1087,1097,1127",
    ]

    try:
        subprocess.run(str2str_command, check=True, timeout=duration)
        print(f"Raw data collected in file: {output_raw_file}")
    except subprocess.TimeoutExpired:
        print(
            f"Data collection timed out after {duration} seconds. Proceeding with the program..."
        )
    # except TimeoutError as e:
    #     pass
    except subprocess.CalledProcessError as e:
        print(f"Error during raw data collection: {e}")
    #     exit(1)


def convert_to_rinex():
    """
    Convert raw GNSS data to RINEX observation file using RTKLIB's convbin.
    """
    print("Converting raw data to RINEX format...")
    convbin_command = [
        "convbin",
        "-v",
        "2.11",
        "-o",
        f"{output_rinex_file}",
        "-f",
        "1",
        "-f",
        "2",
        f"{output_raw_file}",
        "-r",
        "rtcm3",
    ]

    try:
        subprocess.run(convbin_command, check=True)
        print(f"RINEX observation file created: {output_rinex_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error during RINEX conversion: {e}")
        exit(1)


def convert_to_rinex2():
    """
    Convert raw GNSS data to RINEX observation file using RTKLIB's convbin.
    """
    print("Converting raw data to RINEX format...")
    convbin_command = [
        "convbin",
        "-v",
        "2.11",
        "-n",
        f"{output_rinex_file_nav}",
        "-f",
        "1",
        "-f",
        "2",
        f"{output_raw_file}",
    ]

    try:
        subprocess.run(convbin_command, check=True)
        print(f"RINEX observation file created: {output_rinex_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error during RINEX conversion: {e}")
        exit(1)


def upload_file_to_dropbox(file_path, dropbox_path, access_token):
    # Connect to Dropbox
    dbx = dropbox.Dropbox(access_token)

    # Open the file in read mode
    with open(file_path, "rb") as file:
        # Upload and overwrite the file in the specified Dropbox path
        dbx.files_upload(
            file.read(), dropbox_path, mode=dropbox.files.WriteMode("overwrite")
        )
        print(f"{file_path} has been updated in Dropbox at {dropbox_path}")


def get_access_and_refresh_token(auth_code, redirect_uri, app_key, app_secret):
    token_url = "https://api.dropbox.com/oauth2/token"

    response = requests.post(
        token_url,
        data={
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        auth=(app_key, app_secret),
    )

    if response.status_code == 200:
        tokens = response.json()
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        print("Access token:", access_token)
        print("Refresh token:", refresh_token)
        return access_token, refresh_token
    else:
        print("Failed to get tokens:", response.json())
        return None, None


def get_access_token_from_refresh_token(refresh_token, app_key, app_secret):
    # Dropbox OAuth 2.0 token URL
    token_url = "https://api.dropbox.com/oauth2/token"

    # Send a POST request to get a new access token
    response = requests.post(
        token_url,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(app_key, app_secret),  # Use app credentials for basic auth
    )

    if response.status_code == 200:
        access_token = response.json().get("access_token")
        print("New Access Token:", access_token)
        return access_token
    else:
        print("Failed to refresh access token:", response.json())
        return None


def start_gui():
    # Function to update data in the grid
    # Replace this with the actual data-fetching logic
    time.sleep(15)

    def update_data():
        # Sample data for demonstration purposes
        while True:
            ref = db.reference("Realtime")
            data = ref.child("base").get()
            latitude = float(data["lat"])
            longitude = float(data["long"])
            altitude = float(data["alt"])
            status = f"{data['status']}"
            q = 0
            ns = 0
            # ser =initialize_serial_connection(device_port,115200)
            # lat,lon,alt,q,ns = read_and_parse_serial_data(ser)
            data = [
                [f"{latitude}", f"{q}"],
                [f"{longitude}", f"{ns}"],
                [f"{altitude}", f"{status}"],
            ]
            data_name = [
                ["Latitude", "Quality"],
                ["Longitude", "Number of Satellite"],
                ["Altitude", "Status"],
            ]

            for i in range(3):
                for j in range(2):
                    data_labels[i][j]["name"].config(text=data_name[i][j])
                    data_labels[i][j]["value"].config(text=data[i][j])

            # Schedule the next update
            time.sleep(1)

    # Initialize the main tkinter window
    root = tk.Tk()
    root.title("BASE GPS-PPLS")
    root.geometry("480x320")  # Set resolution to match the 3.5" LCD
    root.configure(bg="black")  # Optional background color

    # Create a grid of labels with sections for name and value
    data_labels = []
    label_font = font.Font(family="Helvetica", size=14, weight="bold")
    value_font = font.Font(family="Helvetica", size=12)

    for i in range(3):
        row = []
        for j in range(2):
            frame = tk.Frame(root, bg="black", relief="ridge", bd=2)
            frame.grid(row=i, column=j, padx=5, pady=5, sticky="nsew")

            name_label = tk.Label(
                frame, text="", font=label_font, fg="black", bg="white", anchor="center"
            )
            name_label.pack(fill="x", padx=5, pady=2)

            value_label = tk.Label(
                frame, text="", font=value_font, fg="white", bg="black", anchor="center"
            )
            value_label.pack(fill="x", padx=5, pady=2)

            row.append({"name": name_label, "value": value_label})
        data_labels.append(row)

    # Make the grid cells expand proportionally
    for i in range(3):
        root.grid_rowconfigure(i, weight=1)
    for j in range(2):
        root.grid_columnconfigure(j, weight=1)
    threading.Thread(target=update_data, daemon=True).start()
    root.mainloop()


def start_base():
    run_status = 0
    ref = db.reference(f"/Realtime/base/")
    data = {f"request": 0}
    ref.update(data)
    while True:
        now = datetime.now()
        minute = now.strftime("%M")
        ref = db.reference("Realtime")
        data = ref.child("base").get()
        callout = data["request"]
        if callout == 1:
            ref = db.reference(f"/Realtime/base/")
            data = {f"status": "Standby...."}
            ref.update(data)
            if minute == "00" or minute == "15" or minute == "30" or minute == "45":
                run_status = 1
            else:
                run_status = 0
            if run_status == 1:
                ref = db.reference(f"/Realtime/base/")
                data = {f"status": "Setting Up"}
                ref.update(data)
                ref = db.reference("Realtime")
                data = ref.child("base").get()
                NTRIP_SERVER = data["ntrip"]
                interval = data["Interval"]
                # interval = 15
                duration = 60 * (interval - 3)  # Time in seconds
                # print(duration)
                # ecef_coordinates = geodetic_to_ecef(latitude, longitude, altitude)
                # print(f"ECEF Coordinates: X={ecef_coordinates[0]} Y={ecef_coordinates[1]} Z={ecef_coordinates[2]}")
                # X, Y, Z = ecef_coordinates
                # ubx_payload = b'\x06\x71\x1C\x00' + to_ubx_bytes(X) + to_ubx_bytes(Y) + to_ubx_bytes(Z)
                # ck_a = sum(ubx_payload) & 0xFF
                # ck_b = (sum(ubx_payload) >> 8) & 0xFF
                # ubx_message = b'\xB5\x62' + ubx_payload + bytes([ck_a, ck_b])
                # print(f"UBX Message: {ubx_message.hex()}")
                # with serial.Serial(device_port, 115200, timeout=2) as ser:
                #     ser.write(ubx_message)
                #     print("Fixed base coordinates sent to the receiver.")
                with serial.Serial(device_port, 115200, timeout=2) as ser:
                    send_ubx_message(
                        ser, b"\xb5\x62\x06\x02\x03\x00\x02\x15\x01\x21\x91"
                    )
                    send_ubx_message(
                        ser, b"\xb5\x62\x06\x01\x03\x00\x02\x13\x01\x1f\x97"
                    )
                now = datetime.now()
                tanggal = now.strftime("%d-%m-%Y_%H:%M")
                str1 = now.strftime("%d%m")
                str2 = now.strftime("%H%M")
                str3 = now.strftime("%Y")
                filename = f"BSLP_{str1}_{str2}_{str3}.obs"
                filename_nav = f"BSLP_{str1}_{str2}_{str3}.nav"
                ref = db.reference(f"/Realtime/base/")
                data = {f"status": "Running...."}
                ref.update(data)
                collect_raw_data(duration, NTRIP_SERVER)
                # Convert the raw data to RINEX format
                ref = db.reference(f"/Realtime/base/")
                data = {f"status": "Converting...."}
                convert_to_rinex()
                convert_to_rinex2()
                new_access_token = get_access_token_from_refresh_token(
                    refresh_token, app_key, app_secret
                )
                local_file_path = "/home/ronny/gps-geodesi/output.obs"
                local_file_path_nav = (
                    "/home/ronny/gps-geodesi/output.nav"  # Path to your local .txt file
                )
                dropbox_destination_path = f"/GPS ZED-F9P/Base/{filename}"
                dropbox_destination_path_nav = f"/GPS ZED-F9P/Base/{filename_nav}"  # Path in Dropbox where you want to upload
                ref = db.reference(f"/Realtime/base/")
                data = {f"status": "Uploading...."}
                upload_file_to_dropbox(
                    local_file_path, dropbox_destination_path, new_access_token
                )
                upload_file_to_dropbox(
                    local_file_path_nav, dropbox_destination_path_nav, new_access_token
                )
                print("Success Send to Dropbox")
                ref = db.reference(f"/Realtime/base")
                data = {
                    f"obs": dropbox_destination_path,
                    f"obnavs": dropbox_destination_path_nav,
                }
                ref.update(data)
                ref = db.reference(f"/Realtime/base/Storage/obs")
                data = {f"{tanggal}": dropbox_destination_path}
                ref.update(data)

                ref = db.reference(f"/Realtime/base/Storage/nav")
                data = {f"{tanggal}": dropbox_destination_path_nav}
                ref.update(data)
                run_status = 0
                ref = db.reference(f"/Realtime/base/")
                data = {f"request": 0}
                ref.update(data)
        else:
            ref = db.reference(f"/Realtime/base/")
            data = {f"status": "Waiting...."}
            ref.update(data)
        time.sleep(10)

def initialize_gui():
    root_window = tk.Tk()
    # Setup GUI, ect.
    root_window.mainloop()


# Main execution
if __name__ == "__main__":
    while True:
        try:
            # time.sleep(5)
            print("Starting Base....")
            base_thread = threading.Thread(target=start_base)
            gui_thread = threading.Thread(target=start_gui)
            base_thread.start()
            print("Base System Started!")
            time.sleep(5)
            print("GUI Initialize....")
            gui_thread.start()
            base_thread.join()
            # start_gui()
        except KeyboardInterrupt:
            print("KeyboardInterrupt detected. Exiting...")
            break

        except Exception as e:
            print("Exception occurred:", e)
            print("Trying to restarting system")
            time.sleep(2)
