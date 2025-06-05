# update_checker.py
"""
Handles checking for application updates from GitHub using only standard libraries.
"""
import urllib.request
import urllib.error # For specific error handling
import json
import ssl # For HTTPS context on some systems if needed (currently unused but kept for reference)
import sys # For stderr output in case of direct execution/testing

from constants import ( # constants.py からインポート
    GITHUB_API_URL_LATEST_RELEASE,
    GITHUB_RELEASES_PAGE_URL # Used in testing block
)
# strings.py から S インスタンスをインポートする必要はない。
# GUIに渡すメッセージキーは、gui_app.py側でSを使って翻訳する。

# Standard User-Agent for GitHub API requests
HTTP_USER_AGENT = 'Insta360Convert-GUI-Update-Checker/1.1' # Version bump for clarity
HTTP_TIMEOUT_SECONDS = 20 # Increased timeout for potentially slow connections

def get_latest_release_info():
    """
    Fetches the latest release information from the GitHub API using urllib.

    Returns:
        tuple: (dict or None, str or None)
               A tuple containing the latest release data (dict) and an error
               message string (str, not a key). If successful, data is returned and error is None.
               If an error occurs, data is None and error message is populated.
    """
    try:
        headers = {'User-Agent': HTTP_USER_AGENT}
        req = urllib.request.Request(GITHUB_API_URL_LATEST_RELEASE, headers=headers)

        # For environments needing specific SSL context (e.g., skipping verification - NOT recommended for production)
        # context = ssl._create_unverified_context()
        # with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS, context=context) as response:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
            if response.status == 200:
                data_bytes = response.read()
                # Determine encoding from Content-Type header, default to UTF-8
                encoding = response.info().get_content_charset(failobj='utf-8')
                json_data = json.loads(data_bytes.decode(encoding))
                return json_data, None # Success
            # Specific HTTP status codes that indicate an issue but are not exceptions per se
            elif response.status == 403:
                return None, ("GitHub API rate limit likely exceeded or access forbidden (403). "
                               "Please try again later.")
            elif response.status == 404:
                return None, "Latest release information not found on GitHub (404)."
            else:
                # Other non-200 status codes
                return None, f"GitHub API returned an unexpected HTTP status: {response.status}."

    except urllib.error.HTTPError as e:
        # This catches errors like 4xx, 5xx that urllib.request.urlopen raises as exceptions
        if e.code == 403:
            return None, ("GitHub API rate limit likely exceeded or access forbidden (HTTPError 403). "
                           "Please try again later.")
        elif e.code == 404:
            return None, "Latest release information not found on GitHub (HTTPError 404)."
        # Provide more detail from the HTTPError if possible
        return None, f"HTTP error accessing GitHub API: {e.code} {e.reason}."
    except urllib.error.URLError as e:
        # This catches network-related errors (e.g., no internet connection, DNS failure)
        # e.reason can sometimes be a socket.error or other low-level exception
        if hasattr(e, 'reason'):
            return None, f"Network error connecting to GitHub: {e.reason}."
        return None, "A URL or network error occurred while checking for updates."
    except json.JSONDecodeError:
        return None, "Failed to parse release information from GitHub (invalid JSON)."
    except TimeoutError: # Explicitly catch TimeoutError from socket timeout
        return None, f"Connection to GitHub timed out after {HTTP_TIMEOUT_SECONDS} seconds."
    except Exception as e: # Catch-all for other unexpected issues
        # Provide a generic message but include the specific exception type for debugging
        return None, f"An unexpected error occurred during update check: {type(e).__name__} - {e}."

def compare_versions(current_version_str, latest_version_str_from_git):
    """
    Compares two version strings (e.g., "v2.1.0", "2.0.0").
    Handles 'v' prefix. Ignores pre-release suffixes for simplicity in this basic comparison.
    Returns True if latest_version_str_from_git is considered newer.
    """
    if not current_version_str or not latest_version_str_from_git:
        return False # Cannot compare if one is missing

    try:
        # Strip 'v' or 'V' prefix and any pre-release tags (e.g., -beta, -alpha)
        # This simplifies comparison to major.minor.patch.
        current_v_base = current_version_str.lstrip('vV').split('-')[0]
        latest_v_base = latest_version_str_from_git.lstrip('vV').split('-')[0]

        current_parts = tuple(map(int, current_v_base.split('.')))
        latest_parts = tuple(map(int, latest_v_base.split('.')))

        # Pad shorter version tuple with zeros for correct comparison
        max_len = max(len(current_parts), len(latest_parts))
        current_padded = current_parts + (0,) * (max_len - len(current_parts))
        latest_padded = latest_parts + (0,) * (max_len - len(latest_parts))

        return latest_padded > current_padded
    except (ValueError, AttributeError) as e:
        # Error parsing version strings (e.g., non-integer parts)
        print(
            f"Warning: Could not compare versions due to format error ('{current_version_str}' vs '{latest_version_str_from_git}'). Error: {e}",
            file=sys.stderr
        )
        return False # Treat as not newer if comparison fails

def check_for_updates_background(current_app_version_semver):
    """
    Checks for updates and prepares a result tuple for the GUI.
    Args:
        current_app_version_semver (str): The semantic version of the current app (e.g., "v2.1.0").
    Returns:
        tuple: (update_available, message_key_for_gui, latest_version_tag, release_notes_raw, error_detail_if_any)
               - update_available (bool): True if an update is available.
               - message_key_for_gui (str): A key to be used with strings.S.get().
               - latest_version_tag (str or None): Tag name of the latest release (e.g., "v2.2.0").
               - release_notes_raw (str or None): Raw release notes from GitHub.
               - error_detail_if_any (str or None): Detailed error message (literal string) if an error occurred.
    """
    latest_release_data, error_msg_literal = get_latest_release_info()

    if error_msg_literal:
        # Return the literal error message for detail; GUI will use S.get with this detail.
        return (
            False, # update_available
            "update_check.error.fetch_failed", # message_key for S.get()
            None, # latest_version_tag
            None, # release_notes_raw
            error_msg_literal # error_detail_if_any (literal string from get_latest_release_info)
        )

    if not latest_release_data:
        err_detail = "No valid release data received from GitHub API." # More specific detail
        return False, "update_check.error.no_valid_data", None, None, err_detail

    latest_version_tag = latest_release_data.get("tag_name")
    # Provide default for release notes if body is missing or empty
    release_notes_raw = latest_release_data.get("body") or "No release notes provided for this version."


    if not latest_version_tag:
        err_detail = "Latest release from GitHub API is missing a version tag."
        return False, "update_check.error.no_version_tag", None, None, err_detail

    update_available = compare_versions(current_app_version_semver, latest_version_tag)

    if update_available:
        return (
            True, # update_available
            "update_check.info.update_available_format", # message_key (includes _format)
            latest_version_tag,
            release_notes_raw,
            None # No error detail
        )
    else: # No update available or versions are the same/current is newer
        return (
            False, # update_available
            "update_check.info.no_update_format", # message_key (includes _format)
            latest_version_tag, # Still provide latest version for "you are up to date" message
            None, # Release notes not typically needed for "no update" message
            None # No error detail
        )

if __name__ == '__main__':
    print("Testing update_checker module (using standard libraries)...")

    # --- Mock S class for testing string formatting ---
    class MockStringsForUpdateChecker:
        def get(self, key, **kwargs):
            # Simulate S.get behavior for keys used by GUI after this module returns
            if key == "update_check.error.fetch_failed":
                return f"Update check: Failed to fetch. Detail: {kwargs.get('error_detail', 'N/A')}"
            if key == "update_check.error.no_valid_data":
                return f"Update check: No valid data. Detail: {kwargs.get('error_detail', 'N/A')}"
            if key == "update_check.error.no_version_tag":
                return f"Update check: No version tag. Detail: {kwargs.get('error_detail', 'N/A')}"
            if key == "update_check.info.update_available_format":
                notes_summary = kwargs.get('release_notes_summary', "No notes.")
                return (f"Update available!\n"
                        f"  Latest: {kwargs.get('latest_version', 'N/A')}\n"
                        f"  Current: {kwargs.get('current_version', 'N/A')}\n"
                        f"  Changes:\n{notes_summary}\nDownload?")
            if key == "update_check.info.no_update_format":
                return (f"You are up to date.\n"
                        f"  Current: {kwargs.get('current_version', 'N/A')}\n"
                        f"  Latest on GitHub: {kwargs.get('latest_version', 'N/A')}")
            return f"[[Unknown String Key: {key}]]"

    S_mock_uc = MockStringsForUpdateChecker()
    # --- End Mock S class ---

    test_versions = [
        ("v2.0.0", "Test with current version older"),
        # Assuming a test where the latest release is v2.1.0 or similar
        (None, "Test with current version being the latest (simulate this by providing a very new version)"),
        ("v3.0.0", "Test with current version newer (should report 'no update')")
    ]
    # To simulate "current is latest", we'd need to know the actual latest or mock get_latest_release_info.
    # For this test, we'll just run with a few versions.

    for current_v, desc in test_versions:
        print(f"\n--- {desc} (Current: {current_v or 'Fetched Latest'}) ---")
        effective_current_v = current_v
        if current_v is None: # Simulate being up-to-date by fetching and using that as current
            temp_data, _ = get_latest_release_info()
            if temp_data and temp_data.get("tag_name"):
                effective_current_v = temp_data.get("tag_name")
                print(f"(Simulating up-to-date with fetched latest: {effective_current_v})")
            else:
                print("(Could not fetch latest to simulate up-to-date scenario, skipping this sub-test)")
                continue


        is_available, msg_key_from_checker, latest_tag_from_checker, notes_from_checker, err_detail_from_checker = check_for_updates_background(effective_current_v)

        if err_detail_from_checker:
            # GUI would format this: S.get(msg_key_from_checker, error_detail=err_detail_from_checker)
            formatted_gui_message = S_mock_uc.get(msg_key_from_checker, error_detail=err_detail_from_checker)
            print(f"Error reported by checker:\n{formatted_gui_message}")
        else:
            if is_available:
                notes_summary = (notes_from_checker[:250] + '...') if notes_from_checker and len(notes_from_checker) > 250 else (notes_from_checker or "N/A")
                formatted_gui_message = S_mock_uc.get(msg_key_from_checker,
                                                     latest_version=latest_tag_from_checker,
                                                     current_version=effective_current_v,
                                                     release_notes_summary=notes_summary)
                print(f"Update check result (GUI would show):\n{formatted_gui_message}")
                # print(f"Full release notes (raw):\n{notes_from_checker if notes_from_checker else 'N/A'}")
                print(f"Download from: {GITHUB_RELEASES_PAGE_URL}")
            else:
                formatted_gui_message = S_mock_uc.get(msg_key_from_checker,
                                                     latest_version=latest_tag_from_checker,
                                                     current_version=effective_current_v)
                print(f"Update check result (GUI would show):\n{formatted_gui_message}")

    print("\n--- Version comparison function tests: ---")
    versions_to_test = [
        ("v1.0.0", "v1.0.1", True), ("1.0.0", "v1.0.1", True),
        ("v1.1.0", "v1.0.1", False), ("v1.0.0", "V1.0.0", False),
        ("v1.0", "v1.0.1", True),   # 1.0.0 vs 1.0.1
        ("v1.0.1", "v1.0", False),  # 1.0.1 vs 1.0.0
        ("v2.0.0", "v1.9.9", False),
        ("v1.9.9", "v2.0.0", True),
        ("v1.0.0", "v1.0.0-beta", False), # Ignores -beta part for simple comparison
        ("v1.0.0-alpha", "v1.0.0-beta", False), # Base comparison is equal
        ("v1.0.0", "v1.0.0.1", True), # More parts in latest
        ("v1.0.0.2", "v1.0.0.1", False),
        ("v1.0.10", "v1.0.2", True), # 10 > 2
        ("v1.2.0", "v1.10.0", True), # 10 > 2 at minor
        ("invalid", "v1.0.0", False), # Invalid current
        ("v1.0.0", "invalid", False), # Invalid latest
        ("", "v1.0.0", False),         # Empty current
        ("v1.0.0", "", False),         # Empty latest
    ]
    for cur, lat, exp in versions_to_test:
        result = compare_versions(cur, lat)
        status = "PASS" if result == exp else "FAIL"
        print(f"compare_versions('{cur}', '{lat}') -> {result} (Expected: {exp}) - {status}")