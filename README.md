# Unfollowers

A lightweight desktop app for analysing your Instagram followers and following data. No login required, no internet connection, no third-party accounts. Everything runs locally on your machine.

---

## What it does

Unfollowers reads the HTML export files Instagram gives you and surfaces two panels side by side:

### Left panel - Don't follow you back

Everyone you are currently following who is not following you back. Entries have four possible states:

| State | Description |
|---|---|
| *(no label)* | Currently not following you back |
| **New** | First time detected this run |
| **Removed** | You unfollowed them - kept as a permanent record |
| **Follows back** | They followed you back - greyed out, link disabled |

- If you re-follow a "Removed" person and they still don't follow back, they return to active and are flagged as "New" again.
- If a "Follows back" entry stops following you and you are no longer following them, they move to "Removed".

### Right panel - Quietly unfollowed you

People who were following you, that you never followed back, and who have since stopped following you. These are remembered permanently even after they disappear from your Instagram export.

| State | Description |
|---|---|
| *(no label)* | Quietly unfollowed you |
| **Following again** | They came back - greyed out, link disabled |

---

## Requirements

- Python 3.9 or higher
- tkinter (included with the standard Python installer on Windows and macOS)

No pip packages are required. Everything used is part of the Python standard library.

### Checking your Python version

```bash
python --version
```

### tkinter on Linux

On some Linux distributions tkinter is not bundled with Python and must be installed separately:

```bash
# Debian / Ubuntu
sudo apt install python3-tk

# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

---

## Installation

No installation needed. Just download or clone this repository and run the script directly.

```bash
git clone https://github.com/yourname/unfollowers.git
cd unfollowers
python unfollowers.py
```

---

## How to get your Instagram data

Instagram lets you export your own data as HTML files. Here is how:

1. Open Instagram (web or mobile)
2. Go to **Settings** > **Your activity** > **Download your information**
3. Select **HTML** as the format (not JSON)
4. Choose the date range - "All time" is recommended
5. Tap or click **Request a download**
6. Instagram will email you a link when the archive is ready. This can take anywhere from a few minutes to 48 hours.
7. Download the archive from the link in the email and unzip it.

Inside the unzipped folder, open the **connections** subfolder. You will find two files you need:

- `followers.html`
- `following.html`

These are the two files the app asks you to select.

---

## Usage

1. Run the app: `python unfollowers.py`
2. Click **Browse...** next to "Followers file" and select your `followers.html`
3. Click **Browse...** next to "Following file" and select your `following.html`
4. Click **Run**

Results appear in two panels side by side. You can search within each panel and sort by username. The **Open Report** button opens a formatted HTML version of the results in your browser.

### Keyboard and mouse shortcuts

| Action | How |
|---|---|
| Open a profile | Double-click any active row |
| Copy a username | Right-click > Copy username |
| Open a profile (context menu) | Right-click > Open profile in browser |
| Sort a column | Click the column header |
| Resize panels | Drag the divider between the two panels |

---

## Data files

All data files are saved in a `data/` subfolder inside the Unfollowers project directory. They are never written into your Instagram export folder. The `data/` folder is created automatically on first run.

| File | Purpose |
|---|---|
| `non_followers_registry.txt` | Full history of non-followers with their current status. |
| `previous_followers.txt` | Snapshot of your followers from the last run. Used to detect the "Quietly unfollowed" category. |
| `quietly_unfollowed.txt` | Permanent record of accounts that quietly unfollowed you. |
| `last_run.txt` | Timestamp of the most recent run. Displayed in the app on startup. |
| `unfollowers.html` | Styled HTML report of the latest results. Opened by the "Open Report" button. |

---

## How "Quietly unfollowed" works

On each run the app compares your current followers list against the snapshot from the previous run. Anyone who dropped out of your followers, and who you were never following back, is added to the "Quietly unfollowed" registry.

They stay in the registry permanently. On future runs:

- If they start following you again, their row is greyed and marked "following again".
- If they stop following you again after that, they revert to active.
- They are never removed from the list automatically.

Because this comparison requires two runs, the right panel will be empty on the very first run. Run the app again after your next Instagram export and it will start populating.

---

## Privacy

Unfollowers never connects to the internet. It reads local files only. No data is sent anywhere. Your Instagram credentials are never used or requested.

---

## License

MIT License. See LICENSE for details.
