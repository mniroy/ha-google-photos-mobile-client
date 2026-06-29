# Google Photos Mobile Client Add-on

This add-on allows you to upload photos directly from your Home Assistant directories to Google Photos using the reverse-engineered mobile API.

## Setup Instructions

1. **Get Auth Data**: You need `auth_data` to authenticate with Google Photos. 
   - **Using ADB**: Connect your Android device (with USB debugging enabled), open a terminal, and run `adb logcat | grep "auth%2Fphotos.native"` (or `FINDSTR` on Windows). Open Google Photos and log in. The terminal will output logs. Look for a string starting with `androidId=...` and copy the entire string.
   - **Using HTTP Toolkit**: Follow the instructions on the [original repository](https://github.com/xob0t/google_photos_mobile_client?tab=readme-ov-file#auth_data-where-do-i-get-mine) to use HTTP Toolkit to intercept the auth token from your Android device.

2. **Connect NAS (Optional)**: If you want to upload media from a NAS:
   - In Home Assistant, go to **Settings** > **System** > **Storage**.
   - Click **Add Network Storage** and choose **Media** as Usage.
   - Enter your NAS Remote Share path (e.g. `192.168.1.100/photos`) and Authentication details.
   - Note the chosen name (e.g., `nas_photos`). The path will be `/media/nas_photos`.

3. **Configure Add-on**:
   - Go to the **Configuration** tab of this add-on in Home Assistant.
   - **`auth_data`**: Paste the auth data you obtained.
   - **`path`**: Set the path to the folder containing your media (e.g., `/media/photos` or `/media/nas_photos`). Ensure the folder exists.
   - **`album`**: (Optional) Type an album name to upload photos to. Leave empty for no album, or type `AUTO` to use folder names.
   - **`recursive`**: Switch ON if you want to upload photos from sub-folders as well.

4. **Start**: Click **Start** to begin the upload process.

5. **Monitor Progress**: Switch to the **Log** tab to see the upload progress.

## Note
The add-on will only upload files that are not already in your Google Photos account (skips duplicates).
