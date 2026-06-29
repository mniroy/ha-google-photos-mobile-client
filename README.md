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
Because this add-on uses the mobile API, you need to intercept the authentication token from an Android device or emulator.
- Use a tool like [HTTP Toolkit](https://httptoolkit.com/) to intercept traffic on an Android device or emulator.
- Open the Google Photos app.
- Look for a request to `photos.googleapis.com` or similar.
- Find the authentication headers (or the specific `auth_data` payload). (Follow the instructions in the original reverse-engineered python library for more specifics on obtaining this string).

### 2. Add-on Settings
Go to the **Configuration** tab of the add-on in Home Assistant.

- **`auth_data`**: Paste the auth data string you obtained above.
- **`path`**: Set the path to the folder containing your media inside Home Assistant (e.g., `/media/photos`). Make sure the folder exists.
- **`album`**: (Optional) Type an album name to upload photos to. Leave empty for no album, or type `AUTO` to automatically use the folder names as album names.
- **`recursive`**: Switch ON if you want to upload photos from sub-folders within the path.
- **`delete_from_host`**: Switch ON to automatically delete the local file after it has been successfully uploaded.

## Monitoring

Once started, the add-on provides logs in the **Log** tab of the add-on page.
It also creates a sensor in Home Assistant: `sensor.gpmc_status`. This sensor will report the current upload progress (e.g., "Uploading 150/1000", "Idle", "Completed", etc.). You can use this sensor in your dashboards to monitor the upload state.
