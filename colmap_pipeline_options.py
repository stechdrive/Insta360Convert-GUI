# colmap_pipeline_options.py
# Helpers for COLMAP pipeline presets and options

from __future__ import annotations

import os

VOCAB_TREE_PRIORITY_NAMES = (
    "vocab_tree_flickr100K_words256K.bin",
    "vocab_tree_flickr100K_words1M.bin",
)


def _copy_options(options):
    return {section: dict(values) for section, values in options.items()}


BALANCED_OPTIONS = {
    "feature": {
        "SiftExtraction.max_num_features": 16384,
        "SiftExtraction.estimate_affine_shape": 1,
        "SiftExtraction.domain_size_pooling": 1,
    },
    "matcher": {
        "SiftMatching.guided_matching": 1,
    },
    "mapper": {
        "Mapper.ba_refine_sensor_from_rig": 1,
    },
}

ULTRA_OPTIONS = _copy_options(BALANCED_OPTIONS)
ULTRA_OPTIONS["feature"]["SiftExtraction.max_num_features"] = 32768


COLMAP_PRESETS = {
    "standard": {
        "matcher": "sequential",
        "options": {},
    },
    "balanced": {
        "matcher": "sequential",
        "options": BALANCED_OPTIONS,
    },
    "ultra": {
        "matcher": "sequential",
        "options": ULTRA_OPTIONS,
    },
    "multi_path": {
        "matcher": "vocab_tree",
        "options": BALANCED_OPTIONS,
    },
}


def merge_options(base, preset, overrides):
    merged = {}
    for source in (base or {}, preset or {}, overrides or {}):
        for section, options in source.items():
            if not options:
                continue
            merged_section = merged.setdefault(section, {})
            merged_section.update(options)
    return merged


def _stringify_option_value(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def build_colmap_command(base_command, options):
    command = list(base_command)
    if not options:
        return command
    for key, value in options.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        command.extend([f"--{key}", _stringify_option_value(value)])
    return command


def find_vocab_tree_path(colmap_exec_path):
    if not colmap_exec_path or not os.path.isfile(colmap_exec_path):
        return None
    exe_dir = os.path.dirname(os.path.abspath(colmap_exec_path))
    candidate_dirs = [
        exe_dir,
        os.path.abspath(os.path.join(exe_dir, os.pardir)),
        os.path.abspath(os.path.join(exe_dir, os.pardir, "share", "colmap")),
        os.path.abspath(os.path.join(exe_dir, os.pardir, os.pardir, "share", "colmap")),
    ]
    seen = set()
    search_dirs = []
    for directory in candidate_dirs:
        if directory in seen:
            continue
        seen.add(directory)
        search_dirs.append(directory)

    for name in VOCAB_TREE_PRIORITY_NAMES:
        for directory in search_dirs:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                return candidate

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        try:
            entries = sorted(os.listdir(directory))
        except OSError:
            continue
        for entry in entries:
            if entry.startswith("vocab_tree_") and entry.endswith(".bin"):
                candidate = os.path.join(directory, entry)
                if os.path.isfile(candidate):
                    return candidate
    return None
