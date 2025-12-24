# ffmpeg_worker.py
# FFmpegのワーカープロセスと関連ヘルパー関数

import subprocess
import os
import time
import traceback # 例外発生時のスタックトレース取得用
from colmap_rig_export import (
    DEFAULT_RIG_NAME,
    build_colmap_output_dir,
    build_frame_filename_pattern,
    camera_name_for_index
)
# strings モジュールはインポートしない (マルチプロセスでの共有が複雑なため)

# Constants for FFmpeg error detection (can be expanded)
CUDA_ERROR_PATTERNS = [
    "hwaccel initialisation returned error",
    "failed setup for format cuda",
    "cuda_error_", # Generic CUDA error string
    # Specific error phrases often seen with CUDA issues
    "not within range", # Often with "width" or "height" and "cuda"/"nvdec"/"cuvid"
    "impossible to convert between the formats supported by the filter", # With "cuda"/"hwdownload"/"hwupload"
    "error parsing a filter description", # Common with CUDA pipeline setup issues
    "error parsing filterchain"
]

def check_for_cuda_fallback_error(ffmpeg_output_str):
    """
    FFmpegの出力文字列を解析し、CUDA関連のエラーや
    CPUへのフォールバックを示唆する可能性のあるパターンを検出します。

    Args:
        ffmpeg_output_str (str): FFmpegの標準エラー出力または標準出力の文字列。

    Returns:
        bool: CUDAフォールバックが必要と判断されるエラーが含まれていればTrue、そうでなければFalse。
    """
    if not ffmpeg_output_str: # Handle empty string case
        return False
    output_lower = ffmpeg_output_str.lower()

    for pattern in CUDA_ERROR_PATTERNS:
        if pattern in output_lower:
            # Some patterns need additional context
            if pattern == "not within range":
                if ("width" in output_lower or "height" in output_lower) and \
                   ("cuda" in output_lower or "nvdec" in output_lower or "cuvid" in output_lower):
                    return True
            elif pattern == "impossible to convert between the formats supported by the filter":
                if ("cuda" in output_lower or "hwdownload" in output_lower or "hwupload" in output_lower):
                    return True
            else: # For other patterns, direct match is enough
                return True
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
    process_start_time = time.time()
    try:
        ffmpeg_path = config["ffmpeg_path"]
        input_file = config["input_file"]
        output_folder = config["output_folder"]
        output_width, output_height = config["output_resolution"]
        interp = config["interp"]
        threads_ffmpeg = config["threads_ffmpeg"]
        use_cuda = config["use_cuda"]
        output_format = config["output_format"]
        output_mode = config.get("output_mode", "standard")
        colmap_rig_name = config.get("colmap_rig_name", DEFAULT_RIG_NAME)
        frame_interval_val = config.get("frame_interval", 0) # Default to 0 if not present
        video_preset = config["video_preset"]
        video_cq = config["video_cq"]
        # Use .get() for potentially missing keys with defaults
        png_pred_option = config.get("png_pred_option", "3") # Default to 'average'
        jpeg_quality = config.get("jpeg_quality", 90) # Default quality 90

        fov = viewpoint_data.get("fov", 100.0) # Default FOV if missing
        pitch = viewpoint_data.get("pitch", 0.0)
        yaw = viewpoint_data.get("yaw", 0.0)

        # Normalize yaw for FFmpeg v360 filter (-180 to 180 range is typical)
        ffmpeg_yaw = yaw % 360
        if ffmpeg_yaw > 180:
            ffmpeg_yaw -= 360
        elif ffmpeg_yaw < -180: # Handle cases like -270
             ffmpeg_yaw += 360


        if output_mode == "colmap_rig" and output_format == "video":
            log_queue_mp.put({"type": "log", "level": "ERROR",
                              "message": "COLMAP Rig mode does not support video output."})
            progress_queue_mp.put({
                "type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                "error_message": "Invalid output format for COLMAP Rig.",
                "duration": time.time() - process_start_time
            })
            return

        v360_filter_params = (
            f"e:flat:yaw={ffmpeg_yaw:.2f}:pitch={pitch:.2f}:h_fov={fov:.2f}:v_fov={fov:.2f}"
            f":w={output_width}:h={output_height}:interp={interp}"
        )
        command = [ffmpeg_path, "-y"] # -y to overwrite output files without asking
        filter_complex_parts = []

        if use_cuda:
            command.extend(["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"])
        # Always specify input file after potential hwaccel options
        command.extend(["-i", input_file])


        if output_format in ["png", "jpeg"] and frame_interval_val > 0:
            # Ensure frame_interval_val is positive to avoid division by zero or invalid fps
            safe_fps = 1.0 / frame_interval_val if frame_interval_val > 1e-6 else 1.0 # Default to 1fps if interval is tiny/zero
            filter_complex_parts.append(f"fps=fps={safe_fps:.6f}")


        if use_cuda:
            # Order for CUDA: hwdownload (if needed), format (CPU format like nv12), v360, format (CPU for encoder), hwupload (if encoding on GPU)
            filter_complex_parts.extend(["hwdownload", "format=nv12"]) # Download to system memory, NV12 is common for v360
            filter_complex_parts.append(f"v360={v360_filter_params}")
            if output_format == "png":
                filter_complex_parts.append("format=rgb24") # PNG needs RGB
            elif output_format == "jpeg":
                filter_complex_parts.append("format=yuvj420p") # JPEG often uses YUVJ420P
            elif output_format == "video": # Assuming HEVC_NVENC
                filter_complex_parts.extend(["format=nv12", "hwupload_cuda"]) # Upload back to GPU for NVENC
        else: # CPU processing path
            filter_complex_parts.append(f"v360={v360_filter_params}")
            if output_format == "png":
                filter_complex_parts.append("format=rgb24")
            elif output_format == "jpeg":
                filter_complex_parts.append("format=yuvj420p")
            elif output_format == "video": # Assuming libx265
                filter_complex_parts.append("format=yuv420p") # Common for libx265

        base_input_name = os.path.splitext(os.path.basename(input_file))[0]
        # Format pitch: remove decimal, pad with leading zeros, replace minus with 'm'
        pitch_folder_str = f"{int(round(pitch)):03d}".replace("-", "m")
        yaw_folder_str = f"{int(round(yaw)):03d}".replace("-", "m") # Also handle yaw for consistency if it can be negative

        if output_format in ["png", "jpeg"]:
            if output_mode == "colmap_rig":
                camera_name = viewpoint_data.get("camera_name")
                if not camera_name:
                    camera_index = viewpoint_data.get("camera_index")
                    if camera_index is None:
                        log_queue_mp.put({"type": "log", "level": "ERROR",
                                          "message": "COLMAP Rig mode requires camera_name/camera_index in viewpoint data."})
                        progress_queue_mp.put({
                            "type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                            "error_message": "Missing camera metadata for COLMAP Rig.",
                            "duration": time.time() - process_start_time
                        })
                        return
                    camera_name = camera_name_for_index(int(camera_index), int(camera_index))

                output_dir_for_viewpoint = build_colmap_output_dir(output_folder, colmap_rig_name, camera_name)
                try:
                    os.makedirs(output_dir_for_viewpoint, exist_ok=True)
                except OSError as e:
                    log_queue_mp.put({"type": "log", "level": "ERROR",
                                      "message": f"Failed to create output folder ({camera_name}): {e}"})
                    progress_queue_mp.put({
                        "type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                        "error_message": f"Output folder creation failed: {e}",
                        "duration": time.time() - process_start_time
                    })
                    return

                file_ext = "jpg" if output_format == "jpeg" else "png"
                output_filename_pattern = os.path.join(
                    output_dir_for_viewpoint,
                    build_frame_filename_pattern(file_ext)
                )
            else:
                img_type_suffix = '_jpeg' if output_format == 'jpeg' else '_png' # More explicit suffix
                view_folder_name = f"{base_input_name}_p{pitch_folder_str}_y{yaw_folder_str}{img_type_suffix}"
                output_dir_for_viewpoint = os.path.join(output_folder, view_folder_name)

                try:
                    os.makedirs(output_dir_for_viewpoint, exist_ok=True)
                except OSError as e:
                    log_queue_mp.put({"type": "log", "level": "ERROR",
                                      "message": f"Failed to create output folder ({view_folder_name}): {e}"})
                    progress_queue_mp.put({
                        "type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                        "error_message": f"Output folder creation failed: {e}",
                        "duration": time.time() - process_start_time
                    })
                    return

                file_ext = "jpg" if output_format == "jpeg" else "png"
                # Use a consistent base name for images within the folder
                image_base_name = f"{base_input_name}_p{pitch_folder_str}_y{yaw_folder_str}"
                output_filename_pattern = os.path.join(output_dir_for_viewpoint, f"{image_base_name}_%05d.{file_ext}")

            command.extend(["-vf", ",".join(filter_complex_parts)])
            if not use_cuda: # Threads option is typically for CPU encoders
                command.extend(["-threads", str(threads_ffmpeg)])

            if output_format == "png":
                command.extend(["-pred", png_pred_option]) # PNG specific prediction filter
            elif output_format == "jpeg":
                # Convert 1-100 quality to FFmpeg's qscale:v range (typically 1-31 for M superbly, 2-5 good)
                # Lower qscale means higher quality for JPEG.
                # A common mapping: q = 31 - (quality * 30 / 100) roughly.
                # Let's use a slightly adjusted mapping to ensure q is at least 1.
                # Quality 100 -> q ~1-2; Quality 1 -> q ~31
                q_val = max(1, min(31, int(round(1 + (100 - jpeg_quality) * 30 / 99.0))))
                command.extend(["-qscale:v", str(q_val)])

            command.append(output_filename_pattern)
        elif output_format == "video":
            command.extend(["-vf", ",".join(filter_complex_parts)])
            if use_cuda:
                command.extend(["-c:v", "hevc_nvenc"])
            else:
                command.extend(["-c:v", "libx265", "-threads", str(threads_ffmpeg)])

            view_file_name = f"{base_input_name}_p{pitch_folder_str}_y{yaw_folder_str}.mp4"
            output_file_path = os.path.join(output_folder, view_file_name)
            # CQ for NVENC, CRF for libx265
            quality_param = "-cq" if use_cuda else "-crf"
            command.extend([quality_param, str(video_cq), "-preset", video_preset, "-an", output_file_path])

        log_queue_mp.put({"type": "log", "level": "DEBUG",
                          "message": f"Worker {viewpoint_idx + 1} (CUDA: {use_cuda}) command: {' '.join(command)}"})

        ffmpeg_process = None
        startupinfo = None
        if os.name == 'nt': # Hide console window on Windows
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        # Ensure encoding is robust for FFmpeg output
        ffmpeg_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Redirect stderr to stdout to capture all output
            universal_newlines=False, # Read as bytes
            startupinfo=startupinfo
            # encoding='utf-8', errors='replace' # Let's decode manually
        )

        if ffmpeg_process.stdout:
            for line_bytes in iter(ffmpeg_process.stdout.readline, b''):
                if cancel_event_mp.is_set():
                    log_queue_mp.put({"type": "log", "level": "INFO",
                                      "message": f"Worker {viewpoint_idx + 1} (P{pitch:.1f} Y{yaw:.1f}) processing cancelled."})
                    ffmpeg_process.terminate() # Send SIGTERM
                    try:
                        ffmpeg_process.wait(timeout=5) # Wait a bit for graceful termination
                    except subprocess.TimeoutExpired:
                        log_queue_mp.put({"type": "log", "level": "WARNING",
                                          "message": f"Worker {viewpoint_idx + 1} did not terminate gracefully, killing."})
                        ffmpeg_process.kill() # Force kill if not terminated
                    break
                # Decode line by line, replacing errors
                line_str = line_bytes.decode(encoding='utf-8', errors='replace')
                log_queue_mp.put({"type": "ffmpeg_raw", "line": line_str.strip(), "viewpoint_index": viewpoint_idx})
        ffmpeg_process.wait() # Wait for the process to complete if not cancelled

        if cancel_event_mp.is_set(): # Check again after loop/wait
            progress_queue_mp.put({"type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                                   "cancelled": True, "duration": time.time() - process_start_time})
            return

        if ffmpeg_process.returncode == 0:
            progress_queue_mp.put({"type": "task_result", "viewpoint_index": viewpoint_idx, "success": True,
                                   "duration": time.time() - process_start_time})
        else:
            log_queue_mp.put({"type": "log", "level": "ERROR",
                              "message": f"FFmpeg error (Worker {viewpoint_idx + 1}, P{pitch:.1f} Y{yaw:.1f}): Exit Code {ffmpeg_process.returncode}"})
            progress_queue_mp.put({"type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                                   "error_message": f"FFmpeg failed (code {ffmpeg_process.returncode})",
                                   "duration": time.time() - process_start_time})

    except KeyError as e: # Handle missing keys in config or viewpoint_data
        error_msg = f"Worker {viewpoint_idx + 1} configuration error: Missing key {e}"
        log_queue_mp.put({"type": "log", "level": "CRITICAL", "message": error_msg})
        log_queue_mp.put({"type": "log", "level": "DEBUG", "message": traceback.format_exc()})
        progress_queue_mp.put({"type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                               "error_message": error_msg, "duration": time.time() - process_start_time})
    except Exception as e: # Catch-all for other unexpected errors
        error_msg = f"Worker {viewpoint_idx + 1} (P{pitch:.1f} Y{yaw:.1f}) encountered an exception: {e}"
        log_queue_mp.put({"type": "log", "level": "CRITICAL", "message": error_msg})
        log_queue_mp.put({"type": "log", "level": "DEBUG", "message": traceback.format_exc()})
        progress_queue_mp.put({"type": "task_result", "viewpoint_index": viewpoint_idx, "success": False,
                               "error_message": str(e), "duration": time.time() - process_start_time})
    finally:
        # Ensure stdout is closed if process was opened
        if ffmpeg_process and ffmpeg_process.stdout and not ffmpeg_process.stdout.closed:
            ffmpeg_process.stdout.close()
        # Ensure process is cleaned up if it's still running (e.g., due to an error before wait)
        if ffmpeg_process and ffmpeg_process.poll() is None:
            log_queue_mp.put({"type": "log", "level": "WARNING",
                              "message": f"Worker {viewpoint_idx + 1} FFmpeg process still running in finally block, attempting kill."})
            ffmpeg_process.kill()
            ffmpeg_process.wait()
