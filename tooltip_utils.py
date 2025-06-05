# tooltip_utils.py
# Tkinterウィジェットにツールチップ機能を追加するクラス

import tkinter as tk

class ToolTip:
    """
    Tkinterウィジェットにツールチップを表示するクラス。
    """
    def __init__(self, widget, text, delay_ms=500, wraplength_px=300):
        self.widget = widget
        self.text = text # このtextは呼び出し元で翻訳済みのものが渡される想定
        self.delay_ms = delay_ms # パラメータ名をより明確に
        self.wraplength_px = wraplength_px # パラメータ名をより明確に
        self.tipwindow = None
        # self.id = None # schedule_showで使用するIDは_schedule_idに統一
        # self.x = self.y = 0 # tipwindowの表示位置はshow_tip内で計算するため不要

        self._schedule_id = None # after ID for scheduling showtip
        # self._hide_id = None # hidetipは即時実行のため、スケジュールIDは不要

        # ウィジェットへのイベントバインド
        # add="+" は既存のバインディングを上書きせずに追加することを保証
        self.widget.bind("<Enter>", self.schedule_show, add="+")
        self.widget.bind("<Leave>", self.schedule_hide, add="+")
        self.widget.bind("<ButtonPress>", self.schedule_hide, add="+") # ボタン押下でもツールチップを隠す
        self.widget.bind("<Motion>", self.check_cursor_still_on_widget, add="+") # マウス移動中のチェック


    def check_cursor_still_on_widget(self, event=None):
        """
        <Motion>イベントで呼び出され、カーソルがまだウィジェット上にあるかを確認します。
        カーソルがウィジェットから外れていれば、ツールチップの表示スケジュールをキャンセルし、
        表示されていれば隠します。
        """
        if not event: return

        try:
            if not self.widget.winfo_exists():
                self.hide_tip_immediately()
                return

            widget_under_cursor = self.widget.winfo_containing(event.x_root, event.y_root)
            if widget_under_cursor != self.widget:
                # カーソルがこのToolTipのウィジェットから外れた
                self.schedule_hide() # スケジュールキャンセルと即時非表示
        except tk.TclError:
            # ウィジェットが存在しない場合など
            self.hide_tip_immediately()


    def schedule_show(self, event=None): # pylint: disable=unused-argument
        """ツールチップの表示をスケジュールします。"""
        # 既存の表示スケジュールがあればキャンセル
        if self._schedule_id is not None:
            self.widget.after_cancel(self._schedule_id)
            self._schedule_id = None

        # <Enter>イベントが発生したウィジェットが、このToolTipがバインドされたウィジェットか確認
        # (オプションだが、複合ウィジェットなどで役立つ場合がある)
        if event and event.widget != self.widget:
             self.hide_tip_immediately() # ターゲットウィジェットでなければ即座に隠す
             return

        # 新しい表示スケジュールを設定
        try:
            if self.widget.winfo_exists(): # ウィジェットが存在する場合のみスケジュール
                 self._schedule_id = self.widget.after(self.delay_ms, self.show_tip)
        except tk.TclError:
            self._schedule_id = None # ウィジェット破棄済みなどのエラー

    def schedule_hide(self, event=None): # pylint: disable=unused-argument
        """ツールチップの表示スケジュールをキャンセルし、表示されていれば即座に隠します。"""
        if self._schedule_id is not None:
            self.widget.after_cancel(self._schedule_id)
            self._schedule_id = None
        self.hide_tip_immediately()

    def show_tip(self):
        """ツールチップウィンドウを実際に表示します。"""
        try:
            if not self.widget.winfo_exists() or self.tipwindow or not self.text:
                # ウィジェットが存在しない、既にツールチップ表示中、またはテキストがない場合は何もしない
                return

            # マウスカーソルがまだウィジェット上にあるか最終確認
            # (after遅延中にカーソルが移動している可能性があるため)
            # winfo_pointerx/y はルートウィンドウ座標を返す
            # winfo_containing はルート座標を受け取る
            # このチェックは、特にツールチップ表示直前の最終砦として機能
            current_widget_at_show_time = self.widget.winfo_containing(
                self.widget.winfo_pointerx(), self.widget.winfo_pointery()
            )
            if current_widget_at_show_time != self.widget:
                self.hide_tip_immediately() # カーソルが外れていれば表示しない
                return
        except tk.TclError:
             self.hide_tip_immediately() # ウィジェット関連エラー
             return


        # ツールチップウィンドウを作成
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True) # ウィンドウ枠（タイトルバーなど）を非表示

        label = tk.Label(
            tw, text=self.text, justify=tk.LEFT,
            background="#ffffe0", # 黄色っぽい背景色
            relief=tk.SOLID, borderwidth=1,
            wraplength=self.wraplength_px,
            font=("tahoma", "8", "normal") # フォントは固定
        )
        label.pack(ipadx=1, ipady=1) # 少しパディングを追加

        # ツールチップの位置を計算
        # ポインタ位置を基準に、少しオフセットさせる
        # Toplevelが表示される前にジオメトリを設定する必要がある
        # update_idletasks() でラベルサイズを確定後、ウィンドウサイズを取得して位置調整
        tw.update_idletasks()

        pointer_x = self.widget.winfo_pointerx()
        pointer_y = self.widget.winfo_pointery()
        tip_width = tw.winfo_width()
        tip_height = tw.winfo_height()

        # スクリーンからはみ出ないように位置を調整
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()

        # デフォルトはカーソルの右下
        x_pos = pointer_x + 15
        y_pos = pointer_y + 10

        # 右端チェック
        if x_pos + tip_width > screen_width:
            x_pos = pointer_x - tip_width - 15 # カーソルの左側に表示
            if x_pos < 0 : x_pos = 5 # それでもはみ出るなら左端に寄せる

        # 下端チェック
        if y_pos + tip_height > screen_height:
            y_pos = pointer_y - tip_height - 10 # カーソルの上側に表示
            if y_pos < 0 : y_pos = 5 # それでもはみ出るなら上端に寄せる

        tw.wm_geometry(f"+{int(x_pos)}+{int(y_pos)}")


    def hide_tip_immediately(self):
        """表示されているツールチップウィンドウを即座に破棄します。"""
        # 表示スケジュールも確実にキャンセル
        if self._schedule_id is not None:
            try:
                if self.widget.winfo_exists(): # widgetがまだ存在する場合のみafter_cancelを試みる
                    self.widget.after_cancel(self._schedule_id)
            except tk.TclError: # widgetが破棄されている場合など
                pass
            finally:
                self._schedule_id = None


        current_tip = self.tipwindow
        self.tipwindow = None # 先にNoneに設定して多重処理を防ぐ
        if current_tip:
            try:
                if current_tip.winfo_exists(): # ウィンドウがまだ存在する場合のみdestroy
                    current_tip.destroy()
            except tk.TclError:
                pass # ウィジェットが既に破棄されている場合などのエラーを無視

    def update_text(self, new_text):
        """
        ツールチップのテキストを更新します。
        言語切り替え時などに呼び出されることを想定。
        ツールチップが表示中であれば、一度隠します（再表示は次のEnterイベントに任せる）。
        """
        self.text = new_text
        if self.tipwindow and self.tipwindow.winfo_exists():
            # 表示中にテキストが変わる場合、最も簡単なのは一旦隠すこと。
            # ラベルのテキストを直接更新しても良いが、サイズ変更の追従などが必要になる。
            self.hide_tip_immediately()


if __name__ == '__main__':
    root = tk.Tk()
    root.title("ToolTip Test")
    root.geometry("400x300")

    # ToolTipクラスのテスト用
    test_texts_original = {
        "button1": "This is the first button's tooltip. It can be quite long and should wrap nicely.",
        "label1": "A label with a shorter tooltip.",
        "entry1": "Tooltip for an entry widget."
    }
    test_texts_updated = {
        "button1": "これがボタン1のツールチップです。これは非常に長くなる可能性があり、うまく折り返されるべきです。",
        "label1": "短いツールチップを持つラベルです。",
        "entry1": "エントリーウィジェット用のツールチップ。"
    }

    tooltips_instances = [] # ToolTipインスタンスのリスト (unbindするために保持)

    def unbind_all_tooltips():
        """既存のツールチップのバインドを解除し、インスタンスを破棄する（テスト用）。"""
        global tooltips_instances
        for tip in tooltips_instances:
            if tip.widget.winfo_exists():
                tip.widget.unbind("<Enter>")
                tip.widget.unbind("<Leave>")
                tip.widget.unbind("<ButtonPress>")
                tip.widget.unbind("<Motion>")
            tip.hide_tip_immediately() # 表示中のツールチップを隠す
        tooltips_instances = []


    def setup_tooltips(lang_texts):
        global tooltips_instances
        unbind_all_tooltips() # 既存のバインドをクリア

        if 'button1_widget' in globals() and button1_widget.winfo_exists():
             tip1 = ToolTip(button1_widget, lang_texts["button1"], wraplength_px=250)
             tooltips_instances.append(tip1)
        if 'label1_widget' in globals() and label1_widget.winfo_exists():
             tip2 = ToolTip(label1_widget, lang_texts["label1"], delay_ms=300)
             tooltips_instances.append(tip2)
        if 'entry1_widget' in globals() and entry1_widget.winfo_exists():
             tip3 = ToolTip(entry1_widget, lang_texts["entry1"])
             tooltips_instances.append(tip3)


    # ウィジェットの作成
    button1_widget = tk.Button(root, text="Button 1 (Hover Me for Long Tooltip)")
    button1_widget.pack(pady=10, padx=10)

    label1_widget = tk.Label(root, text="Label 1 (Hover Me for Short Tooltip)", bg="lightyellow")
    label1_widget.pack(pady=10, padx=10)

    entry1_widget = tk.Entry(root, width=30)
    entry1_widget.insert(0, "Entry field (Hover for tooltip)")
    entry1_widget.pack(pady=10, padx=10)


    # テキスト切り替え用ボタン
    switch_button_frame = tk.Frame(root)
    switch_button_frame.pack(pady=20)

    def switch_to_original_texts():
        print("Switching to original tooltips")
        setup_tooltips(test_texts_original)
        # ここで update_text を使う代わりに setup_tooltips で再生成しているので、
        # 個別の update_text のテストは別途行うか、setup_tooltips の中で行う。
        # 例: for tip_obj in tooltips_instances: tip_obj.update_text(new_text_for_its_widget)

    def switch_to_updated_texts():
        print("Switching to updated tooltips")
        setup_tooltips(test_texts_updated)

    tk.Button(switch_button_frame, text="Original Tooltips", command=switch_to_original_texts).pack(side=tk.LEFT, padx=5)
    tk.Button(switch_button_frame, text="Updated Tooltips", command=switch_to_updated_texts).pack(side=tk.LEFT, padx=5)

    # 初期ツールチップ設定
    setup_tooltips(test_texts_original)


    # アプリケーション終了時の処理
    def on_closing_main_test():
        unbind_all_tooltips() # Ensure all tooltips are cleaned up
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing_main_test)
    root.mainloop()