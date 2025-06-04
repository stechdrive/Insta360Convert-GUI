# update_checker.py
"""
Handles checking for application updates from GitHub using only standard libraries.
"""
import urllib.request
import json
import ssl # For HTTPS context on some systems if needed
from constants import (
    GITHUB_API_URL_LATEST_RELEASE,
    GITHUB_RELEASES_PAGE_URL
)

def get_latest_release_info():
    """
    Fetches the latest release information from the GitHub API using urllib.

    Returns:
        tuple: (dict or None, str or None)
               A tuple containing the latest release data (dict) and an error
               message (str). If successful, data is returned and error is None.
               If an error occurs, data is None and error message is populated.
    """
    try:
        # GitHub APIはUser-Agentヘッダーを要求することがあるため設定
        headers = {'User-Agent': 'Insta360Convert-GUI-Update-Checker/1.0'}
        req = urllib.request.Request(GITHUB_API_URL_LATEST_RELEASE, headers=headers)

        # SSL証明書の検証をスキップする必要がある場合（非推奨だが、環境によっては必要になることも）
        # context = ssl._create_unverified_context()
        # with urllib.request.urlopen(req, timeout=10, context=context) as response:

        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = response.read()
                encoding = response.info().get_content_charset('utf-8') # Content-Typeからエンコーディング取得
                json_data = json.loads(data.decode(encoding))
                return json_data, None
            elif response.status == 404:
                return None, "リリース情報が見つかりませんでした (404エラー)。"
            else:
                return None, f"HTTPエラーが発生しました (ステータスコード: {response.status})"

    except urllib.error.URLError as e:
        # URLErrorはHTTPErrorの親クラスでもあるが、より広範なネットワークエラーをキャッチ
        if hasattr(e, 'reason'):
            # 接続関連のエラー (例: [Errno 11001] getaddrinfo failed)
            return None, f"ネットワークエラーが発生しました: {e.reason}"
        elif hasattr(e, 'code'):
            # HTTPエラー (urlopenが直接HTTPErrorを発生させることもある)
            if e.code == 404:
                return None, "リリース情報が見つかりませんでした (404エラー)。"
            return None, f"HTTPエラーが発生しました (ステータスコード: {e.code})"
        return None, f"URLエラーが発生しました: {e}"
    except json.JSONDecodeError:
        return None, "GitHubからの応答の解析に失敗しました。"
    except TimeoutError: # urlopenのtimeoutはsocket.timeoutだが、広義にはTimeoutError
        return None, "GitHubへの接続がタイムアウトしました。"
    except Exception as e:
        return None, f"予期せぬエラーが発生しました: {e}"

def compare_versions(current_version_str, latest_version_str):
    """
    Compares two version strings (e.g., "v2.1.0", "2.0.0").
    Handles 'v' prefix. (This function remains the same)
    """
    try:
        current_v = current_version_str.lstrip('vV')
        latest_v = latest_version_str.lstrip('vV')
        current_parts = tuple(map(int, current_v.split('.')))
        latest_parts = tuple(map(int, latest_v.split('.')))
        return latest_parts > current_parts
    except (ValueError, AttributeError):
        print(
            f"Warning: Could not compare versions due to format: "
            f"'{current_version_str}' vs '{latest_version_str}'"
        )
        return False

def check_for_updates_background(current_app_version):
    """
    Checks for updates and prepares a result tuple for the GUI.
    (This function's logic remains largely the same, it just calls the modified get_latest_release_info)
    """
    latest_release_data, error_msg = get_latest_release_info()

    if error_msg:
        return (
            False,
            f"アップデート情報の取得に失敗しました。\n詳細: {error_msg}",
            None, None, error_msg
        )

    if not latest_release_data:
        err = "GitHubから有効なリリースデータを取得できませんでした。"
        return False, f"アップデート情報の取得に失敗しました。\n詳細: {err}", None, None, err

    latest_version = latest_release_data.get("tag_name")
    release_notes_raw = latest_release_data.get("body", "リリースノートはありません。")
    release_notes_summary = (
        (release_notes_raw[:300] + '...')
        if len(release_notes_raw) > 300
        else release_notes_raw
    )

    if not latest_version:
        err = "最新リリースのバージョンタグを取得できませんでした。"
        return False, f"アップデート情報の取得に失敗しました。\n詳細: {err}", None, None, err

    update_available = compare_versions(current_app_version, latest_version)

    if update_available:
        message_gui = (
            f"新しいバージョン ({latest_version}) が利用可能です！\n\n"
            f"現在のバージョン: {current_app_version}\n\n"
            f"主な変更点:\n{release_notes_summary}\n\n"
            f"ダウンロードページを開きますか？"
        )
        return True, message_gui, latest_version, release_notes_raw, None
    else:
        message_gui = (
            f"現在お使いのバージョン ({current_app_version}) は最新です。\n"
            f"(GitHub上の最新: {latest_version})"
        )
        return False, message_gui, latest_version, None, None

if __name__ == '__main__':
    print("Testing update_checker module (using standard libraries)...")
    test_current_version = "v2.0.0"
    print(f"Simulating current app version: {test_current_version}")

    available, msg, latest_v, notes_full, err_detail = check_for_updates_background(test_current_version)

    if err_detail:
        print(f"\nError during update check:\n{msg}")
    else:
        print(f"\nUpdate check result:\n{msg}")
        if available:
            print(f"Latest version on GitHub: {latest_v}")
            print(f"Link to releases: {GITHUB_RELEASES_PAGE_URL}")