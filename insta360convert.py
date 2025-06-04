# insta360convert.py
# アプリケーションのメイン起動スクリプト

import multiprocessing
from gui_app import Insta360ConvertGUI # gui_app.py からメインGUIクラスをインポート

if __name__ == "__main__":
    # Windowsで `multiprocessing` を使用して実行可能ファイルを作成する場合に必要
    multiprocessing.freeze_support()

    app = Insta360ConvertGUI() # GUIアプリケーションのインスタンスを作成
    app.protocol("WM_DELETE_WINDOW", app.on_closing) # ウィンドウの閉じるボタンの動作をカスタマイズ
    app.mainloop() # Tkinterのメインループを開始