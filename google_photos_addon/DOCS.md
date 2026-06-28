# Google Photos Mobile Client Add-on

This add-on allows you to upload photos directly from your Home Assistant directories to Google Photos using the reverse-engineered mobile API.

## Setup Instructions

1. **Get Auth Data**: You need `auth_data` to authenticate with Google Photos. Follow the instructions on the [original repository](https://github.com/xob0t/google_photos_mobile_client?tab=readme-ov-file#auth_data-where-do-i-get-mine) to obtain your `auth_data`. It involves using HTTP Toolkit to intercept the auth token from your Android device.

2. **Configure Add-on**:
   - Go to the **Configuration** tab of this add-on in Home Assistant.
   - **`auth_data`**: Paste the auth data you obtained.
   - **`path`**: Set the path to the folder containing your media. (e.g., `/media/photos`). Ensure the folder exists.
   - **`album`**: (Optional) Type an album name to upload photos to. Leave empty for no album, or type `AUTO` to use folder names.
   - **`recursive`**: Switch ON if you want to upload photos from sub-folders as well.

3. **Start**: Click **Start** to begin the upload process.

4. **Monitor Progress**: Switch to the **Log** tab to see the upload progress.

## Note
The add-on will only upload files that are not already in your Google Photos account (skips duplicates).
