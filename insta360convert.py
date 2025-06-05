# insta360convert.py
# アプリケーションのメイン起動スクリプト

import multiprocessing
import sys # sysモジュールをインポートしてPythonバージョンチェックに使用
import tkinter as tk # tkinterをインポートしてバージョンチェックに使用

# アプリケーション固有モジュールのインポート
# gui_app は tkinter に依存するため、Python/Tkinterのバージョンチェック後にインポート
# from gui_app import Insta360ConvertGUI

# strings モジュールは gui_app 内で初期化・使用されるため、ここでは不要。
# constants モジュールも同様。

MIN_PYTHON_MAJOR = 3
MIN_PYTHON_MINOR = 9 # 例えばPython 3.9以上を要求する場合

MIN_TK_MAJOR = 8
MIN_TK_MINOR = 6 # Tkinter 8.6以上を要求する場合

def check_python_version():
    """Checks if the current Python version meets the minimum requirements."""
    if sys.version_info < (MIN_PYTHON_MAJOR, MIN_PYTHON_MINOR):
        error_message = (
            f"Error: Python {MIN_PYTHON_MAJOR}.{MIN_PYTHON_MINOR} or newer is required.\n"
            f"You are using Python {sys.version_info.major}.{sys.version_info.minor}."
        )
        # GUIを表示する前にエラーを出すため、printとsys.exitを使用
        print(error_message, file=sys.stderr)
        # 簡単なTkinterウィンドウでエラーメッセージを表示することも検討できるが、
        # Tkinter自体の問題の可能性も考慮し、ここではstderrへの出力に留める。
        sys.exit(1)
    return True

def check_tkinter_version():
    """Checks if the available Tkinter version meets the minimum requirements."""
    try:
        # Tkinterのバージョン情報を取得
        tk_version_str = tk.Tcl().eval('info patchlevel') # 例: "8.6.12"
        tk_major, tk_minor, *_ = map(int, tk_version_str.split('.'))

        if (tk_major, tk_minor) < (MIN_TK_MAJOR, MIN_TK_MINOR):
            error_message = (
                f"Error: Tkinter {MIN_TK_MAJOR}.{MIN_TK_MINOR} or newer is required.\n"
                f"You have Tkinter {tk_version_str}."
            )
            print(error_message, file=sys.stderr)
            # ここでもGUI初期化前にエラーを出力
            sys.exit(1)
    except Exception as e: # pylint: disable=broad-except
        # Tkinterのバージョン取得に失敗した場合や、Tkinterが正しくない場合
        error_message = (
            f"Error: Could not verify Tkinter version or Tkinter is not properly installed.\n"
            f"Details: {e}"
        )
        print(error_message, file=sys.stderr)
        sys.exit(1)
    return True


if __name__ == "__main__":
    # Windowsで `multiprocessing` を使用して実行可能ファイルを作成する場合に必要
    # (PyInstallerなどでバンドルする場合)
    multiprocessing.freeze_support()

    # PythonとTkinterのバージョンチェックを実行
    # これらのチェックが失敗すると、スクリプトはここで終了する
    check_python_version()
    check_tkinter_version()

    # バージョンチェックが通ったら、GUI関連のモジュールをインポート
    try:
        from gui_app import Insta360ConvertGUI
    except ImportError as e:
        print(f"Fatal Error: Could not import the main application module (gui_app.py).\nDetails: {e}", file=sys.stderr)
        sys.exit(1)
    except tk.TclError as e: # gui_app.pyの初期化でTclErrorが発生する可能性も考慮
        print(f"Fatal Error: A problem occurred during Tkinter initialization in gui_app.py.\nDetails: {e}", file=sys.stderr)
        sys.exit(1)


    try:
        app = Insta360ConvertGUI() # GUIアプリケーションのインスタンスを作成

        # ウィンドウの閉じるボタンの動作をカスタマイズ (on_closingメソッドはgui_app.pyで定義)
        app.protocol("WM_DELETE_WINDOW", app.on_closing)

        app.mainloop() # Tkinterのメインループを開始
    except tk.TclError as e:
        # GUIのメインループ中に予期せぬTclErrorが発生した場合の最終防衛ライン
        # (通常はgui_app内で処理されるべきだが、万が一を考慮)
        print(f"Fatal TclError during application execution: {e}", file=sys.stderr)
        print("The application might not have started correctly or encountered a severe UI issue.", file=sys.stderr)
        sys.exit(1)
    except Exception as e: # pylint: disable=broad-except
        # その他の予期せぬエラー
        print(f"An unexpected fatal error occurred: {e}", file=sys.stderr)
        traceback_str = __import__('traceback').format_exc() # 動的インポート
        print(traceback_str, file=sys.stderr)
        sys.exit(1)