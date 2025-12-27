# constants.py
# アプリケーション全体で使用する定数 (翻訳不要なもの)

# --- バージョン情報 ---
APP_RELEASE_DATE = "2025-12-25" # リリース日 (ユーザー提供の値を維持)

APP_VERSION_MAJOR = 2
APP_VERSION_MINOR = 3
APP_VERSION_PATCH = 0
APP_VERSION_STRING_SEMVER = f"v{APP_VERSION_MAJOR}.{APP_VERSION_MINOR}.{APP_VERSION_PATCH}"

# --- FFmpeg関連定数 ---
FFMPEG_PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
DEFAULT_PRESET = "medium"
DEFAULT_RESOLUTION_WIDTH = 1920  # 解像度指定が無効な場合のフォールバック値
HIGH_RESOLUTION_THRESHOLD = 4096 # この解像度を超える入力は高解像度とみなし、CUDA互換性テストの対象とする

# --- COLMAP関連定数 ---
COLMAP_DEFAULT_PRESET_KEY = "balanced"

# --- GitHub関連定数 (アップデートチェック用) ---
GITHUB_REPO_OWNER = "stechdrive"
GITHUB_REPO_NAME = "Insta360Convert-GUI"
GITHUB_API_URL_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"
GITHUB_RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases"

# --- advanced_yaw_selector.py で使用する定数 (一部は strings.py で翻訳されるものもある) ---
# これらのデフォルト値は、strings.py で翻訳されたツールチップ等で使用される場合がある。
# advanced_yaw_selector モジュール自体も、これらの値を使って初期設定を行う。
AYS_INITIAL_CANVAS_SIZE = 380
AYS_MIN_CANVAS_DRAW_SIZE = 50 # Minimum canvas dimension for drawing anything meaningful
AYS_DEBOUNCE_DELAY_MS = 150 # Debounce delay for UI events like slider drags

AYS_MIN_FOV_DEGREES = 30.0
AYS_MAX_FOV_DEGREES = 120.0
AYS_DEFAULT_FOV_INTERNAL = 100.0 # FOVリセット時のデフォルト値
AYS_MAX_YAW_DIVISIONS = 12
AYS_DEFAULT_YAW_DIVISIONS_P0_INTERNAL = 8 # Default divisions for 0 pitch
AYS_DEFAULT_YAW_DIVISIONS_OTHER_INTERNAL = 6 # Default divisions for non-0 pitch
AYS_DEFAULT_PITCHES_STR = "-30,0,30" # ピッチリセット時のデフォルト値
AYS_PREDEFINED_PITCH_ADD_VALUES = [-90, -75, -60, -45, -30, -15, 0, 15, 30, 45, 60, 75, 90]
AYS_MAX_PITCH_ENTRIES = 7

# 色定義 (これらは翻訳対象外の内部識別子や固定色)
AYS_COLOR_CANVAS_BG = "white"
AYS_COLOR_TEXT = "black" # General text color on canvas
AYS_FOV_RING_COLORS_BASE = [
    "skyblue", "lightcoral", "lightgreen", "plum", "gold", "lightpink",
    "orange", "cyan", "magenta", "yellowgreen", "lightblue", "pink"
] # Colors for different yaw sectors
AYS_C_FOV_BOUNDARY_LINE_COLOR = "black" # Outline for selected FOV cones
AYS_COLOR_CENTER_TEXT_BG = "lightgrey" # Background for info text on canvas
AYS_COLOR_PITCHED_EQUATOR = "slateGray" # Color for the equator line
AYS_FAR_SIDE_LINE_COLOR = "#D0D0D0" # Outline for non-selected, back-facing cones
AYS_FAR_SIDE_FILL_COLOR = "#F0F0F0" # Fill for non-selected, back-facing cones (not currently used directly for fill)
AYS_BACKFACE_FILL_COLOR = "#EAEAEA" # Fill for back-facing polygons (general)
AYS_BACKFACE_STIPPLE = "gray50" # Stipple for back-facing polygons
AYS_BUTTON_NORMAL_BG = "SystemButtonFace" # Tkinterのデフォルトボタン背景に依存
AYS_LABEL_TEXT_COLOR = "black" # Text color for yaw labels on canvas
AYS_COLOR_SECTOR_DESELECTED_FILL = "#E0E0E0" # Fill for non-selected, front-facing cones
AYS_COLOR_SECTOR_DESELECTED_OUTLINE = "#C0C0C0" # Outline for non-selected, front-facing cones
AYS_CANVAS_HELP_TEXT_COLOR = "gray40" # Color for the help text on canvas


if __name__ == '__main__':
    # このファイルは主に定数定義なので、直接実行時の動作は通常不要
    print("Constants defined in constants.py:")
    print(f"  APP_VERSION_STRING_SEMVER: {APP_VERSION_STRING_SEMVER} ({APP_RELEASE_DATE})")
    print(f"  DEFAULT_PRESET (FFmpeg): {DEFAULT_PRESET}")
    print(f"  HIGH_RESOLUTION_THRESHOLD: {HIGH_RESOLUTION_THRESHOLD}")
    print(f"  GITHUB_API_URL_LATEST_RELEASE: {GITHUB_API_URL_LATEST_RELEASE}")
    print(f"  AYS_DEFAULT_FOV_INTERNAL: {AYS_DEFAULT_FOV_INTERNAL}")
    print(f"  AYS_DEFAULT_PITCHES_STR: {AYS_DEFAULT_PITCHES_STR}")
    print(f"  AYS_MAX_PITCH_ENTRIES: {AYS_MAX_PITCH_ENTRIES}")
    print(f"  Number of AYS_FOV_RING_COLORS_BASE: {len(AYS_FOV_RING_COLORS_BASE)}")
