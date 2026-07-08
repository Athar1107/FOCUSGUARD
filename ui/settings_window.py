"""
settings_window.py
------------------
Standalone Tkinter settings editor for FocusGuard.
"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


class SettingsWindow:
    """Read, edit, and save FocusGuard config from a Tkinter window."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

    def open(self) -> None:
        with open(self._config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        root = tk.Tk()
        root.title("FocusGuard Settings")
        root.resizable(False, False)

        frame = ttk.Frame(root, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        idle_var = tk.IntVar(value=int(config.get("idle_threshold_seconds", 30)))
        confirmation_var = tk.IntVar(value=int(config.get("confirmation_window_secs", 120)))
        gaze_fps_var = tk.IntVar(value=int(config.get("gaze_fps", 5)))
        webcam_index_var = tk.IntVar(value=int(config.get("webcam_device_index", 0)))
        end_of_day_var = tk.StringVar(value=str(config.get("end_of_day_time", "17:30")))
        launch_var = tk.BooleanVar(value=bool(config.get("launch_at_startup", True)))

        ttk.Label(frame, text="Idle threshold (seconds):").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            frame, from_=10, to=300, textvariable=idle_var, width=8
        ).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Confirmation window (seconds):").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            frame, from_=30, to=600, textvariable=confirmation_var, width=8
        ).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Gaze FPS:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            frame, from_=1, to=30, textvariable=gaze_fps_var, width=8
        ).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Webcam device index:").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            frame, from_=0, to=5, textvariable=webcam_index_var, width=8
        ).grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="End of day time (HH:MM):").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=end_of_day_var, width=10).grid(row=4, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Distracting sites:").grid(row=5, column=0, sticky="nw", pady=4)

        sites_frame = ttk.Frame(frame)
        sites_frame.grid(row=5, column=1, sticky="w", pady=4)

        sites_listbox = tk.Listbox(sites_frame, width=36, height=8)
        sites_scrollbar = ttk.Scrollbar(sites_frame, orient="vertical", command=sites_listbox.yview)
        sites_listbox.configure(yscrollcommand=sites_scrollbar.set)
        sites_listbox.grid(row=0, column=0, sticky="nsew")
        sites_scrollbar.grid(row=0, column=1, sticky="ns")

        for site in config.get("distracting_sites", []):
            sites_listbox.insert(tk.END, site)

        add_entry = ttk.Entry(sites_frame, width=28)
        add_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        sites_buttons = ttk.Frame(sites_frame)
        sites_buttons.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        def add_site() -> None:
            site = add_entry.get().strip().lower()
            if not site:
                return
            existing = sites_listbox.get(0, tk.END)
            if site not in existing:
                sites_listbox.insert(tk.END, site)
            add_entry.delete(0, tk.END)

        def remove_site() -> None:
            selection = sites_listbox.curselection()
            if selection:
                sites_listbox.delete(selection[0])

        ttk.Button(sites_buttons, text="Add", command=add_site).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(sites_buttons, text="Remove", command=remove_site).grid(row=0, column=1)

        launch_check = ttk.Checkbutton(
            frame, text="Launch at startup", variable=launch_var
        )
        launch_check.grid(row=6, column=0, columnspan=2, sticky="w", pady=8)

        status_label = ttk.Label(frame, text="")
        status_label.grid(row=7, column=0, columnspan=2, sticky="w")

        buttons_frame = ttk.Frame(frame)
        buttons_frame.grid(row=8, column=0, columnspan=2, sticky="e", pady=(8, 0))

        def save_settings() -> None:
            end_of_day = end_of_day_var.get().strip()
            if len(end_of_day) != 5 or end_of_day[2] != ":":
                messagebox.showerror("Invalid time", "End of day time must be in HH:MM format.")
                return

            config["idle_threshold_seconds"] = idle_var.get()
            config["confirmation_window_secs"] = confirmation_var.get()
            config["gaze_fps"] = gaze_fps_var.get()
            config["webcam_device_index"] = webcam_index_var.get()
            config["end_of_day_time"] = end_of_day
            config["launch_at_startup"] = launch_var.get()
            config["distracting_sites"] = list(sites_listbox.get(0, tk.END))

            tmp_path = self._config_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            tmp_path.replace(self._config_path)

            status_label.config(text="Settings saved.")
            root.after(2000, lambda: status_label.config(text=""))

        def cancel() -> None:
            root.destroy()

        ttk.Button(buttons_frame, text="Save", command=save_settings).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons_frame, text="Cancel", command=cancel).grid(row=0, column=1)

        root.mainloop()
