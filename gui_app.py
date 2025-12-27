# gui_app.py
# Insta360Convert GUIのメインアプリケーションクラス

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import subprocess
import os
import json
import time
import shutil
import hashlib
from datetime import timedelta
import multiprocessing
import threading # For background update check
import webbrowser # To open web links

# アプリケーション固有モジュールのインポート
from strings import S, initial_app_language
from constants import (
    APP_RELEASE_DATE, APP_VERSION_STRING_SEMVER,
    FFMPEG_PRESETS, DEFAULT_PRESET,
    DEFAULT_RESOLUTION_WIDTH, HIGH_RESOLUTION_THRESHOLD,
    GITHUB_RELEASES_PAGE_URL,
    COLMAP_DEFAULT_PRESET_KEY,
    AYS_DEFAULT_PITCHES_STR, AYS_DEFAULT_FOV_INTERNAL
)
from tooltip_utils import ToolTip
from ffmpeg_worker import ffmpeg_worker_process, check_for_cuda_fallback_error
from advanced_yaw_selector import AdvancedYawSelector
from colmap_rig_export import (
    DEFAULT_RIG_NAME,
    make_unique_session_prefix,
    prepare_viewpoints_for_colmap,
    write_rig_config_json
)
from colmap_pipeline_options import (
    COLMAP_PRESETS,
    build_colmap_command,
    find_vocab_tree_path,
    merge_options
)

try:
    from update_checker import check_for_updates_background
except ImportError:
    def check_for_updates_background(current_app_version): # pylint: disable=unused-argument
        error_message_key = "update_check.error.load_failed"
        print(f"Error: Update checker module could not be loaded. Key: {error_message_key}")
        return (False, error_message_key, None, None, "update_checker.py import error")
    print("Warning: update_checker.py could not be imported. Update check feature will be impaired.")

COLMAP_PIPELINE_STEPS = [
    "feature_extractor",
    "rig_configurator",
    "matcher",
    "mapper",
    "image_undistorter"
]


class Insta360ConvertGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.app_name_short = S.get("app_name_short")
        self.app_version_display = S.get("constants_app_display_version_format",
                                         version=APP_VERSION_STRING_SEMVER,
                                         date=APP_RELEASE_DATE)

        self.title(f"{self.app_name_short} - {self.app_version_display}")
        self.geometry("800x980")
        self.minsize(700, 700)

        self.style = ttk.Style(self)
        try:
            if os.name == 'nt': self.style.theme_use('vista')
            else: self.style.theme_use('clam')
        except tk.TclError:
            self.style.theme_use('default')
            print("Note: Preferred ttk theme not available, using 'default'.")

        self.input_file_var = tk.StringVar()
        self.output_folder_var = tk.StringVar()
        self.resolution_var = tk.StringVar()
        self.custom_resolution_var = tk.StringVar()

        self.logical_cores = os.cpu_count() if os.cpu_count() else 1
        self.parallel_options = [str(i) for i in range(1, self.logical_cores + 1)]
        self.parallel_processes_var = tk.StringVar()

        self.cuda_var = tk.BooleanVar(value=False)
        self.interp_options = ["linear", "cubic", "lanczos", "nearest"]
        self.interp_var = tk.StringVar(value="cubic")
        self.output_mode_var = tk.StringVar(value="standard")
        self.output_format_var = tk.StringVar(value="png")
        self.frame_interval_var = tk.StringVar(value="1.00")
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET)
        self.cq_var = tk.StringVar(value="18")
        self.png_pred_var = tk.StringVar()
        self.jpeg_quality_var = tk.StringVar(value="90")
        self.colmap_rig_folder_var = tk.StringVar()
        self.colmap_postshot_folder_var = tk.StringVar()
        self.colmap_preset_var = tk.StringVar()
        self.colmap_preset_options_map = {}
        self.colmap_preset_key_by_display = {}
        self.colmap_preset_display_by_key = {}
        self.colmap_advanced_overrides = {}
        self.colmap_vocab_tree_path_var = tk.StringVar()
        self.colmap_vocab_tree_path_source = None
        self._setting_vocab_tree_path = False
        self.colmap_vocab_tree_path_var.trace_add("write", self._on_vocab_tree_path_changed)
        self.colmap_matcher_var = tk.StringVar(value="sequential")
        default_colmap_exec = "colmap.exe" if os.name == 'nt' else "colmap"
        self.colmap_exec_path_var = tk.StringVar(value=default_colmap_exec)
        self.colmap_matcher_options = ["sequential", "exhaustive", "vocab_tree"]

        self.ffmpeg_path = "ffmpeg"
        self.ffprobe_path = "ffprobe"
        self.cuda_available = False
        self.cuda_checked_for_high_res_compatibility = False
        self.cuda_fallback_triggered_for_high_res = False
        self.cuda_compatibility_confirmed_for_high_res = False

        self.conversion_pool = None
        self.log_queue_mp = None
        self.progress_queue_mp = None
        self.cancel_event_mp = None
        self.manager_mp = None
        self.colmap_thread = None
        self.colmap_cancel_event = None
        self.colmap_active_process = None
        self.colmap_running = False
        self.colmap_postshot_default = ""
        self.colmap_active_step = None
        self.colmap_pipeline_state_path = None
        self.colmap_advanced_dialog = None
        self.colmap_last_completed_step = None
        self.colmap_pipeline_state_data = None

        self.active_tasks_count = 0
        self.completed_tasks_count = 0
        self.total_tasks_for_conversion = 0
        self.task_durations = []

        self.video_duration = 0.0
        self.video_width = 0
        self.video_height = 0
        self.video_fps = 0.0

        self.start_time = 0
        self.elapsed_time_str = "00:00:00"
        self.overall_remaining_str = S.get("time_display_not_started")
        self.viewpoint_progress_text_var = tk.StringVar()
        self.final_conversion_message = None
        self.avg_time_per_viewpoint_for_estimation = 0
        self.overall_remaining_seconds_at_last_avg_calculation = None
        self.timestamp_of_last_avg_calculation = None
        self.colmap_rig_context = None

        self.yaw_selector_widget = None
        self.tooltips = []
        self.previous_language_for_switch = None

        self.menubar = None
        self.lang_menu = None
        self.helpmenu = None

        self.create_widgets()
        self.update_ui_texts_for_language_switch()

        self.update_resolution_options()
        self.check_ffmpeg_ffprobe()
        self.check_cuda_availability()
        self.update_time_label_display()
        self.update_parallel_options_and_default()
        self.update_colmap_controls_state()


    def _rebuild_menus(self):
        if self.menubar:
            if self.lang_menu: self.lang_menu.destroy()
            if self.helpmenu: self.helpmenu.destroy()
            # If menubar itself needs destruction, it's more complex due to how Tk handles it.
            # Usually, recreating sub-menus and re-adding cascades is sufficient.
            # For this case, we recreate the menubar object too.
            # self.menubar.destroy() # This line can be problematic if not handled carefully.
            # A safer approach if the menubar itself doesn't change structure radically
            # is to delete all entries and re-add them.
            # However, given the current simple structure, recreating is fine.
            pass # Menubar will be assigned a new tk.Menu instance.

        self.menubar = tk.Menu(self)

        self.lang_menu = tk.Menu(self.menubar, tearoff=0)
        self.lang_menu.add_command(label=S.get("language_english"), command=lambda: self.switch_language("en"))
        self.lang_menu.add_command(label=S.get("language_japanese"), command=lambda: self.switch_language("ja"))
        self.menubar.add_cascade(label=S.get("language_menu_label"), menu=self.lang_menu, underline=0)

        self.helpmenu = tk.Menu(self.menubar, tearoff=0)
        self.helpmenu.add_command(label=S.get("menu_help_about"), command=self._show_version_info)
        self.helpmenu.add_separator()
        self.helpmenu.add_command(label=S.get("menu_help_check_updates"), command=self.trigger_update_check)
        self.menubar.add_cascade(label=S.get("menu_help"), menu=self.helpmenu, underline=0)

        self.config(menu=self.menubar)

    def _show_version_info(self):
        messagebox.showinfo(
            S.get("about_dialog_title"),
            S.get("about_dialog_message_format", app_name=self.app_name_short, version_display=self.app_version_display),
            parent=self
        )

    def trigger_update_check(self):
        messagebox.showinfo(
            S.get("update_check_info_title"),
            S.get("update_check_checking_message"),
            parent=self, icon=messagebox.INFO
        )
        update_thread = threading.Thread(target=self.perform_update_check_in_thread, daemon=True)
        update_thread.start()

    def perform_update_check_in_thread(self):
        (update_available, msg_key, latest_v, notes, err_detail_literal) = check_for_updates_background(APP_VERSION_STRING_SEMVER)
        self.after(0, self.handle_update_check_result, update_available, msg_key, latest_v, notes, err_detail_literal)

    def handle_update_check_result(self, update_available, message_key, latest_version_str, release_notes_str, error_detail_literal):
        if error_detail_literal:
            gui_message = S.get(message_key, error_detail=error_detail_literal)
            messagebox.showerror(S.get("update_check_error_title"), gui_message, parent=self)
            return

        if update_available:
            notes_summary = (release_notes_str[:300] + '...') if release_notes_str and len(release_notes_str) > 300 else (release_notes_str or "N/A")
            gui_message = S.get(message_key,
                                latest_version=latest_version_str,
                                current_version=APP_VERSION_STRING_SEMVER,
                                release_notes_summary=notes_summary)
            if messagebox.askyesno(S.get("update_check_info_title"), gui_message, parent=self):
                try:
                    webbrowser.open_new_tab(GITHUB_RELEASES_PAGE_URL)
                except Exception as e:
                    messagebox.showerror(S.get("update_link_error_title"),
                                         S.get("update_link_error_message_format", error=str(e)), parent=self)
        else:
            gui_message = S.get(message_key,
                                latest_version=latest_version_str,
                                current_version=APP_VERSION_STRING_SEMVER)
            messagebox.showinfo(S.get("update_check_info_title"), gui_message, parent=self)

    def add_tooltip_managed(self, widget, text_key, *args, **kwargs):
        text = S.get(text_key, *args, **kwargs)
        tip = ToolTip(widget, text)
        self.tooltips.append({"instance": tip, "key": text_key, "args": args, "kwargs": kwargs})
        return tip

    def update_all_tooltips_text(self):
        for tip_info in self.tooltips:
            new_text = S.get(tip_info["key"], *tip_info["args"], **tip_info["kwargs"])
            tip_info["instance"].update_text(new_text)


    def create_widgets(self): # pylint: disable=too-many-statements
        self._rebuild_menus()
        self.main_frame = ttk.Frame(self, padding="5")
        self.main_frame.pack(expand=True, fill=tk.BOTH)

        self.resolutions_display_texts = ["1920", "1600", "Automatic", "Custom..."]
        self.resolution_var.set(self.resolutions_display_texts[2])

        self.png_pred_options_map = {"Average": "3"}
        self.png_pred_var.set("Average")

        self.viewpoint_progress_text_var.set(S.get("viewpoint_progress_format", completed=0, total=0))

        self.io_frame = ttk.LabelFrame(self.main_frame, text="", padding="5")
        self.io_frame.pack(fill=tk.X, pady=2, side=tk.TOP)
        self.input_file_label = ttk.Label(self.io_frame, text="")
        self.input_file_label.grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.input_file_entry = ttk.Entry(self.io_frame, textvariable=self.input_file_var, state="readonly", width=60)
        self.input_file_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.EW)

        self.browse_input_button = ttk.Button(self.io_frame, text="", command=self.browse_input_file)
        self.browse_input_button.grid(row=0, column=2, padx=5, pady=2)

        self.output_folder_label = ttk.Label(self.io_frame, text="")
        self.output_folder_label.grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.output_folder_entry = ttk.Entry(self.io_frame, textvariable=self.output_folder_var, state="readonly", width=60)
        self.output_folder_entry.grid(row=1, column=1, padx=5, pady=2, sticky=tk.EW)

        self.browse_output_button = ttk.Button(self.io_frame, text="", command=self.browse_output_folder)
        self.browse_output_button.grid(row=1, column=2, padx=5, pady=2)
        self.io_frame.columnconfigure(1, weight=1)

        self.main_content_paned_window = ttk.PanedWindow(self.main_frame, orient=tk.VERTICAL)
        self.main_content_paned_window.pack(fill=tk.BOTH, expand=True, pady=(2,0), side=tk.TOP)

        self.yaw_selector_module_labelframe = ttk.LabelFrame(self.main_content_paned_window, text="", padding="5")
        self.main_content_paned_window.add(self.yaw_selector_module_labelframe, weight=3)

        self.yaw_selector_widget = AdvancedYawSelector(
            self.yaw_selector_module_labelframe,
            initial_pitches_str=AYS_DEFAULT_PITCHES_STR,
            on_selection_change_callback=self.on_yaw_selector_updated
        )
        self.yaw_selector_widget.pack(fill=tk.BOTH, expand=True)

        bottom_content_frame = ttk.Frame(self.main_content_paned_window)
        self.main_content_paned_window.add(bottom_content_frame, weight=2)

        self.output_settings_frame = ttk.LabelFrame(bottom_content_frame, text="", padding="5")
        self.output_settings_frame.pack(fill=tk.X, pady=2, side=tk.TOP)

        common_opts_line1_frame = ttk.Frame(self.output_settings_frame)
        common_opts_line1_frame.pack(fill=tk.X, pady=2)
        self.resolution_label = ttk.Label(common_opts_line1_frame, text="")
        self.resolution_label.pack(side=tk.LEFT, padx=(5,2), pady=2)

        self.resolution_combo = ttk.Combobox(common_opts_line1_frame, textvariable=self.resolution_var,
                                             values=self.resolutions_display_texts, width=20, state="readonly")
        self.resolution_combo.pack(side=tk.LEFT, padx=(0,5), pady=2)
        self.resolution_combo.bind("<<ComboboxSelected>>", self.update_resolution_options)

        self.custom_resolution_entry = ttk.Entry(common_opts_line1_frame, textvariable=self.custom_resolution_var, width=8, state="disabled")
        self.custom_resolution_entry.pack(side=tk.LEFT, padx=(0,15), pady=2)

        self.cuda_check = ttk.Checkbutton(common_opts_line1_frame, text="", variable=self.cuda_var,
                                          state="disabled", command=self.on_cuda_checkbox_changed)
        self.cuda_check.pack(side=tk.LEFT, padx=(0,5), pady=2)

        self.interp_label = ttk.Label(common_opts_line1_frame, text="")
        self.interp_label.pack(side=tk.LEFT, padx=(10,2), pady=2)

        self.interp_combo = ttk.Combobox(common_opts_line1_frame, textvariable=self.interp_var,
                                         values=self.interp_options, width=10, state="readonly")
        self.interp_combo.pack(side=tk.LEFT, padx=(0,5), pady=2)

        output_mode_frame = ttk.Frame(self.output_settings_frame)
        output_mode_frame.pack(fill=tk.X, pady=(5,2))
        self.output_mode_label = ttk.Label(output_mode_frame, text="")
        self.output_mode_label.pack(side=tk.LEFT, padx=(5,2))
        self.output_mode_standard_radio = ttk.Radiobutton(output_mode_frame, text="", variable=self.output_mode_var,
                                                          value="standard", command=self.update_output_format_options)
        self.output_mode_standard_radio.pack(side=tk.LEFT, padx=(5,2))
        self.output_mode_colmap_radio = ttk.Radiobutton(output_mode_frame, text="", variable=self.output_mode_var,
                                                        value="colmap_rig", command=self.update_output_format_options)
        self.output_mode_colmap_radio.pack(side=tk.LEFT, padx=(5,2))

        format_options_main_frame = ttk.Frame(self.output_settings_frame)
        format_options_main_frame.pack(fill=tk.X, pady=(5,2))

        self.png_radio = ttk.Radiobutton(format_options_main_frame, text="", variable=self.output_format_var,
                                         value="png", command=self.update_output_format_options)
        self.png_radio.grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)

        self.png_options_frame = ttk.Frame(format_options_main_frame)
        self.png_options_frame.grid(row=0, column=1, padx=(10,5), pady=0, sticky=tk.W)
        self.png_interval_label = ttk.Label(self.png_options_frame, text="")
        self.png_interval_label.pack(side=tk.LEFT, padx=(0,2))

        self.png_frame_interval_entry = ttk.Entry(self.png_options_frame, textvariable=self.frame_interval_var, width=8)
        self.png_frame_interval_entry.pack(side=tk.LEFT, padx=(0,5))

        self.png_pred_label = ttk.Label(self.png_options_frame, text="")
        self.png_pred_label.pack(side=tk.LEFT, padx=(5,2))

        self.png_pred_combo = ttk.Combobox(self.png_options_frame, textvariable=self.png_pred_var,
                                           values=list(self.png_pred_options_map.keys()), width=25, state="readonly")
        self.png_pred_combo.pack(side=tk.LEFT, padx=(0,5))

        self.jpeg_radio = ttk.Radiobutton(format_options_main_frame, text="", variable=self.output_format_var,
                                          value="jpeg", command=self.update_output_format_options)
        self.jpeg_radio.grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)

        self.jpeg_options_frame = ttk.Frame(format_options_main_frame)
        self.jpeg_options_frame.grid(row=1, column=1, padx=(10,5), pady=0, sticky=tk.W)
        self.jpeg_interval_label = ttk.Label(self.jpeg_options_frame, text="")
        self.jpeg_interval_label.pack(side=tk.LEFT, padx=(0,2))

        self.jpeg_frame_interval_entry = ttk.Entry(self.jpeg_options_frame, textvariable=self.frame_interval_var, width=8)
        self.jpeg_frame_interval_entry.pack(side=tk.LEFT, padx=(0,5))

        self.jpeg_quality_label = ttk.Label(self.jpeg_options_frame, text="")
        self.jpeg_quality_label.pack(side=tk.LEFT, padx=(5,2))

        self.jpeg_quality_entry = ttk.Entry(self.jpeg_options_frame, textvariable=self.jpeg_quality_var, width=5)
        self.jpeg_quality_entry.pack(side=tk.LEFT, padx=(0,5))

        self.video_radio = ttk.Radiobutton(format_options_main_frame, text="", variable=self.output_format_var,
                                           value="video", command=self.update_output_format_options)
        self.video_radio.grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)

        self.video_options_frame = ttk.Frame(format_options_main_frame)
        self.video_options_frame.grid(row=2, column=1, padx=(10,5), pady=0, sticky=tk.W)
        self.video_preset_label = ttk.Label(self.video_options_frame, text="")
        self.video_preset_label.pack(side=tk.LEFT, padx=(0,2))

        self.preset_combo = ttk.Combobox(self.video_options_frame, textvariable=self.preset_var,
                                         values=FFMPEG_PRESETS, width=10, state="readonly")
        self.preset_combo.pack(side=tk.LEFT, padx=(0,5))

        self.video_cq_label = ttk.Label(self.video_options_frame, text="")
        self.video_cq_label.pack(side=tk.LEFT, padx=(5,2))

        self.cq_entry = ttk.Entry(self.video_options_frame, textvariable=self.cq_var, width=5)
        self.cq_entry.pack(side=tk.LEFT, padx=(0,5))
        format_options_main_frame.columnconfigure(1, weight=1)

        self.control_frame_outer = ttk.Frame(bottom_content_frame, padding=(5,0))
        self.control_frame_outer.pack(fill=tk.X, pady=2, side=tk.TOP)

        self.parallel_control_frame = ttk.Frame(self.control_frame_outer)
        self.parallel_control_frame.pack(fill=tk.X)
        self.parallel_label = ttk.Label(self.parallel_control_frame, text="")
        self.parallel_label.pack(side=tk.LEFT, padx=(5,0))

        self.parallel_combo = ttk.Combobox(self.parallel_control_frame, textvariable=self.parallel_processes_var,
                                           values=self.parallel_options, width=5, state="readonly")
        self.parallel_combo.pack(side=tk.LEFT, padx=5)

        self.button_time_frame = ttk.Frame(self.control_frame_outer)
        self.button_time_frame.pack(fill=tk.X, pady=(5,0))
        self.start_button = ttk.Button(self.button_time_frame, text="", command=self.start_conversion_mp)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.cancel_button = ttk.Button(self.button_time_frame, text="", command=self.cancel_conversion_mp, state="disabled")
        self.cancel_button.pack(side=tk.LEFT, padx=5)

        self.time_label = ttk.Label(self.button_time_frame, text="")
        self.time_label.pack(side=tk.LEFT, padx=10, pady=(0,3))

        self.progress_display_frame = ttk.Frame(self.control_frame_outer)
        self.progress_display_frame.pack(fill=tk.X, pady=(2,0))
        self.viewpoint_progress_label = ttk.Label(self.progress_display_frame, textvariable=self.viewpoint_progress_text_var)
        self.viewpoint_progress_label.pack(side=tk.LEFT, padx=5)

        self.progress_bar = ttk.Progressbar(self.progress_display_frame, orient="horizontal", length=200, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.colmap_pipeline_frame = ttk.LabelFrame(bottom_content_frame, text="", padding="5")
        self.colmap_pipeline_frame.pack(fill=tk.X, pady=2, side=tk.TOP)
        self.colmap_rig_label = ttk.Label(self.colmap_pipeline_frame, text="")
        self.colmap_rig_label.grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.colmap_rig_entry = ttk.Entry(self.colmap_pipeline_frame, textvariable=self.colmap_rig_folder_var, width=45)
        self.colmap_rig_entry.grid(row=0, column=1, padx=(0, 5), pady=2, sticky=tk.EW, columnspan=3)
        self.colmap_rig_browse = ttk.Button(self.colmap_pipeline_frame, text="", command=self.browse_colmap_rig_folder)
        self.colmap_rig_browse.grid(row=0, column=4, padx=5, pady=2, sticky=tk.W)

        self.colmap_exec_label = ttk.Label(self.colmap_pipeline_frame, text="")
        self.colmap_exec_label.grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.colmap_exec_entry = ttk.Entry(self.colmap_pipeline_frame, textvariable=self.colmap_exec_path_var, width=45)
        self.colmap_exec_entry.grid(row=1, column=1, padx=(0, 5), pady=2, sticky=tk.EW, columnspan=3)
        self.colmap_exec_browse = ttk.Button(self.colmap_pipeline_frame, text="", command=self.browse_colmap_exec_path)
        self.colmap_exec_browse.grid(row=1, column=4, padx=5, pady=2, sticky=tk.W)

        self.colmap_preset_label = ttk.Label(self.colmap_pipeline_frame, text="")
        self.colmap_preset_label.grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
        self.colmap_preset_combo = ttk.Combobox(self.colmap_pipeline_frame, textvariable=self.colmap_preset_var,
                                                values=[], width=16, state="readonly")
        self.colmap_preset_combo.grid(row=2, column=1, padx=(0, 5), pady=2, sticky=tk.W)
        self.colmap_advanced_button = ttk.Button(self.colmap_pipeline_frame, text="", command=self.open_colmap_advanced_dialog)
        self.colmap_advanced_button.grid(row=2, column=2, padx=5, pady=2, sticky=tk.W)

        self.colmap_matcher_label = ttk.Label(self.colmap_pipeline_frame, text="")
        self.colmap_matcher_label.grid(row=3, column=0, padx=5, pady=2, sticky=tk.W)
        self.colmap_matcher_combo = ttk.Combobox(self.colmap_pipeline_frame, textvariable=self.colmap_matcher_var,
                                                 values=self.colmap_matcher_options, width=12, state="readonly")
        self.colmap_matcher_combo.grid(row=3, column=1, padx=(0, 5), pady=2, sticky=tk.W)
        self.colmap_preset_combo.bind("<<ComboboxSelected>>", self.on_colmap_preset_changed)
        self.colmap_matcher_combo.bind("<<ComboboxSelected>>", self.on_colmap_matcher_changed)

        self.colmap_vocab_tree_label = ttk.Label(self.colmap_pipeline_frame, text="")
        self.colmap_vocab_tree_label.grid(row=4, column=0, padx=5, pady=2, sticky=tk.W)
        self.colmap_vocab_tree_entry = ttk.Entry(self.colmap_pipeline_frame, textvariable=self.colmap_vocab_tree_path_var, width=45)
        self.colmap_vocab_tree_entry.grid(row=4, column=1, padx=(0, 5), pady=2, sticky=tk.EW, columnspan=3)
        self.colmap_vocab_tree_browse = ttk.Button(self.colmap_pipeline_frame, text="", command=self.browse_colmap_vocab_tree_path)
        self.colmap_vocab_tree_browse.grid(row=4, column=4, padx=5, pady=2, sticky=tk.W)

        self.colmap_postshot_label = ttk.Label(self.colmap_pipeline_frame, text="")
        self.colmap_postshot_label.grid(row=5, column=0, padx=5, pady=2, sticky=tk.W)
        self.colmap_postshot_entry = ttk.Entry(self.colmap_pipeline_frame, textvariable=self.colmap_postshot_folder_var, width=35)
        self.colmap_postshot_entry.grid(row=5, column=1, padx=(0, 5), pady=2, sticky=tk.EW, columnspan=3)
        self.colmap_postshot_browse = ttk.Button(self.colmap_pipeline_frame, text="", command=self.browse_postshot_folder)
        self.colmap_postshot_browse.grid(row=5, column=4, padx=5, pady=2, sticky=tk.W)

        self.colmap_run_button = ttk.Button(self.colmap_pipeline_frame, text="", command=self.start_colmap_pipeline)
        self.colmap_run_button.grid(row=6, column=0, padx=5, pady=(4, 2), sticky=tk.W)
        self.colmap_cancel_button = ttk.Button(self.colmap_pipeline_frame, text="", command=self.cancel_colmap_pipeline, state="disabled")
        self.colmap_cancel_button.grid(row=6, column=1, padx=5, pady=(4, 2), sticky=tk.W)
        self.colmap_pipeline_frame.columnconfigure(1, weight=1)
        self.colmap_pipeline_frame.columnconfigure(3, weight=1)

        self.log_notebook = ttk.Notebook(bottom_content_frame, padding=2)
        self.log_notebook.pack(expand=True, fill=tk.BOTH, pady=(2,5), side=tk.TOP)

        self.app_log_frame = ttk.Frame(self.log_notebook, padding=2)
        self.log_notebook.add(self.app_log_frame, text="")
        self.log_area = scrolledtext.ScrolledText(self.app_log_frame, height=6, state="disabled", wrap=tk.WORD, relief=tk.SUNKEN, bd=1)
        self.log_area.pack(expand=True, fill=tk.BOTH)

        self.ffmpeg_log_frame = ttk.Frame(self.log_notebook, padding=2)
        self.log_notebook.add(self.ffmpeg_log_frame, text="")
        self.ffmpeg_log_area = scrolledtext.ScrolledText(self.ffmpeg_log_frame, height=6, state="disabled", wrap=tk.WORD, relief=tk.SUNKEN, bd=1)
        self.ffmpeg_log_area.pack(expand=True, fill=tk.BOTH)


    def switch_language(self, lang_code):
        current_lang = S.language
        if current_lang == lang_code: return

        self.previous_language_for_switch = current_lang
        S.set_language(lang_code)
        self.update_ui_texts_for_language_switch()
        messagebox.showinfo(S.get("info_title"), S.get("language_switched_info"), parent=self)
        self.previous_language_for_switch = None


    def update_ui_texts_for_language_switch(self): # pylint: disable=too-many-statements
        self.app_name_short = S.get("app_name_short")
        self.app_version_display = S.get("constants_app_display_version_format", version=APP_VERSION_STRING_SEMVER, date=APP_RELEASE_DATE)
        self.title(f"{self.app_name_short} - {self.app_version_display}")

        self._rebuild_menus()

        self.io_frame.config(text=S.get("file_settings_label"))
        self.input_file_label.config(text=S.get("input_file_label"))
        self.browse_input_button.config(text=S.get("browse_button"))
        self.output_folder_label.config(text=S.get("output_folder_label"))
        self.browse_output_button.config(text=S.get("browse_button"))
        self.yaw_selector_module_labelframe.config(text=S.get("viewpoint_settings_labelframe_title"))

        self.output_settings_frame.config(text=S.get("output_settings_labelframe_title"))
        self.resolution_label.config(text=S.get("resolution_label"))

        current_res_display_text = self.resolution_var.get()
        self.resolutions_display_texts = ["1920", "1600", S.get("resolution_auto"), S.get("resolution_custom")]
        self.resolution_combo.config(values=self.resolutions_display_texts)

        new_selection_made = False
        if self.previous_language_for_switch:
            original_s_lang_temp = S.language
            S.set_language(self.previous_language_for_switch)
            old_res_auto_text = S.get("resolution_auto")
            old_res_custom_text = S.get("resolution_custom")
            S.set_language(original_s_lang_temp)

            if current_res_display_text == old_res_auto_text:
                self.resolution_var.set(S.get("resolution_auto"))
                new_selection_made = True
            elif current_res_display_text == old_res_custom_text:
                self.resolution_var.set(S.get("resolution_custom"))
                new_selection_made = True
        
        if not new_selection_made:
            if current_res_display_text in self.resolutions_display_texts:
                self.resolution_var.set(current_res_display_text)
            else:
                self.resolution_var.set(S.get("resolution_auto"))
        self.update_resolution_options()

        self.cuda_check.config(text=S.get("cuda_checkbox_label"))
        self.interp_label.config(text=S.get("interpolation_label"))
        self.output_mode_label.config(text=S.get("output_mode_label"))
        self.output_mode_standard_radio.config(text=S.get("output_mode_standard_label"))
        self.output_mode_colmap_radio.config(text=S.get("output_mode_colmap_label"))
        self.colmap_pipeline_frame.config(text=S.get("colmap_pipeline_label"))
        self.colmap_rig_label.config(text=S.get("colmap_rig_folder_label"))
        self.colmap_exec_label.config(text=S.get("colmap_exec_label"))
        self.colmap_preset_label.config(text=S.get("colmap_preset_label"))
        self.colmap_vocab_tree_label.config(text=S.get("colmap_vocab_tree_label"))
        self.colmap_matcher_label.config(text=S.get("colmap_matcher_label"))
        self.colmap_postshot_label.config(text=S.get("colmap_postshot_output_label"))
        self.colmap_rig_browse.config(text=S.get("browse_button"))
        self.colmap_exec_browse.config(text=S.get("browse_button"))
        self.colmap_vocab_tree_browse.config(text=S.get("browse_button"))
        self.colmap_postshot_browse.config(text=S.get("browse_button"))
        self.colmap_run_button.config(text=S.get("colmap_run_button_label"))
        self.colmap_cancel_button.config(text=S.get("colmap_cancel_button_label"))
        self.colmap_advanced_button.config(text=S.get("colmap_advanced_button_label"))

        current_colmap_preset_display = self.colmap_preset_var.get()
        current_colmap_preset_key = None
        for display_name, key in self.colmap_preset_options_map.items():
            if display_name == current_colmap_preset_display:
                current_colmap_preset_key = key
                break

        self.colmap_preset_options_map = {
            S.get("colmap_preset_standard"): "standard",
            S.get("colmap_preset_balanced"): "balanced",
            S.get("colmap_preset_ultra"): "ultra",
            S.get("colmap_preset_multi_path"): "multi_path",
        }
        self.colmap_preset_key_by_display = dict(self.colmap_preset_options_map)
        self.colmap_preset_display_by_key = {key: display for display, key in self.colmap_preset_options_map.items()}
        self.colmap_preset_combo.config(values=list(self.colmap_preset_options_map.keys()))

        if not current_colmap_preset_key:
            current_colmap_preset_key = COLMAP_DEFAULT_PRESET_KEY
        self.colmap_preset_var.set(self.colmap_preset_display_by_key.get(
            current_colmap_preset_key,
            list(self.colmap_preset_options_map.keys())[0]
        ))
        if not current_colmap_preset_display:
            self.on_colmap_preset_changed(log=False)
        self.png_radio.config(text=S.get("png_radio_label"))
        self.png_interval_label.config(text=S.get("png_interval_label"))
        self.png_pred_label.config(text=S.get("png_prediction_label"))

        current_png_pred_internal_value = None
        for disp_name, int_val in self.png_pred_options_map.items(): # Use current map before redefining
            if disp_name == self.png_pred_var.get():
                current_png_pred_internal_value = int_val
                break

        self.png_pred_options_map = {
            S.get("png_pred_none"): "0", S.get("png_pred_sub"): "1",
            S.get("png_pred_up"): "2", S.get("png_pred_average"): "3",
            S.get("png_pred_paeth"): "4"
        }
        new_png_pred_keys = list(self.png_pred_options_map.keys())
        self.png_pred_combo.config(values=new_png_pred_keys)

        restored_png_selection = False
        if current_png_pred_internal_value is not None:
            for display_name, internal_val in self.png_pred_options_map.items(): # Use new map to find display name
                if internal_val == current_png_pred_internal_value:
                    self.png_pred_var.set(display_name)
                    restored_png_selection = True
                    break
        if not restored_png_selection:
            self.png_pred_var.set(S.get("png_pred_average"))

        self.jpeg_radio.config(text=S.get("jpeg_radio_label"))
        self.jpeg_interval_label.config(text=S.get("jpeg_interval_label"))
        self.jpeg_quality_label.config(text=S.get("jpeg_quality_label"))
        self.video_radio.config(text=S.get("video_radio_label"))
        self.video_preset_label.config(text=S.get("video_preset_label"))
        self.video_cq_label.config(text=S.get("video_cq_crf_label"))

        self.parallel_label.config(text=S.get("parallel_processes_label"))
        self.start_button.config(text=S.get("start_button_label"))
        self.cancel_button.config(text=S.get("cancel_button_label"))
        self.update_time_label_display()
        self.viewpoint_progress_text_var.set(S.get("viewpoint_progress_format", completed=self.completed_tasks_count, total=self.total_tasks_for_conversion))

        self.log_notebook.tab(self.app_log_frame, text=S.get("log_tab_app_log_label"))
        self.log_notebook.tab(self.ffmpeg_log_frame, text=S.get("log_tab_ffmpeg_log_label"))

        for tip_info in self.tooltips:
            tip_info["instance"].hide_tip_immediately()
        self.tooltips = []

        self.add_tooltip_managed(self.input_file_entry, "input_file_entry_tooltip")
        self.add_tooltip_managed(self.browse_input_button, "browse_input_button_tooltip")
        self.add_tooltip_managed(self.output_folder_entry, "output_folder_entry_tooltip")
        self.add_tooltip_managed(self.browse_output_button, "browse_output_button_tooltip")
        self.add_tooltip_managed(self.yaw_selector_module_labelframe, "viewpoint_settings_labelframe_tooltip")
        self.add_tooltip_managed(self.resolution_label, "resolution_label_tooltip")
        self.add_tooltip_managed(self.resolution_combo, "resolution_combo_tooltip")
        self.add_tooltip_managed(self.custom_resolution_entry, "custom_resolution_entry_tooltip")
        self.add_tooltip_managed(self.cuda_check, "cuda_checkbox_tooltip")
        self.add_tooltip_managed(self.interp_label, "interpolation_label_tooltip")
        self.add_tooltip_managed(self.interp_combo, "interpolation_combo_tooltip")
        self.add_tooltip_managed(self.output_mode_label, "output_mode_label_tooltip")
        self.add_tooltip_managed(self.output_mode_standard_radio, "output_mode_standard_tooltip")
        self.add_tooltip_managed(self.output_mode_colmap_radio, "output_mode_colmap_tooltip")
        self.add_tooltip_managed(self.colmap_pipeline_frame, "colmap_pipeline_tooltip")
        self.add_tooltip_managed(self.colmap_rig_label, "colmap_rig_folder_tooltip")
        self.add_tooltip_managed(self.colmap_rig_entry, "colmap_rig_folder_tooltip")
        self.add_tooltip_managed(self.colmap_rig_browse, "colmap_rig_folder_browse_tooltip")
        self.add_tooltip_managed(self.colmap_exec_label, "colmap_exec_tooltip")
        self.add_tooltip_managed(self.colmap_exec_entry, "colmap_exec_tooltip")
        self.add_tooltip_managed(self.colmap_exec_browse, "colmap_exec_browse_tooltip")
        self.add_tooltip_managed(self.colmap_preset_label, "colmap_preset_tooltip")
        self.add_tooltip_managed(self.colmap_preset_combo, "colmap_preset_tooltip")
        self.add_tooltip_managed(self.colmap_advanced_button, "colmap_advanced_tooltip")
        self.add_tooltip_managed(self.colmap_matcher_label, "colmap_matcher_tooltip")
        self.add_tooltip_managed(self.colmap_matcher_combo, "colmap_matcher_tooltip")
        self.add_tooltip_managed(self.colmap_vocab_tree_label, "colmap_vocab_tree_tooltip")
        self.add_tooltip_managed(self.colmap_vocab_tree_entry, "colmap_vocab_tree_tooltip")
        self.add_tooltip_managed(self.colmap_vocab_tree_browse, "colmap_vocab_tree_browse_tooltip")
        self.add_tooltip_managed(self.colmap_postshot_label, "colmap_postshot_output_tooltip")
        self.add_tooltip_managed(self.colmap_postshot_entry, "colmap_postshot_output_tooltip")
        self.add_tooltip_managed(self.colmap_postshot_browse, "colmap_postshot_output_browse_tooltip")
        self.add_tooltip_managed(self.colmap_run_button, "colmap_run_button_tooltip")
        self.add_tooltip_managed(self.colmap_cancel_button, "colmap_cancel_button_tooltip")
        self.add_tooltip_managed(self.png_radio, "png_radio_tooltip")
        self.add_tooltip_managed(self.png_interval_label, "png_interval_label_tooltip")
        self.add_tooltip_managed(self.png_frame_interval_entry, "png_frame_interval_entry_tooltip")
        self.add_tooltip_managed(self.png_pred_label, "png_prediction_label_tooltip")
        self.add_tooltip_managed(self.png_pred_combo, "png_prediction_combo_tooltip")
        self.add_tooltip_managed(self.jpeg_radio, "jpeg_radio_tooltip")
        self.add_tooltip_managed(self.jpeg_interval_label, "jpeg_interval_label_tooltip")
        self.add_tooltip_managed(self.jpeg_frame_interval_entry, "jpeg_frame_interval_entry_tooltip")
        self.add_tooltip_managed(self.jpeg_quality_label, "jpeg_quality_label_tooltip")
        self.add_tooltip_managed(self.jpeg_quality_entry, "jpeg_quality_entry_tooltip")
        self.add_tooltip_managed(self.video_radio, "video_radio_tooltip")
        self.add_tooltip_managed(self.video_preset_label, "video_preset_label_tooltip")
        self.add_tooltip_managed(self.preset_combo, "video_preset_combo_tooltip")
        self.add_tooltip_managed(self.video_cq_label, "video_cq_crf_label_tooltip")
        self.add_tooltip_managed(self.cq_entry, "video_cq_crf_entry_tooltip")
        self.add_tooltip_managed(self.parallel_label, "parallel_processes_label_tooltip_format", cores=self.logical_cores)
        self.add_tooltip_managed(self.parallel_combo, "parallel_processes_combo_tooltip")
        self.add_tooltip_managed(self.start_button, "start_button_tooltip")
        self.add_tooltip_managed(self.cancel_button, "cancel_button_tooltip")
        self.add_tooltip_managed(self.time_label, "time_label_tooltip")
        self.add_tooltip_managed(self.viewpoint_progress_label, "viewpoint_progress_label_tooltip")
        self.add_tooltip_managed(self.progress_bar, "progressbar_tooltip")
        self.add_tooltip_managed(self.log_area, "log_tab_app_log_tooltip")
        self.add_tooltip_managed(self.ffmpeg_log_area, "log_tab_ffmpeg_log_tooltip")

        if self.yaw_selector_widget and hasattr(self.yaw_selector_widget, 'update_ui_texts_for_language_switch'):
            self.yaw_selector_widget.update_ui_texts_for_language_switch()
        self.update_output_format_options()
        self.update_colmap_controls_state()


    def on_yaw_selector_updated(self):
        if not self.yaw_selector_widget: return
        self.update_parallel_options_and_default()

    def _update_ffmpeg_log_area(self, message):
        if hasattr(self, 'ffmpeg_log_area') and self.ffmpeg_log_area.winfo_exists():
            self.ffmpeg_log_area.config(state="normal")
            self.ffmpeg_log_area.insert(tk.END, message)
            self.ffmpeg_log_area.see(tk.END)
            self.ffmpeg_log_area.config(state="disabled")
        else:
            print(f"FFMPEG_RAW_LOG: {message.strip()}")

    def on_cuda_checkbox_changed(self):
        self.cuda_checked_for_high_res_compatibility = False
        self.cuda_fallback_triggered_for_high_res = False
        self.cuda_compatibility_confirmed_for_high_res = False
        self.log_message_ui("log_cuda_settings_changed_retest", "DEBUG", is_key=True)
        self.apply_cuda_restrictions_based_on_video_info()

    def update_parallel_options_and_default(self):
        num_pitch_angles = 0
        if self.yaw_selector_widget and hasattr(self.yaw_selector_widget, 'get_num_active_pitches'):
            num_pitch_angles = self.yaw_selector_widget.get_num_active_pitches()
        if num_pitch_angles == 0:
            num_pitch_angles = 1
        default_parallel = max(1, min(num_pitch_angles, self.logical_cores))
        if str(default_parallel) in self.parallel_options:
            self.parallel_processes_var.set(str(default_parallel))
        elif self.parallel_options:
            self.parallel_processes_var.set(self.parallel_options[0])
        else:
            self.parallel_processes_var.set("1")

    def log_message_ui(self, message_key_or_literal, level="INFO", is_key=False, *args, **kwargs):
        if is_key:
            message = S.get(message_key_or_literal, *args, **kwargs)
        else:
            message = message_key_or_literal
        if not hasattr(self, 'log_area') or not self.log_area:
            print(f"LOG_FALLBACK [{level}] {message}")
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        formatted_message = f"[{timestamp}] [{level}] {message}\n"
        try:
            if self.log_area.winfo_exists():
                self._update_log_area(formatted_message)
        except tk.TclError:
            print(f"LOG_TCL_ERROR [{level}] {message}")

    def _update_log_area(self, message):
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, message)
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")

    def process_mp_queues(self): # pylint: disable=too-many-branches
        try:
            while self.log_queue_mp and not self.log_queue_mp.empty():
                log_entry = self.log_queue_mp.get_nowait()
                if log_entry["type"] == "log":
                    self.log_message_ui(log_entry["message"], log_entry["level"], is_key=False)
                elif log_entry["type"] == "ffmpeg_raw":
                    self._update_ffmpeg_log_area(log_entry["line"] + "\n")
        except (multiprocessing.queues.Empty, AttributeError, EOFError, FileNotFoundError):
            pass
        except Exception as e:
            print(f"Log queue processing error: {type(e).__name__} - {e}")

        new_task_completed_this_cycle = False
        try:
            while self.progress_queue_mp and not self.progress_queue_mp.empty():
                prog_entry = self.progress_queue_mp.get_nowait()
                if prog_entry["type"] == "task_result":
                    new_task_completed_this_cycle = True
                    self.completed_tasks_count += 1
                    if self.active_tasks_count > 0:
                        self.active_tasks_count -= 1
                    if prog_entry.get("cancelled", False):
                        self.log_message_ui("log_task_cancelled_format", "INFO", is_key=True,
                                            index=prog_entry['viewpoint_index'] + 1)
                    elif prog_entry["success"]:
                        duration = prog_entry.get('duration', 0)
                        self.log_message_ui("log_task_completed_format", "INFO", is_key=True,
                                            index=prog_entry['viewpoint_index'] + 1, duration=duration)
                        self.task_durations.append(duration)
                    else:
                        self.log_message_ui("log_task_error_format", "ERROR", is_key=True,
                                            index=prog_entry['viewpoint_index'] + 1,
                                            error_message=prog_entry.get('error_message', 'Unknown Error'))
                    self.viewpoint_progress_text_var.set(S.get("viewpoint_progress_format",
                                                               completed=self.completed_tasks_count,
                                                               total=self.total_tasks_for_conversion))
                    if self.total_tasks_for_conversion > 0:
                        self.progress_bar["value"] = (self.completed_tasks_count / self.total_tasks_for_conversion) * 100
        except (multiprocessing.queues.Empty, AttributeError, EOFError, FileNotFoundError):
            pass
        except Exception as e:
            print(f"Progress queue processing error: {type(e).__name__} - {e}")

        if self.conversion_pool:
            if self.start_time > 0:
                self.elapsed_time_str = str(timedelta(seconds=int(time.time() - self.start_time)))
            if new_task_completed_this_cycle and self.total_tasks_for_conversion > 0 and self.completed_tasks_count > 0:
                if self.task_durations:
                    self.avg_time_per_viewpoint_for_estimation = sum(self.task_durations) / len(self.task_durations)
                if self.avg_time_per_viewpoint_for_estimation > 0:
                    remaining_tasks = self.total_tasks_for_conversion - self.completed_tasks_count
                    try:
                        num_parallel_processes = int(self.parallel_processes_var.get())
                        if num_parallel_processes <= 0: num_parallel_processes = 1
                    except ValueError:
                        num_parallel_processes = 1
                    effective_parallelism = min(num_parallel_processes, remaining_tasks if remaining_tasks > 0 else 1)
                    if remaining_tasks > 0:
                        self.overall_remaining_seconds_at_last_avg_calculation = (remaining_tasks * self.avg_time_per_viewpoint_for_estimation) / effective_parallelism
                        self.timestamp_of_last_avg_calculation = time.time()
                    else:
                        self.overall_remaining_seconds_at_last_avg_calculation = 0
                        self.timestamp_of_last_avg_calculation = time.time()
            if self.overall_remaining_seconds_at_last_avg_calculation is not None and \
               self.timestamp_of_last_avg_calculation is not None:
                time_since_last_calc = time.time() - self.timestamp_of_last_avg_calculation
                current_remaining_estimate_sec = self.overall_remaining_seconds_at_last_avg_calculation - time_since_last_calc
                if current_remaining_estimate_sec < 0:
                    current_remaining_estimate_sec = 0
                self.overall_remaining_str = str(timedelta(seconds=int(current_remaining_estimate_sec)))
            elif self.start_time > 0:
                self.overall_remaining_str = S.get("time_display_remaining_calculating")
        self.update_time_label_display()
        all_tasks_accounted_for = (self.completed_tasks_count >= self.total_tasks_for_conversion and
                                   self.total_tasks_for_conversion > 0)
        is_cancelled = (self.cancel_event_mp and self.cancel_event_mp.is_set() and self.conversion_pool)
        if self.conversion_pool and ( (self.active_tasks_count == 0 and all_tasks_accounted_for) or is_cancelled ):
            if all_tasks_accounted_for and not is_cancelled:
                self.overall_remaining_str = "00:00:00"
                self.overall_remaining_seconds_at_last_avg_calculation = 0
                self.timestamp_of_last_avg_calculation = time.time()
            self.update_time_label_display()
            self.conversion_finished_or_cancelled_mp()
        elif self.conversion_pool or (self.manager_mp and self.log_queue_mp and not self.log_queue_mp.empty()):
            self.after(100, self.process_mp_queues)

    def update_time_label_display(self):
        is_converting = bool(self.conversion_pool)
        display_text = ""
        elapsed_text_key = "time_display_elapsed"
        remaining_text_key = "time_display_remaining_overall"
        if self.final_conversion_message and not is_converting:
            display_text = self.final_conversion_message
        elif not is_converting and self.start_time == 0:
            display_text = (f"{S.get(elapsed_text_key)}: 00:00:00 / "
                            f"{S.get(remaining_text_key)}: {S.get('time_display_not_started')}")
        else:
            display_text = (f"{S.get(elapsed_text_key)}: {self.elapsed_time_str} / "
                            f"{S.get(remaining_text_key)}: {self.overall_remaining_str}")
        if hasattr(self, 'time_label') and self.time_label.winfo_exists():
            self.time_label.config(text=display_text)

    def check_ffmpeg_ffprobe(self): # pylint: disable=too-many-try-statements
        try:
            res_ffmpeg = subprocess.run([self.ffmpeg_path, "-version"], capture_output=True, text=True, check=True,
                                        startupinfo=self.get_startupinfo(), encoding='utf-8', errors='replace')
            line_ffmpeg = res_ffmpeg.stdout.splitlines()[0] if res_ffmpeg.stdout else "ffmpeg (unknown version)"
            self.log_message_ui("log_ffmpeg_found_format", "INFO", is_key=True, version_line=line_ffmpeg.strip())
        except FileNotFoundError:
            self.log_message_ui("log_ffmpeg_not_found_format", "ERROR", is_key=True, path=self.ffmpeg_path)
            self.start_button.config(state="disabled")
        except subprocess.CalledProcessError as e:
            self.log_message_ui("log_ffmpeg_error_format", "ERROR", is_key=True, error=str(e))
            self.start_button.config(state="disabled")
        except Exception as e: # pylint: disable=broad-except
            self.log_message_ui("log_ffmpeg_unexpected_error_format", "ERROR", is_key=True, error=str(e))
            self.start_button.config(state="disabled")
        try:
            res_ffprobe = subprocess.run([self.ffprobe_path, "-version"], capture_output=True, text=True, check=True,
                                         startupinfo=self.get_startupinfo(), encoding='utf-8', errors='replace')
            line_ffprobe = res_ffprobe.stdout.splitlines()[0] if res_ffprobe.stdout else "ffprobe (unknown version)"
            self.log_message_ui("log_ffprobe_found_format", "INFO", is_key=True, version_line=line_ffprobe.strip())
        except FileNotFoundError:
            self.log_message_ui("log_ffprobe_not_found_format", "ERROR", is_key=True, path=self.ffprobe_path)
        except subprocess.CalledProcessError as e:
            self.log_message_ui("log_ffprobe_error_format", "ERROR", is_key=True, error=str(e))
        except Exception as e: # pylint: disable=broad-except
            self.log_message_ui("log_ffprobe_unexpected_error_format", "ERROR", is_key=True, error=str(e))

    def check_cuda_availability(self):
        try:
            res = subprocess.run([self.ffmpeg_path, "-hide_banner", "-hwaccels"],
                                 capture_output=True, text=True, check=False,
                                 startupinfo=self.get_startupinfo(), encoding='utf-8', errors='replace')
            if "cuda" in res.stdout.lower():
                self.cuda_available = True
                self.cuda_check.config(state="normal")
                self.cuda_var.set(True)
                self.log_message_ui("log_cuda_available", "INFO", is_key=True)
            else:
                self.cuda_available = False
                self.cuda_check.config(state="disabled")
                self.cuda_var.set(False)
                self.log_message_ui("log_cuda_unavailable", "INFO", is_key=True)
        except Exception as e: # pylint: disable=broad-except
            self.cuda_available = False
            self.cuda_check.config(state="disabled")
            self.cuda_var.set(False)
            self.log_message_ui("log_cuda_detection_error_format", "WARNING", is_key=True, error=str(e))
        self.apply_cuda_restrictions_based_on_video_info()

    def apply_cuda_restrictions_based_on_video_info(self):
        if not self.cuda_available:
            self.cuda_var.set(False)
            self.cuda_check.config(state="disabled")
            return
        is_high_res = (self.video_width > HIGH_RESOLUTION_THRESHOLD or
                       self.video_height > HIGH_RESOLUTION_THRESHOLD)
        if is_high_res and self.cuda_var.get():
            self.log_message_ui("log_cuda_high_res_test_info_format", "INFO", is_key=True,
                                width=self.video_width, height=self.video_height)

    def get_startupinfo(self):
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            return startupinfo
        return None

    def browse_input_file(self):
        file_path = filedialog.askopenfilename(
            title=S.get("browse_input_button_tooltip"),
            filetypes=((S.get("filetype_video_files"), "*.mp4 *.mov *.avi *.mkv *.insv *.insp"),
                       (S.get("filetype_all_files"), "*.*"))
        )
        if file_path:
            self.input_file_var.set(file_path)
            self.log_message_ui("log_input_file_selected", "INFO", is_key=True, filepath=file_path)
            if not self.output_folder_var.get():
                default_output_dir = os.path.dirname(file_path)
                self.output_folder_var.set(default_output_dir)
                self.log_message_ui("log_output_folder_auto_set", "INFO", is_key=True, folderpath=default_output_dir)
            self.get_video_info(file_path)
            self.cuda_checked_for_high_res_compatibility = False
            self.cuda_fallback_triggered_for_high_res = False
            self.cuda_compatibility_confirmed_for_high_res = False

    def browse_output_folder(self):
        folder_path = filedialog.askdirectory(title=S.get("browse_output_button_tooltip"))
        if folder_path:
            self.output_folder_var.set(folder_path)
            self.log_message_ui("log_output_folder_selected", "INFO", is_key=True, folderpath=folder_path)

    def browse_colmap_rig_folder(self):
        folder_path = filedialog.askdirectory(title=S.get("colmap_rig_folder_browse_title"))
        if folder_path:
            self.colmap_rig_folder_var.set(folder_path)
            self._update_postshot_default_for_rig(folder_path)
            self.log_message_ui("log_colmap_rig_folder_selected_format", "INFO", is_key=True, folderpath=folder_path)

    def browse_colmap_exec_path(self):
        file_path = filedialog.askopenfilename(title=S.get("colmap_exec_browse_title"))
        if file_path:
            self.colmap_exec_path_var.set(file_path)
            self.log_message_ui("log_colmap_exec_selected_format", "INFO", is_key=True, filepath=file_path)
            self._auto_detect_vocab_tree_path(file_path, log_missing=True)

    def browse_colmap_vocab_tree_path(self):
        file_path = filedialog.askopenfilename(title=S.get("colmap_vocab_tree_browse_title"),
                                               filetypes=((S.get("filetype_vocab_tree"), "*.bin"),
                                                          (S.get("filetype_all_files"), "*.*")))
        if file_path:
            self._set_vocab_tree_path(file_path, "user")
            self.log_message_ui("log_colmap_vocab_tree_selected_format", "INFO", is_key=True, filepath=file_path)

    def _auto_detect_vocab_tree_path(self, colmap_exec_path, log_missing=False):
        if not colmap_exec_path:
            return None
        if self.colmap_vocab_tree_path_source == "user":
            return self.colmap_vocab_tree_path_var.get().strip()
        detected = find_vocab_tree_path(colmap_exec_path)
        if detected:
            if (self.colmap_vocab_tree_path_var.get().strip() != detected or
                    self.colmap_vocab_tree_path_source != "auto"):
                self._set_vocab_tree_path(detected, "auto")
                self.log_message_ui("log_colmap_vocab_tree_auto_detected_format", "INFO", is_key=True, path=detected)
        elif log_missing:
            self.log_message_ui("log_colmap_vocab_tree_auto_not_found_format", "WARNING", is_key=True, path=colmap_exec_path)
        return self.colmap_vocab_tree_path_var.get().strip()

    def browse_postshot_folder(self):
        folder_path = filedialog.askdirectory(title=S.get("colmap_postshot_output_browse_title"))
        if folder_path:
            self.colmap_postshot_folder_var.set(folder_path)
            self.colmap_postshot_default = folder_path
            self.log_message_ui("log_colmap_postshot_folder_selected_format", "INFO", is_key=True, folderpath=folder_path)

    def _update_postshot_default_for_rig(self, rig_folder):
        default_postshot = os.path.join(rig_folder, "postshot")
        current_postshot = self.colmap_postshot_folder_var.get()
        if not current_postshot or current_postshot == self.colmap_postshot_default:
            self.colmap_postshot_default = default_postshot
            self.colmap_postshot_folder_var.set(default_postshot)

    def get_video_info(self, filepath): # pylint: disable=too-many-branches
        try:
            cmd = [self.ffprobe_path, "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=width,height,duration,r_frame_rate,codec_name",
                   "-of", "json", filepath]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True,
                                 startupinfo=self.get_startupinfo(), encoding='utf-8', errors='replace')
            if not res.stdout.strip():
                self.log_message_ui("log_video_info_error_ffprobe_empty_output_format", "ERROR", is_key=True, filepath=filepath)
                self.video_width, self.video_height, self.video_duration, self.video_fps = 0,0,0.0,0.0
                self.update_resolution_options(); return
            info_data = json.loads(res.stdout)
            if not info_data.get("streams") or not info_data["streams"][0]:
                self.log_message_ui("log_video_info_error_ffprobe_empty_output_format", "ERROR", is_key=True,
                                    details="JSON structure missing 'streams' or stream data.", filepath=filepath)
                self.video_width, self.video_height, self.video_duration, self.video_fps = 0,0,0.0,0.0
                self.update_resolution_options(); return
            stream_info = info_data["streams"][0]
            self.video_width = int(stream_info.get("width", 0))
            self.video_height = int(stream_info.get("height", 0))
            duration_str = stream_info.get("duration", "0.0")
            try:
                self.video_duration = float(duration_str)
                if self.video_duration < 0: self.video_duration = 0.0
            except (ValueError, TypeError):
                self.video_duration = 0.0
                self.log_message_ui(f"Warning: Invalid duration '{duration_str}' in video info. Using 0.0s.", "WARNING")
            r_fps_str = stream_info.get("r_frame_rate", "0/0")
            if '/' in r_fps_str:
                num_str, den_str = r_fps_str.split('/')
                try:
                    num, den = int(num_str), int(den_str)
                    self.video_fps = (num / den) if den > 0 else 0.0
                except ValueError:
                    self.video_fps = 0.0
                    self.log_message_ui(f"Warning: Invalid r_frame_rate '{r_fps_str}'. Using 0.0fps.", "WARNING")
            else:
                try: self.video_fps = float(r_fps_str)
                except ValueError:
                    self.video_fps = 0.0
                    self.log_message_ui(f"Warning: Invalid r_frame_rate '{r_fps_str}'. Using 0.0fps.", "WARNING")
            codec = stream_info.get("codec_name", "Unknown")
            self.log_message_ui("log_video_info_format", "INFO", is_key=True,
                                width=self.video_width, height=self.video_height,
                                duration=self.video_duration, fps=self.video_fps, codec=codec)
        except subprocess.CalledProcessError as e:
            self.log_message_ui("log_video_info_error_ffprobe_failed_format", "ERROR", is_key=True, error=(e.stderr or str(e)))
            self.video_width, self.video_height, self.video_duration, self.video_fps = 0,0,0.0,0.0
        except json.JSONDecodeError:
            output_text = res.stdout if 'res' in locals() and hasattr(res, 'stdout') else 'N/A'
            self.log_message_ui("log_video_info_error_json_parse_failed_format", "ERROR", is_key=True, output=output_text)
            self.video_width, self.video_height, self.video_duration, self.video_fps = 0,0,0.0,0.0
        except Exception as e: # pylint: disable=broad-except
            self.log_message_ui("log_video_info_error_unexpected_format", "ERROR", is_key=True, error=str(e))
            self.video_width, self.video_height, self.video_duration, self.video_fps = 0,0,0.0,0.0
        finally:
            self.update_resolution_options()
            self.apply_cuda_restrictions_based_on_video_info()

    def update_resolution_options(self, event=None): # pylint: disable=unused-argument
        selected_resolution_mode_text = self.resolution_var.get()
        if selected_resolution_mode_text == S.get("resolution_custom"):
            self.custom_resolution_entry.config(state="normal")
        else:
            self.custom_resolution_entry.config(state="disabled")
            if selected_resolution_mode_text == S.get("resolution_auto"):
                auto_res = self.video_height if self.video_height > 0 else DEFAULT_RESOLUTION_WIDTH
                self.custom_resolution_var.set(str(auto_res))
            elif selected_resolution_mode_text.isdigit():
                self.custom_resolution_var.set(selected_resolution_mode_text)
            else: self.custom_resolution_var.set(str(DEFAULT_RESOLUTION_WIDTH))

    def update_output_format_options(self, event=None): # pylint: disable=unused-argument
        selected_format = self.output_format_var.get()
        selected_mode = self.output_mode_var.get()
        is_converting = bool(self.conversion_pool)
        is_colmap_mode = selected_mode == "colmap_rig"
        normal_state_if_not_converting = tk.NORMAL if not is_converting else tk.DISABLED
        readonly_state_if_not_converting = "readonly" if not is_converting else tk.DISABLED
        disabled_state_always = tk.DISABLED
        if is_colmap_mode and selected_format == "video":
            self.output_format_var.set("png")
            selected_format = "png"
        self.video_radio.config(state=normal_state_if_not_converting if not is_colmap_mode else tk.DISABLED)
        self.png_frame_interval_entry.config(state=normal_state_if_not_converting if selected_format == "png" else disabled_state_always)
        self.png_pred_combo.config(state=readonly_state_if_not_converting if selected_format == "png" else disabled_state_always)
        self.jpeg_frame_interval_entry.config(state=normal_state_if_not_converting if selected_format == "jpeg" else disabled_state_always)
        self.jpeg_quality_entry.config(state=normal_state_if_not_converting if selected_format == "jpeg" else disabled_state_always)
        self.preset_combo.config(state=readonly_state_if_not_converting if selected_format == "video" else disabled_state_always)
        self.cq_entry.config(state=normal_state_if_not_converting if selected_format == "video" else disabled_state_always)

    def update_colmap_controls_state(self):
        colmap_enabled = not self.conversion_pool and not self.colmap_running
        entry_state = tk.NORMAL if colmap_enabled else tk.DISABLED
        browse_state = tk.NORMAL if colmap_enabled else tk.DISABLED
        matcher_state = "readonly" if colmap_enabled else tk.DISABLED
        preset_state = "readonly" if colmap_enabled else tk.DISABLED
        run_state = tk.NORMAL if colmap_enabled else tk.DISABLED
        cancel_state = tk.NORMAL if self.colmap_running else tk.DISABLED

        self.colmap_rig_entry.config(state=entry_state)
        self.colmap_rig_browse.config(state=browse_state)
        self.colmap_exec_entry.config(state=entry_state)
        self.colmap_exec_browse.config(state=browse_state)
        self.colmap_preset_combo.config(state=preset_state)
        self.colmap_advanced_button.config(state=run_state)
        self.colmap_matcher_combo.config(state=matcher_state)
        self.colmap_postshot_entry.config(state=entry_state)
        self.colmap_postshot_browse.config(state=browse_state)
        self.colmap_run_button.config(state=run_state)
        self.colmap_cancel_button.config(state=cancel_state)
        self._update_colmap_vocab_tree_state(colmap_enabled)

    def _update_colmap_vocab_tree_state(self, colmap_enabled=None):
        if colmap_enabled is None:
            colmap_enabled = not self.conversion_pool and not self.colmap_running
        enable_vocab_tree = colmap_enabled and self.colmap_matcher_var.get().strip() == "vocab_tree"
        entry_state = tk.NORMAL if enable_vocab_tree else tk.DISABLED
        self.colmap_vocab_tree_entry.config(state=entry_state)
        self.colmap_vocab_tree_browse.config(state=entry_state)

    def _get_colmap_preset_key(self):
        display = self.colmap_preset_var.get()
        return self.colmap_preset_key_by_display.get(display, COLMAP_DEFAULT_PRESET_KEY)

    def _get_colmap_preset_display_name(self, preset_key):
        return self.colmap_preset_display_by_key.get(preset_key, preset_key)

    def on_colmap_preset_changed(self, event=None, log=True): # pylint: disable=unused-argument
        preset_key = self._get_colmap_preset_key()
        preset = COLMAP_PRESETS.get(preset_key) or COLMAP_PRESETS.get(COLMAP_DEFAULT_PRESET_KEY, {})
        preset_matcher = preset.get("matcher", "sequential")
        self.colmap_advanced_overrides = {}
        if preset_matcher in self.colmap_matcher_options:
            self.colmap_matcher_var.set(preset_matcher)
        else:
            self.colmap_matcher_var.set("sequential")
        self._update_colmap_vocab_tree_state()
        if log:
            self.log_message_ui("log_colmap_preset_selected_format", "INFO", is_key=True,
                                preset=self._get_colmap_preset_display_name(preset_key))

    def on_colmap_matcher_changed(self, event=None): # pylint: disable=unused-argument
        self._update_colmap_vocab_tree_state()
        if self.colmap_matcher_var.get().strip() == "vocab_tree":
            colmap_exec = self.resolve_colmap_executable()
            if colmap_exec:
                self._auto_detect_vocab_tree_path(colmap_exec, log_missing=False)

    def _set_vocab_tree_path(self, path, source):
        self._setting_vocab_tree_path = True
        try:
            self.colmap_vocab_tree_path_var.set(path)
        finally:
            self._setting_vocab_tree_path = False
        self.colmap_vocab_tree_path_source = source

    def _on_vocab_tree_path_changed(self, *args): # pylint: disable=unused-argument
        if self._setting_vocab_tree_path:
            return
        value = self.colmap_vocab_tree_path_var.get().strip()
        self.colmap_vocab_tree_path_source = "user" if value else None

    def open_colmap_advanced_dialog(self):
        if self.colmap_running or self.conversion_pool:
            return
        if self.colmap_advanced_dialog and self.colmap_advanced_dialog.winfo_exists():
            self.colmap_advanced_dialog.lift()
            return

        preset_key = self._get_colmap_preset_key()
        preset = COLMAP_PRESETS.get(preset_key) or COLMAP_PRESETS.get(COLMAP_DEFAULT_PRESET_KEY, {})
        preset_options = preset.get("options", {})
        effective_options = merge_options({}, preset_options, self.colmap_advanced_overrides)

        def get_option(section, key, default=None):
            return effective_options.get(section, {}).get(key, default)

        def as_str(value):
            return "" if value is None else str(value)

        def as_int(value, default=0):
            if value is None:
                return default
            try:
                return 1 if int(value) != 0 else 0
            except (TypeError, ValueError):
                return default

        dialog = tk.Toplevel(self)
        self.colmap_advanced_dialog = dialog
        dialog.title(S.get("colmap_advanced_title"))
        dialog.transient(self)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        feature_frame = ttk.LabelFrame(main_frame, text=S.get("colmap_advanced_feature_label"), padding=5)
        feature_frame.pack(fill=tk.X, pady=(0, 6))
        matching_frame = ttk.LabelFrame(main_frame, text=S.get("colmap_advanced_matching_label"), padding=5)
        matching_frame.pack(fill=tk.X, pady=(0, 6))
        mapper_frame = ttk.LabelFrame(main_frame, text=S.get("colmap_advanced_mapper_label"), padding=5)
        mapper_frame.pack(fill=tk.X, pady=(0, 6))
        loop_frame = ttk.LabelFrame(main_frame, text=S.get("colmap_advanced_loop_label"), padding=5)
        loop_frame.pack(fill=tk.X)

        max_num_features_var = tk.StringVar(value=as_str(get_option("feature", "SiftExtraction.max_num_features")))
        max_image_size_var = tk.StringVar(value=as_str(get_option("feature", "SiftExtraction.max_image_size")))
        peak_threshold_var = tk.StringVar(value=as_str(get_option("feature", "SiftExtraction.peak_threshold")))
        estimate_affine_var = tk.IntVar(value=as_int(get_option("feature", "SiftExtraction.estimate_affine_shape", 0)))
        dsp_var = tk.IntVar(value=as_int(get_option("feature", "SiftExtraction.domain_size_pooling", 0)))

        guided_matching_var = tk.IntVar(value=as_int(get_option("matcher", "SiftMatching.guided_matching", 0)))
        max_ratio_var = tk.StringVar(value=as_str(get_option("matcher", "SiftMatching.max_ratio")))
        max_distance_var = tk.StringVar(value=as_str(get_option("matcher", "SiftMatching.max_distance")))

        rig_flex_var = tk.IntVar(value=as_int(get_option("mapper", "Mapper.ba_refine_sensor_from_rig", 0)))
        ba_global_images_ratio_var = tk.StringVar(value=as_str(get_option("mapper", "Mapper.ba_global_images_ratio")))
        ba_global_points_ratio_var = tk.StringVar(value=as_str(get_option("mapper", "Mapper.ba_global_points_ratio")))

        loop_detection_var = tk.IntVar(value=as_int(get_option("matcher", "SequentialMatching.loop_detection", 0)))
        loop_num_images_var = tk.StringVar(value=as_str(get_option("matcher", "SequentialMatching.loop_detection_num_images")))
        loop_num_neighbors_var = tk.StringVar(value=as_str(get_option("matcher", "SequentialMatching.loop_detection_num_nearest_neighbors")))
        loop_num_checks_var = tk.StringVar(value=as_str(get_option("matcher", "SequentialMatching.loop_detection_num_checks")))
        loop_num_after_ver_var = tk.StringVar(value=as_str(get_option("matcher", "SequentialMatching.loop_detection_num_images_after_verification")))
        loop_max_features_var = tk.StringVar(value=as_str(get_option("matcher", "SequentialMatching.loop_detection_max_num_features")))

        def add_labeled_entry(frame, row, label_key, var):
            ttk.Label(frame, text=S.get(label_key)).grid(row=row, column=0, padx=5, pady=2, sticky=tk.W)
            entry = ttk.Entry(frame, textvariable=var, width=12)
            entry.grid(row=row, column=1, padx=5, pady=2, sticky=tk.W)
            return entry

        add_labeled_entry(feature_frame, 0, "colmap_advanced_max_num_features_label", max_num_features_var)
        add_labeled_entry(feature_frame, 1, "colmap_advanced_max_image_size_label", max_image_size_var)
        add_labeled_entry(feature_frame, 2, "colmap_advanced_peak_threshold_label", peak_threshold_var)
        ttk.Checkbutton(feature_frame, text=S.get("colmap_advanced_estimate_affine_label"),
                        variable=estimate_affine_var).grid(row=3, column=0, columnspan=2, padx=5, pady=2, sticky=tk.W)
        ttk.Checkbutton(feature_frame, text=S.get("colmap_advanced_domain_size_pooling_label"),
                        variable=dsp_var).grid(row=4, column=0, columnspan=2, padx=5, pady=2, sticky=tk.W)

        ttk.Checkbutton(matching_frame, text=S.get("colmap_advanced_guided_matching_label"),
                        variable=guided_matching_var).grid(row=0, column=0, columnspan=2, padx=5, pady=2, sticky=tk.W)
        add_labeled_entry(matching_frame, 1, "colmap_advanced_max_ratio_label", max_ratio_var)
        add_labeled_entry(matching_frame, 2, "colmap_advanced_max_distance_label", max_distance_var)

        ttk.Checkbutton(mapper_frame, text=S.get("colmap_advanced_rig_flex_label"),
                        variable=rig_flex_var).grid(row=0, column=0, columnspan=2, padx=5, pady=2, sticky=tk.W)
        add_labeled_entry(mapper_frame, 1, "colmap_advanced_ba_global_images_ratio_label", ba_global_images_ratio_var)
        add_labeled_entry(mapper_frame, 2, "colmap_advanced_ba_global_points_ratio_label", ba_global_points_ratio_var)

        loop_detection_check = ttk.Checkbutton(loop_frame, text=S.get("colmap_advanced_loop_detection_label"),
                                              variable=loop_detection_var)
        loop_detection_check.grid(row=0, column=0, columnspan=2, padx=5, pady=2, sticky=tk.W)
        loop_num_images_entry = add_labeled_entry(loop_frame, 1, "colmap_advanced_loop_num_images_label", loop_num_images_var)
        loop_num_neighbors_entry = add_labeled_entry(loop_frame, 2, "colmap_advanced_loop_num_neighbors_label", loop_num_neighbors_var)
        loop_num_checks_entry = add_labeled_entry(loop_frame, 3, "colmap_advanced_loop_num_checks_label", loop_num_checks_var)
        loop_num_after_ver_entry = add_labeled_entry(loop_frame, 4, "colmap_advanced_loop_num_after_ver_label", loop_num_after_ver_var)
        loop_max_features_entry = add_labeled_entry(loop_frame, 5, "colmap_advanced_loop_max_features_label", loop_max_features_var)

        loop_entries = [
            loop_num_images_entry, loop_num_neighbors_entry, loop_num_checks_entry,
            loop_num_after_ver_entry, loop_max_features_entry
        ]

        def update_loop_state():
            enable_loop = self.colmap_matcher_var.get().strip() == "sequential"
            if not enable_loop:
                loop_detection_var.set(0)
            state = tk.NORMAL if (enable_loop and loop_detection_var.get()) else tk.DISABLED
            loop_detection_check.config(state=tk.NORMAL if enable_loop else tk.DISABLED)
            for entry in loop_entries:
                entry.config(state=state)

        def on_loop_toggle():
            update_loop_state()

        loop_detection_check.config(command=on_loop_toggle)
        update_loop_state()

        def reset_to_preset():
            max_num_features_var.set(as_str(preset_options.get("feature", {}).get("SiftExtraction.max_num_features")))
            max_image_size_var.set(as_str(preset_options.get("feature", {}).get("SiftExtraction.max_image_size")))
            peak_threshold_var.set(as_str(preset_options.get("feature", {}).get("SiftExtraction.peak_threshold")))
            estimate_affine_var.set(as_int(preset_options.get("feature", {}).get("SiftExtraction.estimate_affine_shape", 0)))
            dsp_var.set(as_int(preset_options.get("feature", {}).get("SiftExtraction.domain_size_pooling", 0)))
            guided_matching_var.set(as_int(preset_options.get("matcher", {}).get("SiftMatching.guided_matching", 0)))
            max_ratio_var.set(as_str(preset_options.get("matcher", {}).get("SiftMatching.max_ratio")))
            max_distance_var.set(as_str(preset_options.get("matcher", {}).get("SiftMatching.max_distance")))
            rig_flex_var.set(as_int(preset_options.get("mapper", {}).get("Mapper.ba_refine_sensor_from_rig", 0)))
            ba_global_images_ratio_var.set(as_str(preset_options.get("mapper", {}).get("Mapper.ba_global_images_ratio")))
            ba_global_points_ratio_var.set(as_str(preset_options.get("mapper", {}).get("Mapper.ba_global_points_ratio")))
            loop_detection_var.set(as_int(preset_options.get("matcher", {}).get("SequentialMatching.loop_detection", 0)))
            loop_num_images_var.set(as_str(preset_options.get("matcher", {}).get("SequentialMatching.loop_detection_num_images")))
            loop_num_neighbors_var.set(as_str(preset_options.get("matcher", {}).get("SequentialMatching.loop_detection_num_nearest_neighbors")))
            loop_num_checks_var.set(as_str(preset_options.get("matcher", {}).get("SequentialMatching.loop_detection_num_checks")))
            loop_num_after_ver_var.set(as_str(preset_options.get("matcher", {}).get("SequentialMatching.loop_detection_num_images_after_verification")))
            loop_max_features_var.set(as_str(preset_options.get("matcher", {}).get("SequentialMatching.loop_detection_max_num_features")))
            update_loop_state()

        def on_ok():
            overrides = {}

            def preset_value(section, key, default=None):
                return preset_options.get(section, {}).get(key, default)

            def maybe_set(section, key, value, default=None):
                if isinstance(value, str):
                    value = value.strip()
                if value is None or value == "":
                    return
                preset_val = preset_value(section, key, default)
                if str(preset_val) == str(value):
                    return
                overrides.setdefault(section, {})[key] = value

            maybe_set("feature", "SiftExtraction.max_num_features", max_num_features_var.get())
            maybe_set("feature", "SiftExtraction.max_image_size", max_image_size_var.get())
            maybe_set("feature", "SiftExtraction.peak_threshold", peak_threshold_var.get())
            maybe_set("feature", "SiftExtraction.estimate_affine_shape", estimate_affine_var.get(), 0)
            maybe_set("feature", "SiftExtraction.domain_size_pooling", dsp_var.get(), 0)
            maybe_set("matcher", "SiftMatching.guided_matching", guided_matching_var.get(), 0)
            maybe_set("matcher", "SiftMatching.max_ratio", max_ratio_var.get())
            maybe_set("matcher", "SiftMatching.max_distance", max_distance_var.get())
            maybe_set("mapper", "Mapper.ba_refine_sensor_from_rig", rig_flex_var.get(), 0)
            maybe_set("mapper", "Mapper.ba_global_images_ratio", ba_global_images_ratio_var.get())
            maybe_set("mapper", "Mapper.ba_global_points_ratio", ba_global_points_ratio_var.get())
            maybe_set("matcher", "SequentialMatching.loop_detection", loop_detection_var.get(), 0)
            if loop_detection_var.get():
                maybe_set("matcher", "SequentialMatching.loop_detection_num_images", loop_num_images_var.get())
                maybe_set("matcher", "SequentialMatching.loop_detection_num_nearest_neighbors", loop_num_neighbors_var.get())
                maybe_set("matcher", "SequentialMatching.loop_detection_num_checks", loop_num_checks_var.get())
                maybe_set("matcher", "SequentialMatching.loop_detection_num_images_after_verification", loop_num_after_ver_var.get())
                maybe_set("matcher", "SequentialMatching.loop_detection_max_num_features", loop_max_features_var.get())

            self.colmap_advanced_overrides = overrides
            self.colmap_advanced_dialog = None
            dialog.destroy()

        def on_cancel():
            self.colmap_advanced_dialog = None
            dialog.destroy()

        def on_close():
            self.colmap_advanced_dialog = None
            dialog.destroy()

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(button_frame, text=S.get("colmap_advanced_reset_button"), command=reset_to_preset).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text=S.get("colmap_advanced_ok_button"), command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text=S.get("colmap_advanced_cancel_button"), command=on_cancel).pack(side=tk.RIGHT)

        dialog.protocol("WM_DELETE_WINDOW", on_close)

    def validate_inputs(self): # pylint: disable=too-many-return-statements, too-many-branches
        if not (self.input_file_var.get() and os.path.isfile(self.input_file_var.get())):
            self.log_message_ui("validate_error_input_file_invalid", "ERROR", is_key=True); return False
        if not (self.output_folder_var.get() and os.path.isdir(self.output_folder_var.get())):
            self.log_message_ui("validate_error_output_folder_invalid", "ERROR", is_key=True); return False
        selected_format = self.output_format_var.get()
        if self.output_mode_var.get() == "colmap_rig" and selected_format == "video":
            self.log_message_ui("validate_error_colmap_video_not_supported", "ERROR", is_key=True); return False
        if selected_format in ["png", "jpeg"]:
            try:
                interval = float(self.frame_interval_var.get())
                if interval <= 1e-6:
                    self.log_message_ui("validate_error_frame_interval_positive", "ERROR", is_key=True); return False
                if self.video_duration > 0 and interval > self.video_duration:
                    self.log_message_ui("validate_warning_frame_interval_too_long_format", "WARNING", is_key=True,
                                        interval=interval, duration=self.video_duration)
            except ValueError:
                self.log_message_ui("validate_error_frame_interval_numeric", "ERROR", is_key=True); return False
            if selected_format == "jpeg":
                try:
                    jpeg_q = int(self.jpeg_quality_var.get())
                    if not (1 <= jpeg_q <= 100):
                        self.log_message_ui("validate_error_jpeg_quality_range", "ERROR", is_key=True); return False
                except ValueError:
                    self.log_message_ui("validate_error_jpeg_quality_integer", "ERROR", is_key=True); return False
        elif selected_format == "video":
            try:
                cq_crf_value = int(self.cq_var.get())
                if not (0 <= cq_crf_value <= 51):
                    self.log_message_ui("validate_error_video_quality_range", "ERROR", is_key=True); return False
            except ValueError:
                self.log_message_ui("validate_error_video_quality_integer", "ERROR", is_key=True); return False
        try:
            width, height = self.get_output_resolution()
            if width <= 0 or height <= 0:
                self.log_message_ui("validate_error_resolution_positive", "ERROR", is_key=True); return False
        except ValueError:
            self.log_message_ui("validate_error_resolution_invalid_numeric", "ERROR", is_key=True); return False
        except Exception as e: # pylint: disable=broad-except
            self.log_message_ui("validate_error_resolution_general_format", "ERROR", is_key=True, error=str(e)); return False
        return True

    def _validate_colmap_numeric_options(self, options):
        int_positive_keys = {
            "SiftExtraction.max_num_features",
            "SiftExtraction.max_image_size",
            "SequentialMatching.loop_detection_num_images",
            "SequentialMatching.loop_detection_num_nearest_neighbors",
            "SequentialMatching.loop_detection_num_checks",
            "SequentialMatching.loop_detection_num_images_after_verification",
            "SequentialMatching.loop_detection_max_num_features",
        }
        float_positive_keys = {
            "SiftExtraction.peak_threshold",
            "SiftMatching.max_distance",
            "Mapper.ba_global_images_ratio",
            "Mapper.ba_global_points_ratio",
        }
        float_ratio_keys = {
            "SiftMatching.max_ratio",
        }
        bool_keys = {
            "SiftExtraction.estimate_affine_shape",
            "SiftExtraction.domain_size_pooling",
            "SiftMatching.guided_matching",
            "Mapper.ba_refine_sensor_from_rig",
            "SequentialMatching.loop_detection",
        }

        validated = {}
        for section, values in (options or {}).items():
            if not values:
                continue
            validated_section = {}
            for key, value in values.items():
                if key in bool_keys:
                    try:
                        parsed = int(value)
                    except (TypeError, ValueError):
                        self.log_message_ui("log_colmap_pipeline_option_invalid_format", "ERROR", is_key=True,
                                            option=key, value=value)
                        return None
                    if parsed not in (0, 1):
                        self.log_message_ui("log_colmap_pipeline_option_invalid_format", "ERROR", is_key=True,
                                            option=key, value=value)
                        return None
                    validated_section[key] = parsed
                    continue
                if key in int_positive_keys:
                    try:
                        parsed = int(value)
                    except (TypeError, ValueError):
                        self.log_message_ui("log_colmap_pipeline_option_invalid_format", "ERROR", is_key=True,
                                            option=key, value=value)
                        return None
                    if parsed <= 0:
                        self.log_message_ui("log_colmap_pipeline_option_invalid_format", "ERROR", is_key=True,
                                            option=key, value=value)
                        return None
                    validated_section[key] = parsed
                    continue
                if key in float_positive_keys:
                    try:
                        parsed = float(value)
                    except (TypeError, ValueError):
                        self.log_message_ui("log_colmap_pipeline_option_invalid_format", "ERROR", is_key=True,
                                            option=key, value=value)
                        return None
                    if parsed <= 0:
                        self.log_message_ui("log_colmap_pipeline_option_invalid_format", "ERROR", is_key=True,
                                            option=key, value=value)
                        return None
                    validated_section[key] = parsed
                    continue
                if key in float_ratio_keys:
                    try:
                        parsed = float(value)
                    except (TypeError, ValueError):
                        self.log_message_ui("log_colmap_pipeline_option_invalid_format", "ERROR", is_key=True,
                                            option=key, value=value)
                        return None
                    if parsed <= 0 or parsed > 1:
                        self.log_message_ui("log_colmap_pipeline_option_invalid_format", "ERROR", is_key=True,
                                            option=key, value=value)
                        return None
                    validated_section[key] = parsed
                    continue
                validated_section[key] = value
            if validated_section:
                validated[section] = validated_section
        return validated

    def resolve_colmap_executable(self):
        raw_path = self.colmap_exec_path_var.get().strip()
        if not raw_path:
            raw_path = "colmap.exe" if os.name == 'nt' else "colmap"
        if os.path.isfile(raw_path):
            return raw_path
        resolved = shutil.which(raw_path)
        return resolved

    def validate_colmap_pipeline_inputs(self):
        rig_folder = self.colmap_rig_folder_var.get().strip()
        if not rig_folder or not os.path.isdir(rig_folder):
            self.log_message_ui("log_colmap_pipeline_invalid_rig_folder_format", "ERROR", is_key=True, path=rig_folder)
            return None
        images_dir = os.path.join(rig_folder, "images")
        if not os.path.isdir(images_dir):
            self.log_message_ui("log_colmap_pipeline_missing_images_format", "ERROR", is_key=True, path=images_dir)
            return None
        rig_config = os.path.join(rig_folder, "rig_config.json")
        if not os.path.isfile(rig_config):
            self.log_message_ui("log_colmap_pipeline_missing_rig_config_format", "ERROR", is_key=True, path=rig_config)
            return None
        colmap_exec = self.resolve_colmap_executable()
        if not colmap_exec:
            self.log_message_ui("log_colmap_pipeline_colmap_not_found_format", "ERROR", is_key=True,
                                path=self.colmap_exec_path_var.get().strip())
            return None
        postshot_output = self.colmap_postshot_folder_var.get().strip()
        if not postshot_output:
            postshot_output = os.path.join(rig_folder, "postshot")
            self.colmap_postshot_default = postshot_output
            self.colmap_postshot_folder_var.set(postshot_output)
        preset_key = self._get_colmap_preset_key()
        preset = COLMAP_PRESETS.get(preset_key) or COLMAP_PRESETS.get(COLMAP_DEFAULT_PRESET_KEY, {})
        preset_matcher = preset.get("matcher", "sequential")
        matcher = self.colmap_matcher_var.get().strip() or preset_matcher
        if matcher not in self.colmap_matcher_options:
            matcher = preset_matcher if preset_matcher in self.colmap_matcher_options else "sequential"
            self.colmap_matcher_var.set(matcher)
        options = merge_options({}, preset.get("options", {}), self.colmap_advanced_overrides)
        options = self._validate_colmap_numeric_options(options)
        if options is None:
            return None

        matcher_options = options.get("matcher", {})
        if matcher != "sequential":
            matcher_options = {key: value for key, value in matcher_options.items()
                               if not str(key).startswith("SequentialMatching.")}
        if matcher != "vocab_tree":
            matcher_options = {key: value for key, value in matcher_options.items()
                               if not str(key).startswith("VocabTreeMatching.")}
        if matcher_options:
            options["matcher"] = matcher_options
        else:
            options.pop("matcher", None)
        loop_detection_enabled = matcher == "sequential" and int(options.get("matcher", {}).get("SequentialMatching.loop_detection", 0) or 0) != 0
        needs_vocab_tree = matcher == "vocab_tree" or loop_detection_enabled
        vocab_tree_path = self.colmap_vocab_tree_path_var.get().strip()
        if needs_vocab_tree and not vocab_tree_path:
            vocab_tree_path = self._auto_detect_vocab_tree_path(colmap_exec, log_missing=True) or ""
        if needs_vocab_tree and not vocab_tree_path:
            self.log_message_ui("log_colmap_vocab_tree_required_format", "ERROR", is_key=True)
            return None
        if vocab_tree_path:
            if matcher == "vocab_tree":
                options.setdefault("matcher", {})["VocabTreeMatching.vocab_tree_path"] = vocab_tree_path
            if loop_detection_enabled:
                options.setdefault("matcher", {})["SequentialMatching.vocab_tree_path"] = vocab_tree_path
        return {
            "rig_folder": rig_folder,
            "images_dir": images_dir,
            "rig_config": rig_config,
            "colmap_exec": colmap_exec,
            "postshot_output": postshot_output,
            "matcher": matcher,
            "preset_key": preset_key,
            "options": options,
            "vocab_tree_path": vocab_tree_path
        }

    def log_message_ui_threadsafe(self, message_key_or_literal, level="INFO", is_key=False, *args, **kwargs):
        self.after(0, lambda: self.log_message_ui(message_key_or_literal, level, is_key, *args, **kwargs))

    def _now_iso_timestamp(self):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _get_colmap_pipeline_state_path(self, rig_folder):
        return os.path.join(rig_folder, "colmap_pipeline_state.json")

    def _load_colmap_pipeline_state(self, state_path):
        if not state_path or not os.path.isfile(state_path):
            return None
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e: # pylint: disable=broad-except
            self.log_message_ui("log_colmap_pipeline_state_load_failed_format", "WARNING", is_key=True, error=str(e))
            return None

    def _write_colmap_pipeline_state(self, state_path, state_data, last_step=None, threadsafe=False):
        if not state_path or not state_data:
            return
        if last_step:
            state_data["last_completed_step"] = last_step
        state_data["updated_at"] = self._now_iso_timestamp()
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
        except Exception as e: # pylint: disable=broad-except
            if threadsafe:
                self.log_message_ui_threadsafe("log_colmap_pipeline_state_save_failed_format", "WARNING", is_key=True, error=str(e))
            else:
                self.log_message_ui("log_colmap_pipeline_state_save_failed_format", "WARNING", is_key=True, error=str(e))

    def _get_images_snapshot(self, images_dir):
        if not images_dir or not os.path.isdir(images_dir):
            return None
        count = 0
        latest_mtime = 0
        for root, _, files in os.walk(images_dir):
            for name in files:
                if not name.lower().endswith((".png", ".jpg", ".jpeg")):
                    continue
                count += 1
                try:
                    mtime = os.path.getmtime(os.path.join(root, name))
                except OSError:
                    continue
                latest_mtime = max(latest_mtime, int(mtime))
        return {"count": count, "latest_mtime": int(latest_mtime)}

    def _get_file_mtime(self, filepath):
        try:
            return int(os.path.getmtime(filepath))
        except OSError:
            return None

    def _compute_colmap_options_hash(self, preset_key, matcher, options):
        payload = {
            "preset_key": preset_key,
            "matcher": matcher,
            "options": options
        }
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _get_next_colmap_step(self, last_step):
        if last_step not in COLMAP_PIPELINE_STEPS:
            return COLMAP_PIPELINE_STEPS[0]
        idx = COLMAP_PIPELINE_STEPS.index(last_step)
        return COLMAP_PIPELINE_STEPS[min(idx + 1, len(COLMAP_PIPELINE_STEPS) - 1)]

    def _get_colmap_step_label(self, step):
        labels = {
            "feature_extractor": S.get("colmap_step_feature_extractor"),
            "rig_configurator": S.get("colmap_step_rig_configurator"),
            "matcher": S.get("colmap_step_matcher"),
            "mapper": S.get("colmap_step_mapper"),
            "image_undistorter": S.get("colmap_step_image_undistorter"),
        }
        return labels.get(step, step)

    def _determine_resume_default_step(self, state_data, rig_config_path, images_dir):
        default_step = COLMAP_PIPELINE_STEPS[0]
        if state_data and state_data.get("last_completed_step") in COLMAP_PIPELINE_STEPS:
            default_step = self._get_next_colmap_step(state_data["last_completed_step"])
        if not state_data:
            self.log_message_ui("log_colmap_pipeline_state_not_found", "WARNING", is_key=True)
            return default_step

        forced_step = None
        rig_mtime = self._get_file_mtime(rig_config_path)
        state_rig_mtime = state_data.get("rig_config_mtime")
        if state_rig_mtime is not None and rig_mtime is not None and int(state_rig_mtime) != int(rig_mtime):
            forced_step = "rig_configurator"
            self.log_message_ui("log_colmap_pipeline_resume_forced_rig_config", "WARNING", is_key=True)

        state_snapshot = state_data.get("images_snapshot")
        current_snapshot = self._get_images_snapshot(images_dir)
        if state_snapshot and current_snapshot:
            if (state_snapshot.get("count") != current_snapshot.get("count") or
                    state_snapshot.get("latest_mtime") != current_snapshot.get("latest_mtime")):
                forced_step = "feature_extractor"
                self.log_message_ui("log_colmap_pipeline_resume_forced_images", "WARNING", is_key=True)

        return forced_step if forced_step else default_step

    def _prompt_colmap_db_action(self, db_path):
        result = {"value": None}
        dialog = tk.Toplevel(self)
        dialog.title(S.get("colmap_db_action_title"))
        dialog.transient(self)
        dialog.grab_set()

        message = ttk.Label(dialog, text=S.get("colmap_db_action_message_format", path=db_path),
                            wraplength=420, justify=tk.LEFT)
        message.pack(padx=12, pady=(12, 8))

        button_frame = ttk.Frame(dialog)
        button_frame.pack(padx=12, pady=(0, 12))

        def choose(value):
            result["value"] = value
            dialog.destroy()

        ttk.Button(button_frame, text=S.get("colmap_db_action_overwrite_button"),
                   command=lambda: choose("overwrite")).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_frame, text=S.get("colmap_db_action_resume_button"),
                   command=lambda: choose("resume")).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_frame, text=S.get("colmap_db_action_cancel_button"),
                   command=lambda: choose(None)).pack(side=tk.LEFT, padx=4)

        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        self.wait_window(dialog)
        return result["value"]

    def _prompt_colmap_resume_step(self, default_step):
        result = {"value": None}
        dialog = tk.Toplevel(self)
        dialog.title(S.get("colmap_resume_step_title"))
        dialog.transient(self)
        dialog.grab_set()

        message = ttk.Label(dialog, text=S.get("colmap_resume_step_message"),
                            wraplength=420, justify=tk.LEFT)
        message.pack(padx=12, pady=(12, 8))

        step_var = tk.StringVar(value=default_step if default_step in COLMAP_PIPELINE_STEPS else COLMAP_PIPELINE_STEPS[0])
        for step in COLMAP_PIPELINE_STEPS:
            ttk.Radiobutton(dialog, text=self._get_colmap_step_label(step),
                            variable=step_var, value=step).pack(anchor=tk.W, padx=12)

        button_frame = ttk.Frame(dialog)
        button_frame.pack(padx=12, pady=(8, 12))

        def choose(value):
            result["value"] = value
            dialog.destroy()

        ttk.Button(button_frame, text=S.get("colmap_resume_step_ok_button"),
                   command=lambda: choose(step_var.get())).pack(side=tk.RIGHT, padx=4)
        ttk.Button(button_frame, text=S.get("colmap_resume_step_cancel_button"),
                   command=lambda: choose(None)).pack(side=tk.RIGHT, padx=4)

        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        self.wait_window(dialog)
        return result["value"]

    def start_colmap_pipeline(self):
        if self.conversion_pool:
            self.log_message_ui("log_colmap_pipeline_blocked_by_conversion", "WARNING", is_key=True); return
        if self.colmap_running:
            self.log_message_ui("log_colmap_pipeline_already_running", "WARNING", is_key=True); return
        config = self.validate_colmap_pipeline_inputs()
        if not config:
            return
        rig_folder = config["rig_folder"]
        db_path = os.path.join(rig_folder, "database.db")
        state_path = self._get_colmap_pipeline_state_path(rig_folder)
        existing_state = self._load_colmap_pipeline_state(state_path)
        rig_config_mtime = self._get_file_mtime(config["rig_config"])
        images_snapshot = self._get_images_snapshot(config["images_dir"])
        options_hash = self._compute_colmap_options_hash(config["preset_key"], config["matcher"], config["options"])

        state_data = dict(existing_state) if existing_state else {}
        state_data.update({
            "version": 1,
            "preset_key": config["preset_key"],
            "matcher": config["matcher"],
            "options_hash": options_hash,
            "rig_config_mtime": rig_config_mtime,
            "images_snapshot": images_snapshot,
            "updated_at": self._now_iso_timestamp()
        })

        start_step = COLMAP_PIPELINE_STEPS[0]
        if os.path.exists(db_path):
            action = self._prompt_colmap_db_action(db_path)
            if action is None:
                self.log_message_ui("log_colmap_pipeline_cancelled", "INFO", is_key=True); return
            if action == "overwrite":
                try:
                    os.remove(db_path)
                    self.log_message_ui("log_colmap_pipeline_db_removed_format", "INFO", is_key=True, path=db_path)
                except OSError as e:
                    self.log_message_ui("log_colmap_pipeline_db_remove_failed_format", "ERROR", is_key=True, error=str(e))
                    return
                if os.path.isfile(state_path):
                    try:
                        os.remove(state_path)
                    except OSError:
                        pass
                state_data.pop("last_completed_step", None)
            elif action == "resume":
                if existing_state and existing_state.get("options_hash") and existing_state.get("options_hash") != options_hash:
                    self.log_message_ui("log_colmap_pipeline_options_changed", "WARNING", is_key=True)
                default_step = self._determine_resume_default_step(existing_state, config["rig_config"], config["images_dir"])
                selected_step = self._prompt_colmap_resume_step(default_step)
                if not selected_step:
                    self.log_message_ui("log_colmap_pipeline_cancelled", "INFO", is_key=True); return
                start_step = selected_step
                self.log_message_ui("log_colmap_pipeline_resume_step_format", "INFO", is_key=True,
                                    step=self._get_colmap_step_label(start_step))
        else:
            state_data.pop("last_completed_step", None)

        sparse_dir = os.path.join(rig_folder, "sparse")
        start_index = COLMAP_PIPELINE_STEPS.index(start_step)
        mapper_index = COLMAP_PIPELINE_STEPS.index("mapper")
        undistorter_index = COLMAP_PIPELINE_STEPS.index("image_undistorter")

        if start_index <= mapper_index:
            if os.path.isfile(sparse_dir):
                self.log_message_ui("log_colmap_pipeline_sparse_path_invalid_format", "ERROR", is_key=True, path=sparse_dir)
                return
            os.makedirs(sparse_dir, exist_ok=True)
        else:
            if not os.path.isdir(sparse_dir):
                self.log_message_ui("log_colmap_pipeline_sparse_not_found_format", "ERROR", is_key=True, path=sparse_dir)
                return

        postshot_output = config["postshot_output"]
        if start_index <= undistorter_index:
            if os.path.isdir(postshot_output) and os.listdir(postshot_output):
                if not messagebox.askyesno(S.get("confirm_colmap_overwrite_postshot_title"),
                                           S.get("confirm_colmap_overwrite_postshot_message_format", path=postshot_output), parent=self):
                    self.log_message_ui("log_colmap_pipeline_cancelled", "INFO", is_key=True); return
            os.makedirs(postshot_output, exist_ok=True)

        self.colmap_cancel_event = threading.Event()
        self.colmap_running = True
        self.update_colmap_controls_state()
        self.colmap_pipeline_state_path = state_path
        self.colmap_last_completed_step = state_data.get("last_completed_step")
        self.colmap_pipeline_state_data = state_data
        self.log_message_ui("log_colmap_pipeline_start_format", "INFO", is_key=True,
                            rig_folder=rig_folder, matcher=config["matcher"], postshot_output=postshot_output)
        self.log_message_ui("log_colmap_pipeline_preset_format", "INFO", is_key=True,
                            preset=self._get_colmap_preset_display_name(config["preset_key"]))
        config["state_path"] = state_path
        config["state_data"] = state_data
        config["start_step"] = start_step
        self.colmap_thread = threading.Thread(target=self._run_colmap_pipeline_thread, args=(config,), daemon=True)
        self.colmap_thread.start()

    def cancel_colmap_pipeline(self):
        if self.colmap_cancel_event and not self.colmap_cancel_event.is_set():
            self.colmap_cancel_event.set()
            if self.colmap_active_process and self.colmap_active_process.poll() is None:
                try:
                    self.colmap_active_process.terminate()
                except Exception: # pylint: disable=broad-except
                    pass
            self.log_message_ui("log_colmap_pipeline_cancel_requested", "INFO", is_key=True)
            if self.colmap_pipeline_state_path and self.colmap_pipeline_state_data:
                self._write_colmap_pipeline_state(self.colmap_pipeline_state_path,
                                                  self.colmap_pipeline_state_data,
                                                  last_step=self.colmap_last_completed_step,
                                                  threadsafe=False)

    def _run_colmap_pipeline_thread(self, config):
        try:
            rig_folder = config["rig_folder"]
            colmap_exec = config["colmap_exec"]
            images_dir = config["images_dir"]
            rig_config = config["rig_config"]
            db_path = os.path.join(rig_folder, "database.db")
            sparse_dir = os.path.join(rig_folder, "sparse")
            options = config.get("options", {})
            start_step = config.get("start_step", COLMAP_PIPELINE_STEPS[0])
            start_index = COLMAP_PIPELINE_STEPS.index(start_step)
            state_path = config.get("state_path")
            state_data = config.get("state_data") or {}

            feature_cmd = [
                colmap_exec, "feature_extractor",
                "--database_path", db_path,
                "--image_path", images_dir,
                "--ImageReader.single_camera_per_folder", "1",
                "--ImageReader.camera_model", "PINHOLE"
            ]
            feature_cmd = build_colmap_command(feature_cmd, options.get("feature", {}))
            rig_cmd = [
                colmap_exec, "rig_configurator",
                "--database_path", db_path,
                "--rig_config_path", rig_config
            ]
            if config["matcher"] == "exhaustive":
                matcher_cmd = [colmap_exec, "exhaustive_matcher", "--database_path", db_path]
            elif config["matcher"] == "vocab_tree":
                matcher_cmd = [colmap_exec, "vocab_tree_matcher", "--database_path", db_path]
            else:
                matcher_cmd = [colmap_exec, "sequential_matcher", "--database_path", db_path]
            matcher_cmd = build_colmap_command(matcher_cmd, options.get("matcher", {}))
            mapper_cmd = [
                colmap_exec, "mapper",
                "--database_path", db_path,
                "--image_path", images_dir,
                "--output_path", sparse_dir
            ]
            mapper_cmd = build_colmap_command(mapper_cmd, options.get("mapper", {}))

            step_commands = [
                ("feature_extractor", feature_cmd),
                ("rig_configurator", rig_cmd),
                ("matcher", matcher_cmd),
                ("mapper", mapper_cmd)
            ]
            for idx, (step_name, command) in enumerate(step_commands):
                if idx < start_index:
                    continue
                self.colmap_active_step = step_name
                if not self._run_colmap_command(command):
                    return
                self.colmap_last_completed_step = step_name
                self._write_colmap_pipeline_state(state_path, state_data, last_step=step_name, threadsafe=True)

            undistorter_index = COLMAP_PIPELINE_STEPS.index("image_undistorter")
            if start_index <= undistorter_index:
                sparse_model_dir = self._find_latest_sparse_model_dir(sparse_dir)
                if not sparse_model_dir:
                    self.log_message_ui_threadsafe("log_colmap_pipeline_sparse_not_found_format", "ERROR", is_key=True, path=sparse_dir)
                    return

                postshot_output = config["postshot_output"]
                undistorter_cmd = [
                    colmap_exec, "image_undistorter",
                    "--image_path", images_dir,
                    "--input_path", sparse_model_dir,
                    "--output_path", postshot_output,
                    "--output_type", "COLMAP"
                ]
                self.colmap_active_step = "image_undistorter"
                if not self._run_colmap_command(undistorter_cmd):
                    return
                self.colmap_last_completed_step = "image_undistorter"
                self._write_colmap_pipeline_state(state_path, state_data, last_step="image_undistorter", threadsafe=True)

            self.log_message_ui_threadsafe("log_colmap_pipeline_completed_format", "INFO", is_key=True, path=postshot_output)
        finally:
            self.colmap_running = False
            self.colmap_active_process = None
            self.colmap_active_step = None
            self.colmap_pipeline_state_path = None
            self.colmap_pipeline_state_data = None
            self.after(0, self.update_colmap_controls_state)

    def _run_colmap_command(self, command):
        if self.colmap_cancel_event and self.colmap_cancel_event.is_set():
            self.log_message_ui_threadsafe("log_colmap_pipeline_cancelled", "INFO", is_key=True)
            return False
        command_str = subprocess.list2cmdline(command) if os.name == 'nt' else " ".join(command)
        self.log_message_ui_threadsafe("log_colmap_pipeline_command_format", "DEBUG", is_key=True, command=command_str)
        startupinfo = self.get_startupinfo()
        unsupported_option = False
        try:
            self.colmap_active_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                startupinfo=startupinfo
            )
            if self.colmap_active_process.stdout:
                for line in self.colmap_active_process.stdout:
                    if self.colmap_cancel_event and self.colmap_cancel_event.is_set():
                        self.colmap_active_process.terminate()
                        try:
                            self.colmap_active_process.wait(timeout=5)
                        except Exception: # pylint: disable=broad-except
                            try: self.colmap_active_process.kill()
                            except Exception: # pylint: disable=broad-except
                                pass
                        self.log_message_ui_threadsafe("log_colmap_pipeline_cancelled", "INFO", is_key=True)
                        return False
                    clean_line = line.strip()
                    if clean_line:
                        lower_line = clean_line.lower()
                        if "unrecognized option" in lower_line or "unknown option" in lower_line:
                            unsupported_option = True
                        self.log_message_ui_threadsafe(f"COLMAP: {clean_line}", "DEBUG")
            self.colmap_active_process.wait()
            if self.colmap_active_process.returncode != 0:
                self.log_message_ui_threadsafe("log_colmap_pipeline_command_failed_format", "ERROR", is_key=True,
                                               code=self.colmap_active_process.returncode, command=command_str)
                if unsupported_option:
                    self.log_message_ui_threadsafe("log_colmap_pipeline_option_unsupported_hint", "ERROR", is_key=True)
                return False
            return True
        except Exception as e: # pylint: disable=broad-except
            self.log_message_ui_threadsafe("log_colmap_pipeline_command_exception_format", "ERROR", is_key=True,
                                           command=command_str, error=str(e))
            return False
        finally:
            if self.colmap_active_process and self.colmap_active_process.stdout:
                self.colmap_active_process.stdout.close()
            self.colmap_active_process = None

    def _find_latest_sparse_model_dir(self, sparse_root):
        if not os.path.isdir(sparse_root):
            return None
        model_ids = []
        for entry in os.listdir(sparse_root):
            entry_path = os.path.join(sparse_root, entry)
            if os.path.isdir(entry_path) and entry.isdigit():
                model_ids.append(int(entry))
        if not model_ids:
            return None
        latest_id = max(model_ids)
        return os.path.join(sparse_root, str(latest_id))

    def calculate_viewpoints(self):
        if self.yaw_selector_widget:
            viewpoints = self.yaw_selector_widget.get_selected_viewpoints()
            if not viewpoints: self.log_message_ui("log_viewpoints_none", "WARNING", is_key=True)
            else: self.log_message_ui("log_viewpoints_calculated_format", "DEBUG", is_key=True, count=len(viewpoints))
            return viewpoints
        self.log_message_ui("log_yaw_selector_not_initialized", "ERROR", is_key=True); return []

    def get_output_resolution(self):
        width_str = self.custom_resolution_var.get()
        try:
            width = int(width_str)
            if width <= 0:
                self.log_message_ui("log_resolution_fallback_warning_format", "WARNING", is_key=True,
                                    value=width_str, default_res=DEFAULT_RESOLUTION_WIDTH)
                width = DEFAULT_RESOLUTION_WIDTH; self.custom_resolution_var.set(str(DEFAULT_RESOLUTION_WIDTH))
        except ValueError:
            self.log_message_ui("log_resolution_fallback_warning_format", "WARNING", is_key=True,
                                value=width_str, default_res=DEFAULT_RESOLUTION_WIDTH)
            width = DEFAULT_RESOLUTION_WIDTH; self.custom_resolution_var.set(str(DEFAULT_RESOLUTION_WIDTH))
        return max(1, width), max(1, width)

    def toggle_ui_state(self, converting=False): # pylint: disable=too-many-statements
        new_state_normal = tk.NORMAL if not converting else tk.DISABLED
        new_state_readonly = "readonly" if not converting else tk.DISABLED
        self.browse_input_button.config(state=new_state_normal)
        self.browse_output_button.config(state=new_state_normal)
        self.resolution_combo.config(state=new_state_readonly)
        if not converting and self.resolution_var.get() == S.get("resolution_custom"):
            self.custom_resolution_entry.config(state="normal")
        else: self.custom_resolution_entry.config(state=tk.DISABLED)
        self.cuda_check.config(state=new_state_normal if self.cuda_available else tk.DISABLED)
        self.interp_combo.config(state=new_state_readonly)
        self.output_mode_standard_radio.config(state=new_state_normal)
        self.output_mode_colmap_radio.config(state=new_state_normal)
        if self.yaw_selector_widget:
            if converting:
                if hasattr(self.yaw_selector_widget, 'disable_controls'): self.yaw_selector_widget.disable_controls()
            else:
                if hasattr(self.yaw_selector_widget, 'enable_controls'): self.yaw_selector_widget.enable_controls()
        self.png_radio.config(state=new_state_normal); self.jpeg_radio.config(state=new_state_normal); self.video_radio.config(state=new_state_normal)
        self.update_output_format_options()
        self.parallel_combo.config(state=new_state_readonly)
        self.start_button.config(state=new_state_normal)
        self.cancel_button.config(state=tk.DISABLED if not converting else tk.NORMAL)
        if hasattr(self, 'menubar'):
            try:
                # Configure top-level cascades (Language, Help)
                if self.menubar.index(tk.END) is not None: # Check if menubar has entries
                    for i in range(self.menubar.index(tk.END) + 1):
                         self.menubar.entryconfigure(i, state=new_state_normal)
            except tk.TclError: pass # Ignore if menu doesn't exist or has issues
        self.update_colmap_controls_state()


    def run_cuda_compatibility_test(self): # pylint: disable=too-many-return-statements
        if not (self.cuda_var.get() and self.cuda_available):
            self.log_message_ui("log_cuda_compatibility_test_skip_non_cuda", "DEBUG", is_key=True)
            self.cuda_checked_for_high_res_compatibility = True; self.cuda_compatibility_confirmed_for_high_res = True; return True
        test_fov = AYS_DEFAULT_FOV_INTERNAL
        if self.yaw_selector_widget and hasattr(self.yaw_selector_widget, 'get_current_fov_for_selected_pitch'):
            current_fov_from_selector = self.yaw_selector_widget.get_current_fov_for_selected_pitch()
            if current_fov_from_selector is not None: test_fov = current_fov_from_selector
            else:
                viewpoints_for_fov_test = self.yaw_selector_widget.get_selected_viewpoints()
                if viewpoints_for_fov_test: test_fov = viewpoints_for_fov_test[0]['fov']
        output_w, output_h = self.get_output_resolution()
        v360_params_str = (f"e:flat:yaw=0.00:pitch=0.00:h_fov={test_fov:.2f}:v_fov={test_fov:.2f}"
                           f":w={output_w}:h={output_h}:interp={self.interp_var.get()}")
        filter_complex_parts_test = ["hwdownload", "format=nv12", f"v360={v360_params_str}", "format=rgb24"]
        cmd_test = [self.ffmpeg_path, "-y", "-loglevel", "error",
                    "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
                    "-i", self.input_file_var.get(),
                    "-vf", ",".join(filter_complex_parts_test),
                    "-frames:v", "1", "-an", "-sn", "-f", "null", "-"]
        self.log_message_ui("log_cuda_compatibility_test_starting", "INFO", is_key=True)
        self.log_message_ui("log_cuda_compatibility_test_cmd_format", "DEBUG", is_key=True, command_part=' '.join(cmd_test[:15]))
        ffmpeg_output_str = ""; test_successful_run = False
        try:
            process = subprocess.run(cmd_test, capture_output=True, text=True, check=False,
                                     startupinfo=self.get_startupinfo(), encoding='utf-8', errors='replace', timeout=45)
            ffmpeg_output_str = process.stderr + ("\n" + process.stdout if process.stdout else "")
            if process.returncode == 0:
                self.log_message_ui("log_cuda_compatibility_test_ffmpeg_ok", "INFO", is_key=True); test_successful_run = True
            else:
                self.log_message_ui("log_cuda_compatibility_test_ffmpeg_error_format", "WARNING", is_key=True, code=process.returncode)
                self.log_message_ui("log_cuda_compatibility_test_ffmpeg_error_output_format", "DEBUG", is_key=True, output=ffmpeg_output_str)
        except subprocess.TimeoutExpired:
            self.log_message_ui("log_cuda_compatibility_test_timeout", "ERROR", is_key=True)
            ffmpeg_output_str += "\nError: FFmpeg process timed out during CUDA compatibility test."; self.cuda_fallback_triggered_for_high_res = True
        except Exception as e: # pylint: disable=broad-except
            self.log_message_ui("log_cuda_compatibility_test_exception_format", "ERROR", is_key=True, error=str(e))
            ffmpeg_output_str += f"\nException during CUDA test: {e}"; self.cuda_fallback_triggered_for_high_res = True
        self.cuda_checked_for_high_res_compatibility = True
        if self.cuda_fallback_triggered_for_high_res: return False
        if test_successful_run:
            if check_for_cuda_fallback_error(ffmpeg_output_str):
                self.log_message_ui("log_cuda_test_success_with_error_signs", "WARNING", is_key=True)
                self.cuda_fallback_triggered_for_high_res = True; return False
            else:
                self.log_message_ui("log_cuda_compatibility_test_ok", "INFO", is_key=True)
                self.cuda_compatibility_confirmed_for_high_res = True; return True
        else:
            if check_for_cuda_fallback_error(ffmpeg_output_str):
                self.log_message_ui("log_cuda_test_error_detected_cpu_fallback", "WARNING", is_key=True)
            else: self.log_message_ui("log_cuda_test_ffmpeg_error_cpu_fallback", "ERROR", is_key=True)
            self.cuda_fallback_triggered_for_high_res = True; return False

    def start_conversion_mp(self): # pylint: disable=too-many-locals, too-many-statements, too-many-branches
        if not self.validate_inputs(): return
        viewpoints = self.calculate_viewpoints()
        output_mode = self.output_mode_var.get()
        if output_mode == "colmap_rig":
            viewpoints = prepare_viewpoints_for_colmap(viewpoints)
        if not viewpoints: self.log_message_ui("log_conversion_cannot_start_no_viewpoints", "ERROR", is_key=True); return
        colmap_session_prefix = ""
        if output_mode == "colmap_rig":
            base_name = os.path.splitext(os.path.basename(self.input_file_var.get()))[0]
            try:
                colmap_session_prefix = make_unique_session_prefix(self.output_folder_var.get(), base_name, DEFAULT_RIG_NAME)
            except Exception as e: # pylint: disable=broad-except
                self.log_message_ui("log_colmap_rig_session_prefix_error_format", "ERROR", is_key=True, error=str(e))
                return
            self.log_message_ui("log_colmap_rig_session_prefix_format", "INFO", is_key=True, prefix=colmap_session_prefix)
        self.cuda_checked_for_high_res_compatibility = False; self.cuda_fallback_triggered_for_high_res = False
        self.cuda_compatibility_confirmed_for_high_res = False
        is_high_res_input = (self.video_width > HIGH_RESOLUTION_THRESHOLD or self.video_height > HIGH_RESOLUTION_THRESHOLD)
        effective_use_cuda = self.cuda_var.get() and self.cuda_available
        if is_high_res_input and effective_use_cuda:
            self.log_message_ui("log_cuda_high_res_test_execute", "INFO", is_key=True)
            self.toggle_ui_state(converting=True); self.update_idletasks()
            if not self.run_cuda_compatibility_test():
                self.log_message_ui("log_cuda_high_res_test_fallback_cpu", "WARNING", is_key=True); effective_use_cuda = False
            else: self.log_message_ui("log_cuda_high_res_test_continue_cuda", "INFO", is_key=True)
        else:
            self.cuda_checked_for_high_res_compatibility = True
            self.cuda_compatibility_confirmed_for_high_res = True if effective_use_cuda else True
        self.total_tasks_for_conversion = len(viewpoints); self.completed_tasks_count = 0; self.active_tasks_count = 0
        self.task_durations = []; self.final_conversion_message = None
        self.overall_remaining_seconds_at_last_avg_calculation = None; self.timestamp_of_last_avg_calculation = None
        self.toggle_ui_state(converting=True); self.log_message_ui("log_conversion_starting_parallel", "INFO", is_key=True)
        self.progress_bar["value"] = 0; self.progress_bar["maximum"] = 100
        self.viewpoint_progress_text_var.set(S.get("viewpoint_progress_format", completed=0, total=self.total_tasks_for_conversion))
        self.start_time = time.time(); self.elapsed_time_str = "00:00:00"
        self.overall_remaining_str = S.get("time_display_remaining_calculating") if self.total_tasks_for_conversion > 0 else S.get("time_display_not_started")
        self.update_time_label_display()
        try:
            num_parallel = int(self.parallel_processes_var.get())
            if num_parallel <= 0: raise ValueError("Parallel processes must be positive.")
        except ValueError:
            num_parallel = 1; self.log_message_ui("log_parallel_processes_invalid_fallback_format", "WARNING", is_key=True)
            self.parallel_processes_var.set("1")
        try:
            if self.manager_mp is None or (hasattr(self.manager_mp, '_process') and not self.manager_mp._process.is_alive()): # type: ignore
                self.manager_mp = multiprocessing.Manager()
            self.log_queue_mp = self.manager_mp.Queue(); self.progress_queue_mp = self.manager_mp.Queue()
            self.cancel_event_mp = self.manager_mp.Event(); self.conversion_pool = multiprocessing.Pool(processes=num_parallel)
        except Exception as e: # pylint: disable=broad-except
            self.log_message_ui("log_multiprocessing_init_error_format", "CRITICAL", is_key=True, error=str(e))
            self.toggle_ui_state(converting=False); self.start_time = 0; return
        output_w, output_h = self.get_output_resolution()
        self.colmap_rig_context = None
        if output_mode == "colmap_rig":
            self.colmap_rig_context = {
                "output_folder": self.output_folder_var.get(),
                "output_resolution": (output_w, output_h),
                "viewpoints": viewpoints,
                "rig_name": DEFAULT_RIG_NAME
            }
        if self.cuda_fallback_triggered_for_high_res:
            effective_use_cuda = False; self.log_message_ui("log_cuda_fallback_all_cpu", "INFO", is_key=True)
        elif is_high_res_input and self.cuda_var.get() and self.cuda_available and not self.cuda_compatibility_confirmed_for_high_res:
            effective_use_cuda = False; self.log_message_ui("log_cuda_compatibility_not_confirmed_cpu", "WARNING", is_key=True)
        frame_interval_for_worker = 0.0
        if self.output_format_var.get() in ["png", "jpeg"]:
            try: frame_interval_for_worker = float(self.frame_interval_var.get())
            except ValueError: frame_interval_for_worker = 1.0
        jpeg_quality_for_worker = 90
        try: jpeg_quality_for_worker = int(self.jpeg_quality_var.get())
        except ValueError: pass
        worker_config = {
            "ffmpeg_path": self.ffmpeg_path, "input_file": self.input_file_var.get(),
            "output_folder": self.output_folder_var.get(), "output_resolution": (output_w, output_h),
            "interp": self.interp_var.get(), "threads_ffmpeg": int(os.cpu_count() or 1),
            "use_cuda": effective_use_cuda, "output_format": self.output_format_var.get(),
            "output_mode": output_mode, "colmap_rig_name": DEFAULT_RIG_NAME,
            "colmap_session_prefix": colmap_session_prefix,
            "frame_interval": frame_interval_for_worker, "video_preset": self.preset_var.get(),
            "video_cq": self.cq_var.get(), "png_pred_option": self.png_pred_options_map.get(self.png_pred_var.get(), "3"),
            "jpeg_quality": jpeg_quality_for_worker
        }
        for i, vp_data in enumerate(viewpoints):
            self.conversion_pool.apply_async(ffmpeg_worker_process,
                                             args=(i, vp_data, worker_config,
                                                   self.log_queue_mp, self.progress_queue_mp, self.cancel_event_mp))
            self.active_tasks_count += 1
        self.conversion_pool.close()
        if self.total_tasks_for_conversion > 0: self.after(100, self.process_mp_queues)
        else: self.conversion_finished_or_cancelled_mp()

    def conversion_finished_or_cancelled_mp(self):
        if self.start_time == 0 and not (self.cancel_event_mp and self.cancel_event_mp.is_set()): return
        elapsed_seconds = time.time() - self.start_time if self.start_time > 0 else 0
        elapsed_time_formatted = str(timedelta(seconds=int(elapsed_seconds)))
        was_cancelled = self.cancel_event_mp and self.cancel_event_mp.is_set()
        final_status_key = "viewpoint_progress_status_cancelled" if was_cancelled else "viewpoint_progress_status_completed"
        final_verb_for_log = S.get(final_status_key).lower(); final_verb_for_ui = S.get(final_status_key)
        self.log_message_ui("log_conversion_finished_or_cancelled_format", "INFO", is_key=True, status=final_verb_for_log)
        self.viewpoint_progress_text_var.set(
            f'{S.get("viewpoint_progress_format", completed=self.completed_tasks_count, total=self.total_tasks_for_conversion)} ({final_verb_for_ui})'
        )
        if not was_cancelled and self.completed_tasks_count >= self.total_tasks_for_conversion:
            self.progress_bar["value"] = 100; self.overall_remaining_str = "00:00:00"
        self.final_conversion_message = f"{final_verb_for_ui} - {S.get('time_display_elapsed')}: {elapsed_time_formatted}"
        self.update_time_label_display()
        if not was_cancelled and self.colmap_rig_context:
            try:
                rig_path = write_rig_config_json(
                    self.colmap_rig_context["output_folder"],
                    self.colmap_rig_context["viewpoints"],
                    self.colmap_rig_context["output_resolution"],
                    rig_name=self.colmap_rig_context["rig_name"]
                )
                self.log_message_ui("log_colmap_rig_config_written_format", "INFO", is_key=True, path=rig_path)
            except Exception as e: # pylint: disable=broad-except
                self.log_message_ui("log_colmap_rig_config_write_failed_format", "ERROR", is_key=True, error=str(e))
        self.colmap_rig_context = None
        if self.conversion_pool:
            try:
                if was_cancelled: self.conversion_pool.terminate()
                self.conversion_pool.join() # Removed timeout argument
            except Exception as e: # pylint: disable=broad-except
                self.log_message_ui("log_pool_termination_error_format", "WARNING", is_key=True, error=str(e))
            finally: self.conversion_pool = None
        self.active_tasks_count = 0; self.start_time = 0; self.toggle_ui_state(converting=False)

    def cancel_conversion_mp(self):
        if self.cancel_event_mp and not self.cancel_event_mp.is_set():
            self.log_message_ui("log_cancel_requested", "INFO", is_key=True)
            self.cancel_event_mp.set(); self.cancel_button.config(state=tk.DISABLED)

    def on_closing(self):
        if self.colmap_running:
            if messagebox.askyesno(S.get("confirm_exit_while_colmap_title"),
                                   S.get("confirm_exit_while_colmap_message"), parent=self):
                self.cancel_colmap_pipeline()
                if self.colmap_thread:
                    try: self.colmap_thread.join(timeout=5)
                    except Exception: # pylint: disable=broad-except
                        pass
            else:
                return
        if self.conversion_pool and self.active_tasks_count > 0:
            if messagebox.askyesno(S.get("confirm_exit_while_converting_title"),
                                   S.get("confirm_exit_while_converting_message"), parent=self):
                self.log_message_ui("log_closing_cancelled_conversion", "WARNING", is_key=True)
                if self.cancel_event_mp and not self.cancel_event_mp.is_set(): self.cancel_event_mp.set()
                if self.conversion_pool:
                    try:
                        self.conversion_pool.terminate()
                        self.conversion_pool.join() # Removed timeout argument
                    except Exception as e: # pylint: disable=broad-except
                        self.log_message_ui("log_pool_forced_termination_error_format", "WARNING", is_key=True, error=str(e))
                    finally: self.conversion_pool = None
                if self.manager_mp and hasattr(self.manager_mp, 'shutdown') and \
                   hasattr(self.manager_mp, '_process') and self.manager_mp._process.is_alive(): # type: ignore
                    try: self.manager_mp.shutdown()
                    except Exception as e: # pylint: disable=broad-except
                         print(f"Error shutting down multiprocessing.Manager: {e}")
                self.manager_mp = None; self.destroy()
            else: return
        else:
            if self.manager_mp and hasattr(self.manager_mp, 'shutdown') and \
               hasattr(self.manager_mp, '_process') and self.manager_mp._process.is_alive(): # type: ignore
                try: self.manager_mp.shutdown()
                except Exception as e: # pylint: disable=broad-except
                    print(f"Error shutting down multiprocessing.Manager on exit: {e}")
            self.manager_mp = None; self.destroy()

if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = Insta360ConvertGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
