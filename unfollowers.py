"""
Unfollowers
-----------
Parses followers.html and following.html from an Instagram data export
and surfaces two things:

  1. Don't follow you back  - accounts you follow that don't follow back.
  2. Quietly unfollowed you - accounts that were following you, that you
     never followed back, and have since stopped following you.

Non-follower states:
  active       - currently not following you back
  new          - first time detected this run
  removed      - you unfollowed them (kept as a record)
  follows_back - they followed you back (greyed out, link disabled)

Usage:
    python unfollowers.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# ===========================================================================
# Parsing
# ===========================================================================

class HrefExtractor(HTMLParser):
    """Collect every href attribute value from an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, Optional[str]]]
    ) -> None:
        for name, value in attrs:
            if name == "href" and value:
                self.hrefs.append(value)


def extract_instagram_profile_urls(html: str) -> set[str]:
    """
    Return the set of Instagram profile URLs found in an HTML export file.
    Normalizes the _u/ path variant used in following.html exports so that
    followers and following URLs can be compared correctly as a set.
    """
    extractor = HrefExtractor()
    extractor.feed(html)
    urls: set[str] = set()
    for url in extractor.hrefs:
        if "instagram.com/" not in url:
            continue
        url = url.rstrip("/")
        # Normalize _u/ variant present in following exports
        url = url.replace("instagram.com/_u/", "instagram.com/")
        if url.count("/") >= 3:
            urls.add(url)
    return urls


def load_html_file(path: str) -> str:
    """Read an HTML file, tolerating encoding issues."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ===========================================================================
# Storage
# ===========================================================================

def load_registry(path: Path) -> dict[str, str]:
    """
    Load a URL registry from disk.

    File format - one entry per line:
        <url>|<status>

    Returns a dict mapping url -> status.
    """
    if not path.exists():
        return {}
    registry: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 1)
            url = parts[0].strip()
            status = parts[1].strip() if len(parts) == 2 else "active"
            if url:
                registry[url] = status
    return registry


def save_registry(path: Path, registry: dict[str, str]) -> None:
    """Persist a URL registry (sorted by URL)."""
    with open(path, "w", encoding="utf-8") as fh:
        for url in sorted(registry.keys()):
            fh.write(f"{url}|{registry[url]}\n")


def load_url_set(path: Path) -> set[str]:
    """Load a plain set of URLs from disk (one per line)."""
    if not path.exists():
        return set()
    with open(path, "r", encoding="utf-8") as fh:
        return {line.strip() for line in fh if line.strip()}


def save_url_set(path: Path, urls: set[str]) -> None:
    """Persist a set of URLs to disk (sorted, one per line)."""
    with open(path, "w", encoding="utf-8") as fh:
        for url in sorted(urls):
            fh.write(url + "\n")


def save_last_run_timestamp(base_dir: Path) -> str:
    """Write the current datetime to last_run.txt and return the formatted string."""
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    (base_dir / "last_run.txt").write_text(timestamp, encoding="utf-8")
    return timestamp


def load_last_run_timestamp(base_dir: Path) -> Optional[str]:
    """Read the last run timestamp, or None if not found."""
    path = base_dir / "last_run.txt"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None


# ===========================================================================
# Core logic
# ===========================================================================

def username_from_url(url: str) -> str:
    """Extract the Instagram handle from a profile URL."""
    return url.rstrip("/").split("/")[-1]


def run_analysis(
    followers_path: str,
    following_path: str,
    base_dir: Path,
) -> dict:
    """
    Full analysis pass against the two export files.

    Non-follower statuses:
        active       - currently not following you back
        removed      - you unfollowed them (no longer in your following)
        follows_back - they started following you back

    Returns a dict with keys:
        non_followers       list[{url, username, status, is_new}]
        quietly_unfollowed  list[{url, username, status}]
        total_active_nf     int  (active non-followers only)
        total_quietly       int
        new_non_followers   int
    """
    followers_html = load_html_file(followers_path)
    following_html = load_html_file(following_path)

    current_followers = extract_instagram_profile_urls(followers_html)
    current_following = extract_instagram_profile_urls(following_html)

    if not current_followers and not current_following:
        raise ValueError(
            "No Instagram profile URLs were found in either file.\n\n"
            "Make sure you selected followers.html and following.html "
            "from your Instagram data export (Settings > Your activity > "
            "Download your information)."
        )
    if not current_following:
        raise ValueError(
            "No Instagram profile URLs were found in the following file.\n\n"
            "The file may be empty or in an unexpected format."
        )
    if not current_followers:
        raise ValueError(
            "No Instagram profile URLs were found in the followers file.\n\n"
            "The file may be empty or in an unexpected format."
        )

    # -- Non-followers -------------------------------------------------------
    current_non_followers = current_following - current_followers

    # Load registry - migrate from old plain-text file if needed
    registry_path = base_dir / "non_followers_registry.txt"
    if not registry_path.exists() and (base_dir / "non_followers.txt").exists():
        old_urls = load_url_set(base_dir / "non_followers.txt")
        nf_registry = {url: "active" for url in old_urls}
    else:
        nf_registry = load_registry(registry_path)

    new_non_followers: set[str] = set()

    # Add newly detected non-followers
    for url in current_non_followers:
        prev = nf_registry.get(url)
        if prev is None or prev in ("removed", "follows_back"):
            nf_registry[url] = "active"
            new_non_followers.add(url)
        # already active - stays active, not new

    # Update entries that are no longer current non-followers
    for url, status in list(nf_registry.items()):
        if url in current_non_followers:
            continue  # handled above

        if status == "active":
            if url in current_followers:
                # They followed you back
                nf_registry[url] = "follows_back"
            else:
                # No longer in your following - you unfollowed them
                nf_registry[url] = "removed"

        elif status == "follows_back" and url not in current_followers:
            # They stopped following you again AND you're not following them
            nf_registry[url] = "removed"

        # removed stays removed unless they're back in current_non_followers (handled above)

    save_registry(registry_path, nf_registry)

    nf_results = sorted(
        [
            {
                "url": url,
                "username": username_from_url(url),
                "status": status,
                "is_new": url in new_non_followers,
            }
            for url, status in nf_registry.items()
        ],
        key=lambda r: r["username"].lower(),
    )

    # -- Quietly unfollowed --------------------------------------------------
    previous_followers = load_url_set(base_dir / "previous_followers.txt")
    quietly_registry = load_registry(base_dir / "quietly_unfollowed.txt")

    if previous_followers:
        dropped_followers = previous_followers - current_followers
        newly_quiet = dropped_followers - current_following
        for url in newly_quiet:
            if url not in quietly_registry:
                quietly_registry[url] = "active"

    for url in list(quietly_registry.keys()):
        if url in current_followers:
            quietly_registry[url] = "returned"
        elif quietly_registry.get(url) == "returned":
            quietly_registry[url] = "active"

    save_registry(base_dir / "quietly_unfollowed.txt", quietly_registry)
    save_url_set(base_dir / "previous_followers.txt", current_followers)

    quietly_results = sorted(
        [
            {
                "url": url,
                "username": username_from_url(url),
                "status": status,
            }
            for url, status in quietly_registry.items()
        ],
        key=lambda r: r["username"].lower(),
    )

    return {
        "non_followers": nf_results,
        "quietly_unfollowed": quietly_results,
        "total_active_nf": sum(1 for r in nf_results if r["status"] == "active"),
        "total_quietly": len(quietly_results),
        "new_non_followers": len(new_non_followers),
    }


# ===========================================================================
# HTML report
# ===========================================================================

_REPORT_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f7f7f7; color: #111;
    padding: 40px 20px 60px;
}
.container { max-width: 1020px; margin: 0 auto; }
h1 { font-size: 1.6rem; font-weight: 800; margin-bottom: 4px; letter-spacing: -0.5px; }
.run-meta { color: #999; font-size: 0.82rem; margin-bottom: 32px; }
.columns { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }
@media (max-width: 700px) { .columns { grid-template-columns: 1fr; } }
h2 { font-size: 0.9rem; font-weight: 700; text-transform: uppercase;
     letter-spacing: 0.06em; color: #555; margin-bottom: 4px; }
.section-meta { color: #aaa; font-size: 0.8rem; margin-bottom: 14px; }
.badge {
    display: inline-block; font-size: 0.62rem; font-weight: 700;
    letter-spacing: 0.05em; text-transform: uppercase;
    border-radius: 4px; padding: 2px 6px; margin-left: 8px;
    vertical-align: middle; position: relative; top: -1px;
}
.badge-new      { background: #e1306c; color: #fff; }
.badge-removed  { background: #888; color: #fff; }
ul { list-style: none; }
li {
    display: flex; align-items: center;
    background: #fff; border: 1px solid #e8e8e8;
    border-radius: 8px; padding: 10px 14px;
    margin-bottom: 6px; transition: box-shadow 0.12s;
}
li:hover { box-shadow: 0 2px 10px rgba(0,0,0,0.07); }
li a { font-weight: 600; font-size: 0.9rem; color: #0095f6;
       text-decoration: none; flex: 1; }
li a:hover { text-decoration: underline; }
li a::before, .dim-name::before { content: "@"; opacity: 0.35; margin-right: 1px; }
.dim-name { flex: 1; font-weight: 600; font-size: 0.9rem; color: #ccc; }
.dim-note { font-size: 0.72rem; color: #ccc; margin-left: 8px; font-style: italic; }
.empty { color: #bbb; font-size: 0.88rem; padding: 24px 0; text-align: center; }
"""


def write_html_report(data: dict, output_path: Path) -> None:
    """Generate a two-column styled HTML report."""
    run_time = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    nf = data["non_followers"]
    new_count = data["new_non_followers"]
    nf_meta = f"{data['total_active_nf']} not following back"
    if new_count:
        nf_meta += f" &nbsp;|&nbsp; {new_count} new"

    def nf_row(r: dict) -> str:
        status = r["status"]
        if status == "follows_back":
            return (
                f'<li><span class="dim-name">{r["username"]}</span>'
                f'<span class="dim-note">follows back</span></li>'
            )
        badge = ""
        if r["is_new"]:
            badge = '<span class="badge badge-new">New</span>'
        elif status == "removed":
            badge = '<span class="badge badge-removed">Removed</span>'
        return (
            f'<li><a href="{r["url"]}" target="_blank" rel="noopener">'
            f'{r["username"]}</a>{badge}</li>'
        )

    if nf:
        nf_html = "<ul>\n" + "\n".join(nf_row(r) for r in nf) + "\n</ul>"
    else:
        nf_html = '<p class="empty">Everyone follows you back.</p>'

    qu = data["quietly_unfollowed"]

    def qu_row(r: dict) -> str:
        if r["status"] == "returned":
            return (
                f'<li><span class="dim-name">{r["username"]}</span>'
                f'<span class="dim-note">following again</span></li>'
            )
        return (
            f'<li><a href="{r["url"]}" target="_blank" rel="noopener">'
            f'{r["username"]}</a></li>'
        )

    if qu:
        qu_html = "<ul>\n" + "\n".join(qu_row(r) for r in qu) + "\n</ul>"
    else:
        qu_html = '<p class="empty">None recorded yet.</p>'

    html = (
        f'<!DOCTYPE html>\n'
        f'<html lang="en">\n'
        f'<head>\n'
        f'  <meta charset="utf-8">\n'
        f'  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'  <title>Unfollowers Report</title>\n'
        f'  <style>{_REPORT_CSS}</style>\n'
        f'</head>\n'
        f'<body>\n'
        f'<div class="container">\n'
        f'  <h1>Unfollowers</h1>\n'
        f'  <p class="run-meta">Run on {run_time}</p>\n'
        f'  <div class="columns">\n'
        f'    <div>\n'
        f'      <h2>Don\'t follow you back</h2>\n'
        f'      <p class="section-meta">{nf_meta}</p>\n'
        f'      {nf_html}\n'
        f'    </div>\n'
        f'    <div>\n'
        f'      <h2>Quietly unfollowed you</h2>\n'
        f'      <p class="section-meta">{data["total_quietly"]} recorded</p>\n'
        f'      {qu_html}\n'
        f'    </div>\n'
        f'  </div>\n'
        f'</div>\n'
        f'</body>\n'
        f'</html>\n'
    )

    output_path.write_text(html, encoding="utf-8")


def open_file_or_url(target: str) -> None:
    """Open a local file path or a URL in the system default application."""
    if sys.platform == "win32":
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.call(["open", target])
    else:
        subprocess.run(["xdg-open", target])


# ===========================================================================
# GUI
# ===========================================================================

class UnfollowersApp:
    """Main application window."""

    _PAD = {"padx": 10, "pady": 6}
    _MIN_W = 860
    _MIN_H = 540

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Unfollowers")
        self.root.minsize(self._MIN_W, self._MIN_H)
        self.root.resizable(True, True)

        # State
        self._followers_var = tk.StringVar()
        self._following_var = tk.StringVar()
        self._status_var = tk.StringVar(value="Choose both files, then click Run.")
        self._last_run_var = tk.StringVar(value="Last run: never")
        self._nf_filter_var = tk.StringVar()
        self._qu_filter_var = tk.StringVar()
        self._new_only_var = tk.BooleanVar(value=False)
        self._nf_count_var = tk.StringVar(value="")
        self._qu_count_var = tk.StringVar(value="")
        self._nf_results: list[dict] = []
        self._qu_results: list[dict] = []
        self._report_path: Optional[Path] = None
        self._active_ctx_tree: Optional[ttk.Treeview] = None
        self._nf_sort_asc = True
        self._qu_sort_asc = True

        # Traces
        self._nf_filter_var.trace_add("write", self._apply_nf_filter)
        self._qu_filter_var.trace_add("write", self._apply_qu_filter)
        self._new_only_var.trace_add("write", self._apply_nf_filter)

        self._build_ui()
        self._load_last_run_from_disk()
        self._center_window()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        # File pickers
        picker_frame = ttk.LabelFrame(root, text="Instagram Export Files", padding=10)
        picker_frame.grid(row=0, column=0, sticky="ew", **self._PAD)
        picker_frame.columnconfigure(1, weight=1)

        ttk.Label(picker_frame, text="Followers file:").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(picker_frame, textvariable=self._followers_var, width=48).grid(
            row=0, column=1, padx=(8, 4), sticky="ew"
        )
        ttk.Button(
            picker_frame, text="Browse...", command=self._browse_followers
        ).grid(row=0, column=2)

        ttk.Label(picker_frame, text="Following file:").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Entry(picker_frame, textvariable=self._following_var, width=48).grid(
            row=1, column=1, padx=(8, 4), pady=(6, 0), sticky="ew"
        )
        ttk.Button(
            picker_frame, text="Browse...", command=self._browse_following
        ).grid(row=1, column=2, pady=(6, 0))

        # Toolbar
        toolbar = ttk.Frame(root)
        toolbar.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 2))

        self._run_btn = ttk.Button(toolbar, text="Run", command=self._run, width=10)
        self._run_btn.pack(side="left")

        self._report_btn = ttk.Button(
            toolbar, text="Open Report", command=self._open_report, state="disabled"
        )
        self._report_btn.pack(side="left", padx=(8, 0))

        ttk.Button(
            toolbar, text="How To", command=self._show_instructions
        ).pack(side="right")
        ttk.Label(
            toolbar, textvariable=self._last_run_var,
            foreground="#aaa", font=("TkDefaultFont", 9)
        ).pack(side="right", padx=(0, 16))

        # Status bar
        ttk.Label(
            root, textvariable=self._status_var, foreground="#555"
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 4))

        # Split pane
        paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        paned.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))

        left_frame = ttk.Frame(paned)
        right_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        paned.add(right_frame, weight=1)

        self._build_nf_panel(left_frame)
        self._build_qu_panel(right_frame)

        # Shared context menu
        self._ctx_menu = tk.Menu(root, tearoff=0)
        self._ctx_menu.add_command(
            label="Open profile in browser", command=self._ctx_open_profile
        )
        self._ctx_menu.add_command(
            label="Copy username", command=self._ctx_copy_username
        )

    def _build_nf_panel(self, parent: ttk.Frame) -> None:
        """Left panel - Don't follow you back."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        hdr = ttk.Frame(parent)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(
            hdr, text="Don't follow you back",
            font=("TkDefaultFont", 10, "bold")
        ).pack(side="left")
        ttk.Label(
            hdr, textvariable=self._nf_count_var,
            foreground="#999", font=("TkDefaultFont", 9)
        ).pack(side="left", padx=(8, 0))

        frow = ttk.Frame(parent)
        frow.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        ttk.Entry(frow, textvariable=self._nf_filter_var, width=22).pack(side="left")
        ttk.Checkbutton(
            frow, text="New only", variable=self._new_only_var
        ).pack(side="left", padx=(10, 0))

        lf = ttk.Frame(parent)
        lf.grid(row=2, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)

        self._nf_tree = ttk.Treeview(
            lf, columns=("username", "status"),
            show="headings", selectmode="browse"
        )
        self._nf_tree.heading(
            "username", text="Username",
            command=lambda: self._toggle_sort(self._nf_tree, "nf")
        )
        self._nf_tree.heading("status", text="")
        self._nf_tree.column("username", stretch=True)
        self._nf_tree.column("status", width=90, anchor="center", stretch=False)

        # Tags for non-follower states
        self._nf_tree.tag_configure("follows_back", foreground="#bbb")

        sb = ttk.Scrollbar(lf, orient="vertical", command=self._nf_tree.yview)
        self._nf_tree.configure(yscrollcommand=sb.set)
        self._nf_tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self._nf_tree.bind("<Double-1>", lambda _: self._open_selected(self._nf_tree))
        self._nf_tree.bind("<Button-3>", lambda e: self._show_ctx(e, self._nf_tree))

    def _build_qu_panel(self, parent: ttk.Frame) -> None:
        """Right panel - Quietly unfollowed you."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        hdr = ttk.Frame(parent)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(
            hdr, text="Quietly unfollowed you",
            font=("TkDefaultFont", 10, "bold")
        ).pack(side="left")
        ttk.Label(
            hdr, textvariable=self._qu_count_var,
            foreground="#999", font=("TkDefaultFont", 9)
        ).pack(side="left", padx=(8, 0))

        frow = ttk.Frame(parent)
        frow.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        ttk.Entry(frow, textvariable=self._qu_filter_var, width=22).pack(side="left")

        lf = ttk.Frame(parent)
        lf.grid(row=2, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)

        self._qu_tree = ttk.Treeview(
            lf, columns=("username", "note"),
            show="headings", selectmode="browse"
        )
        self._qu_tree.heading(
            "username", text="Username",
            command=lambda: self._toggle_sort(self._qu_tree, "qu")
        )
        self._qu_tree.heading("note", text="")
        self._qu_tree.column("username", stretch=True)
        self._qu_tree.column("note", width=110, anchor="center", stretch=False)

        self._qu_tree.tag_configure("returned", foreground="#bbb")

        sb = ttk.Scrollbar(lf, orient="vertical", command=self._qu_tree.yview)
        self._qu_tree.configure(yscrollcommand=sb.set)
        self._qu_tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self._qu_tree.bind("<Double-1>", lambda _: self._open_selected(self._qu_tree))
        self._qu_tree.bind("<Button-3>", lambda e: self._show_ctx(e, self._qu_tree))

    def _center_window(self) -> None:
        self.root.update_idletasks()
        w = max(self.root.winfo_width(), self._MIN_W)
        h = max(self.root.winfo_height(), self._MIN_H)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # -----------------------------------------------------------------------
    # File browsing + last run
    # -----------------------------------------------------------------------

    def _browse_followers(self) -> None:
        path = filedialog.askopenfilename(
            title="Select followers.html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
        )
        if path:
            self._followers_var.set(path)

    def _browse_following(self) -> None:
        path = filedialog.askopenfilename(
            title="Select following.html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
        )
        if path:
            self._following_var.set(path)

    def _load_last_run_from_disk(self) -> None:
        data_dir = Path(__file__).parent / "data"
        ts = load_last_run_timestamp(data_dir)
        self._last_run_var.set(f"Last run: {ts}" if ts else "Last run: never")

    # -----------------------------------------------------------------------
    # Run
    # -----------------------------------------------------------------------

    def _run(self) -> None:
        followers = self._followers_var.get().strip()
        following = self._following_var.get().strip()

        if not followers or not following:
            messagebox.showerror(
                "Missing files",
                "Please select both a followers file and a following file.",
            )
            return

        self._run_btn.configure(state="disabled")
        self._report_btn.configure(state="disabled")
        self._status_var.set("Processing...")
        self._clear_trees()

        threading.Thread(
            target=self._run_worker,
            args=(followers, following),
            daemon=True,
        ).start()

    def _run_worker(self, followers: str, following: str) -> None:
        """Runs in a background thread - never touches tkinter widgets directly."""
        try:
            base_dir = Path(__file__).parent / "data"
            base_dir.mkdir(exist_ok=True)
            data = run_analysis(followers, following, base_dir)
            report_path = base_dir / "unfollowers.html"
            write_html_report(data, report_path)
            timestamp = save_last_run_timestamp(base_dir)
            self.root.after(0, self._on_run_success, data, report_path, timestamp)
        except (OSError, ValueError) as exc:
            self.root.after(0, self._on_run_error, str(exc))

    def _on_run_success(
        self, data: dict, report_path: Path, timestamp: str
    ) -> None:
        self._nf_results = data["non_followers"]
        self._qu_results = data["quietly_unfollowed"]
        self._report_path = report_path

        parts = [f"{data['total_active_nf']} not following you back"]
        if data["new_non_followers"]:
            parts.append(f"{data['new_non_followers']} new")
        if data["total_quietly"]:
            parts.append(f"{data['total_quietly']} quietly unfollowed")
        self._status_var.set("  |  ".join(parts))
        self._last_run_var.set(f"Last run: {timestamp}")

        self._apply_nf_filter()
        self._apply_qu_filter()
        self._run_btn.configure(state="normal")
        self._report_btn.configure(state="normal")

    def _on_run_error(self, message: str) -> None:
        messagebox.showerror("Error", message)
        self._status_var.set("Error - see dialog for details.")
        self._run_btn.configure(state="normal")

    # -----------------------------------------------------------------------
    # Results display
    # -----------------------------------------------------------------------

    def _clear_trees(self) -> None:
        for tree in (self._nf_tree, self._qu_tree):
            for item in tree.get_children():
                tree.delete(item)
        self._nf_count_var.set("")
        self._qu_count_var.set("")

    def _apply_nf_filter(self, *_) -> None:
        query = self._nf_filter_var.get().lower().strip()
        new_only = self._new_only_var.get()
        for item in self._nf_tree.get_children():
            self._nf_tree.delete(item)

        shown = 0
        for r in self._nf_results:
            if new_only and not r["is_new"]:
                continue
            if query and query not in r["username"].lower():
                continue

            status = r["status"]
            is_new = r["is_new"]

            if status == "follows_back":
                label = "Follows back"
                tag = "follows_back"
                iid = f"follows_back:{r['url']}"
            elif is_new:
                label = "New"
                tag = ""
                iid = r["url"]
            elif status == "removed":
                label = "Removed"
                tag = ""
                iid = r["url"]
            else:
                label = ""
                tag = ""
                iid = r["url"]

            self._nf_tree.insert(
                "", "end", iid=iid,
                values=(r["username"], label),
                tags=(tag,) if tag else ()
            )
            shown += 1

        total = len(self._nf_results)
        self._nf_count_var.set(
            f"({shown} of {total})" if shown != total else f"({total})"
        )

    def _apply_qu_filter(self, *_) -> None:
        query = self._qu_filter_var.get().lower().strip()
        for item in self._qu_tree.get_children():
            self._qu_tree.delete(item)

        shown = 0
        for r in self._qu_results:
            if query and query not in r["username"].lower():
                continue
            is_returned = r["status"] == "returned"
            note = "following again" if is_returned else ""
            iid = f"returned:{r['url']}" if is_returned else r["url"]
            self._qu_tree.insert(
                "", "end", iid=iid,
                values=(r["username"], note),
                tags=("returned",) if is_returned else ()
            )
            shown += 1

        total = len(self._qu_results)
        self._qu_count_var.set(
            f"({shown} of {total})" if shown != total else f"({total})"
        )

    # -----------------------------------------------------------------------
    # Sorting
    # -----------------------------------------------------------------------

    def _toggle_sort(self, tree: ttk.Treeview, key: str) -> None:
        asc = self._nf_sort_asc if key == "nf" else self._qu_sort_asc
        items = [
            (tree.set(iid, "username"), iid)
            for iid in tree.get_children()
        ]
        items.sort(key=lambda x: x[0].lower(), reverse=not asc)
        for index, (_, iid) in enumerate(items):
            tree.move(iid, "", index)
        if key == "nf":
            self._nf_sort_asc = not asc
        else:
            self._qu_sort_asc = not asc

    # -----------------------------------------------------------------------
    # Interactions
    # -----------------------------------------------------------------------

    def _open_selected(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            return
        iid = selection[0]
        # Prefixed iids are disabled - link not clickable
        if ":" in iid and iid.split(":")[0] in ("follows_back", "returned"):
            return
        open_file_or_url(iid)

    def _show_ctx(self, event: tk.Event, tree: ttk.Treeview) -> None:
        row = tree.identify_row(event.y)
        if not row:
            return
        tree.selection_set(row)
        self._active_ctx_tree = tree
        self._ctx_menu.tk_popup(event.x_root, event.y_root)

    def _ctx_open_profile(self) -> None:
        if self._active_ctx_tree:
            self._open_selected(self._active_ctx_tree)

    def _ctx_copy_username(self) -> None:
        if not self._active_ctx_tree:
            return
        selection = self._active_ctx_tree.selection()
        if not selection:
            return
        username = self._active_ctx_tree.item(selection[0], "values")[0]
        self.root.clipboard_clear()
        self.root.clipboard_append(username)

    def _open_report(self) -> None:
        if self._report_path and self._report_path.exists():
            open_file_or_url(str(self._report_path))
        else:
            messagebox.showinfo(
                "No report yet", "Run the app first to generate a report."
            )

    # -----------------------------------------------------------------------
    # Instructions
    # -----------------------------------------------------------------------

    def _show_instructions(self) -> None:
        messagebox.showinfo(
            "How to use",
            "Step 1 - Request your Instagram data:\n"
            "  Open Instagram > Settings > Your activity >\n"
            "  Download your information.\n"
            "  Choose HTML format and submit the request.\n"
            "  Instagram will email you a download link\n"
            "  (can take up to 48 hours).\n\n"
            "Step 2 - Locate your files:\n"
            "  Unzip the archive Instagram sends you.\n"
            "  Open the 'connections' folder inside.\n"
            "  You need: followers.html and following.html\n\n"
            "Step 3 - Run:\n"
            "  Browse for each file above, then click Run.\n\n"
            "Left panel - Don't follow you back:\n"
            "  New         - first time detected this run\n"
            "  Removed     - you unfollowed them\n"
            "  Follows back - they followed you back (greyed)\n\n"
            "Right panel - Quietly unfollowed you:\n"
            "  Active entries followed you, you never followed\n"
            "  back, and they have since left.\n"
            "  Following again - they came back (greyed)\n\n"
            "Tips:\n"
            "  Double-click any active row to open that profile.\n"
            "  Right-click a row to copy the username.\n"
            "  All data is saved in the data/ folder next to the script.",
        )

    # -----------------------------------------------------------------------
    # Entry point
    # -----------------------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    app = UnfollowersApp()
    app.run()
