# realityscan_xmp_export.py
# RealityScan XMP export helpers

import math
import os
import re
import uuid

REALITYSCAN_RIG_DIRNAME = "realityscan_rig"
REALITYSCAN_IMAGES_DIRNAME = "images"
DEFAULT_RIG_NAME = "rig1"
DEFAULT_CAMERA_PREFIX = "cam"
DEFAULT_FRAME_PREFIX = "frame"
DEFAULT_FRAME_DIGITS = 5
REALITYSCAN_RIG_ID_FILENAME = "rig_id.txt"
_REALITYSCAN_RIG_ID_REGEX = re.compile(r'xcr:Rig="([^"]+)"')

DEFAULT_DISTORTION_MODEL = "brown3"
DEFAULT_DISTORTION_COEFFICIENTS = [0, 0, 0, 0, 0, 0]


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


def realityscan_rig_root(output_folder):
    return os.path.join(output_folder, REALITYSCAN_RIG_DIRNAME)


def realityscan_images_root(output_folder):
    return os.path.join(realityscan_rig_root(output_folder), REALITYSCAN_IMAGES_DIRNAME)


def realityscan_rig_id_path(output_folder):
    return os.path.join(realityscan_rig_root(output_folder), REALITYSCAN_RIG_ID_FILENAME)


def read_realityscan_rig_id(output_folder):
    path = realityscan_rig_id_path(output_folder)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read().strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        return normalize_guid(raw)
    except ValueError:
        return None


def write_realityscan_rig_id(output_folder, rig_id):
    if not rig_id:
        return
    path = realityscan_rig_id_path(output_folder)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"{rig_id}\n")


def _extract_rig_id_from_xmp(xmp_path):
    try:
        with open(xmp_path, "r", encoding="utf-8") as handle:
            snippet = handle.read(4096)
    except OSError:
        return None
    match = _REALITYSCAN_RIG_ID_REGEX.search(snippet)
    if not match:
        return None
    try:
        return normalize_guid(match.group(1))
    except ValueError:
        return None


def find_existing_realityscan_rig_id(output_folder, rig_name=DEFAULT_RIG_NAME):
    rig_root = os.path.join(realityscan_images_root(output_folder), rig_name)
    if not os.path.isdir(rig_root):
        return None
    for cam_name in sorted(os.listdir(rig_root)):
        cam_path = os.path.join(rig_root, cam_name)
        if not os.path.isdir(cam_path):
            continue
        for entry in sorted(os.listdir(cam_path)):
            if entry.lower().endswith(".xmp"):
                rig_id = _extract_rig_id_from_xmp(os.path.join(cam_path, entry))
                if rig_id:
                    return rig_id
    return None


def get_or_create_realityscan_rig_id(output_folder, rig_name=DEFAULT_RIG_NAME):
    rig_id = read_realityscan_rig_id(output_folder)
    if rig_id:
        return rig_id
    rig_id = find_existing_realityscan_rig_id(output_folder, rig_name)
    if rig_id:
        write_realityscan_rig_id(output_folder, rig_id)
        return rig_id
    rig_id = generate_guid()
    write_realityscan_rig_id(output_folder, rig_id)
    return rig_id

def _collect_existing_session_prefixes(output_folder, rig_name):
    rig_root = os.path.join(realityscan_images_root(output_folder), rig_name)
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
    raise RuntimeError("Could not generate a unique session prefix for RealityScan Rig output.")


def _viewpoint_sort_key(viewpoint):
    return (float(viewpoint.get("pitch", 0.0)), float(viewpoint.get("yaw", 0.0)))


def sort_viewpoints(viewpoints):
    return sorted(viewpoints, key=_viewpoint_sort_key)


def camera_name_for_index(index, total_cameras, prefix=DEFAULT_CAMERA_PREFIX):
    digits = max(2, len(str(total_cameras)))
    return f"{prefix}{index:0{digits}d}"


def prepare_viewpoints_for_realityscan(viewpoints, camera_prefix=DEFAULT_CAMERA_PREFIX):
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


def build_realityscan_output_dir(output_folder, rig_name, camera_name):
    return os.path.join(realityscan_images_root(output_folder), rig_name, camera_name)


def build_frame_filename_pattern(file_ext, frame_prefix=DEFAULT_FRAME_PREFIX, frame_digits=DEFAULT_FRAME_DIGITS,
                                 session_prefix=""):
    ext = file_ext.lstrip(".")
    if session_prefix:
        return f"{session_prefix}_{frame_prefix}_%0{frame_digits}d.{ext}"
    return f"{frame_prefix}_%0{frame_digits}d.{ext}"


def compute_focal_length_35mm(fov_deg):
    safe_fov = max(1e-6, min(float(fov_deg), 179.999))
    half_fov_rad = math.radians(safe_fov) / 2.0
    denom = math.tan(half_fov_rad)
    if abs(denom) < 1e-12:
        denom = 1e-12
    return 0.5 * 36.0 / denom


def rotation_matrix_realityscan(yaw_deg, pitch_deg, roll_deg=0.0):
    phi = math.radians(float(yaw_deg))
    theta = math.radians(float(pitch_deg))
    psi = math.radians(float(roll_deg))

    cphi, sphi = math.cos(phi), math.sin(phi)
    ctheta, stheta = math.cos(theta), math.sin(theta)
    cpsi, spsi = math.cos(psi), math.sin(psi)

    r11 = cpsi * cphi + spsi * stheta * sphi
    r12 = -cpsi * sphi + cphi * spsi * stheta
    r13 = -ctheta * spsi
    r21 = -ctheta * sphi
    r22 = -ctheta * cphi
    r23 = -stheta
    r31 = cpsi * stheta * sphi - cphi * spsi
    r32 = cpsi * cphi * stheta + spsi * sphi
    r33 = -cpsi * ctheta

    return [
        [r11, r12, r13],
        [r21, r22, r23],
        [r31, r32, r33],
    ]


def _format_float(value, precision=12):
    if abs(value) < 1e-12:
        value = 0.0
    text = f"{value:.{precision}f}"
    text = text.rstrip("0").rstrip(".")
    if text in ("-0", "-0.0"):
        return "0"
    return text or "0"


def format_matrix(matrix):
    return " ".join(_format_float(value) for row in matrix for value in row)


def format_vector(vector):
    return " ".join(_format_float(value) for value in vector)


def generate_guid():
    return f"{{{str(uuid.uuid4()).upper()}}}"


def normalize_guid(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Empty GUID.")
    raw = raw.strip("{}")
    return f"{{{raw.upper()}}}"


def build_xmp_payload(
    *,
    rig_id,
    rig_instance_id,
    rig_pose_index,
    pose_prior,
    coordinates,
    rotation_matrix,
    position,
    focal_length_35mm,
    aspect_ratio,
    skew,
    principal_point_u,
    principal_point_v,
    distortion_model,
    distortion_coefficients,
    calibration_prior,
    calibration_group,
    distortion_group,
    in_texturing=True,
    in_meshing=True,
    in_coloring=True,
    version="3",
):
    rotation_str = format_matrix(rotation_matrix)
    position_str = format_vector(position)
    distortion_str = " ".join(_format_float(value) for value in distortion_coefficients)
    focal_str = _format_float(focal_length_35mm)
    aspect_ratio_str = _format_float(aspect_ratio)
    skew_str = _format_float(skew)
    pp_u_str = _format_float(principal_point_u)
    pp_v_str = _format_float(principal_point_v)

    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        f'    <rdf:Description xmlns:xcr="http://www.capturingreality.com/ns/xcr/1.1#" '
        f'xcr:Version="{version}" '
        f'xcr:PosePrior="{pose_prior}" '
        f'xcr:Rotation="{rotation_str}" '
        f'xcr:Coordinates="{coordinates}" '
        f'xcr:DistortionModel="{distortion_model}" '
        f'xcr:DistortionCoeficients="{distortion_str}" '
        f'xcr:FocalLength35mm="{focal_str}" '
        f'xcr:Skew="{skew_str}" '
        f'xcr:AspectRatio="{aspect_ratio_str}" '
        f'xcr:PrincipalPointU="{pp_u_str}" '
        f'xcr:PrincipalPointV="{pp_v_str}" '
        f'xcr:CalibrationPrior="{calibration_prior}" '
        f'xcr:CalibrationGroup="{calibration_group}" '
        f'xcr:DistortionGroup="{distortion_group}" '
        f'xcr:Rig="{rig_id}" '
        f'xcr:RigInstance="{rig_instance_id}" '
        f'xcr:RigPoseIndex="{rig_pose_index}" '
        f'xcr:InTexturing="{int(bool(in_texturing))}" '
        f'xcr:InMeshing="{int(bool(in_meshing))}" '
        f'xcr:InColoring="{int(bool(in_coloring))}">\n'
        f'      <xcr:Position>{position_str}</xcr:Position>\n'
        '    </rdf:Description>\n'
        '  </rdf:RDF>\n'
        '</x:xmpmeta>\n'
    )
