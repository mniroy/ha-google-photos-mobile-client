# Google Photos Mobile Client - Home Assistant Add-on

This project is a Home Assistant add-on that allows you to automatically upload photos and videos from your local Home Assistant directories (like `/media`) directly to Google Photos. It uses a reverse-engineered mobile API to bypass some limitations of the official Google Photos API.

## Features

- Background uploads directly from Home Assistant
- Support for auto-creating albums based on folder names
- Recursive folder uploads
- Skips already uploaded media (deduplication)
- Progress reporting via a Home Assistant sensor (`sensor.gpmc_status`)

## Installation

1. In Home Assistant, go to **Settings** > **Add-ons** > **Add-on Store**.
2. Click the three dots in the top right corner and select **Repositories**.
3. Add the URL to this GitHub repository.
4. Close the modal and you should see a new repository section at the bottom.
5. Click on **Google Photos Mobile Client** and click **Install**.

## Configuration

To use this add-on, you must provide your `auth_data` from an authenticated Google Photos Android app session.

### 1. Getting `auth_data`
Because this add-on uses the mobile API, you need to intercept the authentication token from an Android device or emulator. There are a few ways to do this:

**Option A: Using ADB (Android Debug Bridge)**
1. Connect your Android device to your computer via USB (ensure USB debugging is enabled) or use an emulator.
2. Open a terminal and run the following command to listen for the authentication log:
   - Linux/macOS: `adb logcat | grep "auth%2Fphotos.native"`
   - Windows: `adb logcat | FINDSTR "auth%2Fphotos.native"`
3. Open the Google Photos app on your device (you may need to clear its data and log in again, or use ReVanced Google Photos).
4. The terminal will output logs. Look for a string starting with `androidId=...`. Copy the entire string. This is your `auth_data`.

**Option B: Using HTTP Toolkit (Requires Root/Emulator)**
- Use a tool like [HTTP Toolkit](https://httptoolkit.com/) to intercept traffic on a rooted Android device or emulator.
- Open the Google Photos app.
- Look for a request to `photos.googleapis.com` or similar.
- Find the authentication headers (or the specific `auth_data` payload).

### 2. Add-on Settings
Go to the **Configuration** tab of the add-on in Home Assistant.

- **`auth_data`**: Paste the auth data string you obtained above.
- **`path`**: Set the path to the folder containing your media inside Home Assistant (e.g., `/media/photos`). Make sure the folder exists.
- **`album`**: (Optional) Type an album name to upload photos to. Leave empty for no album, or type `AUTO` to automatically use the folder names as album names.
- **`recursive`**: Switch ON if you want to upload photos from sub-folders within the path.
- **`delete_from_host`**: Switch ON to automatically delete the local file after it has been successfully uploaded.

## Connecting NAS as Home Assistant Media

To upload photos from your NAS, you first need to mount the NAS as a media source in Home Assistant:

1. In Home Assistant, go to **Settings** > **System** > **Storage**.
2. Click on **Add Network Storage**.
3. Configure the following:
   - **Name**: Give it a friendly name (e.g., `nas_photos`).
   - **Usage**: Select **Media**.
   - **Remote Share**: Enter the path to your NAS share (e.g., `192.168.1.100/photos`).
   - **Authentication**: Provide your NAS username and password if required.
4. Click **Save**.
5. Once mounted, you can configure the add-on `path` to point to the newly mounted media folder, typically located under `/media/nas_photos` (replace `nas_photos` with your chosen name).

## Monitoring

Once started, the add-on provides logs in the **Log** tab of the add-on page.
It also creates a sensor in Home Assistant: `sensor.gpmc_status`. This sensor will report the current upload progress (e.g., "Uploading 150/1000", "Idle", "Completed", etc.). You can use this sensor in your dashboards to monitor the upload state.
