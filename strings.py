# strings.py
import locale
import json
import os
import sys # sysモジュールをインポート (エラー出力に使用する可能性)

# --- 設定ファイルのパス ---
SETTINGS_FILE_NAME = "app_settings.json" # アプリケーション設定ファイル名
# このファイルは、ユーザーのドキュメントフォルダやAppData/Application Supportのような
# 書き込み可能な場所に保存することを推奨しますが、ここでは簡易的にカレントディレクトリとします。
# PyInstallerでバンドルする場合、os.path.dirname(sys.executable)などを基点にすることも考慮。

def get_user_system_language():
    """
    ユーザーのシステムの主要な言語コードを取得します (例: 'ja', 'en')。
    日本語環境以外は 'en' をデフォルトとして返します。
    """
    try:
        # getdefaultlocaleはロケール設定に依存し、期待通りに動作しないことがある。
        # より堅牢な方法として、環境変数やプラットフォーム固有APIを検討することもできるが、
        # ここではgetdefaultlocaleを維持しつつ、フォールバックを強化。
        loc = locale.getdefaultlocale()
        if loc and loc[0]:
            lang_code_full = loc[0].lower() #例: 'ja_jp', 'en_us'
            lang_code_short = lang_code_full.split('_')[0] # 'ja', 'en'
            if lang_code_short == 'ja':
                return 'ja'
    except Exception as e: # pylint: disable=broad-except
        # エラーが発生した場合（ロケールが未設定など）でもフォールバック
        print(f"Warning: Could not determine system language via locale: {e}. Defaulting to 'en'.", file=sys.stderr)
    return 'en' # デフォルトは英語

def load_language_preference():
    """
    保存された言語設定を読み込みます。なければシステムの言語を返します。
    設定ファイルの読み込みに失敗した場合もシステムの言語にフォールバックします。
    """
    try:
        if os.path.exists(SETTINGS_FILE_NAME):
            with open(SETTINGS_FILE_NAME, "r", encoding='utf-8') as f:
                settings = json.load(f)
                lang_code = settings.get("language")
                if lang_code in ['ja', 'en']: # サポートする言語コードを明示
                    return lang_code
                else:
                    print(f"Warning: Invalid language code '{lang_code}' in settings. Defaulting.", file=sys.stderr)
        else:
            # 設定ファイルが存在しない場合は、初回起動または削除されたとみなし、
            # システム言語に基づいてデフォルトを設定する。
            pass # Fall through to return system language
    except json.JSONDecodeError as e:
        print(f"Warning: Error decoding language settings file '{SETTINGS_FILE_NAME}': {e}. Defaulting.", file=sys.stderr)
    except IOError as e:
        print(f"Warning: Could not read language settings file '{SETTINGS_FILE_NAME}': {e}. Defaulting.", file=sys.stderr)
    except Exception as e: # pylint: disable=broad-except
        print(f"Warning: Unexpected error loading language preference: {e}. Defaulting.", file=sys.stderr)

    # 上記いずれかの条件で設定から読み込めなかった場合、システム言語を返す
    return get_user_system_language()


def save_language_preference(lang_code):
    """
    言語設定をJSONファイルに保存します。
    """
    if lang_code not in ['ja', 'en']:
        print(f"Error: Attempted to save unsupported language code '{lang_code}'. Aborting save.", file=sys.stderr)
        return

    settings_data = {"language": lang_code}
    try:
        with open(SETTINGS_FILE_NAME, "w", encoding='utf-8') as f:
            json.dump(settings_data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"Error: Could not write language settings to '{SETTINGS_FILE_NAME}': {e}", file=sys.stderr)
    except Exception as e: # pylint: disable=broad-except
        print(f"Error: Unexpected error saving language preference: {e}", file=sys.stderr)


class UiStrings:
    def __init__(self, initial_language='ja'): # デフォルトを 'ja' から initial_language へ変更
        self.language = initial_language
        self._strings = {
            'ja': {
                # --- General ---
                "app_name_short": "Insta360Convert GUI",
                "language_menu_label": "言語 (Language)",
                "language_english": "English",
                "language_japanese": "日本語",
                "error_title": "エラー",
                "warning_title": "警告",
                "info_title": "情報",
                "confirm_title": "確認",
                "language_switched_info": "言語が日本語に変更されました。\n一部の変更はアプリケーションの再起動後に完全に適用される場合があります。",

                # --- gui_app.py: Menu ---
                "menu_help": "ヘルプ",
                "menu_help_about": "バージョン情報",
                "menu_help_check_updates": "アップデートを確認...",
                "about_dialog_title": "バージョン情報",
                "about_dialog_message_format": "{app_name}\nバージョン: {version_display}",
                "update_check_checking_message": "GitHubに最新情報を問い合わせています...\n完了後、結果を通知します。",
                "update_check_error_title": "アップデートエラー",
                "update_check_info_title": "アップデート情報",
                "update_link_error_title": "リンクエラー",
                "update_link_error_message_format": "ダウンロードページを開けませんでした: {error}",
                "update_check.error.fetch_failed": "アップデート情報の取得に失敗しました。\n詳細: {error_detail}", # キー名を変更 (ピリオド区切りへ)
                "update_check.error.no_valid_data": "GitHubから有効なリリースデータを取得できませんでした。\n詳細: {error_detail}", # キー名を変更
                "update_check.error.no_version_tag": "最新リリースのバージョンタグを取得できませんでした。\n詳細: {error_detail}", # キー名を変更
                "update_check.error.load_failed": "アップデートチェック機能の読み込みに失敗しました。\nupdate_checker.py が見つからないか、インポートに失敗しました。",
                "update_check.info.update_available_format": "新しいバージョン ({latest_version}) が利用可能です！\n\n現在のバージョン: {current_version}\n\n主な変更点:\n{release_notes_summary}\n\nダウンロードページを開きますか？", # キー名を変更
                "update_check.info.no_update_format": "現在お使いのバージョン ({current_version}) は最新です。\n(GitHub上の最新: {latest_version})", # キー名を変更


                # --- gui_app.py: File Settings ---
                "file_settings_label": "ファイル設定",
                "input_file_label": "入力動画ファイル:",
                "input_file_entry_tooltip": "選択された入力動画ファイルのパスが表示されます。",
                "browse_button": "参照...",
                "browse_input_button_tooltip": "入力動画ファイルを選択するダイアログを開きます。",
                "output_folder_label": "出力フォルダ:",
                "output_folder_entry_tooltip": "選択された出力フォルダのパスが表示されます。",
                "browse_output_button_tooltip": "出力フォルダを選択するダイアログを開きます。",
                "log_input_file_selected": "入力ファイル選択: {filepath}",
                "log_output_folder_auto_set": "出力フォルダ自動設定: {folderpath}",
                "log_output_folder_selected": "出力フォルダ選択: {folderpath}",
                "filetype_video_files": "動画ファイル",
                "filetype_all_files": "すべてのファイル",


                # --- gui_app.py: Viewpoint Settings (LabelFrame Title) ---
                "viewpoint_settings_labelframe_title": "視点設定 (ピッチ・ヨー・FOV)",
                "viewpoint_settings_labelframe_tooltip": "各ピッチ角でのヨー角とFOV（視野角）を設定します。\n3Dビュー: 左ドラッグで回転、右クリックで選択/解除。",

                # --- gui_app.py: Output Settings ---
                "output_settings_labelframe_title": "出力設定",
                "resolution_label": "解像度:",
                "resolution_label_tooltip": "出力画像/動画の解像度（一辺のピクセル数）。",
                "resolution_auto": "自動 (入力動画に合わせる)",
                "resolution_custom": "カスタム...",
                "resolution_combo_tooltip": "プリセット解像度または「カスタム...」を選択。「自動」は入力動画の短辺に合わせます。",
                "custom_resolution_entry_tooltip": "「カスタム...」選択時に解像度を数値で入力。",
                "cuda_checkbox_label": "CUDA",
                "cuda_checkbox_tooltip": "NVIDIA CUDAで高速化 (利用可能な場合)。\n高解像度入力時はテストされ、問題があれば無効化されることがあります。",
                "interpolation_label": "補間:",
                "interpolation_label_tooltip": "画像補間方法。高画質ほど処理時間が長くなる傾向があります。",
                "interpolation_combo_tooltip": "cubic:高画質(推奨), lanczos:最高画質(シャープ),\nlinear:標準, nearest:高速(低画質)。",
                "png_radio_label": "PNGシーケンス",
                "png_radio_tooltip": "PNG画像のシーケンス。各視点ごとにフォルダ作成。",
                "png_interval_label": "抽出間隔(秒):",
                "png_interval_label_tooltip": "何秒ごとに1フレームを抽出するか。例: 0.5 (毎秒2フレーム)。",
                "png_frame_interval_entry_tooltip": "PNG出力時のフレーム抽出間隔(秒)。",
                "png_prediction_label": "PNG予測:",
                "png_prediction_label_tooltip": "PNGエンコード時の予測フィルター (速度とファイルサイズのトレードオフ)。",
                "png_pred_none": "None (最速, サイズ:特大)",
                "png_pred_sub": "Sub (高速, サイズ:大)",
                "png_pred_up": "Up (高速, サイズ:大)",
                "png_pred_average": "Average (中速, サイズ:中)",
                "png_pred_paeth": "Paeth (低速, サイズ:小)",
                "png_prediction_combo_tooltip": "PNG圧縮方法: None(最速,大), Sub(高速,大), Up(高速,大),\nAverage(中速,中,デフォルト), Paeth(低速,小)。",
                "jpeg_radio_label": "JPEGシーケンス",
                "jpeg_radio_tooltip": "JPEG画像のシーケンス。各視点ごとにフォルダ作成。",
                "jpeg_interval_label": "抽出間隔(秒):",
                "jpeg_interval_label_tooltip": "何秒ごとに1フレームを抽出するか。例: 0.5 (毎秒2フレーム)。",
                "jpeg_frame_interval_entry_tooltip": "JPEG出力時のフレーム抽出間隔(秒)。",
                "jpeg_quality_label": "品質(1-100):",
                "jpeg_quality_label_tooltip": "JPEG品質(1-100)。大きいほど高画質・大ファイルサイズ。",
                "jpeg_quality_entry_tooltip": "JPEG品質(1低～100高)。FFmpeg内部で1高～31低スケールに変換。デフォルト90。",
                "video_radio_label": "動画 (HEVC/H.265)",
                "video_radio_tooltip": "HEVC(H.265)コーデックのMP4動画。各視点ごとに動画ファイル作成。",
                "video_preset_label": "Preset:",
                "video_preset_label_tooltip": "FFmpegエンコードプリセット。速いほど低画質、遅いほど高画質。",
                "video_preset_combo_tooltip": "動画出力時のエンコードプリセット。",
                "video_cq_crf_label": "CQ/CRF:",
                "video_cq_crf_label_tooltip": "固定品質値(0-51)。低いほど高画質(大ファイル)。\nlibx265(CPU CRF):推奨18-28。\nNVENC(CUDA CQ):推奨15-28程度。",
                "video_cq_crf_entry_tooltip": "動画出力時の品質値。",

                # --- gui_app.py: Controls and Progress ---
                "parallel_processes_label": "並列処理数:",
                "parallel_processes_label_tooltip_format": "同時に処理する視点の数。最大: {cores} (論理コア数)",
                "parallel_processes_combo_tooltip": "変換処理を並列実行するプロセス数。\nCPUコア数と適用ピッチ角数に応じて調整。",
                "start_button_label": "変換開始",
                "start_button_tooltip": "設定に基づいて変換処理を開始します。",
                "cancel_button_label": "中止",
                "cancel_button_tooltip": "現在進行中の変換処理を中止します。",
                "time_label_tooltip": "変換処理の経過時間と推定残り時間を表示します。",
                "viewpoint_progress_label_tooltip": "処理済みの視点数と総視点数を表示します。",
                "progressbar_tooltip": "全体の変換処理の進捗状況を示します。",
                "log_tab_app_log_label": "アプリケーションログ",
                "log_tab_app_log_tooltip": "アプリケーションの動作ログやエラーメッセージが表示されます。",
                "log_tab_ffmpeg_log_label": "FFmpeg出力ログ",
                "log_tab_ffmpeg_log_tooltip": "FFmpegコマンドの生出力が表示されます。詳細な変換状況の確認に利用します。",
                "time_display_elapsed": "経過時間",
                "time_display_remaining_overall": "全体残り",
                "time_display_remaining_calculating": "計算中...",
                "time_display_not_started": "--:--:--",
                "viewpoint_progress_format": "{completed} / {total} 視点",
                "viewpoint_progress_status_completed": "変換完了",
                "viewpoint_progress_status_cancelled": "処理中断",
                "viewpoint_progress_status_error": "(エラー)",

                # --- gui_app.py: Logging & Messages ---
                "log_ffmpeg_found_format": "FFmpeg: {version_line}",
                "log_ffmpeg_not_found_format": "FFmpegが見つかりません: {path}。 PATHを確認するか、実行ファイルと同じ場所に配置してください。",
                "log_ffmpeg_error_format": "FFmpeg実行エラー (バージョン確認): {error}",
                "log_ffmpeg_unexpected_error_format": "FFmpeg確認中に予期せぬエラー: {error}",
                "log_ffprobe_found_format": "ffprobe: {version_line}",
                "log_ffprobe_not_found_format": "ffprobeが見つかりません: {path}。 PATHを確認するか、実行ファイルと同じ場所に配置してください。",
                "log_ffprobe_error_format": "ffprobe実行エラー (バージョン確認): {error}",
                "log_ffprobe_unexpected_error_format": "ffprobe確認中に予期せぬエラー: {error}",
                "log_cuda_available": "CUDA利用可能 (デフォルト有効)",
                "log_cuda_unavailable": "CUDA利用不可",
                "log_cuda_detection_error_format": "CUDA検出エラー: {error}",
                "log_cuda_high_res_test_info_format": "高解像度({width}x{height})入力。CUDA使用時は互換性テスト実行。",
                "log_cuda_settings_changed_retest": "CUDA設定変更。高解像度入力の場合、次回変換時に互換性テストが再実行されます。",
                "log_video_info_format": "動画情報: {width}x{height}, {duration:.2f}s, FPS:{fps:.2f}, Codec:{codec}",
                "log_video_info_error_ffprobe_failed_format": "動画情報取得エラー (ffprobe実行失敗): {error}",
                "log_video_info_error_ffprobe_empty_output_format": "動画情報取得失敗: ffprobeの出力が空です。ファイルパス: {filepath}",
                "log_video_info_error_json_parse_failed_format": "動画情報取得エラー (JSON解析失敗)。ffprobe出力: {output}",
                "log_video_info_error_unexpected_format": "動画情報取得中に予期せぬエラー: {error}",
                "validate_error_input_file_invalid": "入力動画ファイルが無効です。実在するファイルを選択してください。",
                "validate_error_output_folder_invalid": "出力フォルダが無効です。実在するフォルダを選択してください。",
                "validate_error_frame_interval_positive": "フレーム抽出間隔は正の値でなければなりません。",
                "validate_warning_frame_interval_too_long_format": "フレーム抽出間隔 ({interval:.2f}秒) が動画の総再生時間 ({duration:.2f}秒) を超えています。1フレームのみ抽出される可能性があります。",
                "validate_error_frame_interval_numeric": "フレーム抽出間隔は数値で入力してください。",
                "validate_error_jpeg_quality_range": "JPEG品質は1から100の整数でなければなりません。",
                "validate_error_jpeg_quality_integer": "JPEG品質は整数で入力してください。",
                "validate_error_video_quality_range": "動画品質(CQ/CRF)は0から51の範囲でなければなりません。",
                "validate_error_video_quality_integer": "動画品質(CQ/CRF)は整数で入力してください。",
                "validate_error_resolution_positive": "出力解像度は正の値でなければなりません。",
                "validate_error_resolution_invalid_numeric": "出力解像度の値が無効です。数値で入力してください。",
                "validate_error_resolution_general_format": "出力解像度の検証中にエラーが発生しました: {error}",
                "log_resolution_fallback_warning_format": "解像度指定が無効なため ({value})、デフォルト値({default_res})を使用します。",
                "log_viewpoints_calculated_format": "計算された総視点数: {count}",
                "log_viewpoints_none": "有効な視点がありません。視点設定を確認してください。",
                "log_yaw_selector_not_initialized": "視点セレクターが初期化されていません。",
                "log_conversion_cannot_start_no_viewpoints": "変換対象の視点がありません。処理を開始できません。",
                "log_cuda_compatibility_test_skip_non_cuda": "CUDA非使用または利用不可のため、互換性テストをスキップ。",
                "log_cuda_compatibility_test_starting": "CUDA互換性テスト (1フレーム) 開始...",
                "log_cuda_compatibility_test_cmd_format": "テストCMD(一部): {command_part} ...",
                "log_cuda_compatibility_test_ffmpeg_ok": "CUDAテスト: FFmpeg正常終了 (コード0)。",
                "log_cuda_compatibility_test_ffmpeg_error_format": "CUDAテスト: FFmpegエラー (コード{code})。",
                "log_cuda_compatibility_test_ffmpeg_error_output_format": "FFmpegエラー出力(テスト時):\n{output}",
                "log_cuda_compatibility_test_timeout": "CUDAテストがタイムアウトしました。CPUフォールバックを推奨します。",
                "log_cuda_compatibility_test_exception_format": "CUDAテスト中に例外が発生しました: {error}",
                "log_cuda_test_success_with_error_signs": "CUDAテスト: FFmpegは正常終了しましたが、出力にCUDA関連エラーの兆候が見られます。CPUフォールバックを推奨します。",
                "log_cuda_compatibility_test_ok": "CUDAテスト: 互換性ありと判断されました。",
                "log_cuda_test_error_detected_cpu_fallback": "CUDAテスト: CUDA関連のエラーが検出されました。CPUフォールバックします。",
                "log_cuda_test_ffmpeg_error_cpu_fallback": "CUDAテスト: FFmpegがエラーで終了しました (CUDA関連以外の可能性あり)。安全のためCPUフォールバックします。",
                "log_cuda_high_res_test_execute": "高解像度入力のため、CUDA互換性テストを実行します...",
                "log_cuda_high_res_test_fallback_cpu": "CUDA互換性テストの結果、CPU処理へフォールバックします。",
                "log_cuda_high_res_test_continue_cuda": "CUDA互換性テストの結果、CUDA処理を継続します。",
                "log_conversion_starting_parallel": "変換処理を開始します (並列処理)...",
                "log_parallel_processes_invalid_fallback_format": "並列処理数の値が無効です。1に設定しました。",
                "log_multiprocessing_init_error_format": "並列処理の初期化に失敗しました: {error}",
                "log_cuda_fallback_all_cpu": "CUDAフォールバックがトリガーされたため、全ての視点をCPUで処理します。",
                "log_cuda_compatibility_not_confirmed_cpu": "CUDA互換性が明確に確認できなかったため、安全のためCPUで処理します。",
                "log_task_completed_format": "視点 {index} 完了。(処理時間: {duration:.2f}秒)",
                "log_task_cancelled_format": "視点 {index} はキャンセルされました。",
                "log_task_error_format": "視点 {index} エラー: {error_message}",
                "log_conversion_finished_or_cancelled_format": "全ての変換処理が{status}しました。",
                "log_pool_termination_error_format": "Pool終了処理中にエラー: {error}",
                "log_cancel_requested": "変換中止を要求しました...",
                "confirm_exit_while_converting_title": "確認",
                "confirm_exit_while_converting_message": "変換処理が実行中です。中止して終了しますか？",
                "log_closing_cancelled_conversion": "ウィンドウクローズによる変換中止...",
                "log_pool_forced_termination_error_format": "終了時のPool強制停止エラー: {error}",
                "constants_app_display_version_format": "バージョン: {version} ({date})", # constants.py由来の文字列キー

                # --- advanced_yaw_selector.py ---
                "ays_pitch_to_add_combo_tooltip": "追加するピッチ角をリストから選択します。",
                "ays_add_pitch_button_label": "追加",
                "ays_add_pitch_button_tooltip_format": "選択したピッチ角をリストに追加します (最大{max_entries}個)。",
                "ays_remove_pitch_button_label": "削除",
                "ays_remove_pitch_button_tooltip": "リストで選択中のピッチ角を削除します。",
                "ays_output_pitch_list_label": "出力するピッチ角リスト:",
                "ays_pitch_listbox_tooltip": "出力するピッチ角のリスト。\n選択して右のコントロールで詳細設定を編集します。",
                "ays_pitch_reset_button_label": "P.Reset",
                "ays_pitch_reset_button_tooltip_format": "ピッチ角リストをデフォルト ({default_pitches}) にリセットします。",
                "ays_fov_reset_button_label": "FOV.Rst",
                "ays_fov_reset_button_tooltip_format": "現在選択中のピッチ角のFOVをデフォルト ({default_fov:.0f}度) にリセットします。",
                "ays_yaw_selection_label": "ヨー角選択:",
                "ays_yaw_buttons_tooltip": "現在選択中のピッチ角に対する個別のヨー角を選択/解除します。\n色は3Dプレビューの視点の色と連動します。",
                "ays_pitch_adjust_label_format": "ピッチ角調整 (-90°〜+90°):",
                "ays_pitch_slider_tooltip": "リストで選択中のピッチ角をスライダーで調整します。\nマウスリリース時に値が確定されます。",
                "ays_pitch_entry_tooltip": "選択中のピッチ角を数値で入力 (Enter/FocusOutで確定)。",
                "ays_fov_adjust_label_format": "FOV調整 ({min_fov:.0f}°〜{max_fov:.0f}°):",
                "ays_fov_slider_tooltip_format": "選択中のピッチ角に対する視野角(FOV)を調整します ({min_fov:.0f}°〜{max_fov:.0f}°)。",
                "ays_fov_entry_tooltip": "選択中ピッチのFOVを数値で入力 (Enter/FocusOutで確定)。",
                "ays_yaw_divisions_label_format": "水平視点数 (1〜{max_divisions}):",
                "ays_yaw_divisions_scale_tooltip": "選択中のピッチ角に対する水平方向の視点分割数を設定します。\n変更するとヨー角の選択はリセットされます。",
                "ays_canvas_status_unselected": "Pitch: N/A\nTotal VPs: 0",
                "ays_canvas_status_error": "設定エラー",
                "ays_canvas_status_select_pitch": "ピッチを選択",
                "ays_canvas_status_info_format": "Pitch: {pitch:.1f}° (FOV: {fov_display})\nDivs: {divs}\nTotal VPs: {total_vps}",
                "ays_canvas_help_text": "左ドラッグ:回転  右クリック:視点選択/解除",
                "ays_error_pitch_parse_invalid_string_format": "無効なピッチ入力文字列です: {pitches_str}",
                "ays_warning_pitch_limit_exceeded_format": "初期ピッチ数が{max_entries}個を超えています。\n最初の{max_entries}個のみ読み込みました。",
                "ays_warning_add_pitch_limit_format": "ピッチ角は最大 {max_entries} 個までしか追加できません。",
                "ays_warning_add_pitch_select_pitch": "追加するピッチ角を選択してください。",
                "ays_info_pitch_already_exists": "指定されたピッチ角は既にリストに存在します。",
                "ays_error_add_pitch_invalid_value": "有効な数値を選択してください。",
                "ays_warning_remove_pitch_select_pitch": "削除するピッチ角をリストから選択してください。",
                "ays_info_cannot_remove_last_pitch": "最後のピッチ角は削除できません。\n(最低1つのピッチ角が必要です)",
                "ays_error_remove_pitch_internal_error": "選択されたピッチが内部設定に見つかりません。",
                "ays_error_pitch_entry_invalid_numeric": "ピッチ角には有効な数値を入力してください。",
                "ays_warning_pitch_entry_duplicate_format": "ピッチ角 {pitch_value}° は既にリストに存在します。変更を元に戻します。",
                "ays_error_fov_entry_invalid_numeric": "FOVには有効な数値を入力してください。",
                "ays_info_reset_fov_no_pitch_selected": "FOVをリセットするピッチが選択されていません。",
                "ays_error_key_not_found_in_settings_format": "Error: Key '{key}' not found in pitch_settings during on_pitch_selected.",
            },
            'en': {
                # --- General ---
                "app_name_short": "Insta360Convert GUI",
                "language_menu_label": "Language (言語)",
                "language_english": "English",
                "language_japanese": "日本語",
                "error_title": "Error",
                "warning_title": "Warning",
                "info_title": "Information",
                "confirm_title": "Confirm",
                "language_switched_info": "Language changed to English.\nSome changes may fully apply after restarting the application.",

                # --- gui_app.py: Menu ---
                "menu_help": "Help",
                "menu_help_about": "About",
                "menu_help_check_updates": "Check for Updates...",
                "about_dialog_title": "About",
                "about_dialog_message_format": "{app_name}\nVersion: {version_display}",
                "update_check_checking_message": "Checking GitHub for the latest information...\nYou will be notified of the result.",
                "update_check_error_title": "Update Error",
                "update_check_info_title": "Update Information",
                "update_link_error_title": "Link Error",
                "update_link_error_message_format": "Could not open download page: {error}",
                "update_check.error.fetch_failed": "Failed to fetch update information.\nDetails: {error_detail}", # Key name changed
                "update_check.error.no_valid_data": "Could not retrieve valid release data from GitHub.\nDetails: {error_detail}", # Key name changed
                "update_check.error.no_version_tag": "Could not retrieve version tag for the latest release.\nDetails: {error_detail}", # Key name changed
                "update_check.error.load_failed": "Failed to load the update check feature.\nupdate_checker.py is missing or failed to import.",
                "update_check.info.update_available_format": "A new version ({latest_version}) is available!\n\nCurrent version: {current_version}\n\nMain changes:\n{release_notes_summary}\n\nOpen download page?", # Key name changed
                "update_check.info.no_update_format": "Your current version ({current_version}) is up to date.\n(Latest on GitHub: {latest_version})", # Key name changed


                # --- gui_app.py: File Settings ---
                "file_settings_label": "File Settings",
                "input_file_label": "Input Video File:",
                "input_file_entry_tooltip": "Displays the path of the selected input video file.",
                "browse_button": "Browse...",
                "browse_input_button_tooltip": "Open a dialog to select the input video file.",
                "output_folder_label": "Output Folder:",
                "output_folder_entry_tooltip": "Displays the path of the selected output folder.",
                "browse_output_button_tooltip": "Open a dialog to select the output folder.",
                "log_input_file_selected": "Input file selected: {filepath}",
                "log_output_folder_auto_set": "Output folder auto-set: {folderpath}",
                "log_output_folder_selected": "Output folder selected: {folderpath}",
                "filetype_video_files": "Video Files",
                "filetype_all_files": "All Files",


                # --- gui_app.py: Viewpoint Settings (LabelFrame Title) ---
                "viewpoint_settings_labelframe_title": "Viewpoint Settings (Pitch/Yaw/FOV)",
                "viewpoint_settings_labelframe_tooltip": "Set yaw angles and FOV for each pitch angle.\n3D View: Left-drag to rotate, Right-click to select/deselect.",

                # --- gui_app.py: Output Settings ---
                "output_settings_labelframe_title": "Output Settings",
                "resolution_label": "Resolution:",
                "resolution_label_tooltip": "Resolution (pixels per side) of the output image/video.",
                "resolution_auto": "Automatic (match input video)",
                "resolution_custom": "Custom...",
                "resolution_combo_tooltip": "Select a preset resolution or 'Custom...'. 'Automatic' matches the input video's shorter side.",
                "custom_resolution_entry_tooltip": "Enter resolution numerically when 'Custom...' is selected.",
                "cuda_checkbox_label": "CUDA",
                "cuda_checkbox_tooltip": "Accelerate with NVIDIA CUDA (if available).\nCompatibility is tested for high-res inputs; may be disabled if issues arise.",
                "interpolation_label": "Interpolation:",
                "interpolation_label_tooltip": "Image interpolation method. Higher quality tends to increase processing time.",
                "interpolation_combo_tooltip": "cubic:High quality(recommended), lanczos:Max quality(sharp),\nlinear:Standard, nearest:Fast(low quality).",
                "png_radio_label": "PNG Sequence",
                "png_radio_tooltip": "Sequence of PNG images. Folders created for each viewpoint.",
                "png_interval_label": "Interval (sec):",
                "png_interval_label_tooltip": "Interval for extracting frames (e.g., 0.5 for 2fps).",
                "png_frame_interval_entry_tooltip": "Frame extraction interval (seconds) for PNG output.",
                "png_prediction_label": "PNG Prediction:",
                "png_prediction_label_tooltip": "PNG encoding prediction filter (speed vs. file size tradeoff).",
                "png_pred_none": "None (Fastest, Size:Very Large)",
                "png_pred_sub": "Sub (Fast, Size:Large)",
                "png_pred_up": "Up (Fast, Size:Large)",
                "png_pred_average": "Average (Medium Speed, Size:Medium)",
                "png_pred_paeth": "Paeth (Slow, Size:Small)",
                "png_prediction_combo_tooltip": "PNG compression: None(Fastest,Large), Sub(Fast,Large), Up(Fast,Large),\nAverage(Medium,Medium,Default), Paeth(Slow,Small).",
                "jpeg_radio_label": "JPEG Sequence",
                "jpeg_radio_tooltip": "Sequence of JPEG images. Folders created for each viewpoint.",
                "jpeg_interval_label": "Interval (sec):",
                "jpeg_interval_label_tooltip": "Interval for extracting frames (e.g., 0.5 for 2fps).",
                "jpeg_frame_interval_entry_tooltip": "Frame extraction interval (seconds) for JPEG output.",
                "jpeg_quality_label": "Quality (1-100):",
                "jpeg_quality_label_tooltip": "JPEG quality (1-100). Higher means better quality/larger file.",
                "jpeg_quality_entry_tooltip": "JPEG quality (1 low - 100 high). Converted to FFmpeg's 1 high - 31 low scale. Default 90.",
                "video_radio_label": "Video (HEVC/H.265)",
                "video_radio_tooltip": "MP4 video with HEVC(H.265) codec. Video file for each viewpoint.",
                "video_preset_label": "Preset:",
                "video_preset_label_tooltip": "FFmpeg encoding preset. Faster means lower quality, slower means higher quality.",
                "video_preset_combo_tooltip": "Encoding preset for video output.",
                "video_cq_crf_label": "CQ/CRF:",
                "video_cq_crf_label_tooltip": "Constant Quality value (0-51). Lower means higher quality (larger file).\nlibx265(CPU CRF):Rec. 18-28.\nNVENC(CUDA CQ):Rec. 15-28.",
                "video_cq_crf_entry_tooltip": "Quality value for video output.",

                # --- gui_app.py: Controls and Progress ---
                "parallel_processes_label": "Parallel Processes:",
                "parallel_processes_label_tooltip_format": "Number of viewpoints to process simultaneously. Max: {cores} (logical cores)",
                "parallel_processes_combo_tooltip": "Number of processes for parallel conversion.\nAdjust based on CPU cores and number of pitch angles.",
                "start_button_label": "Start Conversion",
                "start_button_tooltip": "Start the conversion process based on current settings.",
                "cancel_button_label": "Cancel",
                "cancel_button_tooltip": "Cancel the ongoing conversion process.",
                "time_label_tooltip": "Displays elapsed and estimated remaining time for the conversion.",
                "viewpoint_progress_label_tooltip": "Displays the number of processed viewpoints versus the total.",
                "progressbar_tooltip": "Indicates the overall progress of the conversion process.",
                "log_tab_app_log_label": "Application Log",
                "log_tab_app_log_tooltip": "Displays application operation logs and error messages.",
                "log_tab_ffmpeg_log_label": "FFmpeg Output Log",
                "log_tab_ffmpeg_log_tooltip": "Displays raw output from FFmpeg commands. Useful for detailed troubleshooting.",
                "time_display_elapsed": "Elapsed",
                "time_display_remaining_overall": "Overall Rem.",
                "time_display_remaining_calculating": "Calculating...",
                "time_display_not_started": "--:--:--",
                "viewpoint_progress_format": "{completed} / {total} Viewpoints",
                "viewpoint_progress_status_completed": "Completed",
                "viewpoint_progress_status_cancelled": "Cancelled",
                "viewpoint_progress_status_error": "(Error)",

                # --- gui_app.py: Logging & Messages ---
                "log_ffmpeg_found_format": "FFmpeg: {version_line}",
                "log_ffmpeg_not_found_format": "FFmpeg not found: {path}. Check PATH or place it in the same directory.",
                "log_ffmpeg_error_format": "FFmpeg execution error (version check): {error}",
                "log_ffmpeg_unexpected_error_format": "Unexpected error while checking FFmpeg: {error}",
                "log_ffprobe_found_format": "ffprobe: {version_line}",
                "log_ffprobe_not_found_format": "ffprobe not found: {path}. Check PATH or place it in the same directory.",
                "log_ffprobe_error_format": "ffprobe execution error (version check): {error}",
                "log_ffprobe_unexpected_error_format": "Unexpected error while checking ffprobe: {error}",
                "log_cuda_available": "CUDA available (enabled by default)",
                "log_cuda_unavailable": "CUDA unavailable",
                "log_cuda_detection_error_format": "CUDA detection error: {error}",
                "log_cuda_high_res_test_info_format": "High-resolution ({width}x{height}) input. CUDA compatibility test will run if enabled.",
                "log_cuda_settings_changed_retest": "CUDA settings changed. Compatibility test will re-run for high-res input if CUDA is enabled.",
                "log_video_info_format": "Video info: {width}x{height}, {duration:.2f}s, FPS:{fps:.2f}, Codec:{codec}",
                "log_video_info_error_ffprobe_failed_format": "Error getting video info (ffprobe execution failed): {error}",
                "log_video_info_error_ffprobe_empty_output_format": "Error getting video info: ffprobe output is empty. Filepath: {filepath}",
                "log_video_info_error_json_parse_failed_format": "Error getting video info (JSON parse failed). ffprobe output: {output}",
                "log_video_info_error_unexpected_format": "Unexpected error while getting video info: {error}",
                "validate_error_input_file_invalid": "Input video file is invalid. Please select an existing file.",
                "validate_error_output_folder_invalid": "Output folder is invalid. Please select an existing folder.",
                "validate_error_frame_interval_positive": "Frame extraction interval must be a positive value.",
                "validate_warning_frame_interval_too_long_format": "Frame extraction interval ({interval:.2f}s) exceeds video duration ({duration:.2f}s). Only one frame might be extracted.",
                "validate_error_frame_interval_numeric": "Frame extraction interval must be a number.",
                "validate_error_jpeg_quality_range": "JPEG quality must be an integer between 1 and 100.",
                "validate_error_jpeg_quality_integer": "JPEG quality must be an integer.",
                "validate_error_video_quality_range": "Video quality (CQ/CRF) must be between 0 and 51.",
                "validate_error_video_quality_integer": "Video quality (CQ/CRF) must be an integer.",
                "validate_error_resolution_positive": "Output resolution must be a positive value.",
                "validate_error_resolution_invalid_numeric": "Output resolution value is invalid. Please enter a number.",
                "validate_error_resolution_general_format": "Error validating output resolution: {error}",
                "log_resolution_fallback_warning_format": "Invalid resolution specified ({value}), using default ({default_res}).",
                "log_viewpoints_calculated_format": "Calculated total viewpoints: {count}",
                "log_viewpoints_none": "No valid viewpoints. Check viewpoint settings.",
                "log_yaw_selector_not_initialized": "Yaw selector not initialized.",
                "log_conversion_cannot_start_no_viewpoints": "No viewpoints to convert. Cannot start process.",
                "log_cuda_compatibility_test_skip_non_cuda": "Skipping CUDA compatibility test (CUDA not used or unavailable).",
                "log_cuda_compatibility_test_starting": "Starting CUDA compatibility test (1 frame)...",
                "log_cuda_compatibility_test_cmd_format": "Test CMD (partial): {command_part} ...",
                "log_cuda_compatibility_test_ffmpeg_ok": "CUDA Test: FFmpeg exited successfully (code 0).",
                "log_cuda_compatibility_test_ffmpeg_error_format": "CUDA Test: FFmpeg error (code {code}).",
                "log_cuda_compatibility_test_ffmpeg_error_output_format": "FFmpeg error output (test):\n{output}",
                "log_cuda_compatibility_test_timeout": "CUDA test timed out. CPU fallback recommended.",
                "log_cuda_compatibility_test_exception_format": "Exception during CUDA test: {error}",
                "log_cuda_test_success_with_error_signs": "CUDA Test: FFmpeg exited successfully, but output shows signs of CUDA-related errors. CPU fallback recommended.",
                "log_cuda_compatibility_test_ok": "CUDA Test: Determined as compatible.",
                "log_cuda_test_error_detected_cpu_fallback": "CUDA Test: CUDA-related error detected. Falling back to CPU.",
                "log_cuda_test_ffmpeg_error_cpu_fallback": "CUDA Test: FFmpeg exited with error (possibly not CUDA-related). Falling back to CPU for safety.",
                "log_cuda_high_res_test_execute": "High-resolution input. Executing CUDA compatibility test...",
                "log_cuda_high_res_test_fallback_cpu": "CUDA compatibility test resulted in fallback to CPU processing.",
                "log_cuda_high_res_test_continue_cuda": "CUDA compatibility test passed. Continuing with CUDA processing.",
                "log_conversion_starting_parallel": "Starting conversion process (parallel)...",
                "log_parallel_processes_invalid_fallback_format": "Invalid value for parallel processes. Set to 1.",
                "log_multiprocessing_init_error_format": "Failed to initialize parallel processing: {error}",
                "log_cuda_fallback_all_cpu": "CUDA fallback triggered. All viewpoints will be processed with CPU.",
                "log_cuda_compatibility_not_confirmed_cpu": "CUDA compatibility not clearly confirmed. Processing with CPU for safety.",
                "log_task_completed_format": "Viewpoint {index} completed. (Processing time: {duration:.2f}s)",
                "log_task_cancelled_format": "Viewpoint {index} was cancelled.",
                "log_task_error_format": "Viewpoint {index} error: {error_message}",
                "log_conversion_finished_or_cancelled_format": "All conversion processes have {status}.",
                "log_pool_termination_error_format": "Error during Pool termination: {error}",
                "log_cancel_requested": "Cancel conversion requested...",
                "confirm_exit_while_converting_title": "Confirm",
                "confirm_exit_while_converting_message": "Conversion is in progress. Cancel and exit?",
                "log_closing_cancelled_conversion": "Cancelling conversion due to window close...",
                "log_pool_forced_termination_error_format": "Pool forced termination error on exit: {error}",
                "constants_app_display_version_format": "Version: {version} ({date})", # Key for constants.py string

                # --- advanced_yaw_selector.py ---
                "ays_pitch_to_add_combo_tooltip": "Select pitch angle to add from the list.",
                "ays_add_pitch_button_label": "Add",
                "ays_add_pitch_button_tooltip_format": "Add the selected pitch angle to the list (max {max_entries}).",
                "ays_remove_pitch_button_label": "Remove",
                "ays_remove_pitch_button_tooltip": "Remove the selected pitch angle from the list.",
                "ays_output_pitch_list_label": "Output Pitch Angle List:",
                "ays_pitch_listbox_tooltip": "List of pitch angles for output.\nSelect to edit details in the right controls.",
                "ays_pitch_reset_button_label": "P.Reset",
                "ays_pitch_reset_button_tooltip_format": "Reset pitch angle list to default ({default_pitches}).",
                "ays_fov_reset_button_label": "FOV.Rst",
                "ays_fov_reset_button_tooltip_format": "Reset FOV of the currently selected pitch to default ({default_fov:.0f} degrees).",
                "ays_yaw_selection_label": "Yaw Selection:",
                "ays_yaw_buttons_tooltip": "Select/deselect individual yaw angles for the current pitch.\nColors correspond to the 3D preview.",
                "ays_pitch_adjust_label_format": "Pitch Angle Adjust (-90° to +90°):",
                "ays_pitch_slider_tooltip": "Adjust the selected pitch angle with the slider.\nValue confirmed on mouse release.",
                "ays_pitch_entry_tooltip": "Enter pitch angle numerically (confirm with Enter/FocusOut).",
                "ays_fov_adjust_label_format": "FOV Adjust ({min_fov:.0f}° to {max_fov:.0f}°):",
                "ays_fov_slider_tooltip_format": "Adjust Field of View (FOV) for the selected pitch ({min_fov:.0f}° to {max_fov:.0f}°).",
                "ays_fov_entry_tooltip": "Enter FOV for selected pitch numerically (confirm with Enter/FocusOut).",
                "ays_yaw_divisions_label_format": "Horizontal Viewpoints (1 to {max_divisions}):",
                "ays_yaw_divisions_scale_tooltip": "Set the number of horizontal viewpoint divisions for the selected pitch.\nChanging this resets yaw selections.",
                "ays_canvas_status_unselected": "Pitch: N/A\nTotal VPs: 0",
                "ays_canvas_status_error": "Settings Error",
                "ays_canvas_status_select_pitch": "Select Pitch",
                "ays_canvas_status_info_format": "Pitch: {pitch:.1f}° (FOV: {fov_display})\nDivs: {divs}\nTotal VPs: {total_vps}",
                "ays_canvas_help_text": "Left-drag:Rotate  Right-click:Toggle VP",
                "ays_error_pitch_parse_invalid_string_format": "Invalid pitch input string: {pitches_str}",
                "ays_warning_pitch_limit_exceeded_format": "Initial pitch count exceeds {max_entries}.\nOnly the first {max_entries} were loaded.",
                "ays_warning_add_pitch_limit_format": "Cannot add more than {max_entries} pitch angles.",
                "ays_warning_add_pitch_select_pitch": "Please select a pitch angle to add.",
                "ays_info_pitch_already_exists": "The specified pitch angle already exists in the list.",
                "ays_error_add_pitch_invalid_value": "Please select a valid number.",
                "ays_warning_remove_pitch_select_pitch": "Please select a pitch angle from the list to remove.",
                "ays_info_cannot_remove_last_pitch": "Cannot remove the last pitch angle.\n(At least one pitch angle is required)",
                "ays_error_remove_pitch_internal_error": "Selected pitch not found in internal settings.",
                "ays_error_pitch_entry_invalid_numeric": "Please enter a valid number for the pitch angle.",
                "ays_warning_pitch_entry_duplicate_format": "Pitch angle {pitch_value}° already exists. Reverting change.",
                "ays_error_fov_entry_invalid_numeric": "Please enter a valid number for FOV.",
                "ays_info_reset_fov_no_pitch_selected": "No pitch selected to reset FOV for.",
                "ays_error_key_not_found_in_settings_format": "Error: Key '{key}' not found in pitch_settings during on_pitch_selected.",
            }
        }

    def set_language(self, lang_code):
        if lang_code in self._strings:
            self.language = lang_code
            save_language_preference(lang_code) # Save preference when language is successfully set
        else:
            # Log an error or warning if an unsupported language code is provided
            print(f"Warning: Language code '{lang_code}' is not supported. Keeping '{self.language}'.", file=sys.stderr)

    def get(self, key, *args, default_text=None, **kwargs):
        # Get strings for the current language, falling back to English if key not found
        lang_strings = self._strings.get(self.language, self._strings.get('en', {}))
        translation = lang_strings.get(key)

        if translation is None:
            # If key is not in current language's strings, try English as a fallback
            if self.language != 'en': # Avoid re-checking English if it's already the current language
                en_strings = self._strings.get('en', {})
                translation_en = en_strings.get(key)
                if translation_en is not None:
                    # print(f"Warning: String key '{key}' not found for language '{self.language}'. Falling back to English.", file=sys.stderr)
                    translation = translation_en
                else: # Also not in English, try Japanese as a last resort before default/key
                    if self.language != 'ja': # Avoid re-checking Japanese
                        ja_strings = self._strings.get('ja',{})
                        translation_ja = ja_strings.get(key)
                        if translation_ja is not None:
                            # print(f"Warning: String key '{key}' not found for '{self.language}' or 'en'. Falling back to Japanese.", file=sys.stderr)
                            translation = translation_ja


        if translation is None: # Still not found after fallbacks
            if default_text is not None:
                # print(f"Warning: String key '{key}' not found in any configured language. Using provided default text.", file=sys.stderr)
                translation = default_text
            else:
                # print(f"Warning: String key '{key}' not found in any configured language. Returning key name as placeholder.", file=sys.stderr)
                translation = f"[{key}]" # Return key itself as a clear placeholder

        # Format the string if arguments are provided
        if args or kwargs:
            try:
                return translation.format(*args, **kwargs)
            except (KeyError, IndexError, TypeError) as e_format:
                # Log formatting error and return a modified string indicating the error
                print(f"Formatting error for key '{key}' with translation '{translation}' (lang: {self.language}). Args: {args}, Kwargs: {kwargs}. Error: {e_format}", file=sys.stderr)
                return f"{translation} {{FORMAT_ERROR: {e_format}}}" # Include error type in output
        return translation

# --- Initialization ---
# Load language preference at module import time
# This ensures S is initialized with the user's preferred language or system default
initial_app_language = load_language_preference()
S = UiStrings(initial_language=initial_app_language)

# Attempt to set the global locale for the application.
# This can affect things like number formatting, date formatting, etc., if Tkinter widgets
# or other libraries respect the locale. It might not be strictly necessary if all UI
# text is handled via the S instance, but can be good practice.
try:
    # For Japanese, try to set a common Japanese locale.
    # For English or other languages, 'en_US.UTF-8' is a common, robust choice.
    # 'C.UTF-8' or '' (system default) are fallbacks.
    if S.language == 'ja':
        # Common Japanese locales. Order might matter based on system availability.
        locales_to_try = ['ja_JP.UTF-8', 'Japanese_Japan.932', 'ja_JP.eucJP', 'ja_JP.sjis', '']
    else: # Default to English-like locales
        locales_to_try = ['en_US.UTF-8', 'C.UTF-8', '']

    for loc_setting in locales_to_try:
        try:
            locale.setlocale(locale.LC_ALL, loc_setting)
            # print(f"Locale set to: {locale.getlocale(locale.LC_ALL)} with setting '{loc_setting}'")
            break # Success
        except locale.Error:
            # print(f"Could not set locale to '{loc_setting}'. Trying next.")
            continue # Try next locale
    else: # Loop completed without break (no locale could be set from the list)
        print(f"Warning: Could not set any preferred locale. System default locale might be used or locale features might be limited.", file=sys.stderr)

except Exception as e: # pylint: disable=broad-except
    # Catch any other unexpected error during locale setting
    print(f"Warning: An unexpected error occurred during locale setup: {e}", file=sys.stderr)


if __name__ == '__main__':
    print(f"Initial language from settings/system: {S.language}")
    print(f"Current locale: {locale.getlocale(locale.LC_ALL)}")


    print("\n--- Testing Japanese Strings ---")
    S.set_language('ja')
    print(f"Language set to: {S.language}")
    print(S.get("app_name_short"))
    print(S.get("browse_button"))
    print(S.get("log_input_file_selected", filepath="test.mp4"))
    print(S.get("non_existent_key_test", default_text="指定されたフォールバックテキスト"))
    print(S.get("validate_warning_frame_interval_too_long_format", interval=5.0, duration=2.0))
    print(S.get("update_check.info.no_update_format", current_version="v1.0", latest_version="v1.0"))
    print(S.get("resolution_auto"))
    print(S.get("missing_arg_key_test", "{test_arg}")) # Test missing argument in format string

    print("\n--- Testing English Strings ---")
    S.set_language('en')
    print(f"Language set to: {S.language}")
    print(S.get("app_name_short"))
    print(S.get("browse_button"))
    print(S.get("log_input_file_selected", filepath="test.mp4"))
    print(S.get("non_existent_key_test", default_text="Specified Fallback Text")) # Should use this
    print(S.get("another_non_existent_key")) # Should return "[another_non_existent_key]"
    print(S.get("validate_warning_frame_interval_too_long_format", interval=5.0, duration=2.0))
    print(S.get("update_check.info.no_update_format", current_version="v1.0", latest_version="v1.0"))
    print(S.get("resolution_auto"))

    print("\n--- Testing Fallback to English from non-existent language ---")
    S.set_language('fr') # 'fr' is not defined
    print(f"Language attempted: fr, Actual language: {S.language}")
    print(S.get("browse_button")) # Should be English "Browse..."
    print(S.get("app_name_short")) # Should be English "Insta360Convert GUI"

    print("\n--- Testing Settings Save/Load ---")
    # Simulate saving and reloading
    current_lang_before_save = S.language
    save_language_preference('ja')
    print(f"Saved 'ja', loaded on next S init would be: {load_language_preference()}")
    S_new = UiStrings(initial_language=load_language_preference())
    print(f"New S instance language: {S_new.language}, expected 'ja'. Test: {S_new.get('browse_button')}")

    save_language_preference('en')
    print(f"Saved 'en', loaded on next S init would be: {load_language_preference()}")
    S_new_en = UiStrings(initial_language=load_language_preference())
    print(f"New S instance language: {S_new_en.language}, expected 'en'. Test: {S_new_en.get('browse_button')}")


    # Clean up the test settings file
    if os.path.exists(SETTINGS_FILE_NAME):
        try:
            os.remove(SETTINGS_FILE_NAME)
            print(f"Cleaned up test settings file: {SETTINGS_FILE_NAME}")
        except OSError as e:
            print(f"Error cleaning up test settings file: {e}")

    # Restore original S.language if it was changed for testing only within this block
    # S.set_language(initial_app_language) # This line might be problematic if S was rebound
    # Instead, rely on S being re-initialized at the start of the actual application.