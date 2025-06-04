# ffmpeg_worker.py
# FFmpegのワーカープロセスと関連ヘルパー関数

import subprocess
import os
import time
# import json # configは呼び出し側で準備され、worker内では直接jsonをパースしない
# import queue # キューは引数として渡される
# import multiprocessing # イベントは引数として渡される
import traceback # 例外発生時のスタックトレース取得用

def check_for_cuda_fallback_error(ffmpeg_output_str):
    """
    FFmpegの出力文字列を解析し、CUDA関連のエラーや
    CPUへのフォールバックを示唆する可能性のあるパターンを検出します。

    Args:
        ffmpeg_output_str (str): FFmpegの標準エラー出力または標準出力の文字列。

    Returns:
        bool: CUDAフォールバックが必要と判断されるエラーが含まれていればTrue、そうでなければFalse。
    """
    output_lower = ffmpeg_output_str.lower()
    # CUDA初期化エラー
    if "hwaccel initialisation returned error" in output_lower or \
       "failed setup for format cuda" in output_lower:
        return True
    # 一般的なCUDAエラー
    if "cuda_error_" in output_lower: # Generic CUDA error string
        return True
    # 解像度関連のCUDAエラー (特定のキーワードの組み合わせ)
    if "not within range" in output_lower and \
       ("width" in output_lower or "height" in output_lower) and \
       ("cuda" in output_lower or "nvdec" in output_lower or "cuvid" in output_lower): # Resolution issues with CUDA
        return True
    # フォーマット変換関連のCUDAエラー
    if "impossible to convert between the formats supported by the filter" in output_lower and \
       ("cuda" in output_lower or "hwdownload" in output_lower or "hwupload" in output_lower): # Format conversion issues with CUDA pipeline
        return True
    # フィルタ記述パースエラー (CUDA利用時によく見られる)
    if "error parsing a filter description" in output_lower or \
       "error parsing filterchain" in output_lower: # Often seen with CUDA issues if filters are complex
        return True # This might be too broad, but often indicates a problem in CUDA pipeline setup
    return False

def ffmpeg_worker_process(viewpoint_idx, viewpoint_data, config, log_queue_mp, progress_queue_mp, cancel_event_mp):
    """
    個別の視点に対するFFmpeg変換処理をサブプロセスとして実行します。
    マルチプロセッシングプールから呼び出されることを想定しています。

    Args:
        viewpoint_idx (int): 処理中の視点のインデックス。
        viewpoint_data (dict): 視点情報 (fov, pitch, yaw)。
        config (dict): 変換設定 (ffmpeg_path, input_file, output_folderなど)。
        log_queue_mp (multiprocessing.Queue): ログメッセージをGUIプロセスに送るためのキュー。
        progress_queue_mp (multiprocessing.Queue): 進捗情報をGUIプロセスに送るためのキュー。
        cancel_event_mp (multiprocessing.Event): キャンセル指示を検知するためのイベント。
    """
    process_start_time = time.time() # 処理開始時間
    # configから必要な設定値を取得
    ffmpeg_path = config["ffmpeg_path"]
    input_file = config["input_file"]
    output_folder = config["output_folder"]
    output_width, output_height = config["output_resolution"]
    interp = config["interp"]
    threads_ffmpeg = config["threads_ffmpeg"] # CPU処理時のスレッド数
    use_cuda = config["use_cuda"]
    output_format = config["output_format"]
    frame_interval_val = config["frame_interval"] # PNG/JPEG時のフレーム抽出間隔
    video_preset = config["video_preset"] # 動画出力時のプリセット
    video_cq = config["video_cq"] # 動画出力時の品質値 (CQ/CRF)
    png_pred_option = config.get("png_pred_option", "3") # PNG予測オプション
    jpeg_quality = config.get("jpeg_quality", 90) # JPEG品質

    # 視点データを展開
    fov, pitch, yaw = viewpoint_data["fov"], viewpoint_data["pitch"], viewpoint_data["yaw"]
    # FFmpegのyawは -180 から 180 の範囲であるため調整
    ffmpeg_yaw = yaw
    if ffmpeg_yaw > 180:
        ffmpeg_yaw -= 360

    # v360フィルタのパラメータ文字列を生成
    v360_filter_params = (
        f"e:flat:yaw={ffmpeg_yaw:.2f}:pitch={pitch:.2f}:h_fov={fov:.2f}:v_fov={fov:.2f}"
        f":w={output_width}:h={output_height}:interp={interp}"
    )
    command = [ffmpeg_path, "-y"] # -y: 出力ファイルを無条件に上書き
    filter_complex_parts = [] # -vf または -filter_complex に渡すフィルタのリスト

    # CUDAを使用する場合のオプション追加
    if use_cuda:
        command.extend(["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"])
    command.extend(["-i", input_file]) # 入力ファイル指定

    # 静止画シーケンスでフレームレート指定がある場合
    if output_format in ["png", "jpeg"] and frame_interval_val > 0:
        filter_complex_parts.append(f"fps=fps=1/{frame_interval_val:.3f}")

    # フィルタチェーンの構築
    if use_cuda:
        # CUDAパイプライン: hwdownloadでGPUメモリからシステムメモリへ -> v360 -> hwuploadでシステムメモリからGPUメモリへ
        filter_complex_parts.extend(["hwdownload", "format=nv12", f"v360={v360_filter_params}"])
        if output_format == "png":
            filter_complex_parts.append("format=rgb24") # PNGはrgb24が必要
        elif output_format == "jpeg":
            filter_complex_parts.append("format=yuvj420p") # JPEGはyuvj420p
        elif output_format == "video": # 動画(hevc_nvenc)
            filter_complex_parts.extend(["format=nv12", "hwupload_cuda"]) # hevc_nvencはnv12入力を期待
    else: # CPU処理
        filter_complex_parts.append(f"v360={v360_filter_params}")
        if output_format == "png":
            filter_complex_parts.append("format=rgb24")
        elif output_format == "jpeg":
            filter_complex_parts.append("format=yuvj420p")
        elif output_format == "video": # 動画(libx265)
            filter_complex_parts.append("format=yuv420p") # libx265はyuv420p


    # 出力ファイル名/フォルダ名の生成
    base_input_name = os.path.splitext(os.path.basename(input_file))[0]
    pitch_folder_str = f"{int(pitch):03d}".replace("-", "m") # ピッチ角をフォルダ名用に整形 (例: -30 -> m030)

    if output_format in ["png", "jpeg"]:
        # 静止画シーケンスの場合、視点ごとにフォルダを作成
        view_folder_name = f"{base_input_name}_p{pitch_folder_str}_y{int(yaw):03d}{'_jpeg' if output_format == 'jpeg' else ''}"
        output_dir_for_viewpoint = os.path.join(output_folder, view_folder_name)
        try:
            os.makedirs(output_dir_for_viewpoint, exist_ok=True)
        except OSError as e:
            log_queue_mp.put({"type": "log", "level": "ERROR", "message": f"出力フォルダ作成失敗({view_folder_name}): {e}"})
            progress_queue_mp.put({
                "type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                "error_message": f"出力フォルダ作成失敗: {e}", "duration": time.time() - process_start_time
            })
            return
        file_ext = "jpg" if output_format == "jpeg" else "png"
        output_filename_pattern = os.path.join(output_dir_for_viewpoint, f"{view_folder_name}_%05d.{file_ext}")
        command.extend(["-vf", ",".join(filter_complex_parts)])
        if not use_cuda: # CPU処理時のみスレッド数を指定
            command.extend(["-threads", str(threads_ffmpeg)])
        if output_format == "png":
            command.extend(["-pred", png_pred_option]) # PNG予測オプション
        elif output_format == "jpeg":
            # JPEG品質をFFmpegのqscale:vに変換 (1-100 -> 1-31, 1が高い)
            q_val = max(1, min(31, int(round(1 + (100 - jpeg_quality) * 30 / 99))))
            command.extend(["-qscale:v", str(q_val)])
        command.append(output_filename_pattern)
    elif output_format == "video":
        command.extend(["-vf", ",".join(filter_complex_parts)])
        if use_cuda:
            command.extend(["-c:v", "hevc_nvenc"]) # CUDAエンコーダ
        else:
            command.extend(["-c:v", "libx265", "-threads", str(threads_ffmpeg)]) # CPUエンコーダ
        view_file_name = f"{base_input_name}_p{pitch_folder_str}_y{int(yaw):03d}.mp4"
        output_file = os.path.join(output_folder, view_file_name)
        command.extend(["-preset", video_preset, "-cq" if use_cuda else "-crf", str(video_cq), "-an", output_file]) # -an: 音声なし

    # FFmpegコマンドをログに出力 (デバッグ用)
    log_queue_mp.put({"type": "log", "level": "DEBUG", "message": f"Worker {viewpoint_idx + 1} (CUDA: {use_cuda}) command: {' '.join(command)}"})
    ffmpeg_process = None
    try:
        # Windowsでコンソールウィンドウを非表示にするための設定
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        # FFmpegプロセスを開始
        ffmpeg_process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, # 標準出力と標準エラーをパイプで取得
            universal_newlines=True, startupinfo=startupinfo,
            encoding='utf-8', errors='replace' # エンコーディング指定
        )

        # FFmpegの出力をリアルタイムで読み取り、ログキューに送信
        if ffmpeg_process.stdout: # stdoutがNoneでないことを確認
            for line in iter(ffmpeg_process.stdout.readline, ''):
                if cancel_event_mp.is_set(): # キャンセルが要求されたかチェック
                    log_queue_mp.put({"type": "log", "level": "INFO", "message": f"Worker {viewpoint_idx + 1} (P{pitch:.1f} Y{yaw:.1f}) cancelled."})
                    ffmpeg_process.terminate() # プロセスを終了
                    try:
                        ffmpeg_process.wait(timeout=2) # 終了待機 (タイムアウト付き)
                    except subprocess.TimeoutExpired:
                        ffmpeg_process.kill() # 強制終了
                    break
                log_queue_mp.put({"type": "ffmpeg_raw", "line": line.strip(), "viewpoint_index": viewpoint_idx})
        ffmpeg_process.wait() # プロセスの終了を待つ

        if cancel_event_mp.is_set():
            progress_queue_mp.put({
                "type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                "cancelled": True, "duration": time.time() - process_start_time
            })
            return

        # FFmpegの終了コードをチェック
        if ffmpeg_process.returncode == 0:
            progress_queue_mp.put({
                "type": "task_result", "viewpoint_index": viewpoint_idx, "success": True,
                "duration": time.time() - process_start_time
            })
        else:
            log_queue_mp.put({"type": "log", "level": "ERROR", "message": f"FFmpeg error (Worker {viewpoint_idx + 1}, P{pitch:.1f} Y{yaw:.1f}): Code {ffmpeg_process.returncode}"})
            progress_queue_mp.put({
                "type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                "error_message": f"FFmpeg failed (code {ffmpeg_process.returncode})",
                "duration": time.time() - process_start_time
            })
    except Exception as e:
        log_queue_mp.put({"type": "log", "level": "CRITICAL", "message": f"Worker {viewpoint_idx + 1} (P{pitch:.1f} Y{yaw:.1f}) exception: {e}"})
        log_queue_mp.put({"type": "log", "level": "DEBUG", "message": traceback.format_exc()})
        progress_queue_mp.put({
            "type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
            "error_message": str(e), "duration": time.time() - process_start_time
        })
    finally:
        # プロセスがまだ実行中であれば強制終了
        if ffmpeg_process and ffmpeg_process.poll() is None:
            ffmpeg_process.kill()
            if ffmpeg_process.stdout:
                ffmpeg_process.stdout.close()
            # stderrも同様にクローズ (Popenでstdout=PIPE, stderr=STDOUTにしているのでstdoutのクローズで十分なはず)
            ffmpeg_process.wait()