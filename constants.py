# constants.py
# アプリケーション全体で使用する定数

APP_NAME = "Insta360Convert GUI"

# --- バージョン情報 ---
# リリース日 (ユーザー提供の値を維持、必要に応じて更新)
APP_RELEASE_DATE = "2025-06-04"

# アプリケーションのセマンティックバージョン番号
# これを v2.1.0 に更新する場合
APP_VERSION_MAJOR = 2
APP_VERSION_MINOR = 1
APP_VERSION_PATCH = 0
# 文字列としてのバージョン (例: "v2.1.0" や "2.1.0")
# 'v'プレフィックスを付けるかどうかは一貫性を持たせます。
# GitHubのタグ名と合わせるなら 'v' を付けるのが一般的。
APP_VERSION_STRING_SEMVER = f"v{APP_VERSION_MAJOR}.{APP_VERSION_MINOR}.{APP_VERSION_PATCH}"

# 開発バージョン文字列 (以前のAPP_DEV_VERSIONの役割。必要なら残すか、上記に統合)
# もし APP_VERSION_STRING_SEMVER で十分なら、この行は不要かもしれません。
# APP_DEV_LABEL = "dev" # 例えば開発版なら "dev", "beta", "rc1" など
# APP_FULL_VERSION_STRING = f"{APP_VERSION_STRING_SEMVER}-{APP_DEV_LABEL}" if APP_DEV_LABEL else APP_VERSION_STRING_SEMVER

# GUIのタイトルバーやバージョン情報ダイアログで表示する文字列
# (以前のAPP_VERSION_STRINGの役割。日付とバージョンを組み合わせるか、バージョンのみにするか選択)
# 例1: 日付とセマンティックバージョン
APP_DISPLAY_VERSION = f"{APP_VERSION_STRING_SEMVER} ({APP_RELEASE_DATE})"
# 例2: セマンティックバージョンのみ (より一般的かも)
# APP_DISPLAY_VERSION = APP_VERSION_STRING_SEMVER

# --- ここまでバージョン情報 ---


# FFmpeg関連定数
FFMPEG_PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
DEFAULT_PRESET = "medium"
DEFAULT_RESOLUTION_WIDTH = 1920
HIGH_RESOLUTION_THRESHOLD = 4096 # この解像度を超える入力は高解像度とみなす

# --- GitHub関連定数 (アップデートチェック用) ---
GITHUB_REPO_OWNER = "stechdrive"
GITHUB_REPO_NAME = "Insta360Convert-GUI"
GITHUB_API_URL_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"
GITHUB_RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases"
