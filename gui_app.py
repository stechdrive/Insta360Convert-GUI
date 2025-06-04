# gui_app.py
# Insta360Convert GUIのメインアプリケーションクラス

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import subprocess
# import queue # Not directly used with multiprocessing.Queue, but often imported with it
import os
import json
import time
from datetime import timedelta
import multiprocessing
import threading # For background update check
import webbrowser # To open web links

# 分割したモジュールからのインポート
from constants import (
    APP_NAME, APP_DISPLAY_VERSION, APP_VERSION_STRING_SEMVER,
    FFMPEG_PRESETS, DEFAULT_PRESET,
    DEFAULT_RESOLUTION_WIDTH, HIGH_RESOLUTION_THRESHOLD,
    GITHUB_RELEASES_PAGE_URL
)
from tooltip_utils import ToolTip
from ffmpeg_worker import ffmpeg_worker_process, check_for_cuda_fallback_error
from advanced_yaw_selector import AdvancedYawSelector, DEFAULT_PITCHES_STR, DEFAULT_FOV_INTERNAL # DEFAULT_FOV_INTERNAL from advanced_yaw_selector

# update_checkerモジュールのインポート (エラーハンドリング付き)
try:
    from update_checker import check_for_updates_background
except ImportError:
    # Fallback function if update_checker.py is missing or import fails
    def check_for_updates_background(current_app_version):
        error_message = (
            "アップデートチェック機能の読み込みに失敗しました。\n"
            "update_checker.py が見つからないか、インポートに失敗しました。"
        )
        print(f"Error: {error_message}")
        return (
            False,  # update_available
            error_message,  # message_for_gui
            None,  # latest_version_str
            None,  # release_notes_str
            "update_checker.py load error"  # error_message_detail
        )
    print("Warning: update_checker.py could not be imported. Update check feature will be impaired.")


class Insta360ConvertGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        # --- Versioning ---
        self.app_name = APP_NAME
        self.app_version_display = APP_DISPLAY_VERSION # For display in title, about box
        self.app_version_semver = APP_VERSION_STRING_SEMVER # For version comparison

        self.title(f"{self.app_name} - {self.app_version_display}")
        self.geometry("800x980") # ウィンドウの高さを確保
        self.style = ttk.Style(self)
        self.style.theme_use('clam')

        # --- Variable initializations ---
        self.input_file_var = tk.StringVar()
        self.output_folder_var = tk.StringVar()
        self.resolutions = ["1920", "1600", "自動 (入力動画に合わせる)", "カスタム..."]
        self.resolution_var = tk.StringVar(value="自動 (入力動画に合わせる)")
        self.custom_resolution_var = tk.StringVar()

        try:
            default_threads_os = os.cpu_count()
            if default_threads_os is None:
                default_threads_os = 1
        except NotImplementedError:
            default_threads_os = 1
        self.internal_threads_value = str(max(1, default_threads_os // 2))

        self.logical_cores = os.cpu_count() if os.cpu_count() else 1
        self.parallel_options = [str(i) for i in range(1, self.logical_cores + 1)]
        self.parallel_processes_var = tk.StringVar()

        self.cuda_var = tk.BooleanVar(value=False)
        self.interp_options = ["linear", "cubic", "lanczos", "nearest"]
        self.interp_var = tk.StringVar(value="cubic")
        self.output_format_var = tk.StringVar(value="png")
        self.frame_interval_var = tk.StringVar(value="1.00")
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET)
        self.cq_var = tk.StringVar(value="18")
        self.png_pred_options_map = {
            "None (最速, サイズ:特大)": "0", "Sub (高速, サイズ:大)": "1",
            "Up (高速, サイズ:大)": "2", "Average (中速, サイズ:中)": "3",
            "Paeth (低速, サイズ:小)": "4"
        }
        self.png_pred_var = tk.StringVar(value="Average (中速, サイズ:中)")
        self.jpeg_quality_var = tk.StringVar(value="90")

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
        self.manager_mp = None # Multiprocessing manager

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
        self.overall_remaining_str = "--:--:--"
        self.viewpoint_progress_text_var = tk.StringVar(value="0 / 0 視点")
        self.final_conversion_message = None
        self.avg_time_per_viewpoint_for_estimation = 0
        self.overall_remaining_seconds_at_last_avg_calculation = None
        self.timestamp_of_last_avg_calculation = None

        self.yaw_selector_widget = None # Placeholder for AdvancedYawSelector instance

        # --- UI Creation and Initial Setup ---
        self._create_menu() # Menu creation before other widgets
        self.create_widgets()
        self.update_resolution_options()
        self.check_ffmpeg_ffprobe()
        self.check_cuda_availability()
        self.update_time_label_display()
        self.update_parallel_options_and_default()

    def _create_menu(self):
        menubar = tk.Menu(self)

        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="バージョン情報", command=self._show_version_info)
        helpmenu.add_separator()
        helpmenu.add_command(label="アップデートを確認...", command=self.trigger_update_check)
        menubar.add_cascade(label="ヘルプ", menu=helpmenu)

        self.config(menu=menubar)

    def _show_version_info(self):
        messagebox.showinfo(
            "バージョン情報",
            f"{self.app_name}\nバージョン: {self.app_version_display}"
        )

    def trigger_update_check(self):
        """Initiates the update check in a separate thread."""
        # Provide immediate feedback to the user
        messagebox.showinfo(
            "アップデート確認",
            "GitHubに最新情報を問い合わせています...\n完了後、結果を通知します。",
            parent=self,
            icon=messagebox.INFO
        )

        update_thread = threading.Thread(
            target=self.perform_update_check_in_thread,
            daemon=True # Thread will exit when the main program exits
        )
        update_thread.start()

    def perform_update_check_in_thread(self):
        """Performs the update check (to be run in a thread)."""
        (update_available, msg_gui, latest_v,
         notes, err_detail) = check_for_updates_background(self.app_version_semver)

        # Schedule GUI update on the main thread
        # Using after(0, ...) ensures it runs in the next Tkinter event loop cycle
        self.after(0, self.handle_update_check_result,
                   update_available, msg_gui, latest_v, notes, err_detail)

    def handle_update_check_result(
            self, update_available, message_for_gui, latest_version_str,
            release_notes_str, error_message_detail):
        """Handles the result from the update check and updates the GUI."""
        if error_message_detail:
            messagebox.showerror("アップデートエラー", message_for_gui, parent=self)
            return

        if update_available:
            if messagebox.askyesno("アップデート情報", message_for_gui, parent=self):
                try:
                    webbrowser.open_new_tab(GITHUB_RELEASES_PAGE_URL)
                except Exception as e:
                    messagebox.showerror(
                        "リンクエラー",
                        f"ダウンロードページを開けませんでした: {e}",
                        parent=self
                    )
        else:
            messagebox.showinfo("アップデート情報", message_for_gui, parent=self)

    def create_widgets(self):
        self.main_frame = ttk.Frame(self, padding="5")
        self.main_frame.pack(expand=True, fill=tk.BOTH)

        # --- ファイル設定フレーム (一番上に配置) ---
        self.io_frame = ttk.LabelFrame(self.main_frame, text="ファイル設定", padding="5")
        self.io_frame.pack(fill=tk.X, pady=2, side=tk.TOP)

        self.input_file_label = ttk.Label(self.io_frame, text="入力動画ファイル:")
        self.input_file_label.grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        ToolTip(self.input_file_label, "変換元の360度動画ファイルを選択します。")
        self.input_file_entry = ttk.Entry(self.io_frame, textvariable=self.input_file_var, state="readonly", width=60)
        self.input_file_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.EW)
        ToolTip(self.input_file_entry, "選択された入力動画ファイルのパスが表示されます。")
        self.browse_input_button = ttk.Button(self.io_frame, text="参照...", command=self.browse_input_file)
        self.browse_input_button.grid(row=0, column=2, padx=5, pady=2)
        ToolTip(self.browse_input_button, "入力動画ファイルを選択するダイアログを開きます。")

        self.output_folder_label = ttk.Label(self.io_frame, text="出力フォルダ:")
        self.output_folder_label.grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        ToolTip(self.output_folder_label, "変換後のファイルが保存されるフォルダを選択します。")
        self.output_folder_entry = ttk.Entry(self.io_frame, textvariable=self.output_folder_var, state="readonly", width=60)
        self.output_folder_entry.grid(row=1, column=1, padx=5, pady=2, sticky=tk.EW)
        ToolTip(self.output_folder_entry, "選択された出力フォルダのパスが表示されます。")
        self.browse_output_button = ttk.Button(self.io_frame, text="参照...", command=self.browse_output_folder)
        self.browse_output_button.grid(row=1, column=2, padx=5, pady=2)
        ToolTip(self.browse_output_button, "出力フォルダを選択するダイアログを開きます。")
        self.io_frame.columnconfigure(1, weight=1)

        # --- メインの PanedWindow (視点設定 と ログエリアを含む下部コンテンツ) ---
        self.main_content_paned_window = ttk.PanedWindow(self.main_frame, orient=tk.VERTICAL)
        self.main_content_paned_window.pack(fill=tk.BOTH, expand=True, pady=(2,0), side=tk.TOP)

        # --- 視点設定フレーム (PanedWindow の上部ペイン) ---
        self.yaw_selector_module_labelframe = ttk.LabelFrame(self.main_content_paned_window, text="視点設定 (ピッチ・ヨー・FOV)", padding="5")
        self.main_content_paned_window.add(self.yaw_selector_module_labelframe, weight=3)

        self.yaw_selector_widget = AdvancedYawSelector(
            self.yaw_selector_module_labelframe,
            initial_pitches_str=DEFAULT_PITCHES_STR, # From advanced_yaw_selector
            on_selection_change_callback=self.on_yaw_selector_updated
        )
        self.yaw_selector_widget.pack(fill=tk.BOTH, expand=True)
        ToolTip(self.yaw_selector_module_labelframe, "各ピッチ角でのヨー角とFOV（視野角）を設定します。\n3Dビュー: 左ドラッグで回転、右クリックで選択/解除。")

        # --- 下部コンテンツ用のフレーム (PanedWindow の下部ペイン) ---
        bottom_content_frame = ttk.Frame(self.main_content_paned_window)
        self.main_content_paned_window.add(bottom_content_frame, weight=2)

        # --- 出力設定フレーム (bottom_content_frame 内) ---
        self.output_settings_frame = ttk.LabelFrame(bottom_content_frame, text="出力設定", padding="5")
        self.output_settings_frame.pack(fill=tk.X, pady=2, side=tk.TOP)

        common_opts_line1_frame = ttk.Frame(self.output_settings_frame)
        common_opts_line1_frame.pack(fill=tk.X, pady=2)
        self.resolution_label = ttk.Label(common_opts_line1_frame, text="解像度:")
        self.resolution_label.pack(side=tk.LEFT, padx=(5,2), pady=2)
        ToolTip(self.resolution_label, "出力画像/動画の解像度（一辺のピクセル数）。")
        self.resolution_combo = ttk.Combobox(common_opts_line1_frame, textvariable=self.resolution_var, values=self.resolutions, width=20, state="readonly")
        self.resolution_combo.pack(side=tk.LEFT, padx=(0,5), pady=2)
        self.resolution_combo.bind("<<ComboboxSelected>>", self.update_resolution_options)
        ToolTip(self.resolution_combo, "プリセット解像度または「カスタム...」を選択。「自動」は入力動画の短辺に合わせます。")
        self.custom_resolution_entry = ttk.Entry(common_opts_line1_frame, textvariable=self.custom_resolution_var, width=8, state="disabled")
        self.custom_resolution_entry.pack(side=tk.LEFT, padx=(0,15), pady=2)
        ToolTip(self.custom_resolution_entry, "「カスタム...」選択時に解像度を数値で入力。")
        self.cuda_check = ttk.Checkbutton(common_opts_line1_frame, text="CUDA", variable=self.cuda_var, state="disabled", command=self.on_cuda_checkbox_changed)
        self.cuda_check.pack(side=tk.LEFT, padx=(0,5), pady=2)
        ToolTip(self.cuda_check, "NVIDIA CUDAで高速化 (利用可能な場合)。\n高解像度入力時はテストされ、問題があれば無効化されることがあります。")
        self.interp_label = ttk.Label(common_opts_line1_frame, text="補間:")
        self.interp_label.pack(side=tk.LEFT, padx=(10,2), pady=2)
        ToolTip(self.interp_label, "画像補間方法。高画質ほど処理時間が長くなる傾向があります。")
        self.interp_combo = ttk.Combobox(common_opts_line1_frame, textvariable=self.interp_var, values=self.interp_options, width=10, state="readonly")
        self.interp_combo.pack(side=tk.LEFT, padx=(0,5), pady=2)
        ToolTip(self.interp_combo, "cubic:高画質(推奨), lanczos:最高画質(シャープ),\nlinear:標準, nearest:高速(低画質)。")

        format_options_main_frame = ttk.Frame(self.output_settings_frame)
        format_options_main_frame.pack(fill=tk.X, pady=(5,2))
        self.png_radio = ttk.Radiobutton(format_options_main_frame, text="PNGシーケンス", variable=self.output_format_var, value="png", command=self.update_output_format_options)
        self.png_radio.grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        ToolTip(self.png_radio, "PNG画像のシーケンス。各視点ごとにフォルダ作成。")
        self.png_options_frame = ttk.Frame(format_options_main_frame)
        self.png_options_frame.grid(row=0, column=1, padx=(10,5), pady=0, sticky=tk.W)
        self.png_interval_label = ttk.Label(self.png_options_frame, text="抽出間隔(秒):")
        self.png_interval_label.pack(side=tk.LEFT, padx=(0,2))
        ToolTip(self.png_interval_label, "何秒ごとに1フレームを抽出するか。例: 0.5 (毎秒2フレーム)。")
        self.png_frame_interval_entry = ttk.Entry(self.png_options_frame, textvariable=self.frame_interval_var, width=8)
        self.png_frame_interval_entry.pack(side=tk.LEFT, padx=(0,5))
        ToolTip(self.png_frame_interval_entry, "PNG出力時のフレーム抽出間隔(秒)。")
        self.png_pred_label = ttk.Label(self.png_options_frame, text="PNG予測:")
        self.png_pred_label.pack(side=tk.LEFT, padx=(5,2))
        ToolTip(self.png_pred_label, "PNGエンコード時の予測フィルター (速度とファイルサイズのトレードオフ)。")
        self.png_pred_combo = ttk.Combobox(self.png_options_frame, textvariable=self.png_pred_var, values=list(self.png_pred_options_map.keys()), width=25, state="readonly")
        self.png_pred_combo.pack(side=tk.LEFT, padx=(0,5))
        ToolTip(self.png_pred_combo, "PNG圧縮方法: None(最速,大), Sub(高速,大), Up(高速,大),\nAverage(中速,中,デフォルト), Paeth(低速,小)。")

        self.jpeg_radio = ttk.Radiobutton(format_options_main_frame, text="JPEGシーケンス", variable=self.output_format_var, value="jpeg", command=self.update_output_format_options)
        self.jpeg_radio.grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        ToolTip(self.jpeg_radio, "JPEG画像のシーケンス。各視点ごとにフォルダ作成。")
        self.jpeg_options_frame = ttk.Frame(format_options_main_frame)
        self.jpeg_options_frame.grid(row=1, column=1, padx=(10,5), pady=0, sticky=tk.W)
        self.jpeg_interval_label = ttk.Label(self.jpeg_options_frame, text="抽出間隔(秒):")
        self.jpeg_interval_label.pack(side=tk.LEFT, padx=(0,2))
        ToolTip(self.jpeg_interval_label, "何秒ごとに1フレームを抽出するか。例: 0.5 (毎秒2フレーム)。")
        self.jpeg_frame_interval_entry = ttk.Entry(self.jpeg_options_frame, textvariable=self.frame_interval_var, width=8)
        self.jpeg_frame_interval_entry.pack(side=tk.LEFT, padx=(0,5))
        ToolTip(self.jpeg_frame_interval_entry, "JPEG出力時のフレーム抽出間隔(秒)。")
        self.jpeg_quality_label = ttk.Label(self.jpeg_options_frame, text="品質(1-100):")
        self.jpeg_quality_label.pack(side=tk.LEFT, padx=(5,2))
        ToolTip(self.jpeg_quality_label, "JPEG品質(1-100)。大きいほど高画質・大ファイルサイズ。")
        self.jpeg_quality_entry = ttk.Entry(self.jpeg_options_frame, textvariable=self.jpeg_quality_var, width=5)
        self.jpeg_quality_entry.pack(side=tk.LEFT, padx=(0,5))
        ToolTip(self.jpeg_quality_entry, "JPEG品質(1低～100高)。FFmpeg内部で1高～31低スケールに変換。デフォルト90。")

        self.video_radio = ttk.Radiobutton(format_options_main_frame, text="動画 (HEVC/H.265)", variable=self.output_format_var, value="video", command=self.update_output_format_options)
        self.video_radio.grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
        ToolTip(self.video_radio, "HEVC(H.265)コーデックのMP4動画。各視点ごとに動画ファイル作成。")
        self.video_options_frame = ttk.Frame(format_options_main_frame)
        self.video_options_frame.grid(row=2, column=1, padx=(10,5), pady=0, sticky=tk.W)
        self.video_preset_label = ttk.Label(self.video_options_frame, text="Preset:")
        self.video_preset_label.pack(side=tk.LEFT, padx=(0,2))
        ToolTip(self.video_preset_label, "FFmpegエンコードプリセット。速いほど低画質、遅いほど高画質。")
        self.preset_combo = ttk.Combobox(self.video_options_frame, textvariable=self.preset_var, values=FFMPEG_PRESETS, width=10, state="readonly")
        self.preset_combo.pack(side=tk.LEFT, padx=(0,5))
        ToolTip(self.preset_combo, "動画出力時のエンコードプリセット。")
        self.video_cq_label = ttk.Label(self.video_options_frame, text="CQ/CRF:")
        self.video_cq_label.pack(side=tk.LEFT, padx=(5,2))
        ToolTip(self.video_cq_label, "固定品質値(0-51)。低いほど高画質(大ファイル)。\nlibx265(CPU CRF):推奨18-28。\nNVENC(CUDA CQ):推奨15-28程度。")
        self.cq_entry = ttk.Entry(self.video_options_frame, textvariable=self.cq_var, width=5)
        self.cq_entry.pack(side=tk.LEFT, padx=(0,5))
        ToolTip(self.cq_entry, "動画出力時の品質値。")
        format_options_main_frame.columnconfigure(1, weight=1)

        # --- コントロールフレーム (bottom_content_frame 内) ---
        self.control_frame_outer = ttk.Frame(bottom_content_frame, padding=(5,0))
        self.control_frame_outer.pack(fill=tk.X, pady=2, side=tk.TOP)

        self.parallel_control_frame = ttk.Frame(self.control_frame_outer)
        self.parallel_control_frame.pack(fill=tk.X)
        self.parallel_label = ttk.Label(self.parallel_control_frame, text="並列処理数:")
        self.parallel_label.pack(side=tk.LEFT, padx=(5,0))
        ToolTip(self.parallel_label, f"同時に処理する視点の数。最大: {self.logical_cores} (論理コア数)")
        self.parallel_combo = ttk.Combobox(self.parallel_control_frame, textvariable=self.parallel_processes_var, values=self.parallel_options, width=5, state="readonly")
        self.parallel_combo.pack(side=tk.LEFT, padx=5)
        ToolTip(self.parallel_combo, "変換処理を並列実行するプロセス数。\nCPUコア数と適用ピッチ角数に応じて調整。")

        self.button_time_frame = ttk.Frame(self.control_frame_outer)
        self.button_time_frame.pack(fill=tk.X, pady=(5,0))
        self.start_button = ttk.Button(self.button_time_frame, text="変換開始", command=self.start_conversion_mp)
        self.start_button.pack(side=tk.LEFT, padx=5)
        ToolTip(self.start_button, "設定に基づいて変換処理を開始します。")
        self.cancel_button = ttk.Button(self.button_time_frame, text="中止", command=self.cancel_conversion_mp, state="disabled")
        self.cancel_button.pack(side=tk.LEFT, padx=5)
        ToolTip(self.cancel_button, "現在進行中の変換処理を中止します。")
        self.time_label = ttk.Label(self.button_time_frame, text="") # Initialized in update_time_label_display
        self.time_label.pack(side=tk.LEFT, padx=10, pady=(0,3))
        ToolTip(self.time_label, "変換処理の経過時間と推定残り時間を表示します。")

        self.progress_display_frame = ttk.Frame(self.control_frame_outer)
        self.progress_display_frame.pack(fill=tk.X, pady=(2,0))
        self.viewpoint_progress_label = ttk.Label(self.progress_display_frame, textvariable=self.viewpoint_progress_text_var)
        self.viewpoint_progress_label.pack(side=tk.LEFT, padx=5)
        ToolTip(self.viewpoint_progress_label, "処理済みの視点数と総視点数を表示します。")
        self.progress_bar = ttk.Progressbar(self.progress_display_frame, orient="horizontal", length=200, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ToolTip(self.progress_bar, "全体の変換処理の進捗状況を示します。")

        # --- ログエリア (bottom_content_frame 内, 残りのスペースを全て使用) ---
        self.log_notebook = ttk.Notebook(bottom_content_frame, padding=2)
        self.log_notebook.pack(expand=True, fill=tk.BOTH, pady=(2,5), side=tk.TOP)

        self.app_log_frame = ttk.Frame(self.log_notebook, padding=2)
        self.log_notebook.add(self.app_log_frame, text="アプリケーションログ")
        self.log_area = scrolledtext.ScrolledText(self.app_log_frame, height=6, state="disabled", wrap=tk.WORD)
        self.log_area.pack(expand=True, fill=tk.BOTH)
        ToolTip(self.log_area, "アプリケーションの動作ログやエラーメッセージが表示されます。")

        self.ffmpeg_log_frame = ttk.Frame(self.log_notebook, padding=2)
        self.log_notebook.add(self.ffmpeg_log_frame, text="FFmpeg出力ログ")
        self.ffmpeg_log_area = scrolledtext.ScrolledText(self.ffmpeg_log_frame, height=6, state="disabled", wrap=tk.WORD)
        self.ffmpeg_log_area.pack(expand=True, fill=tk.BOTH)
        ToolTip(self.ffmpeg_log_area, "FFmpegコマンドの生出力が表示されます。詳細な変換状況の確認に利用します。")

        self.update_output_format_options()
        self.update_time_label_display() # Initialize time label text

    def on_yaw_selector_updated(self):
        if not self.yaw_selector_widget:
            return
        # selected_vps = self.yaw_selector_widget.get_selected_viewpoints()
        # num_vps = len(selected_vps)
        # self.log_message_ui(f"視点設定更新: {num_vps} 視点選択中。", "DEBUG")
        self.update_parallel_options_and_default()

    def _update_ffmpeg_log_area(self, message):
        if hasattr(self, 'ffmpeg_log_area') and self.ffmpeg_log_area.winfo_exists():
            self.ffmpeg_log_area.config(state="normal")
            self.ffmpeg_log_area.insert(tk.END, message)
            self.ffmpeg_log_area.see(tk.END)
            self.ffmpeg_log_area.config(state="disabled")
        else:
            # Fallback or log if ffmpeg_log_area is not ready
            print(f"FFMPEG_RAW_LOG: {message.strip()}")


    def on_cuda_checkbox_changed(self):
        self.cuda_checked_for_high_res_compatibility = False
        self.cuda_fallback_triggered_for_high_res = False
        self.cuda_compatibility_confirmed_for_high_res = False
        self.log_message_ui("CUDA設定変更。高解像度入力の場合、次回変換時に互換性テストが再実行されます。", "DEBUG")
        self.apply_cuda_restrictions_based_on_video_info()

    def update_parallel_options_and_default(self):
        num_pitch_angles = 0
        if self.yaw_selector_widget and hasattr(self.yaw_selector_widget, 'get_num_active_pitches'):
            num_pitch_angles = self.yaw_selector_widget.get_num_active_pitches()

        if num_pitch_angles == 0:
            num_pitch_angles = 1 # Avoid division by zero or invalid range

        default_parallel = max(1, min(num_pitch_angles, self.logical_cores))

        if str(default_parallel) in self.parallel_options:
            self.parallel_processes_var.set(str(default_parallel))
        elif self.parallel_options: # If default_parallel is not an option, pick first
            self.parallel_processes_var.set(self.parallel_options[0])
        else: # Should not happen if logical_cores >= 1
             self.parallel_processes_var.set("1")

    def log_message_ui(self, message, level="INFO"):
        if not hasattr(self, 'log_area') or not self.log_area: # Check if log_area is initialized
            print(f"LOG_FALLBACK [{level}] {message}")
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        formatted_message = f"[{timestamp}] [{level}] {message}\n"
        try:
            if self.log_area.winfo_exists(): # Check if widget is still alive
                self._update_log_area(formatted_message)
        except tk.TclError:
             # This can happen if log_message_ui is called during shutdown
             print(f"LOG_TCL_ERROR [{level}] {message}")


    def _update_log_area(self, message):
        # Assumes self.log_area exists and is valid when called
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, message)
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")

    def process_mp_queues(self):
        # Using multiprocessing.queues.Empty for more specific exception handling
        try:
            while self.log_queue_mp and not self.log_queue_mp.empty():
                log_entry = self.log_queue_mp.get_nowait()
                if log_entry["type"] == "log":
                    self.log_message_ui(log_entry["message"], log_entry["level"])
                elif log_entry["type"] == "ffmpeg_raw":
                    self._update_ffmpeg_log_area(log_entry["line"] + "\n")
        except (multiprocessing.queues.Empty, AttributeError, EOFError, FileNotFoundError):
            pass # Expected when queue is empty or during shutdown
        except Exception as e:
            print(f"Log queue processing error: {type(e).__name__} - {e}")

        new_task_completed_this_cycle = False
        try:
            while self.progress_queue_mp and not self.progress_queue_mp.empty():
                prog_entry = self.progress_queue_mp.get_nowait()
                if prog_entry["type"] == "task_result":
                    new_task_completed_this_cycle = True
                    self.completed_tasks_count += 1
                    if self.active_tasks_count > 0: # Should always be true if tasks are running
                        self.active_tasks_count -= 1

                    if prog_entry.get("cancelled", False):
                        self.log_message_ui(f"視点 {prog_entry['viewpoint_index'] + 1} はキャンセルされました。", "INFO")
                    elif prog_entry["success"]:
                        dur = prog_entry.get('duration', 0)
                        self.log_message_ui(f"視点 {prog_entry['viewpoint_index'] + 1} 完了。(処理時間: {dur:.2f}秒)", "INFO")
                        self.task_durations.append(dur)
                    else:
                        self.log_message_ui(f"視点 {prog_entry['viewpoint_index'] + 1} エラー: {prog_entry.get('error_message', '不明なエラー')}", "ERROR")

                    self.viewpoint_progress_text_var.set(f"{self.completed_tasks_count} / {self.total_tasks_for_conversion} 視点")
                    if self.total_tasks_for_conversion > 0:
                        self.progress_bar["value"] = (self.completed_tasks_count / self.total_tasks_for_conversion) * 100
        except (multiprocessing.queues.Empty, AttributeError, EOFError, FileNotFoundError):
            pass # Expected
        except Exception as e:
            print(f"Progress queue processing error: {type(e).__name__} - {e}")

        # --- Time estimation logic (only if conversion_pool is active) ---
        if self.conversion_pool:
            if self.start_time > 0:
                self.elapsed_time_str = str(timedelta(seconds=int(time.time() - self.start_time)))

            if new_task_completed_this_cycle and self.total_tasks_for_conversion > 0 and self.completed_tasks_count > 0:
                if self.task_durations: # Make sure there are durations to average
                    self.avg_time_per_viewpoint_for_estimation = sum(self.task_durations) / len(self.task_durations)

                if self.avg_time_per_viewpoint_for_estimation > 0:
                    remaining_tasks = self.total_tasks_for_conversion - self.completed_tasks_count
                    try:
                        num_parallel_processes = int(self.parallel_processes_var.get())
                    except ValueError:
                        num_parallel_processes = 1 # Fallback
                    effective_parallelism = min(num_parallel_processes, remaining_tasks if remaining_tasks > 0 else 1)

                    if remaining_tasks > 0:
                        self.overall_remaining_seconds_at_last_avg_calculation = \
                            (remaining_tasks * self.avg_time_per_viewpoint_for_estimation) / effective_parallelism
                        self.timestamp_of_last_avg_calculation = time.time()
                    else: # All tasks completed
                        self.overall_remaining_seconds_at_last_avg_calculation = 0
                        self.timestamp_of_last_avg_calculation = time.time()

            # Update remaining time string based on last calculation
            if self.overall_remaining_seconds_at_last_avg_calculation is not None and \
               self.timestamp_of_last_avg_calculation is not None:
                time_since_last_calc = time.time() - self.timestamp_of_last_avg_calculation
                current_remaining_estimate_sec = self.overall_remaining_seconds_at_last_avg_calculation - time_since_last_calc
                if current_remaining_estimate_sec < 0:
                    current_remaining_estimate_sec = 0
                self.overall_remaining_str = str(timedelta(seconds=int(current_remaining_estimate_sec)))
            elif self.start_time > 0: # Conversion started but no tasks completed yet or no estimate
                self.overall_remaining_str = "計算中..."
            # else: self.overall_remaining_str remains "--:--:--" (set in __init__)

        self.update_time_label_display() # Update the GUI label

        # --- Check for conversion completion or cancellation ---
        all_tasks_accounted_for = (self.completed_tasks_count >= self.total_tasks_for_conversion and self.total_tasks_for_conversion > 0)
        is_cancelled = (self.cancel_event_mp and self.cancel_event_mp.is_set() and self.conversion_pool)

        if self.conversion_pool and ( (self.active_tasks_count == 0 and all_tasks_accounted_for) or is_cancelled ):
            if all_tasks_accounted_for and not is_cancelled: # Normal completion
                self.overall_remaining_str = "00:00:00"
                self.overall_remaining_seconds_at_last_avg_calculation = 0
                self.timestamp_of_last_avg_calculation = time.time()
            self.update_time_label_display()
            self.conversion_finished_or_cancelled_mp()
        elif self.conversion_pool or \
             (self.manager_mp and self.log_queue_mp and not self.log_queue_mp.empty()): # Continue processing if pool exists or logs pending
            self.after(100, self.process_mp_queues)


    def update_time_label_display(self):
        is_converting = bool(self.conversion_pool)
        display_text = ""
        if self.final_conversion_message and not is_converting:
            display_text = self.final_conversion_message
        elif not is_converting and self.start_time == 0:
            display_text = "経過時間: 00:00:00 / 全体残り: --:--:--"
        else:
            display_text = f"経過時間: {self.elapsed_time_str} / 全体残り: {self.overall_remaining_str}"

        if hasattr(self, 'time_label') and self.time_label.winfo_exists():
            self.time_label.config(text=display_text)
        # else: label might not be created yet or is destroyed.

    def check_ffmpeg_ffprobe(self):
        try:
            res_ffmpeg = subprocess.run(
                [self.ffmpeg_path, "-version"], capture_output=True, text=True, check=True,
                startupinfo=self.get_startupinfo(), encoding='utf-8', errors='replace'
            )
            line_ffmpeg = res_ffmpeg.stdout.splitlines()[0] if res_ffmpeg.stdout else "ffmpeg (バージョン不明)"
            self.log_message_ui(f"FFmpeg: {line_ffmpeg.strip()}", "INFO")
        except FileNotFoundError:
            self.log_message_ui(f"FFmpegが見つかりません: {self.ffmpeg_path}. PATHを確認するか、実行ファイルと同じ場所に配置してください。", "ERROR")
            if hasattr(self, 'start_button'): self.start_button.config(state="disabled")
        except subprocess.CalledProcessError as e:
            self.log_message_ui(f"FFmpeg実行エラー (バージョン確認): {e}", "ERROR")
            if hasattr(self, 'start_button'): self.start_button.config(state="disabled")
        except Exception as e:
            self.log_message_ui(f"FFmpeg確認中に予期せぬエラー: {e}", "ERROR")
            if hasattr(self, 'start_button'): self.start_button.config(state="disabled")

        try:
            res_ffprobe = subprocess.run(
                [self.ffprobe_path, "-version"], capture_output=True, text=True, check=True,
                startupinfo=self.get_startupinfo(), encoding='utf-8', errors='replace'
            )
            line_ffprobe = res_ffprobe.stdout.splitlines()[0] if res_ffprobe.stdout else "ffprobe (バージョン不明)"
            self.log_message_ui(f"ffprobe: {line_ffprobe.strip()}", "INFO")
        except FileNotFoundError:
            self.log_message_ui(f"ffprobeが見つかりません: {self.ffprobe_path}. PATHを確認するか、実行ファイルと同じ場所に配置してください。", "ERROR")
            if hasattr(self, 'start_button'): self.start_button.config(state="disabled")
        except subprocess.CalledProcessError as e:
            self.log_message_ui(f"ffprobe実行エラー (バージョン確認): {e}", "ERROR")
            if hasattr(self, 'start_button'): self.start_button.config(state="disabled")
        except Exception as e:
            self.log_message_ui(f"ffprobe確認中に予期せぬエラー: {e}", "ERROR")
            if hasattr(self, 'start_button'): self.start_button.config(state="disabled")


    def check_cuda_availability(self):
        try:
            res = subprocess.run(
                [self.ffmpeg_path, "-hide_banner", "-hwaccels"],
                capture_output=True, text=True, startupinfo=self.get_startupinfo(),
                encoding='utf-8', errors='replace'
            )
            if "cuda" in res.stdout.lower():
                self.cuda_available = True
                if hasattr(self, 'cuda_check'): self.cuda_check.config(state="normal")
                self.cuda_var.set(True)
                self.log_message_ui("CUDA利用可能 (デフォルト有効)", "INFO")
            else:
                self.cuda_available = False
                if hasattr(self, 'cuda_check'): self.cuda_check.config(state="disabled")
                self.cuda_var.set(False)
                self.log_message_ui("CUDA利用不可", "INFO")
        except Exception as e:
            self.cuda_available = False
            if hasattr(self, 'cuda_check'): self.cuda_check.config(state="disabled")
            self.cuda_var.set(False)
            self.log_message_ui(f"CUDA検出エラー: {e}", "WARNING")

        self.apply_cuda_restrictions_based_on_video_info()

    def apply_cuda_restrictions_based_on_video_info(self):
        if not self.cuda_available:
            self.cuda_var.set(False)
            if hasattr(self, 'cuda_check'): self.cuda_check.config(state="disabled")
            return
        is_high_res = (self.video_width > HIGH_RESOLUTION_THRESHOLD or
                       self.video_height > HIGH_RESOLUTION_THRESHOLD)
        if is_high_res and self.cuda_var.get():
            self.log_message_ui(
                f"高解像度({self.video_width}x{self.video_height})入力。CUDA使用時は互換性テスト実行。", "INFO"
            )

    def get_startupinfo(self):
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            return startupinfo
        return None

    def browse_input_file(self):
        fp = filedialog.askopenfilename(
            title="入力動画ファイルを選択",
            filetypes=(("動画ファイル", "*.mp4 *.mov *.avi *.mkv"), ("すべてのファイル", "*.*"))
        )
        if fp:
            self.input_file_var.set(fp)
            self.log_message_ui(f"入力ファイル選択: {fp}", "INFO")
            if not self.output_folder_var.get(): # Set default output if not already set
                default_output_dir = os.path.dirname(fp)
                self.output_folder_var.set(default_output_dir)
                self.log_message_ui(f"出力フォルダ自動設定: {default_output_dir}", "INFO")

            self.get_video_info(fp) # This will call update_resolution_options
            self.apply_cuda_restrictions_based_on_video_info()
            # Reset CUDA compatibility flags for the new file
            self.cuda_checked_for_high_res_compatibility = False
            self.cuda_fallback_triggered_for_high_res = False
            self.cuda_compatibility_confirmed_for_high_res = False

    def browse_output_folder(self):
        fp = filedialog.askdirectory(title="出力フォルダを選択")
        if fp:
            self.output_folder_var.set(fp)
            self.log_message_ui(f"出力フォルダ選択: {fp}", "INFO")

    def get_video_info(self, filepath):
        try:
            cmd = [
                self.ffprobe_path, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,duration,r_frame_rate,codec_name",
                "-of", "json", filepath
            ]
            res = subprocess.run(
                cmd, capture_output=True, text=True, check=True,
                startupinfo=self.get_startupinfo(), encoding='utf-8', errors='replace'
            )
            if not res.stdout.strip():
                self.log_message_ui(f"動画情報取得失敗: ffprobeの出力が空です。ファイルパス: {filepath}", "ERROR")
                self.video_width, self.video_height, self.video_duration, self.video_fps = 0, 0, 0.0, 0.0
                self.update_resolution_options() # Update with zeroed info
                return

            info = json.loads(res.stdout)["streams"][0]
            self.video_width = int(info.get("width", 0))
            self.video_height = int(info.get("height", 0))
            try:
                self.video_duration = float(info.get("duration", 0.0))
            except (ValueError, TypeError):
                self.video_duration = 0.0
            if self.video_duration < 0: self.video_duration = 0.0 # Duration cannot be negative

            r_fps_str = info.get("r_frame_rate", "0/0")
            if '/' in r_fps_str:
                num_str, den_str = r_fps_str.split('/')
                try:
                    self.video_fps = (int(num_str) / int(den_str)) if int(den_str) > 0 else 0.0
                except ValueError: self.video_fps = 0.0
            else:
                try: self.video_fps = float(r_fps_str)
                except ValueError: self.video_fps = 0.0

            codec = info.get("codec_name", "不明")
            self.log_message_ui(
                f"動画情報: {self.video_width}x{self.video_height}, "
                f"{self.video_duration:.2f}s, FPS:{self.video_fps:.2f}, Codec:{codec}",
                "INFO"
            )
        except subprocess.CalledProcessError as e:
            self.log_message_ui(f"動画情報取得エラー (ffprobe実行失敗): {e.stderr or e}", "ERROR")
            self.video_width, self.video_height, self.video_duration, self.video_fps = 0, 0, 0.0, 0.0
        except json.JSONDecodeError:
            output = res.stdout if 'res' in locals() else 'N/A'
            self.log_message_ui(f"動画情報取得エラー (JSON解析失敗)。ffprobe出力: {output}", "ERROR")
            self.video_width, self.video_height, self.video_duration, self.video_fps = 0, 0, 0.0, 0.0
        except Exception as e:
            self.log_message_ui(f"動画情報取得中に予期せぬエラー: {e}", "ERROR")
            self.video_width, self.video_height, self.video_duration, self.video_fps = 0, 0, 0.0, 0.0

        self.update_resolution_options() # Always update resolution options after getting info


    def update_resolution_options(self, event=None):
        selected_resolution_mode = self.resolution_var.get()
        if selected_resolution_mode == "カスタム...":
            self.custom_resolution_entry.config(state="normal")
        else:
            self.custom_resolution_entry.config(state="disabled")
            if selected_resolution_mode == "自動 (入力動画に合わせる)":
                # Use video_height (shorter side for typical landscape 360 video)
                # or default if video info is not available
                resolution_value = str(self.video_height) if self.video_height > 0 else str(DEFAULT_RESOLUTION_WIDTH)
                self.custom_resolution_var.set(resolution_value)
            else: # A specific numeric value was chosen from the combobox
                self.custom_resolution_var.set(selected_resolution_mode)

    def update_output_format_options(self, event=None):
        selected_format = self.output_format_var.get()
        is_converting = bool(self.conversion_pool) # Check if conversion is in progress

        normal_state = tk.NORMAL if not is_converting else tk.DISABLED
        readonly_state = "readonly" if not is_converting else tk.DISABLED
        disabled_state = tk.DISABLED

        # PNG options
        self.png_frame_interval_entry.config(state=normal_state if selected_format == "png" else disabled_state)
        self.png_pred_combo.config(state=readonly_state if selected_format == "png" else disabled_state)

        # JPEG options
        self.jpeg_frame_interval_entry.config(state=normal_state if selected_format == "jpeg" else disabled_state)
        self.jpeg_quality_entry.config(state=normal_state if selected_format == "jpeg" else disabled_state)

        # Video options
        self.preset_combo.config(state=readonly_state if selected_format == "video" else disabled_state)
        self.cq_entry.config(state=normal_state if selected_format == "video" else disabled_state)


    def validate_inputs(self):
        if not (self.input_file_var.get() and os.path.isfile(self.input_file_var.get())):
            self.log_message_ui("入力動画ファイルが無効です。実在するファイルを選択してください。", "ERROR")
            return False
        if not (self.output_folder_var.get() and os.path.isdir(self.output_folder_var.get())):
            self.log_message_ui("出力フォルダが無効です。実在するフォルダを選択してください。", "ERROR")
            return False

        selected_format = self.output_format_var.get() # ここで定義されている
        if selected_format in ["png", "jpeg"]:
            try:
                interval = float(self.frame_interval_var.get())
                if interval <= 0:
                    self.log_message_ui("フレーム抽出間隔は正の値でなければなりません。", "ERROR")
                    return False
                # --- 動画デュレーションチェック ---
                elif self.video_duration > 0 and interval > self.video_duration:
                    # 警告として表示し、処理は止めない場合 (もし止めるなら return False)
                    self.log_message_ui(
                        f"フレーム抽出間隔 ({interval:.2f}秒) が動画の総再生時間 ({self.video_duration:.2f}秒) を超えています。"
                        "1フレームのみ抽出される可能性があります。",
                        "WARNING"
                    )
            except ValueError:
                self.log_message_ui("フレーム抽出間隔は数値で入力してください。", "ERROR")
                return False

            if selected_format == "jpeg": # selected_format を使用
                try:
                    jpeg_q = int(self.jpeg_quality_var.get())
                    if not (1 <= jpeg_q <= 100):
                        self.log_message_ui("JPEG品質は1から100の整数でなければなりません。", "ERROR")
                        return False
                except ValueError:
                    self.log_message_ui("JPEG品質は整数で入力してください。", "ERROR")
                    return False
        elif selected_format == "video":
            try:
                cq_crf_value = int(self.cq_var.get())
                if not (0 <= cq_crf_value <= 51): # Common range for CRF/CQ
                    self.log_message_ui("動画品質(CQ/CRF)は0から51の範囲でなければなりません。", "ERROR")
                    return False
            except ValueError:
                self.log_message_ui("動画品質(CQ/CRF)は整数で入力してください。", "ERROR")
                return False

        try:
            width, height = self.get_output_resolution()
            if width <= 0 or height <= 0:
                 self.log_message_ui("出力解像度は正の値でなければなりません。", "ERROR")
                 return False
        except ValueError: # get_output_resolution might raise if custom_resolution_var is non-numeric
            self.log_message_ui("出力解像度の値が無効です。数値で入力してください。", "ERROR")
            return False
        except Exception as e: # Catch any other unexpected errors during resolution validation
            self.log_message_ui(f"出力解像度の検証中にエラーが発生しました: {e}", "ERROR")
            return False
        return True


    def calculate_viewpoints(self):
        if self.yaw_selector_widget:
            viewpoints = self.yaw_selector_widget.get_selected_viewpoints()
            if not viewpoints:
                self.log_message_ui("有効な視点がありません。視点設定を確認してください。", "WARNING")
            else:
                self.log_message_ui(f"計算された総視点数: {len(viewpoints)}", "DEBUG")
            return viewpoints
        else:
            self.log_message_ui("視点セレクターが初期化されていません。", "ERROR")
            return []


    def get_output_resolution(self):
        width_str = self.custom_resolution_var.get()
        try:
            width = int(width_str)
            if width <= 0:
                self.log_message_ui(
                    f"解像度指定が無効なため ({width_str})、"
                    f"デフォルト値({DEFAULT_RESOLUTION_WIDTH})を使用します。", "WARNING"
                )
                width = DEFAULT_RESOLUTION_WIDTH
                self.custom_resolution_var.set(str(DEFAULT_RESOLUTION_WIDTH)) 
        except ValueError:
            self.log_message_ui(
                f"解像度指定が数値ではないため ({width_str})、"
                f"デフォルト値({DEFAULT_RESOLUTION_WIDTH})を使用します。", "WARNING"
            )
            width = DEFAULT_RESOLUTION_WIDTH
            self.custom_resolution_var.set(str(DEFAULT_RESOLUTION_WIDTH)) 

        return max(1, width), max(1, width) 


    def toggle_ui_state(self, converting=False):
        new_state = tk.DISABLED if converting else tk.NORMAL
        readonly_state_if_not_converting = "readonly" if not converting else tk.DISABLED

        self.browse_input_button.config(state=new_state)
        self.browse_output_button.config(state=new_state)

        self.resolution_combo.config(state=readonly_state_if_not_converting)
        if not converting and self.resolution_var.get() == "カスタム...":
            self.custom_resolution_entry.config(state="normal")
        else:
            self.custom_resolution_entry.config(state=tk.DISABLED)

        self.cuda_check.config(state="normal" if not converting and self.cuda_available else tk.DISABLED)
        self.interp_combo.config(state=readonly_state_if_not_converting)

        if self.yaw_selector_widget:
            if converting:
                if hasattr(self.yaw_selector_widget, 'disable_controls'):
                    self.yaw_selector_widget.disable_controls()
            else:
                if hasattr(self.yaw_selector_widget, 'enable_controls'):
                    self.yaw_selector_widget.enable_controls()

        self.png_radio.config(state=new_state)
        self.jpeg_radio.config(state=new_state)
        self.video_radio.config(state=new_state)
        self.update_output_format_options() 

        self.parallel_combo.config(state=readonly_state_if_not_converting)
        self.start_button.config(state=tk.NORMAL if not converting else tk.DISABLED)
        self.cancel_button.config(state=tk.DISABLED if not converting else tk.NORMAL)


    def run_cuda_compatibility_test(self):
        if not (self.cuda_var.get() and self.cuda_available):
            self.log_message_ui("CUDA非使用または利用不可のため、互換性テストをスキップ。", "DEBUG")
            self.cuda_checked_for_high_res_compatibility = True 
            self.cuda_compatibility_confirmed_for_high_res = True 
            return True

        test_fov = DEFAULT_FOV_INTERNAL 
        if self.yaw_selector_widget and hasattr(self.yaw_selector_widget, 'get_current_fov_for_selected_pitch'):
            current_fov_from_selector = self.yaw_selector_widget.get_current_fov_for_selected_pitch()
            if current_fov_from_selector is not None:
                test_fov = current_fov_from_selector
            else: 
                viewpoints_for_fov_test = self.yaw_selector_widget.get_selected_viewpoints()
                if viewpoints_for_fov_test:
                    test_fov = viewpoints_for_fov_test[0]['fov']

        output_w, output_h = self.get_output_resolution()
        v360_params_str = (
            f"e:flat:yaw=0.00:pitch=0.00:h_fov={test_fov:.2f}:v_fov={test_fov:.2f}"
            f":w={output_w}:h={output_h}:interp={self.interp_var.get()}"
        )
        filter_complex_parts_test = ["hwdownload", "format=nv12", f"v360={v360_params_str}", "format=rgb24"]
        cmd_test = [
            self.ffmpeg_path, "-y", "-loglevel", "error", 
            "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
            "-i", self.input_file_var.get(),
            "-vf", ",".join(filter_complex_parts_test),
            "-frames:v", "1", "-an", "-sn", "-f", "null", "-" 
        ]
        self.log_message_ui("CUDA互換性テスト (1フレーム) 開始...", "INFO")
        self.log_message_ui(f"テストCMD(一部): {' '.join(cmd_test[:15])} ...", "DEBUG")

        ffmpeg_output_str = ""
        test_successful_run = False
        try:
            process = subprocess.run(
                cmd_test, capture_output=True, text=True, startupinfo=self.get_startupinfo(),
                encoding='utf-8', errors='replace', timeout=30 
            )
            ffmpeg_output_str = process.stderr + ("\n" + process.stdout if process.stdout else "")
            if process.returncode == 0:
                self.log_message_ui("CUDAテスト: FFmpeg正常終了 (コード0)。", "INFO")
                test_successful_run = True
            else:
                self.log_message_ui(f"CUDAテスト: FFmpegエラー (コード{process.returncode})。", "WARNING")
                self.log_message_ui(f"FFmpegエラー出力(テスト時):\n{ffmpeg_output_str}", "DEBUG")
        except subprocess.TimeoutExpired:
            self.log_message_ui("CUDAテストがタイムアウトしました。CPUフォールバックを推奨します。", "ERROR")
            ffmpeg_output_str += "\nError: FFmpeg process timed out during CUDA compatibility test."
            self.cuda_fallback_triggered_for_high_res = True 
        except Exception as e:
            self.log_message_ui(f"CUDAテスト中に例外が発生しました: {e}", "ERROR")
            ffmpeg_output_str += f"\nException during CUDA test: {e}"
            self.cuda_fallback_triggered_for_high_res = True 

        self.cuda_checked_for_high_res_compatibility = True 

        if self.cuda_fallback_triggered_for_high_res: 
            return False

        if test_successful_run:
            if check_for_cuda_fallback_error(ffmpeg_output_str): 
                self.log_message_ui(
                    "CUDAテスト: FFmpegは正常終了しましたが、出力にCUDA関連エラーの兆候が見られます。"
                    "CPUフォールバックを推奨します。", "WARNING"
                )
                self.cuda_fallback_triggered_for_high_res = True
                return False
            else:
                self.log_message_ui("CUDAテスト: 互換性ありと判断されました。", "INFO")
                self.cuda_compatibility_confirmed_for_high_res = True
                return True
        else: 
            if check_for_cuda_fallback_error(ffmpeg_output_str):
                self.log_message_ui("CUDAテスト: CUDA関連のエラーが検出されました。CPUフォールバックします。", "WARNING")
            else:
                self.log_message_ui(
                    "CUDAテスト: FFmpegがエラーで終了しました (CUDA関連以外の可能性あり)。"
                    "安全のためCPUフォールバックします。", "ERROR"
                )
            self.cuda_fallback_triggered_for_high_res = True
            return False


    def start_conversion_mp(self):
        if not self.validate_inputs():
            return

        viewpoints = self.calculate_viewpoints()
        if not viewpoints:
            self.log_message_ui("変換対象の視点がありません。処理を開始できません。", "ERROR")
            return

        self.cuda_checked_for_high_res_compatibility = False
        self.cuda_fallback_triggered_for_high_res = False
        self.cuda_compatibility_confirmed_for_high_res = False

        is_high_res_input = (self.video_width > HIGH_RESOLUTION_THRESHOLD or
                             self.video_height > HIGH_RESOLUTION_THRESHOLD)
        effective_use_cuda = self.cuda_var.get() and self.cuda_available

        if is_high_res_input and effective_use_cuda:
            self.log_message_ui("高解像度入力のため、CUDA互換性テストを実行します...", "INFO")
            self.toggle_ui_state(converting=True) 
            self.update_idletasks() 

            if not self.run_cuda_compatibility_test():
                self.log_message_ui("CUDA互換性テストの結果、CPU処理へフォールバックします。", "WARNING")
                effective_use_cuda = False 
            else:
                self.log_message_ui("CUDA互換性テストの結果、CUDA処理を継続します。", "INFO")
        else:
            self.cuda_checked_for_high_res_compatibility = True
            self.cuda_compatibility_confirmed_for_high_res = True 

        self.total_tasks_for_conversion = len(viewpoints)
        self.completed_tasks_count = 0
        self.active_tasks_count = 0
        self.task_durations = []
        self.final_conversion_message = None
        self.overall_remaining_seconds_at_last_avg_calculation = None
        self.timestamp_of_last_avg_calculation = None

        self.toggle_ui_state(converting=True) 
        self.log_message_ui("変換処理を開始します (並列処理)...", "INFO")

        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = 100 
        self.viewpoint_progress_text_var.set(f"0 / {self.total_tasks_for_conversion} 視点")
        self.start_time = time.time()
        self.elapsed_time_str = "00:00:00"
        self.overall_remaining_str = "計算中..." if self.total_tasks_for_conversion > 0 else "--:--:--"
        self.update_time_label_display()

        try:
            num_parallel = int(self.parallel_processes_var.get())
        except ValueError:
            num_parallel = 1 
            self.log_message_ui(f"並列処理数の値が無効です。1に設定しました。", "WARNING")
            self.parallel_processes_var.set("1")


        try:
            if self.manager_mp is None or \
               (hasattr(self.manager_mp, '_process') and not self.manager_mp._process.is_alive()):
                self.manager_mp = multiprocessing.Manager()

            self.log_queue_mp = self.manager_mp.Queue()
            self.progress_queue_mp = self.manager_mp.Queue()
            self.cancel_event_mp = self.manager_mp.Event()
            self.conversion_pool = multiprocessing.Pool(processes=num_parallel)
        except Exception as e:
            self.log_message_ui(f"並列処理の初期化に失敗しました: {e}", "CRITICAL")
            self.toggle_ui_state(converting=False)
            self.start_time = 0 
            return

        output_w, output_h = self.get_output_resolution()

        if self.cuda_fallback_triggered_for_high_res: 
            effective_use_cuda = False
            self.log_message_ui("CUDAフォールバックがトリガーされたため、全ての視点をCPUで処理します。", "INFO")
        elif is_high_res_input and self.cuda_var.get() and self.cuda_available and \
             not self.cuda_compatibility_confirmed_for_high_res:
            self.log_message_ui("CUDA互換性が明確に確認できなかったため、安全のためCPUで処理します。", "WARNING")
            effective_use_cuda = False

        worker_config = {
            "ffmpeg_path": self.ffmpeg_path,
            "input_file": self.input_file_var.get(),
            "output_folder": self.output_folder_var.get(),
            "output_resolution": (output_w, output_h),
            "interp": self.interp_var.get(),
            "threads_ffmpeg": self.internal_threads_value, 
            "use_cuda": effective_use_cuda,
            "output_format": self.output_format_var.get(),
            "frame_interval": float(self.frame_interval_var.get()) if self.output_format_var.get() in ["png", "jpeg"] else 0,
            "video_preset": self.preset_var.get(),
            "video_cq": self.cq_var.get(),
            "png_pred_option": self.png_pred_options_map.get(self.png_pred_var.get(), "3"),
            "jpeg_quality": int(self.jpeg_quality_var.get()) if self.jpeg_quality_var.get().isdigit() else 90
        }

        for i, vp_data in enumerate(viewpoints):
            self.conversion_pool.apply_async(
                ffmpeg_worker_process,
                args=(i, vp_data, worker_config, self.log_queue_mp, self.progress_queue_mp, self.cancel_event_mp)
            )
            self.active_tasks_count += 1

        self.conversion_pool.close() 

        if self.total_tasks_for_conversion > 0:
            self.after(100, self.process_mp_queues) 
        else: 
            self.conversion_finished_or_cancelled_mp()


    def conversion_finished_or_cancelled_mp(self):
        if self.start_time == 0 and not (self.cancel_event_mp and self.cancel_event_mp.is_set()):
            return

        elapsed_seconds = time.time() - self.start_time if self.start_time > 0 else 0
        elapsed_time_formatted = str(timedelta(seconds=int(elapsed_seconds)))

        was_cancelled = self.cancel_event_mp and self.cancel_event_mp.is_set()
        final_verb = "処理中断" if was_cancelled else "変換完了"

        self.log_message_ui(f"全ての変換処理が{final_verb.lower()}しました。", "INFO")
        self.viewpoint_progress_text_var.set(
            f"{self.completed_tasks_count} / {self.total_tasks_for_conversion} 視点 ({final_verb})"
        )

        if not was_cancelled and self.completed_tasks_count >= self.total_tasks_for_conversion:
            self.progress_bar["value"] = 100
            self.overall_remaining_str = "00:00:00" 

        self.final_conversion_message = f"{final_verb} - 総時間: {elapsed_time_formatted}"
        self.update_time_label_display() 

        if self.conversion_pool:
            try:
                if was_cancelled:
                    self.conversion_pool.terminate()
                self.conversion_pool.join() # timeout 引数を削除
            except Exception as e:
                self.log_message_ui(f"Pool終了処理中にエラー: {e}", "WARNING")
            finally:
                self.conversion_pool = None 

        self.active_tasks_count = 0
        self.start_time = 0 
        self.toggle_ui_state(converting=False) 


    def cancel_conversion_mp(self):
        if self.cancel_event_mp and not self.cancel_event_mp.is_set():
            self.log_message_ui("変換中止を要求しました...", "INFO")
            self.cancel_event_mp.set()
            if hasattr(self, 'cancel_button'):
                self.cancel_button.config(state=tk.DISABLED) 


    def on_closing(self):
        if self.conversion_pool and self.active_tasks_count > 0:
            if messagebox.askyesno("確認", "変換処理が実行中です。中止して終了しますか？"):
                self.log_message_ui("ウィンドウクローズによる変換中止...", "WARNING")
                if self.cancel_event_mp and not self.cancel_event_mp.is_set():
                    self.cancel_event_mp.set()

                if self.conversion_pool:
                    try:
                        self.conversion_pool.terminate() 
                        self.conversion_pool.join() # timeout 引数を削除
                    except Exception as e:
                        self.log_message_ui(f"終了時のPool強制停止エラー: {e}", "WARNING")
                    finally:
                        self.conversion_pool = None

                if self.manager_mp and hasattr(self.manager_mp, 'shutdown'):
                    if hasattr(self.manager_mp, '_process') and self.manager_mp._process.is_alive():
                        try:
                            self.manager_mp.shutdown()
                        except Exception as e:
                            print(f"Manager shutdown error on closing (active pool): {e}")
                    self.manager_mp = None
                self.destroy()
            else:
                return 
        else: 
            if self.manager_mp and hasattr(self.manager_mp, 'shutdown'):
                if hasattr(self.manager_mp, '_process') and self.manager_mp._process.is_alive():
                    try:
                        self.manager_mp.shutdown()
                    except Exception as e:
                        print(f"Manager shutdown error on closing (no active pool): {e}")
                self.manager_mp = None
            self.destroy()

if __name__ == '__main__':
    multiprocessing.freeze_support() 
    app = Insta360ConvertGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing) 
    app.mainloop()