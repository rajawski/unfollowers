import re
from urllib.parse import urlparse
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import tkinter.messagebox


def extract_links(html_string):
    # Use a regular expression to search for links in the HTML
    link_regex = r'href="([^"]*)'
    # Find all the links in the HTML
    links = re.findall(link_regex, html_string)
    return links


def script(followers, following):
    if followers == None or following == None:
        tkinter.messagebox.showerror("Error", "Please choose both followers and following files.")
        return
    try:
        # Read the followers HTML file
        with open(followers, "r") as html_file:
            html_string = html_file.read()
    except:
        tkinter.messagebox.showerror("Error", "Followers file not found. Please choose a valid file.")
    else:
        # Extract the links from the HTML
        followers_links = set(extract_links(html_string))
        print('Followers link extracted into a set')
    try:
        # Read the following HTML file
        with open(following, "r") as html_file:
            html_string = html_file.read()
    except:
        tkinter.messagebox.showerror("Error", "Following file not found. Please choose a valid file.")
    else:
        # Extract the links from the HTML
        following_links = set(extract_links(html_string))
        print('Following link extracted into a set')

    # Finding people who don't follow you back
    new_non_followers = list(following_links.difference(followers_links))

    # Creating a text file to store people who don't follow you back
    if os.path.exists('non_followers.txt'):
        if os.path.getsize('non_followers.txt') == 0:
            print('Empty non followers file. Writing for the first time')
            with open("non_followers.txt", "w") as html_file:
                for item in new_non_followers:
                    html_file.write(item + "\n")
        else:
            print('Non followers file is not empty')
    else:
        with open("non_followers.txt", "w") as html_file:
            print('Non followers file is absent so created a blank one and writing for the first time')
            for item in new_non_followers:
                html_file.write(item + "\n")

    # loading old non followers to a list
    old_non_followers = []
    with open("non_followers.txt", "r") as html_file:
        for line in html_file:
            line = line.rstrip("\n")
            old_non_followers.append(line)

    # Construct the HTML output using a template
    html_template = """
    <html>
    <body>
    {links}
    </body>
    </html>
    """

    # Construct the list of links as HTML anchor elements
    link_elements = ""
    updated_non_followers = list(set(old_non_followers + new_non_followers))
    for link in updated_non_followers:
        if link in old_non_followers:
            handle = urlparse(link).path.split('/')[-1]
            link_elements += f'<a href="{link}">{handle}</a><br>'
        else:
            handle = urlparse(link).path.split('/')[-1]
            link_elements += f'<a href="{link}">{handle}</a>{" -------> New Unfollower"}<br>'

    # Updating the non followers file
    with open("non_followers.txt", "w") as html_file:
        for item in updated_non_followers:
            html_file.write(item + "\n")

    # Fill in the template with the constructed links
    html_output = html_template.format(links=link_elements)

    # Write the HTML output to the unfollowers file
    with open("unfollowers.html", "w") as html_file:
        print('Updating the unfollowers file')
        html_file.write(html_output)
    print("Done. Opening the unfollowers file now.")

    html_file = "unfollowers.html"
    # open the HTML file in the default browser
    if sys.platform == 'win32':  # For Windows
        os.startfile(html_file)
    elif sys.platform == "darwin":  # For mac
        subprocess.call(["open", html_file])
    else:
        subprocess.run(["xdg-open", html_file])  # For Linux


def run_script():
    followers = followers_entry.get()
    following = following_entry.get()
    script(followers, following)
    root.destroy()


def browse_followers():
    followers_path = filedialog.askopenfilename(initialdir="/", title="Select followers.html file",
                                                filetypes=(("HTML files", "*.html"), ("all files", "*.*")))
    followers_entry.delete(0, tk.END)
    followers_entry.insert(0, followers_path)


def browse_following():
    following_path = filedialog.askopenfilename(initialdir="/", title="Select following.html file",
                                                filetypes=(("HTML files", "*.html"), ("all files", "*.*")))
    following_entry.delete(0, tk.END)
    following_entry.insert(0, following_path)


def cancel():
    root.destroy()


def how_to():
    tkinter.messagebox.showinfo("Instructions",
                                "1. Select the file containing your followers\n2. Select the file containing the accounts you are following\n3. Click on 'Run' to find the unfollowers\n4. Click on 'Cancel' to exit the program\nNOTE: Request your Information from Instagram to get your followers.html and following.html files")


root = tk.Tk()
root.title("Instagram Unfollowers APP")

# Get the screen width and height
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

# Calculate the position of the window on the screen
x = (screen_width / 2) - (root.winfo_width() / 2)
y = (screen_height / 2) - (root.winfo_height() / 2)

# Set the position of the window
root.geometry("+%d+%d" % (x, y))

# Create the heading label
heading = ttk.Label(root, text="Run to find Unfollowers")
heading.grid(row=0, column=0, columnspan=3, padx=10, pady=10)

# Create a label and entry for the followers file
followers_label = ttk.Label(root, text="Followers File:")
followers_label.grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
followers_entry = ttk.Entry(root)
followers_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.E + tk.W)

# Create a button to browse for the followers file
browse_followers_button = ttk.Button(root, text="Browse", command=browse_followers)
browse_followers_button.grid(row=1, column=2, padx=5, pady=5)

# Create a label and entry for the following file
following_label = ttk.Label(root, text="Following File:")
following_label.grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
following_entry = ttk.Entry(root)
following_entry.grid(row=2, column=1, padx=5, pady=5, sticky=tk.E + tk.W)

# Create a button to browse for the following file
browse_following_button = ttk.Button(root, text="Browse", command=browse_following)
browse_following_button.grid(row=2, column=2, padx=5, pady=5)

# Create a button to run the script
run_button = ttk.Button(root, text="Run", command=run_script)
run_button.grid(row=3, column=0, columnspan=1, padx=5, pady=5, ipadx=20)

# Create a button to cancel the script
cancel_button = ttk.Button(root, text="Cancel", command=cancel)
cancel_button.grid(row=3, column=2, columnspan=2, padx=5, pady=5, ipadx=20)

# Create a button to open the how to instructions
how_to_button = ttk.Button(root, text="How to", command=how_to)
how_to_button.grid(row=3, column=1, padx=5, pady=5, ipadx=20)

# Align all the widgets in the center of the GUI
for child in root.winfo_children():
    child.grid_configure(padx=5, pady=5, ipadx=20)
    child.grid_columnconfigure(1, weight=1)

root.mainloop()
