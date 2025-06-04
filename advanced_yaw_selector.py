# advanced_yaw_selector.py
import tkinter as tk
from tkinter import ttk, messagebox
import math
from tooltip_utils import ToolTip

# --- 定数 ---
INITIAL_CANVAS_SIZE = 380
MIN_CANVAS_DRAW_SIZE = 50
DEBOUNCE_DELAY_MS = 150

MIN_FOV_DEGREES = 30.0
MAX_FOV_DEGREES = 120.0
DEFAULT_FOV_INTERNAL = 100.0
MAX_YAW_DIVISIONS = 12
DEFAULT_YAW_DIVISIONS_P0_INTERNAL = 8
DEFAULT_YAW_DIVISIONS_OTHER_INTERNAL = 6
DEFAULT_PITCHES_STR = "-30,0,30"
PREDEFINED_PITCH_ADD_VALUES = [-90, -75, -60, -45, -30, -15, 0, 15, 30, 45, 60, 75, 90]
MAX_PITCH_ENTRIES = 7


COLOR_CANVAS_BG = "white"
COLOR_TEXT = "black"
FOV_RING_COLORS_BASE = ["skyblue", "lightcoral", "lightgreen", "plum", "gold", "lightpink", "orange", "cyan", "magenta", "yellowgreen", "lightblue", "pink"]
C_FOV_BOUNDARY_LINE_COLOR = "black"
COLOR_CENTER_TEXT_BG = "lightgrey"
COLOR_PITCHED_EQUATOR = "slateGray"
FAR_SIDE_LINE_COLOR = "#D0D0D0"
FAR_SIDE_FILL_COLOR = "#F0F0F0"
BACKFACE_FILL_COLOR = "#EAEAEA"
BACKFACE_STIPPLE = "gray50"
BUTTON_NORMAL_BG = "SystemButtonFace"
LABEL_TEXT_COLOR = "black"
COLOR_SECTOR_DESELECTED_FILL = "#E0E0E0"
COLOR_SECTOR_DESELECTED_OUTLINE = "#C0C0C0"
CANVAS_HELP_TEXT_COLOR = "gray40"


class AdvancedYawSelector(tk.Frame):
    def __init__(self, master, initial_pitches_str=DEFAULT_PITCHES_STR,
                 on_selection_change_callback=None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_selection_change_callback = on_selection_change_callback

        self.current_pitch_key_var = tk.StringVar()
        self.current_yaw_divisions_var = tk.IntVar()
        self.selected_pitch_value_var = tk.DoubleVar()
        self.selected_pitch_entry_var = tk.StringVar()
        self.selected_pitch_fov_var = tk.DoubleVar(value=DEFAULT_FOV_INTERNAL)
        self.selected_pitch_fov_entry_var = tk.StringVar()
        self.pitch_to_add_var = tk.StringVar()

        self.pitch_settings = {}
        self.yaw_to_fixed_ring_assignment = {}
        self.yaw_buttons = []

        self.global_rotation_y_rad = 0.0
        self.global_rotation_x_rad = math.pi / 6
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self.is_dragging = False
        self._slider_update_active = False
        self._entry_update_active = False
        self._fov_slider_update_active = False
        self._fov_entry_update_active = False
        self._internal_update_active = False
        
        self._configure_timer_id = None
        self._pitch_slider_debounce_timer_id = None
        self._fov_slider_debounce_timer_id = None

        self.canvas_actual_width = INITIAL_CANVAS_SIZE
        self.canvas_actual_height = INITIAL_CANVAS_SIZE
        
        self.controls_enabled = True # コントロールが有効かどうかのフラグ

        self._setup_ui_layout()

        if hasattr(self, 'yaw_canvas'):
            self.yaw_canvas.bind("<Configure>", self._on_canvas_configure)

        self._parse_and_set_initial_pitches(initial_pitches_str, initial_load=True)
        self._select_initial_pitch(initial_load=True)

    def on_mouse_press(self,event):
        if not self.controls_enabled: return
        item = self.yaw_canvas.find_withtag(tk.CURRENT) 
        if item:
            tags = self.yaw_canvas.gettags(item[0])
            if "clickable_label_surface" in tags:
                 return 
        self.is_dragging=True
        self.last_mouse_x,self.last_mouse_y=event.x,event.y
        
    def on_mouse_motion(self,e):
        if not self.controls_enabled: return
        if self.is_dragging:
            dx,dy,sens=e.x-self.last_mouse_x,e.y-self.last_mouse_y,200.0
            self.global_rotation_y_rad=(self.global_rotation_y_rad+dx/sens)%(2*math.pi)
            self.global_rotation_x_rad=max(-math.pi/2*.999,min(math.pi/2*.999,self.global_rotation_x_rad-dy/sens))
            self.last_mouse_x,self.last_mouse_y=e.x,e.y
            if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
            
    def on_mouse_release(self,e):
        if not self.controls_enabled: return
        self.is_dragging=False

    def _on_canvas_configure(self, event):
        new_width = event.width
        new_height = event.height
        if new_width < MIN_CANVAS_DRAW_SIZE or new_height < MIN_CANVAS_DRAW_SIZE:
            pass
        self.canvas_actual_width = new_width
        self.canvas_actual_height = new_height
        if self._configure_timer_id is not None:
            self.after_cancel(self._configure_timer_id)
        self._configure_timer_id = self.after(50, self.draw_yaw_selector)

    def _select_initial_pitch(self, initial_load=False):
        if self.pitch_listbox.size() == 0:
            self.current_pitch_key_var.set("")
            self.selected_pitch_slider.config(state=tk.DISABLED)
            self.selected_pitch_entry.config(state=tk.DISABLED,textvariable=tk.StringVar(value=""))
            self.selected_pitch_fov_slider.config(state=tk.DISABLED)
            self.selected_pitch_fov_entry.config(state=tk.DISABLED, textvariable=tk.StringVar(value=""))
            self.yaw_divisions_scale.config(state=tk.DISABLED)
            if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
            self._create_or_update_yaw_buttons()
            if self.on_selection_change_callback and not initial_load:
                self.on_selection_change_callback()
            return
        found_zero_pitch_idx = -1
        for i in range(self.pitch_listbox.size()):
            if self.pitch_listbox.get(i) == "0.0°":
                found_zero_pitch_idx = i; break
        target_idx = 0
        if found_zero_pitch_idx != -1: target_idx = found_zero_pitch_idx
        if target_idx >= self.pitch_listbox.size(): target_idx = 0 
        if self.pitch_listbox.size() > 0 :
            self.pitch_listbox.selection_clear(0, tk.END)
            self.pitch_listbox.selection_set(target_idx)
            self.pitch_listbox.activate(target_idx)
            self.pitch_listbox.see(target_idx)
            self.on_pitch_selected(None, initial_load=initial_load)
        else:
            self.current_pitch_key_var.set("")
            self.selected_pitch_entry_var.set("")
            self.selected_pitch_fov_entry_var.set("")

    def _setup_ui_layout(self):
        main_paned_window = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=6)
        main_paned_window.pack(fill=tk.BOTH, expand=True)
        left_frame = tk.Frame(main_paned_window, bd=1, relief=tk.SUNKEN)
        main_paned_window.add(left_frame, width=220, minsize=200, stretch="never")
        pitch_control_frame = tk.Frame(left_frame)
        pitch_control_frame.pack(fill=tk.X, padx=5, pady=(5,2))
        self.pitch_to_add_combo = ttk.Combobox(pitch_control_frame, textvariable=self.pitch_to_add_var,
                                               values=[str(p) for p in PREDEFINED_PITCH_ADD_VALUES],
                                               width=5, state="readonly")
        self.pitch_to_add_combo.pack(side=tk.LEFT, padx=(0,2))
        if PREDEFINED_PITCH_ADD_VALUES: self.pitch_to_add_combo.set("0")
        ToolTip(self.pitch_to_add_combo, "追加するピッチ角をリストから選択します。")
        self.add_pitch_button = tk.Button(pitch_control_frame, text="追加", command=self._add_pitch_from_combo, width=4)
        self.add_pitch_button.pack(side=tk.LEFT, padx=(0,2))
        ToolTip(self.add_pitch_button, f"選択したピッチ角をリストに追加します (最大{MAX_PITCH_ENTRIES}個)。")
        self.remove_pitch_button = tk.Button(pitch_control_frame, text="削除", command=self._remove_selected_pitch, width=4)
        self.remove_pitch_button.pack(side=tk.LEFT)
        ToolTip(self.remove_pitch_button, "リストで選択中のピッチ角を削除します。")
        tk.Label(left_frame, text="出力するピッチ角リスト:").pack(anchor="w", padx=5, pady=(5,0))
        self.pitch_listbox = tk.Listbox(left_frame, exportselection=False, height=MAX_PITCH_ENTRIES)
        self.pitch_listbox.pack(fill=tk.X, padx=5, pady=(2,5))
        self.pitch_listbox.bind("<<ListboxSelect>>", lambda event: self.on_pitch_selected(event, initial_load=False))
        ToolTip(self.pitch_listbox, "出力するピッチ角のリスト。\n選択して右のコントロールで詳細設定を編集します。")
        reset_buttons_control_frame_left = tk.Frame(left_frame)
        reset_buttons_control_frame_left.pack(pady=(5,2), padx=5, fill=tk.X)
        self.pitch_reset_button = tk.Button(reset_buttons_control_frame_left,
                                            text="P.Reset", 
                                            command=lambda: self.set_pitches_externally(DEFAULT_PITCHES_STR))
        self.pitch_reset_button.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ToolTip(self.pitch_reset_button, f"ピッチ角リストをデフォルト ({DEFAULT_PITCHES_STR}) にリセットします。")
        self.fov_reset_button = tk.Button(reset_buttons_control_frame_left,
                                          text="FOV.Rst", 
                                          command=self.reset_current_pitch_fov)
        self.fov_reset_button.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        ToolTip(self.fov_reset_button, f"現在選択中のピッチ角のFOVをデフォルト ({DEFAULT_FOV_INTERNAL:.0f}度) にリセットします。")
        tk.Label(left_frame, text="ヨー角選択:").pack(anchor="w", padx=5, pady=(5,0))
        self.yaw_buttons_outer_frame = tk.Frame(left_frame) 
        self.yaw_buttons_outer_frame.pack(pady=(0,5), padx=5, fill=tk.X, expand=True)
        self.yaw_buttons_frame = tk.Frame(self.yaw_buttons_outer_frame)
        self.yaw_buttons_frame.pack(anchor="n")
        ToolTip(self.yaw_buttons_outer_frame, "現在選択中のピッチ角に対する個別のヨー角を選択/解除します。\n色は3Dプレビューの視点の色と連動します。")
        right_container_frame = tk.Frame(main_paned_window)
        main_paned_window.add(right_container_frame, stretch="always", minsize=300)
        options_area = tk.Frame(right_container_frame)
        options_area.pack(fill=tk.X, pady=(5,0), padx=5)
        tk.Label(options_area, text="ピッチ角調整 (-90°〜+90°):").grid(row=0, column=0, sticky="w", pady=2)
        pitch_adjust_frame = tk.Frame(options_area)
        pitch_adjust_frame.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        self.selected_pitch_slider = tk.Scale(pitch_adjust_frame, from_=-90, to=90, orient=tk.HORIZONTAL,
                                            variable=self.selected_pitch_value_var, resolution=0.1,
                                            length=120, command=self._on_selected_pitch_slider_drag,
                                            state=tk.DISABLED, showvalue=0)
        self.selected_pitch_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.selected_pitch_slider.bind("<ButtonRelease-1>", self._on_selected_pitch_slider_release)
        ToolTip(self.selected_pitch_slider, "リストで選択中のピッチ角をスライダーで調整します。\nマウスリリース時に値が確定されます。")
        self.selected_pitch_entry = tk.Entry(pitch_adjust_frame, textvariable=self.selected_pitch_entry_var, width=7, justify='right', state=tk.DISABLED)
        self.selected_pitch_entry.pack(side=tk.LEFT, padx=(5,0))
        self.selected_pitch_entry.bind("<Return>", self._on_selected_pitch_entry_confirm)
        self.selected_pitch_entry.bind("<FocusOut>", self._on_selected_pitch_entry_confirm)
        ToolTip(self.selected_pitch_entry, "選択中のピッチ角を数値で入力 (Enter/FocusOutで確定)。")
        tk.Label(options_area, text=f"FOV調整 ({MIN_FOV_DEGREES:.0f}°〜{MAX_FOV_DEGREES:.0f}°):").grid(row=1, column=0, sticky="w", pady=2)
        fov_adjust_frame = tk.Frame(options_area)
        fov_adjust_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        self.selected_pitch_fov_slider = tk.Scale(fov_adjust_frame, from_=MIN_FOV_DEGREES, to=MAX_FOV_DEGREES, orient=tk.HORIZONTAL,
                                  variable=self.selected_pitch_fov_var, length=120, resolution=0.1,
                                  command=self._on_selected_fov_slider_drag, state=tk.DISABLED, showvalue=0)
        self.selected_pitch_fov_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.selected_pitch_fov_slider.bind("<ButtonRelease-1>", self._on_selected_fov_slider_release)
        ToolTip(self.selected_pitch_fov_slider, f"選択中のピッチ角に対する視野角(FOV)を調整します ({MIN_FOV_DEGREES:.0f}°〜{MAX_FOV_DEGREES:.0f}°)。")
        self.selected_pitch_fov_entry = tk.Entry(fov_adjust_frame, textvariable=self.selected_pitch_fov_entry_var, width=7, justify='right', state=tk.DISABLED)
        self.selected_pitch_fov_entry.pack(side=tk.LEFT, padx=(5,0))
        self.selected_pitch_fov_entry.bind("<Return>", self._on_selected_fov_entry_confirm)
        self.selected_pitch_fov_entry.bind("<FocusOut>", self._on_selected_fov_entry_confirm)
        ToolTip(self.selected_pitch_fov_entry, "選択中ピッチのFOVを数値で入力 (Enter/FocusOutで確定)。")
        tk.Label(options_area, text=f"水平視点数 (1〜{MAX_YAW_DIVISIONS}):").grid(row=2, column=0, sticky="w", pady=2)
        self.yaw_divisions_scale = tk.Scale(options_area, from_=1, to=MAX_YAW_DIVISIONS, orient=tk.HORIZONTAL,
                                            variable=self.current_yaw_divisions_var, length=150, resolution=1,
                                            command=self._on_fov_or_divisions_changed, state=tk.DISABLED)
        self.yaw_divisions_scale.grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        ToolTip(self.yaw_divisions_scale, "選択中のピッチ角に対する水平方向の視点分割数を設定します。\n変更するとヨー角の選択はリセットされます。")
        options_area.columnconfigure(1, weight=1)
        self.yaw_canvas = tk.Canvas(right_container_frame, width=INITIAL_CANVAS_SIZE, height=INITIAL_CANVAS_SIZE,
                                    bg=COLOR_CANVAS_BG, relief=tk.SUNKEN, borderwidth=1)
        self.yaw_canvas.pack(pady=(5,5), padx=5, expand=True, fill=tk.BOTH)
        self.yaw_canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.yaw_canvas.bind("<B1-Motion>", self.on_mouse_motion)
        self.yaw_canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.yaw_canvas.bind("<Button-3>", lambda event: self._handle_canvas_right_click(event))

    def _on_selected_pitch_slider_drag(self, new_val_str):
        if self._entry_update_active or self._internal_update_active: return
        try:
            val = float(new_val_str)
            self.selected_pitch_entry_var.set(f"{val:.1f}")
            if self._pitch_slider_debounce_timer_id is not None:
                self.after_cancel(self._pitch_slider_debounce_timer_id)
            self._pitch_slider_debounce_timer_id = self.after(
                DEBOUNCE_DELAY_MS, 
                lambda v=val: self._perform_pitch_update_after_debounce(v)
            )
        except ValueError: pass

    def _perform_pitch_update_after_debounce(self, value_from_slider):
        self._pitch_slider_debounce_timer_id = None
        if self._slider_update_active or self._entry_update_active or self._internal_update_active : return
        self._process_pitch_change(value_from_slider)

    def _on_selected_pitch_slider_release(self, event=None):
        if self._entry_update_active or self._internal_update_active: return
        if self._pitch_slider_debounce_timer_id is not None:
            self.after_cancel(self._pitch_slider_debounce_timer_id)
            self._pitch_slider_debounce_timer_id = None
        self._slider_update_active = True
        try:
            new_val = self.selected_pitch_value_var.get()
            snapped_val = round(new_val)
            snap_threshold = 0.25
            if abs(new_val - snapped_val) < snap_threshold:
                new_val = float(snapped_val)
                self.selected_pitch_value_var.set(new_val)
            self.selected_pitch_entry_var.set(f"{new_val:.1f}")
            self._process_pitch_change(new_val)
        except ValueError:
            current_slider_val = self.selected_pitch_value_var.get()
            self.selected_pitch_entry_var.set(f"{current_slider_val:.1f}")
        finally:
            self._slider_update_active = False
            
    def _on_selected_fov_slider_drag(self, new_val_str):
        if self._fov_entry_update_active or self._internal_update_active: return
        try:
            val = float(new_val_str)
            self.selected_pitch_fov_entry_var.set(f"{val:.1f}")
            if self._fov_slider_debounce_timer_id is not None:
                self.after_cancel(self._fov_slider_debounce_timer_id)
            self._fov_slider_debounce_timer_id = self.after(
                DEBOUNCE_DELAY_MS,
                lambda v=val: self._perform_fov_update_after_debounce(v)
            )
        except ValueError: pass

    def _perform_fov_update_after_debounce(self, value_from_slider):
        self._fov_slider_debounce_timer_id = None
        if self._fov_slider_update_active or self._fov_entry_update_active or self._internal_update_active: return
        corrected_value = max(MIN_FOV_DEGREES, min(value_from_slider, MAX_FOV_DEGREES))
        self._process_fov_change(corrected_value)

    def _on_selected_fov_slider_release(self, event=None):
        if self._fov_entry_update_active or self._internal_update_active: return
        if self._fov_slider_debounce_timer_id is not None:
            self.after_cancel(self._fov_slider_debounce_timer_id)
            self._fov_slider_debounce_timer_id = None
        self._fov_slider_update_active = True
        try:
            new_val = self.selected_pitch_fov_var.get()
            snapped_val = round(new_val)
            snap_threshold = 0.25
            if abs(new_val - snapped_val) < snap_threshold:
                 if MIN_FOV_DEGREES <= snapped_val <= MAX_FOV_DEGREES:
                    new_val = float(snapped_val)
            new_val = max(MIN_FOV_DEGREES, min(new_val, MAX_FOV_DEGREES))
            self.selected_pitch_fov_var.set(new_val)
            self.selected_pitch_fov_entry_var.set(f"{new_val:.1f}")
            self._process_fov_change(new_val)
        except ValueError:
            current_fov_val = self.selected_pitch_fov_var.get()
            self.selected_pitch_fov_entry_var.set(f"{current_fov_val:.1f}")
        finally:
            self._fov_slider_update_active = False

    def _parse_and_set_initial_pitches(self, pitches_str, initial_load=False):
        self._internal_update_active = True
        parsed_valid_pitch_keys = set()
        current_default_fov = DEFAULT_FOV_INTERNAL
        if pitches_str.strip():
            try:
                temp_keys_list = []
                for p_str_raw in pitches_str.split(','):
                    p_str = p_str_raw.strip()
                    if p_str:
                        float_val = float(p_str)
                        if not (-90 <= float_val <= 90): continue
                        key_candidate = f"{float_val:.1f}"
                        if key_candidate not in temp_keys_list:
                            temp_keys_list.append(key_candidate)
                parsed_valid_pitch_keys = set(temp_keys_list)
            except ValueError:
                messagebox.showerror("入力エラー", f"無効なピッチ入力文字列です: {pitches_str}", parent=self)
                self._internal_update_active = False; return
        all_pitch_keys_to_manage = parsed_valid_pitch_keys
        if len(all_pitch_keys_to_manage) > MAX_PITCH_ENTRIES:
            sorted_keys = sorted(list(all_pitch_keys_to_manage), key=float)
            all_pitch_keys_to_manage = set(sorted_keys[:MAX_PITCH_ENTRIES])
            if initial_load:
                messagebox.showwarning("ピッチ数制限",
                                       f"初期ピッチ数が{MAX_PITCH_ENTRIES}個を超えています。\n"
                                       f"最初の{MAX_PITCH_ENTRIES}個のみ読み込みました。", parent=self)
        if not all_pitch_keys_to_manage : all_pitch_keys_to_manage.add("0.0")
        current_settings_keys = set(self.pitch_settings.keys())
        keys_to_add = all_pitch_keys_to_manage - current_settings_keys
        keys_to_remove = current_settings_keys - all_pitch_keys_to_manage
        for k_rem in keys_to_remove:
            if k_rem in self.pitch_settings: del self.pitch_settings[k_rem]
            if k_rem in self.yaw_to_fixed_ring_assignment: del self.yaw_to_fixed_ring_assignment[k_rem]
        for key_str in keys_to_add:
            div = DEFAULT_YAW_DIVISIONS_P0_INTERNAL if math.isclose(float(key_str),0.0) else DEFAULT_YAW_DIVISIONS_OTHER_INTERNAL
            yaws = [round(i*(360.0/div),2) for i in range(div)]
            self.pitch_settings[key_str] = {"yaws": yaws, "divisions": div, "fov": current_default_fov}
        self._update_pitch_listbox_from_settings(initial_load=initial_load)
        self._internal_update_active = False

    def _update_pitch_listbox_from_settings(self, initial_load=False):
        self._internal_update_active = True
        current_sel_indices = self.pitch_listbox.curselection()
        current_selection_key = ""
        if current_sel_indices and current_sel_indices[0] < self.pitch_listbox.size():
            current_selection_key = self.pitch_listbox.get(current_sel_indices[0]).replace("°", "")
        self.pitch_listbox.delete(0, tk.END)
        sorted_pitch_keys_float = []
        if self.pitch_settings:
             sorted_pitch_keys_float = sorted([float(k) for k in self.pitch_settings.keys()])
        new_selection_idx = -1; current_selection_found_in_new_list = False
        for i, p_float in enumerate(sorted_pitch_keys_float):
            display_text = f"{p_float:.1f}°"
            self.pitch_listbox.insert(tk.END, display_text)
            if f"{p_float:.1f}" == current_selection_key:
                new_selection_idx = i; current_selection_found_in_new_list = True
        if self.pitch_listbox.size() > 0:
            if current_selection_found_in_new_list and new_selection_idx != -1:
                self.pitch_listbox.selection_set(new_selection_idx)
                self.pitch_listbox.activate(new_selection_idx)
                self.on_pitch_selected(None, initial_load=True) 
            else:
                self._select_initial_pitch(initial_load=initial_load)
                self._internal_update_active = False; return
        else:
            self.current_pitch_key_var.set("")
            self.selected_pitch_value_var.set(0)
            self.selected_pitch_entry_var.set("")
            self.selected_pitch_slider.config(state=tk.DISABLED)
            self.selected_pitch_entry.config(state=tk.DISABLED)
            self.selected_pitch_fov_var.set(DEFAULT_FOV_INTERNAL)
            self.selected_pitch_fov_entry_var.set(f"{DEFAULT_FOV_INTERNAL:.1f}")
            self.selected_pitch_fov_slider.config(state=tk.DISABLED)
            self.selected_pitch_fov_entry.config(state=tk.DISABLED)
            self.current_yaw_divisions_var.set(0)
            self.yaw_divisions_scale.config(state=tk.DISABLED)
            self._create_or_update_yaw_buttons()
            if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
            if self.on_selection_change_callback and not initial_load: self.on_selection_change_callback()
        self._internal_update_active = False

    def _add_pitch_from_combo(self):
        if len(self.pitch_settings) >= MAX_PITCH_ENTRIES:
            messagebox.showwarning("追加制限", f"ピッチ角は最大 {MAX_PITCH_ENTRIES} 個までしか追加できません。", parent=self)
            return
        new_pitch_val_str = self.pitch_to_add_var.get()
        if not new_pitch_val_str:
            messagebox.showwarning("追加エラー", "追加するピッチ角を選択してください。", parent=self); return
        try:
            new_pitch_val = float(new_pitch_val_str)
            new_pitch_key = f"{new_pitch_val:.1f}"
            if new_pitch_key not in self.pitch_settings:
                div = DEFAULT_YAW_DIVISIONS_P0_INTERNAL if math.isclose(new_pitch_val,0.0) else DEFAULT_YAW_DIVISIONS_OTHER_INTERNAL
                yaws = [round(i*(360.0/div),2) for i in range(div)]
                self.pitch_settings[new_pitch_key] = {"yaws": yaws, "divisions": div, "fov": DEFAULT_FOV_INTERNAL}
                self._update_pitch_listbox_from_settings(initial_load=False)
                newly_added_idx = -1
                for i in range(self.pitch_listbox.size()):
                    if self.pitch_listbox.get(i).replace("°","") == new_pitch_key: newly_added_idx = i; break
                if newly_added_idx != -1:
                    self.pitch_listbox.selection_clear(0,tk.END); self.pitch_listbox.selection_set(newly_added_idx)
                    self.pitch_listbox.activate(newly_added_idx); self.on_pitch_selected(None,False)
            else: messagebox.showinfo("情報", "指定されたピッチ角は既にリストに存在します。", parent=self)
        except ValueError: messagebox.showwarning("入力エラー", "有効な数値を選択してください。", parent=self)

    def _remove_selected_pitch(self):
        sel_idx_tuple = self.pitch_listbox.curselection()
        if not sel_idx_tuple: messagebox.showwarning("削除エラー", "削除するピッチ角をリストから選択してください。", parent=self); return
        idx = sel_idx_tuple[0]
        if idx >= self.pitch_listbox.size(): return
        key_to_remove = self.pitch_listbox.get(idx).replace("°","")
        if len(self.pitch_settings) <= 1: messagebox.showinfo("情報", "最後のピッチ角は削除できません。\n(最低1つのピッチ角が必要です)", parent=self); return
        if key_to_remove in self.pitch_settings:
            del self.pitch_settings[key_to_remove]
            if key_to_remove in self.yaw_to_fixed_ring_assignment: del self.yaw_to_fixed_ring_assignment[key_to_remove]
            self.pitch_listbox.delete(idx)
            if self.pitch_listbox.size() > 0:
                new_sel = max(0, min(idx, self.pitch_listbox.size()-1))
                self.pitch_listbox.selection_set(new_sel); self.pitch_listbox.activate(new_sel)
                self.on_pitch_selected(None,False)
            else: self._update_pitch_listbox_from_settings(False)
        else: messagebox.showerror("内部エラー", "選択されたピッチが内部設定に見つかりません。", parent=self)
        
    def _on_selected_pitch_entry_confirm(self, event=None):
        if self._slider_update_active or self._internal_update_active: return
        self._entry_update_active = True
        try:
            new_val_str = self.selected_pitch_entry_var.get()
            new_val = float(new_val_str)
            new_val = max(-90.0, min(90.0, new_val))
            self.selected_pitch_value_var.set(new_val)
            self.selected_pitch_entry_var.set(f"{new_val:.1f}")
            self._process_pitch_change(new_val)
        except ValueError:
            current_slider_val = self.selected_pitch_value_var.get()
            self.selected_pitch_entry_var.set(f"{current_slider_val:.1f}")
            messagebox.showerror("入力エラー", "ピッチ角には有効な数値を入力してください。", parent=self)
        finally:
            self._entry_update_active = False

    def _process_pitch_change(self, new_val_float):
        if self._internal_update_active: return
        sel_idx_tuple = self.pitch_listbox.curselection()
        if not sel_idx_tuple: return
        idx = sel_idx_tuple[0]
        if idx >= self.pitch_listbox.size(): return
        old_key = self.pitch_listbox.get(idx).replace("°", "")
        new_key_candidate = f"{new_val_float:.1f}"
        snapped_new_val_float = round(new_val_float)
        if math.isclose(new_val_float, snapped_new_val_float, abs_tol=0.05):
            new_val_float = snapped_new_val_float
            new_key_candidate = f"{new_val_float:.1f}"
        if old_key == new_key_candidate:
            if old_key in self.pitch_settings:
                self.selected_pitch_value_var.set(new_val_float)
                self.selected_pitch_entry_var.set(new_key_candidate)
                if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
                if self.on_selection_change_callback: self.on_selection_change_callback()
            return
        if new_key_candidate in self.pitch_settings and new_key_candidate != old_key:
            messagebox.showwarning("重複エラー", f"ピッチ角 {new_key_candidate}° は既にリストに存在します。変更を元に戻します。", parent=self)
            old_val_float = float(old_key)
            self.selected_pitch_value_var.set(old_val_float)
            self.selected_pitch_entry_var.set(f"{old_val_float:.1f}")
            return
        if old_key in self.pitch_settings:
            self._internal_update_active = True
            s_move = self.pitch_settings.pop(old_key)
            self.pitch_settings[new_key_candidate] = s_move
            if old_key in self.yaw_to_fixed_ring_assignment:
                r_move = self.yaw_to_fixed_ring_assignment.pop(old_key)
                self.yaw_to_fixed_ring_assignment[new_key_candidate] = r_move
            self.current_pitch_key_var.set(new_key_candidate)
            self.selected_pitch_value_var.set(new_val_float)
            self.selected_pitch_entry_var.set(new_key_candidate)
            self.pitch_listbox.delete(idx)
            self.pitch_listbox.insert(idx, f"{new_key_candidate}°")
            self.pitch_listbox.selection_set(idx)
            self.pitch_listbox.activate(idx)
            self.precompute_ring_assignments_for_pitch(new_key_candidate)
            if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
            if self.on_selection_change_callback:
                self.on_selection_change_callback()
            self._internal_update_active = False
    
    def _on_selected_fov_entry_confirm(self, event=None):
        if self._fov_slider_update_active or self._internal_update_active: return
        self._fov_entry_update_active = True
        try:
            new_val_str = self.selected_pitch_fov_entry_var.get()
            new_val = float(new_val_str)
            new_val = max(MIN_FOV_DEGREES, min(new_val, MAX_FOV_DEGREES))
            self.selected_pitch_fov_var.set(new_val)
            self.selected_pitch_fov_entry_var.set(f"{new_val:.1f}")
            self._process_fov_change(new_val)
        except ValueError:
            current_fov_val = self.selected_pitch_fov_var.get()
            self.selected_pitch_fov_entry_var.set(f"{current_fov_val:.1f}")
            messagebox.showerror("入力エラー", "FOVには有効な数値を入力してください。", parent=self)
        finally:
            self._fov_entry_update_active = False

    def _process_fov_change(self, new_fov_float):
        if self._internal_update_active: return
        pitch_key = self.current_pitch_key_var.get()
        if not pitch_key or pitch_key not in self.pitch_settings: return
        snapped_new_fov_float = round(new_fov_float)
        if math.isclose(new_fov_float, snapped_new_fov_float, abs_tol=0.05):
            new_fov_float = snapped_new_fov_float
        new_fov_float = max(MIN_FOV_DEGREES, min(new_fov_float, MAX_FOV_DEGREES))
        self._internal_update_active = True
        self.pitch_settings[pitch_key]["fov"] = new_fov_float
        self.selected_pitch_fov_var.set(new_fov_float)
        self.selected_pitch_fov_entry_var.set(f"{new_fov_float:.1f}")
        self.precompute_ring_assignments_for_pitch(pitch_key)
        if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
        if self.on_selection_change_callback:
            self.on_selection_change_callback()
        self._internal_update_active = False

    def reset_current_pitch_fov(self):
        pitch_key = self.current_pitch_key_var.get()
        if not pitch_key or pitch_key not in self.pitch_settings:
            messagebox.showinfo("情報", "FOVをリセットするピッチが選択されていません。", parent=self)
            return
        target_fov = DEFAULT_FOV_INTERNAL
        self.selected_pitch_fov_var.set(target_fov)
        self.selected_pitch_fov_entry_var.set(f"{target_fov:.1f}")
        self._process_fov_change(target_fov)

    def on_pitch_selected(self, event, initial_load=False):
        sel_idx_tuple = self.pitch_listbox.curselection()
        if not sel_idx_tuple:
            self.selected_pitch_slider.config(state=tk.DISABLED)
            self.selected_pitch_entry.config(state=tk.DISABLED); self.selected_pitch_entry_var.set("")
            self.selected_pitch_fov_slider.config(state=tk.DISABLED)
            self.selected_pitch_fov_entry.config(state=tk.DISABLED); self.selected_pitch_fov_entry_var.set("")
            self.yaw_divisions_scale.config(state=tk.DISABLED)
            if self.pitch_listbox.size()==0:
                 self.current_pitch_key_var.set(""); self.current_yaw_divisions_var.set(0)
                 self._create_or_update_yaw_buttons()
                 if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
            if self.on_selection_change_callback and not initial_load: self.on_selection_change_callback()
            return
        idx = sel_idx_tuple[0]
        if idx >= self.pitch_listbox.size(): return
        key = self.pitch_listbox.get(idx).replace("°","")
        self._internal_update_active = True
        self.current_pitch_key_var.set(key)
        try:
            val_f=float(key)
            self.selected_pitch_value_var.set(val_f)
            self.selected_pitch_entry_var.set(f"{val_f:.1f}")
            if self.controls_enabled: # Only enable if overall controls are enabled
                self.selected_pitch_slider.config(state=tk.NORMAL)
                self.selected_pitch_entry.config(state=tk.NORMAL)
            else:
                self.selected_pitch_slider.config(state=tk.DISABLED)
                self.selected_pitch_entry.config(state=tk.DISABLED)
        except ValueError:
            self.selected_pitch_value_var.set(0)
            self.selected_pitch_entry_var.set("0.0")
            self.selected_pitch_slider.config(state=tk.DISABLED)
            self.selected_pitch_entry.config(state=tk.DISABLED)
        
        if self.controls_enabled:
            self.yaw_divisions_scale.config(state=tk.NORMAL)
        else:
            self.yaw_divisions_scale.config(state=tk.DISABLED)

        if key in self.pitch_settings:
            s=self.pitch_settings[key]; self.current_yaw_divisions_var.set(s["divisions"])
            current_pitch_fov = s.get("fov", DEFAULT_FOV_INTERNAL)
            self.selected_pitch_fov_var.set(current_pitch_fov)
            self.selected_pitch_fov_entry_var.set(f"{current_pitch_fov:.1f}")
            if self.controls_enabled: # Only enable if overall controls are enabled
                self.selected_pitch_fov_slider.config(state=tk.NORMAL)
                self.selected_pitch_fov_entry.config(state=tk.NORMAL)
            else:
                self.selected_pitch_fov_slider.config(state=tk.DISABLED)
                self.selected_pitch_fov_entry.config(state=tk.DISABLED)

            if key not in self.yaw_to_fixed_ring_assignment or not self.yaw_to_fixed_ring_assignment.get(key):
                self.precompute_ring_assignments_for_pitch(key)
            self._create_or_update_yaw_buttons()
            if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
        else: 
            self.current_yaw_divisions_var.set(0); self.yaw_divisions_scale.config(state=tk.DISABLED)
            self.selected_pitch_fov_slider.config(state=tk.DISABLED)
            self.selected_pitch_fov_entry.config(state=tk.DISABLED); self.selected_pitch_fov_entry_var.set("")
            self._create_or_update_yaw_buttons()
            if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
            print(f"Error: Key '{key}' not found in pitch_settings during on_pitch_selected.")
        self._internal_update_active = False
        if self.on_selection_change_callback and not initial_load: self.on_selection_change_callback()

    def _on_fov_or_divisions_changed(self,event=None):
        if self._internal_update_active:return
        key=self.current_pitch_key_var.get()
        if not key or key not in self.pitch_settings:return
        new_divs=self.current_yaw_divisions_var.get(); s=self.pitch_settings[key]
        if s["divisions"]!=new_divs:
            s["divisions"]=new_divs; yaws=[round(i*(360.0/new_divs),2) for i in range(new_divs)]; s["yaws"]=yaws
            self.precompute_ring_assignments_for_pitch(key); self._create_or_update_yaw_buttons()
        self._update_yaw_button_states()
        if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
        if self.on_selection_change_callback:self.on_selection_change_callback()
            
    def _create_or_update_yaw_buttons(self):
        for w in self.yaw_buttons_frame.winfo_children(): w.destroy()
        self.yaw_buttons.clear()
        key=self.current_pitch_key_var.get();
        if not key or key not in self.pitch_settings:return
        s=self.pitch_settings.get(key);
        if not s:return
        divs=s["divisions"];
        if divs==0:return
        step=360.0/divs
        max_c = 3
        for i in range(divs):
            y_a=round(i*step,2);txt=f"{y_a:.0f}°"
            import functools; cmd=functools.partial(self._toggle_yaw_selection_from_button,y_a)
            btn_state = tk.NORMAL if self.controls_enabled else tk.DISABLED
            btn=tk.Button(self.yaw_buttons_frame,text=txt,command=cmd,bg=BUTTON_NORMAL_BG, width=5, state=btn_state)
            r,c=i//max_c,i%max_c; btn.grid(row=r,column=c,padx=2,pady=2,sticky="ew")
            if c<max_c:self.yaw_buttons_frame.columnconfigure(c,weight=1)
            self.yaw_buttons.append({"button":btn,"yaw":y_a})
        self._update_yaw_button_states()

    def _toggle_yaw_selection_from_button(self,y_a):self._toggle_yaw_selection(y_a)
    def _toggle_yaw_selection(self,y_a_toggle):
        if self._internal_update_active:return
        key=self.current_pitch_key_var.get();
        if not key or key not in self.pitch_settings:return
        s=self.pitch_settings[key];yaws=s.get("yaws",[]);y_f=float(y_a_toggle);found=False
        for i,sy_raw in enumerate(yaws):
            if math.isclose(float(sy_raw),y_f):yaws.pop(i);found=True;break
        if not found:yaws.append(y_a_toggle);yaws.sort(key=float)
        s["yaws"]=yaws;self._update_yaw_button_states()
        if hasattr(self, 'yaw_canvas'): self.draw_yaw_selector()
        if self.on_selection_change_callback:self.on_selection_change_callback()

    def _update_yaw_button_states(self):
        key=self.current_pitch_key_var.get()
        if not key or key not in self.pitch_settings:
            [b["button"].config(relief=tk.RAISED,bg=BUTTON_NORMAL_BG) for b in self.yaw_buttons];return
        s=self.pitch_settings.get(key)
        if not s:
            [b["button"].config(relief=tk.RAISED,bg=BUTTON_NORMAL_BG) for b in self.yaw_buttons];return
        sel_yaws=s.get("yaws",[]);rings=self.yaw_to_fixed_ring_assignment.get(key,{})
        if not rings and s.get("divisions",0)>0:
             self.precompute_ring_assignments_for_pitch(key);rings=self.yaw_to_fixed_ring_assignment.get(key,{})
        for b_info in self.yaw_buttons:
            btn,yaw=b_info["button"],b_info["yaw"];is_sel=any(math.isclose(float(yaw),float(s_y)) for s_y in sel_yaws)
            bg_c=BUTTON_NORMAL_BG
            if is_sel:r_data=rings.get(yaw);bg_c=r_data["color"] if r_data else "lightgray"
            btn.config(relief=tk.SUNKEN if is_sel else tk.RAISED,bg=bg_c)
    
    def _apply_rotation(self,point,angle_rad,axis_char):
        x,y,z=point;c,s=math.cos(angle_rad),math.sin(angle_rad)
        if axis_char=='x': return(x,y*c-z*s,y*s+z*c)
        if axis_char=='y': return(z*s+x*c,y,z*c-x*s)
        return point

    def _transform_and_project_point(self,local_point_world_scale,local_pitch_rad,local_yaw_rad):
        p_pitched=self._apply_rotation(local_point_world_scale,-local_pitch_rad,'x')
        p_world_rotated=self._apply_rotation(p_pitched,local_yaw_rad,'y')     
        p_global_y_rotated=self._apply_rotation(p_world_rotated,self.global_rotation_y_rad,'y')
        p_global_xy_rotated=self._apply_rotation(p_global_y_rotated,self.global_rotation_x_rad,'x')
        gx,gy,gz=p_global_xy_rotated
        current_c_center_x = self.canvas_actual_width / 2
        current_c_center_y = self.canvas_actual_height / 2
        screen_x = current_c_center_x + gx
        screen_y = current_c_center_y - gy
        return screen_x, screen_y, gz
    
    def precompute_ring_assignments_for_pitch(self,pk_str):
        if pk_str not in self.pitch_settings:return
        s=self.pitch_settings[pk_str];d=s["divisions"];cpa={}
        if d<=0:self.yaw_to_fixed_ring_assignment[pk_str]={};return
        step=360.0/d;yaws=[round(i*step,2) for i in range(d)]
        for i,y_a in enumerate(yaws):
            color_idx = i % len(FOV_RING_COLORS_BASE)
            layer_idx = i % MAX_YAW_DIVISIONS
            cpa[y_a]={"color":FOV_RING_COLORS_BASE[color_idx],"layer":layer_idx}
        self.yaw_to_fixed_ring_assignment[pk_str]=cpa
        
    def _hex_to_darker_hex(self, hex_color, factor=0.7):
        if not isinstance(hex_color, str) or not hex_color.startswith('#') or len(hex_color) != 7:
            return hex_color 
        try:
            r = int(hex_color[1:3], 16);g = int(hex_color[3:5], 16);b = int(hex_color[5:7], 16)
            r = int(r * factor); g = int(g * factor); b = int(b * factor)
            r = max(0, min(255, r)); g = max(0, min(255, g)); b = max(0, min(255, b))
            return f"#{r:02x}{g:02x}{b:02x}"
        except ValueError: return hex_color

    def draw_yaw_selector(self):
        if not hasattr(self, 'yaw_canvas') or not self.yaw_canvas.winfo_exists(): return
        self.yaw_canvas.delete("all")
        pk_str=self.current_pitch_key_var.get()
        canvas_width = self.canvas_actual_width
        canvas_height = self.canvas_actual_height
        local_c_center_x = canvas_width / 2
        local_c_center_y = canvas_height / 2
        current_canvas_size_for_scaling = min(canvas_width, canvas_height)
        if current_canvas_size_for_scaling < MIN_CANVAS_DRAW_SIZE:
             self.yaw_canvas.create_text(local_c_center_x, local_c_center_y, text="Canvas too small", fill="red")
             return
        if not pk_str or pk_str not in self.pitch_settings:
            padding = 5
            info_text_unselected = "Pitch: N/A\nTotal VPs: 0"
            text_id_info_unselected = self.yaw_canvas.create_text(padding, padding, text=info_text_unselected, fill=COLOR_TEXT, font=("Arial", 9, "bold"), anchor="nw", justify="left")
            try:
                bbox_info_unselected = self.yaw_canvas.bbox(text_id_info_unselected)
                if bbox_info_unselected:
                    self.yaw_canvas.create_rectangle(bbox_info_unselected[0]-3, bbox_info_unselected[1]-2, bbox_info_unselected[2]+3, bbox_info_unselected[3]+2, fill=COLOR_CENTER_TEXT_BG, outline="darkgray", width=1.0)
                    self.yaw_canvas.lift(text_id_info_unselected)
            except tk.TclError: pass
            self.yaw_canvas.create_text(local_c_center_x,local_c_center_y,text="ピッチを選択",fill=COLOR_TEXT)
        else: # ピッチが選択されている場合のみ詳細を描画
            s=self.pitch_settings.get(pk_str)
            if not s: 
                self.yaw_canvas.create_text(local_c_center_x,local_c_center_y,text="設定エラー",fill="red"); return
            base_p_deg=float(pk_str)
            divs,sel_yaws = s["divisions"],s.get("yaws",[])
            fov_d = s.get("fov", DEFAULT_FOV_INTERNAL)
            fov_r,world_radius_scale=math.radians(fov_d),current_canvas_size_for_scaling*0.42
            self.yaw_canvas.create_oval(local_c_center_x-world_radius_scale,local_c_center_y-world_radius_scale,local_c_center_x+world_radius_scale,local_c_center_y+world_radius_scale,outline="#E0E0E0",dash=(1,3))
            pyramids_data_list=[];base_p_r=math.radians(base_p_deg);ang_s=360.0/divs if divs>0 else 0;apx=(0,0,0)
            tan_fh=math.tan(fov_r/2.0) if fov_r > 0.001 else 0.0001
            d_pl_denom_val = 1+2*tan_fh**2
            if d_pl_denom_val < 0: d_pl_denom_val = 1 
            d_pl_denom = math.sqrt(d_pl_denom_val)
            d_pl=world_radius_scale/d_pl_denom if tan_fh>1e-5 and d_pl_denom > 1e-9 else world_radius_scale
            s_on_pl=d_pl*tan_fh
            c_ws=[(-s_on_pl,s_on_pl,d_pl),(s_on_pl,s_on_pl,d_pl),(s_on_pl,-s_on_pl,d_pl),(-s_on_pl,-s_on_pl,d_pl)] if fov_r>0.001 else []
            rings=self.yaw_to_fixed_ring_assignment.get(pk_str,{})
            if not rings and divs > 0:
                self.precompute_ring_assignments_for_pitch(pk_str)
                rings=self.yaw_to_fixed_ring_assignment.get(pk_str,{})
            for i in range(divs if divs>0 else 0):
                y_d=round(i*ang_s,2);is_s=any(math.isclose(float(y_d),float(sy))for sy in sel_yaws);y_r=math.radians(y_d)
                pax_x,pax_y,pax_z=self._transform_and_project_point(apx,base_p_r,y_r);pcs=[];sum_z_s=0
                if c_ws:
                    for cws_pt in c_ws:px,py,pz=self._transform_and_project_point(cws_pt,base_p_r,y_r);pcs.append((px,py));sum_z_s+=pz
                dep=sum_z_s/4 if c_ws and pcs else pax_z
                lbl_anc=(0,0,d_pl) if c_ws else apx;lx,ly,lz=self._transform_and_project_point(lbl_anc,base_p_r,y_r)
                pyramids_data_list.append({"yaw_deg":y_d,"is_selected":is_s,"apex_proj":(pax_x,pax_y),"corners_proj":pcs,"depth":dep,"label_proj_pos":(lx,ly),"label_depth":lz})
            pyramids_data_list.sort(key=lambda p:p["depth"])
            for p_d in pyramids_data_list:
                pxa,pya=p_d["apex_proj"];pcs=p_d["corners_proj"];front=True
                if len(pcs)==4:v0,v1,v2=pcs[0],pcs[1],pcs[2];area=(v1[0]-v0[0])*(v2[1]-v0[1])-(v1[1]-v0[1])*(v2[0]-v0[0]);front=area>=0
                f_color, o_color, line_w, stipple_fill, stipple_line = "", "", 1.0, "", ""
                ring_color_data = rings.get(p_d["yaw_deg"], {})
                base_button_color = ring_color_data.get("color", FOV_RING_COLORS_BASE[0])
                if p_d["is_selected"]:
                    if front: f_color = base_button_color; o_color = C_FOV_BOUNDARY_LINE_COLOR; line_w = 1.5
                    else: f_color = base_button_color; o_color = self._hex_to_darker_hex(base_button_color, 0.65); line_w = 1.0; stipple_fill = "gray25" ; stipple_line = "gray50" 
                else: 
                    if front: f_color = COLOR_SECTOR_DESELECTED_FILL; o_color = COLOR_SECTOR_DESELECTED_OUTLINE
                    else: f_color = BACKFACE_FILL_COLOR; o_color = FAR_SIDE_LINE_COLOR; stipple_fill = BACKFACE_STIPPLE; stipple_line = "gray50"; line_w = 0.8
                depth_ratio = (p_d["depth"] + world_radius_scale) / (2 * world_radius_scale) if world_radius_scale > 0 else 0.5
                if front and not p_d["is_selected"]:
                    if depth_ratio < 0.3: stipple_fill = "gray75" if not stipple_fill else stipple_fill; o_color = "darkgrey" if o_color == COLOR_SECTOR_DESELECTED_OUTLINE else o_color; stipple_line = "gray75"
                    elif depth_ratio < 0.6: stipple_fill = "gray50" if not stipple_fill else stipple_fill; o_color = "grey" if o_color == COLOR_SECTOR_DESELECTED_OUTLINE else o_color; stipple_line = "gray50"
                if len(pcs)==4:
                    self.yaw_canvas.create_polygon(pcs,fill=f_color,outline="",stipple=stipple_fill)
                    for ic in range(4): p1,p2=pcs[ic],pcs[(ic+1)%4]; self.yaw_canvas.create_line(p1[0],p1[1],p2[0],p2[1],fill=o_color,width=line_w,stipple=stipple_line)
                if c_ws: 
                    side_line_color = o_color; side_line_stipple = stipple_line; side_line_width = line_w * 0.8 if line_w > 1 else line_w
                    for cp in pcs: self.yaw_canvas.create_line(pxa,pya,cp[0],cp[1],fill=side_line_color,width=side_line_width,stipple=side_line_stipple)
                elif fov_r<=0.01:
                     dot_fill = o_color if p_d["is_selected"] else "grey"; self.yaw_canvas.create_oval(pxa-1.5,pya-1.5,pxa+1.5,pya+1.5,fill=dot_fill,outline="")
            for p_d in reversed(pyramids_data_list):
                if p_d["label_depth"] > -world_radius_scale * 0.8 : 
                    lx, ly = p_d["label_proj_pos"]; yaw_deg_val = p_d['yaw_deg']; lt = f"{yaw_deg_val:.0f}°"
                    label_item_tag = f"label_yaw_{str(yaw_deg_val).replace('.', '_')}"; clickable_surface_tag = "clickable_label_surface"
                    tid = self.yaw_canvas.create_text(lx, ly, text=lt, fill=LABEL_TEXT_COLOR, font=("Arial", 7), anchor=tk.CENTER, tags=(label_item_tag, clickable_surface_tag))
                    bg_rect_id = None
                    try:
                        b = self.yaw_canvas.bbox(tid)
                        if b: bg_rect_id = self.yaw_canvas.create_rectangle(b[0]-1,b[1]-1,b[2]+1,b[3]+1,fill="white",outline="gray",width=0.5, tags=(f"bg_{label_item_tag}", clickable_surface_tag)); self.yaw_canvas.lift(tid)
                    except tk.TclError: pass
                    self.yaw_canvas.tag_bind(tid, "<Button-3>", lambda event, y=yaw_deg_val: self._on_label_right_click(event, y))
                    if bg_rect_id: self.yaw_canvas.tag_bind(bg_rect_id, "<Button-3>", lambda event, y=yaw_deg_val: self._on_label_right_click(event, y))
            eqf,eqb=[],[];neq=48;lprr=math.radians(base_p_deg)
            for i in range(neq+1):
                lyrr=(i/neq)*2*math.pi;ex,ey,ez=math.cos(lprr)*math.sin(lyrr)*world_radius_scale,math.sin(lprr)*world_radius_scale,math.cos(lprr)*math.cos(lyrr)*world_radius_scale
                cx,cy,gz=self._transform_and_project_point((ex,ey,ez),0,0)
                if gz>=0: eqf.append((cx,cy))
                else: eqb.append((cx,cy))
            if len(eqb)>1:self.yaw_canvas.create_line(eqb,fill=COLOR_PITCHED_EQUATOR,dash=(1,2),width=1.0,stipple="gray75")
            if len(eqf)>1:self.yaw_canvas.create_line(eqf,fill=COLOR_PITCHED_EQUATOR,dash=(2,2),width=1.5)
            padding = 5
            total_vps = len(self.get_selected_viewpoints())
            current_pitch_fov = self.get_current_fov_for_selected_pitch()
            fov_display = f"{current_pitch_fov:.1f}°" if current_pitch_fov is not None else "N/A"
            info_text = f"Pitch: {base_p_deg:.1f}° (FOV: {fov_display})\nDivs: {divs}\nTotal VPs: {total_vps}"
            text_id_info = self.yaw_canvas.create_text(padding, padding, text=info_text, fill=COLOR_TEXT, font=("Arial", 9, "bold"), anchor="nw", justify=tk.LEFT)
            try:
                bbox_info = self.yaw_canvas.bbox(text_id_info)
                if bbox_info:
                    self.yaw_canvas.create_rectangle(bbox_info[0]-3, bbox_info[1]-2, bbox_info[2]+3, bbox_info[3]+2, fill=COLOR_CENTER_TEXT_BG, outline="darkgray", width=1.0)
                    self.yaw_canvas.lift(text_id_info)
            except tk.TclError: pass

        # キャンバス右上に操作説明テキストを描画
        help_text_padding = 5
        help_text_content = "左ドラッグ:回転  右クリック:視点選択/解除"
        help_text_x = canvas_width - help_text_padding
        self.yaw_canvas.create_text(
            help_text_x, help_text_padding, text=help_text_content,
            fill=CANVAS_HELP_TEXT_COLOR, font=("Arial", 8), anchor="ne"
        )

    def _on_label_right_click(self, event, yaw_angle):
        if not self.controls_enabled: return "break"
        if self.is_dragging: return "break" 
        self._toggle_yaw_selection(yaw_angle)
        return "break"

    def _handle_canvas_right_click(self, event):
        if not self.controls_enabled: return "break"
        if self.is_dragging: return "break"
        overlapping_items = self.yaw_canvas.find_overlapping(event.x-1, event.y-1, event.x+1, event.y+1)
        for item_id in reversed(overlapping_items):
            tags = self.yaw_canvas.gettags(item_id)
            if "clickable_label_surface" in tags: return "break" 
        self._perform_cone_selection_on_right_click(event)
        return "break"

    def _perform_cone_selection_on_right_click(self, event):
        pk_str=self.current_pitch_key_var.get()
        if not pk_str or pk_str not in self.pitch_settings:return
        s=self.pitch_settings.get(pk_str);
        if not s:return
        divisions=s["divisions"]
        if divisions<=0:return
        click_x,click_y=event.x,event.y; target_yaw_to_toggle=-1
        current_pitch_fov_deg = s.get("fov", DEFAULT_FOV_INTERNAL)
        current_pitch_fov_rad = math.radians(current_pitch_fov_deg)
        tan_fov_half = math.tan(current_pitch_fov_rad/2.0) if current_pitch_fov_rad > 0.001 else 0.0001
        canvas_width = self.canvas_actual_width; canvas_height = self.canvas_actual_height
        current_canvas_size_for_scaling = min(canvas_width, canvas_height)
        if current_canvas_size_for_scaling < MIN_CANVAS_DRAW_SIZE: current_canvas_size_for_scaling = MIN_CANVAS_DRAW_SIZE
        world_radius = current_canvas_size_for_scaling * 0.42
        d_pl_denom_val = 1 + 2 * tan_fov_half**2
        if d_pl_denom_val < 0: d_pl_denom_val = 1 
        d_pl_denom = math.sqrt(d_pl_denom_val)
        d_plane = world_radius / d_pl_denom if tan_fov_half > 1e-5 and d_pl_denom > 1e-9 else world_radius
        apex_world_scaled=(0,0,0)
        htd=[]; base_pitch_rad=math.radians(float(pk_str)); angle_step=360.0/divisions
        for i in range(divisions):
            yaw_deg_iter=round(i*angle_step,2); yaw_rad=math.radians(yaw_deg_iter)
            label_anchor_point_world_scaled=(0,0,d_plane) if current_pitch_fov_rad > 0.001 else apex_world_scaled
            lpx,lpy,lpz=self._transform_and_project_point(label_anchor_point_world_scaled, base_pitch_rad, yaw_rad)
            htd.append({"yaw_deg":yaw_deg_iter,"proj_center_x":lpx,"proj_center_y":lpy,"depth":lpz})
        htd.sort(key=lambda p:p["depth"],reverse=True)
        min_dist_sq = float('inf')
        click_radius_threshold_sq = (current_canvas_size_for_scaling*0.08)**2 
        for cone_data in htd:
            if cone_data["depth"] < -world_radius * 0.3: continue
            dist_sq=(click_x-cone_data["proj_center_x"])**2+(click_y-cone_data["proj_center_y"])**2
            if dist_sq < click_radius_threshold_sq:
                if dist_sq < min_dist_sq:
                    min_dist_sq = dist_sq; target_yaw_to_toggle = cone_data["yaw_deg"]
        if target_yaw_to_toggle != -1: self._toggle_yaw_selection(target_yaw_to_toggle)

    def get_selected_viewpoints(self):
        vps=[]
        for pk_str,s_val in self.pitch_settings.items():
            try:
                p_ang=float(pk_str)
                yaws_raw=s_val.get("yaws",[])
                current_fov_for_pitch = s_val.get("fov", DEFAULT_FOV_INTERNAL)
                for y_raw in yaws_raw: 
                    vps.append({"pitch":p_ang,"yaw":float(y_raw),"fov":current_fov_for_pitch})
            except ValueError:print(f"Warning: Invalid value for pitch key {pk_str} in pitch_settings.");continue
        return vps
        
    def set_pitches_externally(self,pitches_string):
        self._parse_and_set_initial_pitches(pitches_string,False)
        self._select_initial_pitch(False)

    def enable_controls(self):
        self.controls_enabled = True
        self.pitch_to_add_combo.config(state="readonly")
        self.add_pitch_button.config(state=tk.NORMAL)
        self.remove_pitch_button.config(state=tk.NORMAL)
        self.pitch_listbox.config(state=tk.NORMAL)
        
        has_selection = bool(self.pitch_listbox.curselection())
        slider_entry_state = tk.NORMAL if has_selection else tk.DISABLED
        
        self.selected_pitch_slider.config(state=slider_entry_state)
        self.selected_pitch_entry.config(state=slider_entry_state)
        self.selected_pitch_fov_slider.config(state=slider_entry_state)
        self.selected_pitch_fov_entry.config(state=slider_entry_state)
        self.yaw_divisions_scale.config(state=slider_entry_state)
        
        self.pitch_reset_button.config(state=tk.NORMAL)
        self.fov_reset_button.config(state=tk.NORMAL)
        for item in self.yaw_buttons:
            item["button"].config(state=tk.NORMAL)

    def disable_controls(self):
        self.controls_enabled = False
        self.pitch_to_add_combo.config(state=tk.DISABLED)
        self.add_pitch_button.config(state=tk.DISABLED)
        self.remove_pitch_button.config(state=tk.DISABLED)
        self.pitch_listbox.config(state=tk.DISABLED)
        self.selected_pitch_slider.config(state=tk.DISABLED)
        self.selected_pitch_entry.config(state=tk.DISABLED)
        self.selected_pitch_fov_slider.config(state=tk.DISABLED)
        self.selected_pitch_fov_entry.config(state=tk.DISABLED)
        self.yaw_divisions_scale.config(state=tk.DISABLED)
        self.pitch_reset_button.config(state=tk.DISABLED)
        self.fov_reset_button.config(state=tk.DISABLED)
        for item in self.yaw_buttons:
            item["button"].config(state=tk.DISABLED)

    def get_num_active_pitches(self):
        return len(self.pitch_settings)

    def get_current_fov_for_selected_pitch(self):
        pitch_key = self.current_pitch_key_var.get()
        if pitch_key and pitch_key in self.pitch_settings:
            return self.pitch_settings[pitch_key].get("fov", DEFAULT_FOV_INTERNAL)
        return None


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Advanced Yaw Selector Test")
    root.geometry("750x650")
    info_label_var = tk.StringVar(value="Selection info will appear here.")
    selector_widget_instance = None
    
    def handle_update_from_selector_main():
        if selector_widget_instance is None: return
        vps=selector_widget_instance.get_selected_viewpoints()
        pk_str_main=selector_widget_instance.current_pitch_key_var.get()
        divs_main=selector_widget_instance.current_yaw_divisions_var.get()
        
        current_pitch_fov_text = "N/A"
        if pk_str_main and pk_str_main in selector_widget_instance.pitch_settings:
            fov_val = selector_widget_instance.pitch_settings[pk_str_main].get('fov', DEFAULT_FOV_INTERNAL)
            current_pitch_fov_text = f"{fov_val:.1f}°"

        txt_main=f"Sel.Pitch:{pk_str_main}° (FOV: {current_pitch_fov_text})\n"
        txt_main+=f"Divs:{divs_main}\nTotal VPs:{len(vps)}\n"
        if vps:
            txt_main+="Sample Viewpoints:\n"
            for vp_idx, vp_item in enumerate(vps[:min(len(vps),3)]):
                 txt_main += f" P:{vp_item['pitch']:.1f}°, Y:{vp_item['yaw']:.1f}°, F:{vp_item['fov']:.1f}°\n"
            if len(vps)>3: txt_main+=f" ...and {len(vps)-3} more.\n"
        else: txt_main+="No Viewpoints selected."
        info_label_var.set(txt_main)
        
    selector_widget_instance = AdvancedYawSelector(root, initial_pitches_str=DEFAULT_PITCHES_STR, on_selection_change_callback=handle_update_from_selector_main)
    selector_widget_instance.pack(expand=True,fill=tk.BOTH,padx=10,pady=10)
    
    idl=tk.Label(root,textvariable=info_label_var,justify=tk.LEFT,anchor="nw",relief=tk.SUNKEN,bd=1,height=8,font=("Consolas",9));
    idl.pack(fill=tk.X,padx=10,pady=(0,10))
    
    root.update_idletasks()
    if selector_widget_instance: handle_update_from_selector_main()
    
    root.mainloop()