# colmap_rig_export.py
# COLMAP Rig export helpers and rig_config.json generation

import json
import math
import os
import re

COLMAP_RIG_DIRNAME = "colmap_rig"
COLMAP_IMAGES_DIRNAME = "images"
DEFAULT_RIG_NAME = "rig1"
DEFAULT_CAMERA_PREFIX = "cam"
DEFAULT_FRAME_PREFIX = "frame"
DEFAULT_FRAME_DIGITS = 5


def sanitize_session_prefix(raw_name):
    name = (raw_name or "").strip()
    if not name:
        return ""
    sanitized_chars = []
    for ch in name:
        if ch.isascii() and (ch.isalnum() or ch in "-_"):
            sanitized_chars.append(ch)
        elif ch in (" ", ".", "+"):
            sanitized_chars.append("_")
        else:
            sanitized_chars.append("_")
    sanitized = "".join(sanitized_chars)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized


def _collect_existing_session_prefixes(output_folder, rig_name):
    rig_root = os.path.join(colmap_images_root(output_folder), rig_name)
    prefixes = set()
    if not os.path.isdir(rig_root):
        return prefixes
    token = f"_{DEFAULT_FRAME_PREFIX}_"
    for cam_name in os.listdir(rig_root):
        cam_path = os.path.join(rig_root, cam_name)
        if not os.path.isdir(cam_path):
            continue
        for entry in os.listdir(cam_path):
            if not entry.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            stem = os.path.splitext(entry)[0]
            if token in stem:
                prefix = stem.split(token)[0]
                if prefix:
                    prefixes.add(prefix)
    return prefixes


def make_unique_session_prefix(output_folder, base_name, rig_name=DEFAULT_RIG_NAME):
    base_prefix = sanitize_session_prefix(base_name)
    if not base_prefix:
        base_prefix = "session"
    used_prefixes = _collect_existing_session_prefixes(output_folder, rig_name)
    if base_prefix not in used_prefixes:
        return base_prefix
    for idx in range(2, 1000):
        candidate = f"{base_prefix}_{idx:02d}"
        if candidate not in used_prefixes:
            return candidate
    raise RuntimeError("Could not generate a unique session prefix for COLMAP Rig output.")


def _viewpoint_sort_key(viewpoint):
    return (float(viewpoint.get("pitch", 0.0)), float(viewpoint.get("yaw", 0.0)))


def sort_viewpoints(viewpoints):
    return sorted(viewpoints, key=_viewpoint_sort_key)


def camera_name_for_index(index, total_cameras, prefix=DEFAULT_CAMERA_PREFIX):
    digits = max(2, len(str(total_cameras)))
    return f"{prefix}{index:0{digits}d}"


def prepare_viewpoints_for_colmap(viewpoints, camera_prefix=DEFAULT_CAMERA_PREFIX):
    sorted_viewpoints = sort_viewpoints(viewpoints)
    total = len(sorted_viewpoints)
    prepared = []
    for idx, viewpoint in enumerate(sorted_viewpoints, start=1):
        camera_name = camera_name_for_index(idx, total, prefix=camera_prefix)
        vp_copy = dict(viewpoint)
        vp_copy["camera_index"] = idx
        vp_copy["camera_name"] = camera_name
        prepared.append(vp_copy)
    return prepared


def colmap_rig_root(output_folder):
    return os.path.join(output_folder, COLMAP_RIG_DIRNAME)


def colmap_images_root(output_folder):
    return os.path.join(colmap_rig_root(output_folder), COLMAP_IMAGES_DIRNAME)


def build_colmap_output_dir(output_folder, rig_name, camera_name):
    return os.path.join(colmap_images_root(output_folder), rig_name, camera_name)


def build_colmap_image_prefix(rig_name, camera_name):
    return f"{rig_name}/{camera_name}/"


def build_frame_filename_pattern(file_ext, frame_prefix=DEFAULT_FRAME_PREFIX, frame_digits=DEFAULT_FRAME_DIGITS,
                                 session_prefix=""):
    ext = file_ext.lstrip(".")
    if session_prefix:
        return f"{session_prefix}_{frame_prefix}_%0{frame_digits}d.{ext}"
    return f"{frame_prefix}_%0{frame_digits}d.{ext}"


def _quat_multiply(q1, q2):
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def _quat_conjugate(q):
    w, x, y, z = q
    return (w, -x, -y, -z)


def cam_from_rig_rotation_quaternion(yaw_deg, pitch_deg, roll_deg=0.0):
    yaw_rad = math.radians(float(yaw_deg))
    pitch_rad = math.radians(float(pitch_deg))
    roll_rad = math.radians(float(roll_deg))

    q_yaw = (math.cos(yaw_rad / 2.0), 0.0, math.sin(yaw_rad / 2.0), 0.0)
    q_pitch = (math.cos(pitch_rad / 2.0), math.sin(pitch_rad / 2.0), 0.0, 0.0)
    q_roll = (math.cos(roll_rad / 2.0), 0.0, 0.0, math.sin(roll_rad / 2.0))

    q_rig_from_cam = _quat_multiply(_quat_multiply(q_yaw, q_pitch), q_roll)
    q_cam_from_rig = _quat_conjugate(q_rig_from_cam)
    return [q_cam_from_rig[0], q_cam_from_rig[1], q_cam_from_rig[2], q_cam_from_rig[3]]


def compute_pinhole_camera_params(width, height, fov_deg):
    safe_fov = max(1e-6, min(float(fov_deg), 179.999))
    half_fov_rad = math.radians(safe_fov) / 2.0
    denom = math.tan(half_fov_rad)
    if abs(denom) < 1e-12:
        denom = 1e-12
    fx = 0.5 * float(width) / denom
    fy = 0.5 * float(height) / denom
    cx = float(width) / 2.0
    cy = float(height) / 2.0
    return [fx, fy, cx, cy]


def build_rig_config(prepared_viewpoints, output_resolution, rig_name=DEFAULT_RIG_NAME):
    cameras = []
    total = len(prepared_viewpoints)
    for idx, viewpoint in enumerate(prepared_viewpoints, start=1):
        camera_name = viewpoint.get("camera_name") or camera_name_for_index(idx, total)
        pitch = float(viewpoint.get("pitch", 0.0))
        yaw = float(viewpoint.get("yaw", 0.0))
        fov = float(viewpoint.get("fov", 100.0))
        camera_entry = {
            "image_prefix": build_colmap_image_prefix(rig_name, camera_name),
            "camera_model_name": "PINHOLE",
            "camera_params": compute_pinhole_camera_params(output_resolution[0], output_resolution[1], fov)
        }
        if idx == 1:
            camera_entry["ref_sensor"] = True
        else:
            camera_entry["cam_from_rig_rotation"] = cam_from_rig_rotation_quaternion(yaw, pitch, 0.0)
            camera_entry["cam_from_rig_translation"] = [0, 0, 0]
        cameras.append(camera_entry)
    return [{"cameras": cameras}]


def rig_config_path(output_folder):
    return os.path.join(colmap_rig_root(output_folder), "rig_config.json")


def write_rig_config_json(output_folder, prepared_viewpoints, output_resolution, rig_name=DEFAULT_RIG_NAME):
    config = build_rig_config(prepared_viewpoints, output_resolution, rig_name=rig_name)
    os.makedirs(colmap_rig_root(output_folder), exist_ok=True)
    path = rig_config_path(output_folder)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return path
