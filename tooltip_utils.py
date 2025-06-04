# tooltip_utils.py
# Tkinterウィジェットにツールチップ機能を追加するクラス

import tkinter as tk

class ToolTip:
    """
    Tkinterウィジェットにツールチップを表示するクラス。
    """
    def __init__(self, widget, text, delay=500, wraplength=300):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.schedule)
        self.widget.bind("<Leave>", self.hidetip_event)
        self.widget.bind("<ButtonPress>", self.hidetip_event)

    def schedule(self, event=None):
        # マウスカーソル下のウィジェットが、このToolTipがバインドされたウィジェットか確認
        # これにより、子ウィジェット上にカーソルがある場合に親のToolTipが意図せず表示されるのを防ぐ
        if event:
            # event.widget はイベントが発生したウィジェットを指す
            # self.widget.winfo_containing(event.x_root, event.y_root) は
            # スクリーン座標(x_root, y_root)に実際にあるウィジェットを返す
            # より確実なのは、イベントが発生したウィジェットが self.widget 自身か、
            # または、マウスカーソル直下のウィジェットが self.widget かどうか。
            # ここでは、イベントが発生したウィジェットが self.widget でない場合、
            # またはマウス直下のウィジェットが self.widget でない場合はスケジュールしない。
            widget_under_cursor = self.widget.winfo_containing(event.x_root, event.y_root)
            if event.widget != self.widget or widget_under_cursor != self.widget:
                self.unschedule()
                self.hidetip()
                return
        
        self.unschedule()
        self.id = self.widget.after(self.delay, self.showtip)

    def unschedule(self):
        current_id = self.id
        self.id = None
        if current_id:
            self.widget.after_cancel(current_id)

    def showtip(self, event=None): # event引数を追加（ただし、after経由なので通常はNone）
        # showtipが呼ばれる前に再度チェック（オプション）
        # afterで遅延実行されるため、showtip実行時にはカーソル位置が変わっている可能性がある。
        # より厳密にするなら、ここで再度カーソル位置を確認するが、
        # schedule段階でのチェックで多くはカバーできるはず。

        x = self.widget.winfo_pointerx() + 15
        y = self.widget.winfo_pointery() + 10
        if self.tipwindow or not self.text:
            return
        
        # 表示する直前に、本当に表示すべきか最終確認（オプション強化）
        # このチェックは、delay中にマウスがwidgetから離れたがLeaveイベントが何らかの理由で
        # hidetipを呼ばなかった、という稀なケースを考慮する場合。
        # ただし、<Leave>でunscheduleしているので通常は不要。
        # current_widget_at_show = self.widget.winfo_containing(self.widget.winfo_pointerx(), self.widget.winfo_pointery())
        # if current_widget_at_show != self.widget:
        #     self.hidetip() # tipwindowがNoneなので実際にはdestroyは呼ばれないが、念のため。
        #     return

        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw, text=self.text, justify=tk.LEFT, background="#ffffe0",
            relief=tk.SOLID, borderwidth=1, wraplength=self.wraplength,
            font=("tahoma", "8", "normal")
        )
        label.pack(ipadx=1)

    def hidetip(self):
        current_tipwindow = self.tipwindow
        self.tipwindow = None
        if current_tipwindow:
            current_tipwindow.destroy()

    def hidetip_event(self, event=None): # event引数を受け取るようにする
        self.unschedule()
        self.hidetip()