# advanced_yaw_selector.py
import tkinter as tk
from tkinter import ttk, messagebox
import math
import functools # For partial

from strings import S # グローバル文字列インスタンスをインポート
from tooltip_utils import ToolTip
from constants import ( # このモジュール固有の定数をインポート
    AYS_INITIAL_CANVAS_SIZE, AYS_MIN_CANVAS_DRAW_SIZE, AYS_DEBOUNCE_DELAY_MS,
    AYS_MIN_FOV_DEGREES, AYS_MAX_FOV_DEGREES, AYS_DEFAULT_FOV_INTERNAL,
    AYS_MAX_YAW_DIVISIONS, AYS_DEFAULT_YAW_DIVISIONS_P0_INTERNAL,
    AYS_DEFAULT_YAW_DIVISIONS_OTHER_INTERNAL, AYS_DEFAULT_PITCHES_STR,
    AYS_PREDEFINED_PITCH_ADD_VALUES, AYS_MAX_PITCH_ENTRIES,
    AYS_COLOR_CANVAS_BG, AYS_COLOR_TEXT, AYS_FOV_RING_COLORS_BASE,
    AYS_C_FOV_BOUNDARY_LINE_COLOR, AYS_COLOR_CENTER_TEXT_BG,
    AYS_COLOR_PITCHED_EQUATOR, AYS_FAR_SIDE_LINE_COLOR,
    AYS_FAR_SIDE_FILL_COLOR, AYS_BACKFACE_FILL_COLOR, AYS_BACKFACE_STIPPLE,
    AYS_BUTTON_NORMAL_BG, AYS_LABEL_TEXT_COLOR,
    AYS_COLOR_SECTOR_DESELECTED_FILL, AYS_COLOR_SECTOR_DESELECTED_OUTLINE,
    AYS_CANVAS_HELP_TEXT_COLOR
)

# Constants for canvas interaction (consider moving to constants.py if widely used)
AYS_MOUSE_DRAG_SENSITIVITY = 200.0
AYS_MAX_VIEW_X_ROTATION_FACTOR = 0.999 # Prevents gimbal lock visualization issues
AYS_CLICKABLE_LABEL_TAG = "clickable_label_surface"


class AdvancedYawSelector(tk.Frame):
    def __init__(self, master, initial_pitches_str=AYS_DEFAULT_PITCHES_STR,
                 on_selection_change_callback=None, **kwargs):
        super().__init__(master, **kwargs)

        self.on_selection_change_callback = on_selection_change_callback

        self.current_pitch_key_var = tk.StringVar()
        self.current_yaw_divisions_var = tk.IntVar()
        self.selected_pitch_value_var = tk.DoubleVar()
        self.selected_pitch_entry_var = tk.StringVar()
        self.selected_pitch_fov_var = tk.DoubleVar(value=AYS_DEFAULT_FOV_INTERNAL)
        self.selected_pitch_fov_entry_var = tk.StringVar()
        self.pitch_to_add_var = tk.StringVar()

        self.pitch_settings = {} # Stores {"pitch_key": {"yaws": [...], "divisions": N, "fov": F}, ...}
        self.yaw_to_fixed_ring_assignment = {} # Stores {"pitch_key": {yaw_angle: {"color": ..., "layer": ...}}}
        self.yaw_buttons = [] # Stores {"button": widget, "yaw": angle}

        self.global_rotation_y_rad = 0.0
        self.global_rotation_x_rad = math.pi / 6 # Initial tilt
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self.is_dragging = False
        self._slider_update_active = False      # Flag to prevent slider event recursion
        self._entry_update_active = False       # Flag to prevent entry event recursion
        self._fov_slider_update_active = False
        self._fov_entry_update_active = False
        self._internal_update_active = False    # General flag for internal state updates

        self._configure_timer_id = None         # For debouncing canvas resize
        self._pitch_slider_debounce_timer_id = None # For debouncing pitch slider drags
        self._fov_slider_debounce_timer_id = None   # For debouncing FOV slider drags

        self.canvas_actual_width = AYS_INITIAL_CANVAS_SIZE
        self.canvas_actual_height = AYS_INITIAL_CANVAS_SIZE

        self.controls_enabled = True
        self.tooltips = [] # Managed tooltips

        self._setup_ui_layout()

        # Bind configure event to the canvas for redraws on resize
        if hasattr(self, 'yaw_canvas') and self.yaw_canvas: # Ensure canvas exists
            self.yaw_canvas.bind("<Configure>", self._on_canvas_configure)

        self._parse_and_set_initial_pitches(initial_pitches_str, initial_load=True)
        self._select_initial_pitch(initial_load=True)

    def add_tooltip_managed(self, widget, text_key, *args, **kwargs):
        text = S.get(text_key, *args, **kwargs) if text_key else ""
        tip = ToolTip(widget, text)
        self.tooltips.append({"instance": tip, "key": text_key, "args": args, "kwargs": kwargs})
        return tip

    def update_all_tooltips_text(self):
        for tip_info in self.tooltips:
            new_text = S.get(tip_info["key"], *tip_info["args"], **tip_info["kwargs"]) if tip_info["key"] else ""
            tip_info["instance"].update_text(new_text)

    def update_ui_texts_for_language_switch(self):
        self.add_pitch_button.config(text=S.get("ays_add_pitch_button_label"))
        self.remove_pitch_button.config(text=S.get("ays_remove_pitch_button_label"))
        self.output_pitch_list_label.config(text=S.get("ays_output_pitch_list_label"))
        self.pitch_reset_button.config(text=S.get("ays_pitch_reset_button_label"))
        self.fov_reset_button.config(text=S.get("ays_fov_reset_button_label"))
        self.yaw_selection_title_label.config(text=S.get("ays_yaw_selection_label"))
        self.pitch_adjust_title_label.config(text=S.get("ays_pitch_adjust_label_format"))
        self.fov_adjust_title_label.config(text=S.get("ays_fov_adjust_label_format", min_fov=AYS_MIN_FOV_DEGREES, max_fov=AYS_MAX_FOV_DEGREES))
        self.yaw_divisions_title_label.config(text=S.get("ays_yaw_divisions_label_format", max_divisions=AYS_MAX_YAW_DIVISIONS))

        self.update_all_tooltips_text() # This will re-fetch and apply tooltip texts

        if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
            self.draw_yaw_selector()

    def _setup_ui_layout(self):
        main_paned_window = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=6)
        main_paned_window.pack(fill=tk.BOTH, expand=True)

        # --- Left Frame (Pitch Controls & Yaw Buttons) ---
        left_frame = tk.Frame(main_paned_window, bd=1, relief=tk.SUNKEN)
        main_paned_window.add(left_frame, width=220, minsize=200, stretch="never")

        pitch_control_frame = tk.Frame(left_frame)
        pitch_control_frame.pack(fill=tk.X, padx=5, pady=(5,2))

        self.pitch_to_add_combo = ttk.Combobox(pitch_control_frame, textvariable=self.pitch_to_add_var,
                                               values=[str(p) for p in AYS_PREDEFINED_PITCH_ADD_VALUES],
                                               width=5, state="readonly")
        self.pitch_to_add_combo.pack(side=tk.LEFT, padx=(0,2))
        if AYS_PREDEFINED_PITCH_ADD_VALUES: # Ensure list is not empty
            self.pitch_to_add_combo.set("0") # Default selection
        self.add_tooltip_managed(self.pitch_to_add_combo, "ays_pitch_to_add_combo_tooltip")

        self.add_pitch_button = tk.Button(pitch_control_frame, text=S.get("ays_add_pitch_button_label"), command=self._add_pitch_from_combo, width=4)
        self.add_pitch_button.pack(side=tk.LEFT, padx=(0,2))
        self.add_tooltip_managed(self.add_pitch_button, "ays_add_pitch_button_tooltip_format", max_entries=AYS_MAX_PITCH_ENTRIES)

        self.remove_pitch_button = tk.Button(pitch_control_frame, text=S.get("ays_remove_pitch_button_label"), command=self._remove_selected_pitch, width=4)
        self.remove_pitch_button.pack(side=tk.LEFT)
        self.add_tooltip_managed(self.remove_pitch_button, "ays_remove_pitch_button_tooltip")

        self.output_pitch_list_label = tk.Label(left_frame, text=S.get("ays_output_pitch_list_label"))
        self.output_pitch_list_label.pack(anchor="w", padx=5, pady=(5,0))

        self.pitch_listbox = tk.Listbox(left_frame, exportselection=False, height=AYS_MAX_PITCH_ENTRIES)
        self.pitch_listbox.pack(fill=tk.X, padx=5, pady=(2,5))
        self.pitch_listbox.bind("<<ListboxSelect>>", lambda event: self.on_pitch_selected(event, initial_load=False))
        self.add_tooltip_managed(self.pitch_listbox, "ays_pitch_listbox_tooltip")

        reset_buttons_control_frame_left = tk.Frame(left_frame)
        reset_buttons_control_frame_left.pack(pady=(5,2), padx=5, fill=tk.X)
        self.pitch_reset_button = tk.Button(reset_buttons_control_frame_left, text=S.get("ays_pitch_reset_button_label"),
                                            command=lambda: self.set_pitches_externally(AYS_DEFAULT_PITCHES_STR))
        self.pitch_reset_button.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        self.add_tooltip_managed(self.pitch_reset_button, "ays_pitch_reset_button_tooltip_format", default_pitches=AYS_DEFAULT_PITCHES_STR)

        self.fov_reset_button = tk.Button(reset_buttons_control_frame_left, text=S.get("ays_fov_reset_button_label"),
                                          command=self.reset_current_pitch_fov)
        self.fov_reset_button.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        self.add_tooltip_managed(self.fov_reset_button, "ays_fov_reset_button_tooltip_format", default_fov=AYS_DEFAULT_FOV_INTERNAL)

        self.yaw_selection_title_label = tk.Label(left_frame, text=S.get("ays_yaw_selection_label"))
        self.yaw_selection_title_label.pack(anchor="w", padx=5, pady=(5,0))

        self.yaw_buttons_outer_frame = tk.Frame(left_frame) # For consistent padding and centering
        self.yaw_buttons_outer_frame.pack(pady=(0,5), padx=5, fill=tk.X, expand=True)
        self.yaw_buttons_frame = tk.Frame(self.yaw_buttons_outer_frame) # Actual grid for buttons
        self.yaw_buttons_frame.pack(anchor="n") # Center the grid of buttons
        self.add_tooltip_managed(self.yaw_buttons_outer_frame, "ays_yaw_buttons_tooltip")

        # --- Right Frame (Canvas & Adjustment Controls) ---
        right_container_frame = tk.Frame(main_paned_window)
        main_paned_window.add(right_container_frame, stretch="always", minsize=300)

        options_area = tk.Frame(right_container_frame)
        options_area.pack(fill=tk.X, pady=(5,0), padx=5)

        self.pitch_adjust_title_label = tk.Label(options_area, text=S.get("ays_pitch_adjust_label_format"))
        self.pitch_adjust_title_label.grid(row=0, column=0, sticky="w", pady=2)

        pitch_adjust_frame = tk.Frame(options_area)
        pitch_adjust_frame.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        self.selected_pitch_slider = tk.Scale(pitch_adjust_frame, from_=-90, to=90, orient=tk.HORIZONTAL,
                                            variable=self.selected_pitch_value_var, resolution=0.1,
                                            length=120, command=self._on_selected_pitch_slider_drag,
                                            state=tk.DISABLED, showvalue=0)
        self.selected_pitch_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.selected_pitch_slider.bind("<ButtonRelease-1>", self._on_selected_pitch_slider_release)
        self.add_tooltip_managed(self.selected_pitch_slider, "ays_pitch_slider_tooltip")

        self.selected_pitch_entry = tk.Entry(pitch_adjust_frame, textvariable=self.selected_pitch_entry_var, width=7, justify='right', state=tk.DISABLED)
        self.selected_pitch_entry.pack(side=tk.LEFT, padx=(5,0))
        self.selected_pitch_entry.bind("<Return>", self._on_selected_pitch_entry_confirm)
        self.selected_pitch_entry.bind("<FocusOut>", self._on_selected_pitch_entry_confirm)
        self.add_tooltip_managed(self.selected_pitch_entry, "ays_pitch_entry_tooltip")

        self.fov_adjust_title_label = tk.Label(options_area, text=S.get("ays_fov_adjust_label_format", min_fov=AYS_MIN_FOV_DEGREES, max_fov=AYS_MAX_FOV_DEGREES))
        self.fov_adjust_title_label.grid(row=1, column=0, sticky="w", pady=2)

        fov_adjust_frame = tk.Frame(options_area)
        fov_adjust_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        self.selected_pitch_fov_slider = tk.Scale(fov_adjust_frame, from_=AYS_MIN_FOV_DEGREES, to=AYS_MAX_FOV_DEGREES, orient=tk.HORIZONTAL,
                                  variable=self.selected_pitch_fov_var, length=120, resolution=0.1,
                                  command=self._on_selected_fov_slider_drag, state=tk.DISABLED, showvalue=0)
        self.selected_pitch_fov_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.selected_pitch_fov_slider.bind("<ButtonRelease-1>", self._on_selected_fov_slider_release)
        self.add_tooltip_managed(self.selected_pitch_fov_slider, "ays_fov_slider_tooltip_format", min_fov=AYS_MIN_FOV_DEGREES, max_fov=AYS_MAX_FOV_DEGREES)

        self.selected_pitch_fov_entry = tk.Entry(fov_adjust_frame, textvariable=self.selected_pitch_fov_entry_var, width=7, justify='right', state=tk.DISABLED)
        self.selected_pitch_fov_entry.pack(side=tk.LEFT, padx=(5,0))
        self.selected_pitch_fov_entry.bind("<Return>", self._on_selected_fov_entry_confirm)
        self.selected_pitch_fov_entry.bind("<FocusOut>", self._on_selected_fov_entry_confirm)
        self.add_tooltip_managed(self.selected_pitch_fov_entry, "ays_fov_entry_tooltip")

        self.yaw_divisions_title_label = tk.Label(options_area, text=S.get("ays_yaw_divisions_label_format", max_divisions=AYS_MAX_YAW_DIVISIONS))
        self.yaw_divisions_title_label.grid(row=2, column=0, sticky="w", pady=2)

        self.yaw_divisions_scale = tk.Scale(options_area, from_=1, to=AYS_MAX_YAW_DIVISIONS, orient=tk.HORIZONTAL,
                                            variable=self.current_yaw_divisions_var, length=150, resolution=1,
                                            command=self._on_fov_or_divisions_changed, state=tk.DISABLED)
        self.yaw_divisions_scale.grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        self.add_tooltip_managed(self.yaw_divisions_scale, "ays_yaw_divisions_scale_tooltip")

        options_area.columnconfigure(1, weight=1) # Ensure adjustment controls expand

        self.yaw_canvas = tk.Canvas(right_container_frame, width=AYS_INITIAL_CANVAS_SIZE, height=AYS_INITIAL_CANVAS_SIZE,
                                    bg=AYS_COLOR_CANVAS_BG, relief=tk.SUNKEN, borderwidth=1)
        self.yaw_canvas.pack(pady=(5,5), padx=5, expand=True, fill=tk.BOTH)
        self.yaw_canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.yaw_canvas.bind("<B1-Motion>", self.on_mouse_motion)
        self.yaw_canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.yaw_canvas.bind("<Button-3>", lambda event: self._handle_canvas_right_click(event)) # For right-click selection

    def on_mouse_press(self, event):
        if not self.controls_enabled:
            return
        # Check if the click is on a label surface; if so, don't start dragging.
        # This allows right-click on labels to pass through to _on_label_right_click.
        item = self.yaw_canvas.find_withtag(tk.CURRENT)
        if item:
            tags = self.yaw_canvas.gettags(item[0])
            if AYS_CLICKABLE_LABEL_TAG in tags:
                return # Let label-specific bindings handle this
        self.is_dragging = True
        self.last_mouse_x, self.last_mouse_y = event.x, event.y

    def on_mouse_motion(self, event):
        if not self.controls_enabled or not self.is_dragging:
            return
        dx = event.x - self.last_mouse_x
        dy = event.y - self.last_mouse_y
        self.global_rotation_y_rad = (self.global_rotation_y_rad + dx / AYS_MOUSE_DRAG_SENSITIVITY) % (2 * math.pi)
        self.global_rotation_x_rad = max(
            -math.pi / 2 * AYS_MAX_VIEW_X_ROTATION_FACTOR,
            min(math.pi / 2 * AYS_MAX_VIEW_X_ROTATION_FACTOR, self.global_rotation_x_rad - dy / AYS_MOUSE_DRAG_SENSITIVITY)
        )
        self.last_mouse_x, self.last_mouse_y = event.x, event.y
        if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
            self.draw_yaw_selector()

    def on_mouse_release(self, event): # pylint: disable=unused-argument
        if not self.controls_enabled:
            return
        self.is_dragging = False

    def _on_canvas_configure(self, event):
        new_width = event.width
        new_height = event.height
        # Basic check, drawing might still occur if one dim is small but other is large.
        if new_width < AYS_MIN_CANVAS_DRAW_SIZE or new_height < AYS_MIN_CANVAS_DRAW_SIZE:
            # Optionally, you could clear the canvas or show a "too small" message here
            pass # Drawing will be handled by draw_yaw_selector which checks size again

        self.canvas_actual_width = new_width
        self.canvas_actual_height = new_height

        if self._configure_timer_id is not None:
            self.after_cancel(self._configure_timer_id)
        self._configure_timer_id = self.after(50, self.draw_yaw_selector) # Debounce redraw

    def _select_initial_pitch(self, initial_load=False):
        if self.pitch_listbox.size() == 0:
            self.current_pitch_key_var.set("")
            self.selected_pitch_slider.config(state=tk.DISABLED)
            self.selected_pitch_entry.config(state=tk.DISABLED, textvariable=tk.StringVar(value="")) # Reset entry
            self.selected_pitch_fov_slider.config(state=tk.DISABLED)
            self.selected_pitch_fov_entry.config(state=tk.DISABLED, textvariable=tk.StringVar(value="")) # Reset entry
            self.yaw_divisions_scale.config(state=tk.DISABLED)
            if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
                self.draw_yaw_selector()
            self._create_or_update_yaw_buttons()
            if self.on_selection_change_callback and not initial_load:
                self.on_selection_change_callback()
            return

        # Try to select "0.0°" if it exists
        found_zero_pitch_idx = -1
        for i in range(self.pitch_listbox.size()):
            if self.pitch_listbox.get(i) == "0.0°":
                found_zero_pitch_idx = i
                break

        target_idx = 0 # Default to first item
        if found_zero_pitch_idx != -1:
            target_idx = found_zero_pitch_idx
        elif self.pitch_listbox.size() > 0: # if 0.0 not found, but list is not empty
             pass # target_idx remains 0
        else: # List is empty, should have been caught by the first check
            return


        if target_idx >= self.pitch_listbox.size() and self.pitch_listbox.size() > 0: # Safety for index
            target_idx = 0

        if self.pitch_listbox.size() > 0 :
            self.pitch_listbox.selection_clear(0, tk.END)
            self.pitch_listbox.selection_set(target_idx)
            self.pitch_listbox.activate(target_idx)
            self.pitch_listbox.see(target_idx)
            self.on_pitch_selected(None, initial_load=initial_load)
        else: # Should not happen if first check is robust
            self.current_pitch_key_var.set("")
            self.selected_pitch_entry_var.set("")
            self.selected_pitch_fov_entry_var.set("")

    def _on_selected_pitch_slider_drag(self, new_val_str):
        if self._entry_update_active or self._internal_update_active:
            return
        try:
            val = float(new_val_str)
            self.selected_pitch_entry_var.set(f"{val:.1f}") # Update entry during drag
            if self._pitch_slider_debounce_timer_id is not None:
                self.after_cancel(self._pitch_slider_debounce_timer_id)
            self._pitch_slider_debounce_timer_id = self.after(
                AYS_DEBOUNCE_DELAY_MS, lambda v=val: self._perform_pitch_update_after_debounce(v)
            )
        except ValueError:
            pass # Ignore if conversion fails during drag

    def _perform_pitch_update_after_debounce(self, value_from_slider):
        self._pitch_slider_debounce_timer_id = None # Clear timer ID
        if self._slider_update_active or self._entry_update_active or self._internal_update_active:
            return
        # This is where the actual update logic for dragging happens (if not on release)
        self._process_pitch_change(value_from_slider)


    def _on_selected_pitch_slider_release(self, event=None): # pylint: disable=unused-argument
        if self._entry_update_active or self._internal_update_active:
            return

        # Cancel any pending debounce timer from dragging
        if self._pitch_slider_debounce_timer_id is not None:
            self.after_cancel(self._pitch_slider_debounce_timer_id)
            self._pitch_slider_debounce_timer_id = None

        self._slider_update_active = True
        try:
            new_val = self.selected_pitch_value_var.get()
            # Snap to whole number if very close
            snapped_val = round(new_val)
            if abs(new_val - snapped_val) < 0.25: # Threshold for snapping
                new_val = float(snapped_val)
                self.selected_pitch_value_var.set(new_val) # Update slider's var

            self.selected_pitch_entry_var.set(f"{new_val:.1f}")
            self._process_pitch_change(new_val)
        except ValueError:
            # Restore entry if something went wrong with var.get()
            self.selected_pitch_entry_var.set(f"{self.selected_pitch_value_var.get():.1f}")
        finally:
            self._slider_update_active = False

    def _on_selected_fov_slider_drag(self, new_val_str):
        if self._fov_entry_update_active or self._internal_update_active:
            return
        try:
            val = float(new_val_str)
            self.selected_pitch_fov_entry_var.set(f"{val:.1f}")
            if self._fov_slider_debounce_timer_id is not None:
                self.after_cancel(self._fov_slider_debounce_timer_id)
            self._fov_slider_debounce_timer_id = self.after(
                AYS_DEBOUNCE_DELAY_MS, lambda v=val: self._perform_fov_update_after_debounce(v)
            )
        except ValueError:
            pass

    def _perform_fov_update_after_debounce(self, value_from_slider):
        self._fov_slider_debounce_timer_id = None
        if self._fov_slider_update_active or self._fov_entry_update_active or self._internal_update_active:
            return
        corrected_value = max(AYS_MIN_FOV_DEGREES, min(value_from_slider, AYS_MAX_FOV_DEGREES))
        self._process_fov_change(corrected_value)

    def _on_selected_fov_slider_release(self, event=None): # pylint: disable=unused-argument
        if self._fov_entry_update_active or self._internal_update_active:
            return
        if self._fov_slider_debounce_timer_id is not None:
            self.after_cancel(self._fov_slider_debounce_timer_id)
            self._fov_slider_debounce_timer_id = None

        self._fov_slider_update_active = True
        try:
            new_val = self.selected_pitch_fov_var.get()
            snapped_val = round(new_val)
            if abs(new_val - snapped_val) < 0.25 and AYS_MIN_FOV_DEGREES <= snapped_val <= AYS_MAX_FOV_DEGREES:
                new_val = float(snapped_val)

            new_val = max(AYS_MIN_FOV_DEGREES, min(new_val, AYS_MAX_FOV_DEGREES)) # Clamp
            self.selected_pitch_fov_var.set(new_val)
            self.selected_pitch_fov_entry_var.set(f"{new_val:.1f}")
            self._process_fov_change(new_val)
        except ValueError:
            self.selected_pitch_fov_entry_var.set(f"{self.selected_pitch_fov_var.get():.1f}")
        finally:
            self._fov_slider_update_active = False

    def _parse_and_set_initial_pitches(self, pitches_str, initial_load=False):
        self._internal_update_active = True
        parsed_valid_pitch_keys = set()
        current_default_fov = AYS_DEFAULT_FOV_INTERNAL # Use the constant

        if pitches_str and pitches_str.strip():
            try:
                temp_keys_list = []
                for p_str_raw in pitches_str.split(','):
                    p_str = p_str_raw.strip()
                    if not p_str: continue # Skip empty elements

                    float_val = float(p_str)
                    if not (-90 <= float_val <= 90): continue # Skip out-of-range

                    key_candidate = f"{float_val:.1f}" # Normalize to one decimal place
                    if key_candidate not in temp_keys_list: # Maintain order of first appearance for unique values
                        temp_keys_list.append(key_candidate)
                parsed_valid_pitch_keys = set(temp_keys_list) # Convert to set for efficient operations later
            except ValueError:
                messagebox.showerror(S.get("error_title"), S.get("ays_error_pitch_parse_invalid_string_format", pitches_str=pitches_str), parent=self)
                self._internal_update_active = False
                return # Exit if parsing fails

        # Manage pitch limit
        all_pitch_keys_to_manage = parsed_valid_pitch_keys
        if len(all_pitch_keys_to_manage) > AYS_MAX_PITCH_ENTRIES:
            # Sort by float value to ensure consistent truncation
            sorted_keys = sorted(list(all_pitch_keys_to_manage), key=float)
            all_pitch_keys_to_manage = set(sorted_keys[:AYS_MAX_PITCH_ENTRIES])
            if initial_load: # Show warning only on initial load, not on programmatic reset
                messagebox.showwarning(S.get("warning_title"), S.get("ays_warning_pitch_limit_exceeded_format", max_entries=AYS_MAX_PITCH_ENTRIES), parent=self)

        # Ensure at least one pitch (0.0) if list becomes empty or was empty
        if not all_pitch_keys_to_manage:
            all_pitch_keys_to_manage.add("0.0")

        # Update pitch_settings based on new keys
        current_settings_keys = set(self.pitch_settings.keys())
        keys_to_add = all_pitch_keys_to_manage - current_settings_keys
        keys_to_remove = current_settings_keys - all_pitch_keys_to_manage

        for k_rem in keys_to_remove:
            if k_rem in self.pitch_settings:
                del self.pitch_settings[k_rem]
            if k_rem in self.yaw_to_fixed_ring_assignment:
                del self.yaw_to_fixed_ring_assignment[k_rem]

        for key_str in keys_to_add:
            pitch_val_float = float(key_str)
            is_zero_pitch = math.isclose(pitch_val_float, 0.0)
            divisions = AYS_DEFAULT_YAW_DIVISIONS_P0_INTERNAL if is_zero_pitch else AYS_DEFAULT_YAW_DIVISIONS_OTHER_INTERNAL
            yaws = [round(i * (360.0 / divisions), 2) for i in range(divisions)] if divisions > 0 else []
            self.pitch_settings[key_str] = {"yaws": yaws, "divisions": divisions, "fov": current_default_fov}

        self._update_pitch_listbox_from_settings(initial_load=initial_load)
        self._internal_update_active = False


    def _update_pitch_listbox_from_settings(self, initial_load=False):
        self._internal_update_active = True
        current_sel_indices = self.pitch_listbox.curselection()
        current_selection_key = ""
        if current_sel_indices and current_sel_indices[0] < self.pitch_listbox.size():
            try:
                current_selection_key = self.pitch_listbox.get(current_sel_indices[0]).replace("°", "")
            except tk.TclError: # Listbox might be empty or index out of bounds
                current_selection_key = ""

        self.pitch_listbox.delete(0, tk.END)
        sorted_pitch_keys_float = []
        if self.pitch_settings:
            try:
                sorted_pitch_keys_float = sorted([float(k) for k in self.pitch_settings.keys()])
            except ValueError: # Should not happen if keys are well-formed
                 messagebox.showerror(S.get("error_title"), "Internal error: Invalid pitch key format in settings.", parent=self)
                 self._internal_update_active = False
                 return


        new_selection_idx = -1
        current_selection_found_in_new_list = False

        for i, p_float in enumerate(sorted_pitch_keys_float):
            display_text = f"{p_float:.1f}°"
            self.pitch_listbox.insert(tk.END, display_text)
            if f"{p_float:.1f}" == current_selection_key:
                new_selection_idx = i
                current_selection_found_in_new_list = True

        if self.pitch_listbox.size() > 0:
            if current_selection_found_in_new_list and new_selection_idx != -1:
                self.pitch_listbox.selection_set(new_selection_idx)
                self.pitch_listbox.activate(new_selection_idx)
                # Call on_pitch_selected, but ensure it knows this is part of an internal update if 'initial_load' is true
                self.on_pitch_selected(None, initial_load=initial_load) # Let on_pitch_selected handle UI updates
            else:
                # If previous selection is gone, or no selection, select initial/default
                self._select_initial_pitch(initial_load=initial_load) # This will also call on_pitch_selected
        else:
            # Listbox is empty, clear/disable relevant controls
            self.current_pitch_key_var.set("")
            self.selected_pitch_value_var.set(0) # Default value
            self.selected_pitch_entry_var.set("")
            self.selected_pitch_slider.config(state=tk.DISABLED)
            self.selected_pitch_entry.config(state=tk.DISABLED)

            self.selected_pitch_fov_var.set(AYS_DEFAULT_FOV_INTERNAL)
            self.selected_pitch_fov_entry_var.set(f"{AYS_DEFAULT_FOV_INTERNAL:.1f}")
            self.selected_pitch_fov_slider.config(state=tk.DISABLED)
            self.selected_pitch_fov_entry.config(state=tk.DISABLED)

            self.current_yaw_divisions_var.set(0) # Or a default if applicable
            self.yaw_divisions_scale.config(state=tk.DISABLED)

            self._create_or_update_yaw_buttons() # Clear buttons
            if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
                self.draw_yaw_selector() # Update canvas display

            if self.on_selection_change_callback and not initial_load:
                self.on_selection_change_callback()

        self._internal_update_active = False

    def _add_pitch_from_combo(self):
        if len(self.pitch_settings) >= AYS_MAX_PITCH_ENTRIES:
            messagebox.showwarning(S.get("warning_title"), S.get("ays_warning_add_pitch_limit_format", max_entries=AYS_MAX_PITCH_ENTRIES), parent=self)
            return

        new_pitch_val_str = self.pitch_to_add_var.get()
        if not new_pitch_val_str: # No selection in combobox
            messagebox.showwarning(S.get("warning_title"), S.get("ays_warning_add_pitch_select_pitch"), parent=self)
            return

        try:
            new_pitch_val_float = float(new_pitch_val_str)
            new_pitch_key = f"{new_pitch_val_float:.1f}" # Normalized key

            if new_pitch_key not in self.pitch_settings:
                is_zero_pitch = math.isclose(new_pitch_val_float, 0.0)
                divisions = AYS_DEFAULT_YAW_DIVISIONS_P0_INTERNAL if is_zero_pitch else AYS_DEFAULT_YAW_DIVISIONS_OTHER_INTERNAL
                yaws = [round(i * (360.0 / divisions), 2) for i in range(divisions)] if divisions > 0 else []
                self.pitch_settings[new_pitch_key] = {"yaws": yaws, "divisions": divisions, "fov": AYS_DEFAULT_FOV_INTERNAL}

                self._update_pitch_listbox_from_settings(initial_load=False) # This will re-sort and update listbox

                # Find and select the newly added item
                newly_added_idx = -1
                for i in range(self.pitch_listbox.size()):
                    if self.pitch_listbox.get(i).replace("°","") == new_pitch_key:
                        newly_added_idx = i
                        break
                if newly_added_idx != -1:
                    self.pitch_listbox.selection_clear(0, tk.END)
                    self.pitch_listbox.selection_set(newly_added_idx)
                    self.pitch_listbox.activate(newly_added_idx)
                    self.on_pitch_selected(None, initial_load=False) # Trigger update for the new selection
            else:
                messagebox.showinfo(S.get("info_title"), S.get("ays_info_pitch_already_exists"), parent=self)
        except ValueError:
            messagebox.showerror(S.get("error_title"), S.get("ays_error_add_pitch_invalid_value"), parent=self)


    def _remove_selected_pitch(self):
        sel_idx_tuple = self.pitch_listbox.curselection()
        if not sel_idx_tuple:
            messagebox.showwarning(S.get("warning_title"), S.get("ays_warning_remove_pitch_select_pitch"), parent=self)
            return

        idx = sel_idx_tuple[0]
        # Ensure index is valid, though curselection should provide a valid one if not empty
        if idx >= self.pitch_listbox.size():
            return # Should not happen

        key_to_remove = self.pitch_listbox.get(idx).replace("°","")

        if len(self.pitch_settings) <= 1:
            messagebox.showinfo(S.get("info_title"), S.get("ays_info_cannot_remove_last_pitch"), parent=self)
            return

        if key_to_remove in self.pitch_settings:
            del self.pitch_settings[key_to_remove]
            if key_to_remove in self.yaw_to_fixed_ring_assignment:
                del self.yaw_to_fixed_ring_assignment[key_to_remove]

            self.pitch_listbox.delete(idx) # Remove from listbox

            if self.pitch_listbox.size() > 0:
                new_sel_idx = max(0, min(idx, self.pitch_listbox.size() - 1)) # Select adjacent or last item
                self.pitch_listbox.selection_set(new_sel_idx)
                self.pitch_listbox.activate(new_sel_idx)
                self.on_pitch_selected(None, initial_load=False) # Update based on new selection
            else:
                # This case should be prevented by len(self.pitch_settings) <= 1 check,
                # but as a fallback, refresh everything.
                self._update_pitch_listbox_from_settings(initial_load=False)
        else:
            # This indicates an internal inconsistency
            messagebox.showerror(S.get("error_title"), S.get("ays_error_remove_pitch_internal_error"), parent=self)


    def _on_selected_pitch_entry_confirm(self, event=None): # pylint: disable=unused-argument
        if self._slider_update_active or self._internal_update_active:
            return
        self._entry_update_active = True
        try:
            new_val_str = self.selected_pitch_entry_var.get()
            new_val_float = float(new_val_str)
            new_val_float = max(-90.0, min(90.0, new_val_float)) # Clamp value

            # Update the slider's variable first
            self.selected_pitch_value_var.set(new_val_float)
            # Then update the entry's variable to the (potentially clamped) value
            self.selected_pitch_entry_var.set(f"{new_val_float:.1f}")

            self._process_pitch_change(new_val_float)
        except ValueError:
            # Restore entry from slider's current value if input was invalid
            current_slider_val = self.selected_pitch_value_var.get()
            self.selected_pitch_entry_var.set(f"{current_slider_val:.1f}")
            messagebox.showerror(S.get("error_title"), S.get("ays_error_pitch_entry_invalid_numeric"), parent=self)
        finally:
            self._entry_update_active = False


    def _process_pitch_change(self, new_val_float):
        if self._internal_update_active: # Prevent processing during internal batch updates
            return

        sel_idx_tuple = self.pitch_listbox.curselection()
        if not sel_idx_tuple: return # No item selected in listbox

        idx = sel_idx_tuple[0]
        if idx >= self.pitch_listbox.size(): return # Should not happen

        old_key = self.pitch_listbox.get(idx).replace("°", "")
        new_key_candidate_unsnapped = f"{new_val_float:.1f}"

        # Snap to whole number if very close (e.g., 0.05 tolerance)
        snapped_new_val_float = round(new_val_float)
        final_new_val_float = new_val_float
        if math.isclose(new_val_float, snapped_new_val_float, abs_tol=0.05):
            final_new_val_float = snapped_new_val_float
        new_key_candidate = f"{final_new_val_float:.1f}"


        if old_key == new_key_candidate: # Value effectively hasn't changed key
            # Ensure internal value and UI are consistent even if key is same
            if old_key in self.pitch_settings:
                self.selected_pitch_value_var.set(final_new_val_float)
                self.selected_pitch_entry_var.set(new_key_candidate) # Display normalized value
            if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
                self.draw_yaw_selector()
            if self.on_selection_change_callback:
                self.on_selection_change_callback()
            return

        # Check for duplication with other existing pitches
        if new_key_candidate in self.pitch_settings and new_key_candidate != old_key:
            messagebox.showwarning(S.get("warning_title"), S.get("ays_warning_pitch_entry_duplicate_format", pitch_value=new_key_candidate), parent=self)
            # Revert UI to old value
            try:
                old_val_float = float(old_key)
                self.selected_pitch_value_var.set(old_val_float)
                self.selected_pitch_entry_var.set(f"{old_val_float:.1f}")
            except ValueError: # Should not happen with well-formed old_key
                pass
            return

        # Proceed with changing the key
        if old_key in self.pitch_settings:
            self._internal_update_active = True # Guard against re-entry during listbox update
            settings_to_move = self.pitch_settings.pop(old_key)
            self.pitch_settings[new_key_candidate] = settings_to_move

            ring_assignment_to_move = None
            if old_key in self.yaw_to_fixed_ring_assignment:
                ring_assignment_to_move = self.yaw_to_fixed_ring_assignment.pop(old_key)
            if ring_assignment_to_move is not None:
                 self.yaw_to_fixed_ring_assignment[new_key_candidate] = ring_assignment_to_move

            self.current_pitch_key_var.set(new_key_candidate) # Update current key var
            # Ensure slider and entry vars are also synced to the final processed value
            self.selected_pitch_value_var.set(final_new_val_float)
            self.selected_pitch_entry_var.set(new_key_candidate)


            # Update listbox: delete old, insert new, re-select
            # This might change sort order, so a full refresh is safer
            # self.pitch_listbox.delete(idx)
            # self.pitch_listbox.insert(idx, f"{new_key_candidate}°")
            # self.pitch_listbox.selection_set(idx)
            # self.pitch_listbox.activate(idx)
            self._update_pitch_listbox_from_settings(initial_load=False) # This will re-select and re-sort

            # Since key changed, precomputation might be needed if it relied on the key string directly,
            # but ring assignments are usually by value. Still, good to ensure.
            self.precompute_ring_assignments_for_pitch(new_key_candidate)

            if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
                self.draw_yaw_selector()
            if self.on_selection_change_callback:
                self.on_selection_change_callback()
            self._internal_update_active = False


    def _on_selected_fov_entry_confirm(self, event=None): # pylint: disable=unused-argument
        if self._fov_slider_update_active or self._internal_update_active:
            return
        self._fov_entry_update_active = True
        try:
            new_val_str = self.selected_pitch_fov_entry_var.get()
            new_val_float = float(new_val_str)
            new_val_float = max(AYS_MIN_FOV_DEGREES, min(new_val_float, AYS_MAX_FOV_DEGREES)) # Clamp

            self.selected_pitch_fov_var.set(new_val_float) # Update slider's var
            self.selected_pitch_fov_entry_var.set(f"{new_val_float:.1f}") # Update entry's var
            self._process_fov_change(new_val_float)
        except ValueError:
            current_slider_fov = self.selected_pitch_fov_var.get()
            self.selected_pitch_fov_entry_var.set(f"{current_slider_fov:.1f}")
            messagebox.showerror(S.get("error_title"), S.get("ays_error_fov_entry_invalid_numeric"), parent=self)
        finally:
            self._fov_entry_update_active = False

    def _process_fov_change(self, new_fov_float):
        if self._internal_update_active: return

        pitch_key = self.current_pitch_key_var.get()
        if not pitch_key or pitch_key not in self.pitch_settings:
            return # No selected pitch or key invalid

        # Snap FOV if very close to a whole number
        snapped_new_fov_float = round(new_fov_float)
        final_new_fov_float = new_fov_float
        if math.isclose(new_fov_float, snapped_new_fov_float, abs_tol=0.05): # Tolerance for snapping
            final_new_fov_float = snapped_new_fov_float

        # Ensure FOV is within defined bounds
        final_new_fov_float = max(AYS_MIN_FOV_DEGREES, min(final_new_fov_float, AYS_MAX_FOV_DEGREES))

        self._internal_update_active = True # Guard block
        self.pitch_settings[pitch_key]["fov"] = final_new_fov_float
        self.selected_pitch_fov_var.set(final_new_fov_float) # Sync slider var
        self.selected_pitch_fov_entry_var.set(f"{final_new_fov_float:.1f}") # Sync entry var

        # FOV change affects visualization and potentially ring assignments if they depend on FOV visuals
        self.precompute_ring_assignments_for_pitch(pitch_key) # Re-run if assignments visually depend on FOV

        if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
            self.draw_yaw_selector()
        if self.on_selection_change_callback:
            self.on_selection_change_callback()
        self._internal_update_active = False

    def reset_current_pitch_fov(self):
        pitch_key = self.current_pitch_key_var.get()
        if not pitch_key or pitch_key not in self.pitch_settings:
            messagebox.showinfo(S.get("info_title"), S.get("ays_info_reset_fov_no_pitch_selected"), parent=self)
            return

        target_fov = AYS_DEFAULT_FOV_INTERNAL
        # Directly update vars and then process, similar to entry confirm
        self.selected_pitch_fov_var.set(target_fov)
        self.selected_pitch_fov_entry_var.set(f"{target_fov:.1f}")
        self._process_fov_change(target_fov)


    def on_pitch_selected(self, event, initial_load=False): # pylint: disable=unused-argument
        sel_idx_tuple = self.pitch_listbox.curselection()

        if not sel_idx_tuple: # No selection
            # Disable controls if nothing is selected
            self.selected_pitch_slider.config(state=tk.DISABLED)
            self.selected_pitch_entry.config(state=tk.DISABLED)
            self.selected_pitch_entry_var.set("") # Clear entry

            self.selected_pitch_fov_slider.config(state=tk.DISABLED)
            self.selected_pitch_fov_entry.config(state=tk.DISABLED)
            self.selected_pitch_fov_entry_var.set("") # Clear entry

            self.yaw_divisions_scale.config(state=tk.DISABLED)

            if self.pitch_listbox.size() == 0: # Listbox is actually empty
                self.current_pitch_key_var.set("")
                self.current_yaw_divisions_var.set(0) # Or some default
                self._create_or_update_yaw_buttons() # Clear/disable yaw buttons

            if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
                self.draw_yaw_selector() # Update canvas

            if self.on_selection_change_callback and not initial_load:
                self.on_selection_change_callback()
            return

        idx = sel_idx_tuple[0]
        if idx >= self.pitch_listbox.size(): return # Should not happen

        key = self.pitch_listbox.get(idx).replace("°","")
        self._internal_update_active = True # Start guarded block
        self.current_pitch_key_var.set(key)

        try:
            val_f = float(key)
            self.selected_pitch_value_var.set(val_f)
            self.selected_pitch_entry_var.set(f"{val_f:.1f}")
            # Enable/disable based on master controls_enabled flag
            current_state = tk.NORMAL if self.controls_enabled else tk.DISABLED
            self.selected_pitch_slider.config(state=current_state)
            self.selected_pitch_entry.config(state=current_state)
        except ValueError: # Should not happen if listbox items are well-formed
            self.selected_pitch_value_var.set(0) # Fallback
            self.selected_pitch_entry_var.set("0.0") # Fallback
            self.selected_pitch_slider.config(state=tk.DISABLED)
            self.selected_pitch_entry.config(state=tk.DISABLED)

        current_div_scale_state = tk.NORMAL if self.controls_enabled else tk.DISABLED
        self.yaw_divisions_scale.config(state=current_div_scale_state)


        if key in self.pitch_settings:
            settings = self.pitch_settings[key]
            self.current_yaw_divisions_var.set(settings["divisions"])
            current_pitch_fov = settings.get("fov", AYS_DEFAULT_FOV_INTERNAL)
            self.selected_pitch_fov_var.set(current_pitch_fov)
            self.selected_pitch_fov_entry_var.set(f"{current_pitch_fov:.1f}")

            current_fov_controls_state = tk.NORMAL if self.controls_enabled else tk.DISABLED
            self.selected_pitch_fov_slider.config(state=current_fov_controls_state)
            self.selected_pitch_fov_entry.config(state=current_fov_controls_state)

            # Ensure ring assignments are computed for this pitch
            if key not in self.yaw_to_fixed_ring_assignment or not self.yaw_to_fixed_ring_assignment.get(key):
                self.precompute_ring_assignments_for_pitch(key)

            self._create_or_update_yaw_buttons() # Update yaw buttons based on new pitch
            if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
                self.draw_yaw_selector() # Redraw canvas for new pitch
        else:
            # Key not in settings, disable controls that depend on it
            self.current_yaw_divisions_var.set(0) # Or default
            self.yaw_divisions_scale.config(state=tk.DISABLED)
            self.selected_pitch_fov_slider.config(state=tk.DISABLED)
            self.selected_pitch_fov_entry.config(state=tk.DISABLED)
            self.selected_pitch_fov_entry_var.set("") # Clear

            self._create_or_update_yaw_buttons() # Clear/disable
            if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
                self.draw_yaw_selector() # Show default/empty state
            # Log error for development/debugging
            print(S.get("ays_error_key_not_found_in_settings_format", key=key)) # Use S.get for msg

        self._internal_update_active = False # End guarded block

        if self.on_selection_change_callback and not initial_load:
            self.on_selection_change_callback()

    def _on_fov_or_divisions_changed(self,event=None): # pylint: disable=unused-argument
        if self._internal_update_active: return
        key = self.current_pitch_key_var.get()
        if not key or key not in self.pitch_settings: return

        new_divs = self.current_yaw_divisions_var.get()
        pitch_specific_settings = self.pitch_settings[key]

        if pitch_specific_settings["divisions"] != new_divs:
            pitch_specific_settings["divisions"] = new_divs
            # Recalculate yaws based on new divisions; this also resets selection
            yaws = [round(i * (360.0 / new_divs), 2) for i in range(new_divs)] if new_divs > 0 else []
            pitch_specific_settings["yaws"] = yaws # Store all potential yaws, selection handled by buttons/canvas

            self.precompute_ring_assignments_for_pitch(key) # Divs changed, so ring assignments need update
            self._create_or_update_yaw_buttons() # Rebuild buttons for new divisions
            # _update_yaw_button_states() will be called by _create_or_update_yaw_buttons

        # FOV change is handled by its own dedicated _process_fov_change method
        # This method is primarily for division changes.

        self._update_yaw_button_states() # Ensure button states reflect current yaws
        if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
            self.draw_yaw_selector()
        if self.on_selection_change_callback:
            self.on_selection_change_callback()

    def _create_or_update_yaw_buttons(self):
        # Clear existing buttons
        for widget in self.yaw_buttons_frame.winfo_children():
            widget.destroy()
        self.yaw_buttons.clear()

        key = self.current_pitch_key_var.get()
        if not key or key not in self.pitch_settings:
            return # No pitch selected or invalid key

        settings = self.pitch_settings.get(key)
        if not settings: return # Should not happen if key is valid

        divisions = settings["divisions"]
        if divisions == 0: return # No divisions, no buttons

        yaw_angle_step = 360.0 / divisions
        max_columns = 3 # Number of buttons per row

        for i in range(divisions):
            yaw_angle = round(i * yaw_angle_step, 2)
            button_text = f"{yaw_angle:.0f}°" # Display as integer
            # Use functools.partial to pass the yaw_angle to the command
            command = functools.partial(self._toggle_yaw_selection_from_button, yaw_angle)

            button_state = tk.NORMAL if self.controls_enabled else tk.DISABLED
            button = tk.Button(self.yaw_buttons_frame, text=button_text, command=command,
                               bg=AYS_BUTTON_NORMAL_BG, width=5, state=button_state)

            row, col = i // max_columns, i % max_columns
            button.grid(row=row, column=col, padx=2, pady=2, sticky="ew")

            # Configure column weights for responsiveness if fewer than max_columns in the last row
            if col < max_columns: # Ensure all used columns have weight
                 self.yaw_buttons_frame.columnconfigure(col, weight=1)

            self.yaw_buttons.append({"button": button, "yaw": yaw_angle})

        self._update_yaw_button_states() # Set initial state of new buttons

    def _toggle_yaw_selection_from_button(self, yaw_angle_to_toggle):
        self._toggle_yaw_selection(yaw_angle_to_toggle) # Common logic

    def _toggle_yaw_selection(self, yaw_angle_to_toggle):
        if self._internal_update_active: return

        key = self.current_pitch_key_var.get()
        if not key or key not in self.pitch_settings: return

        settings = self.pitch_settings[key]
        selected_yaws_for_pitch = settings.get("yaws", []) # Current list of selected yaws
        yaw_float_to_toggle = float(yaw_angle_to_toggle)

        found_and_removed = False
        for i, selected_yaw_raw in enumerate(selected_yaws_for_pitch):
            if math.isclose(float(selected_yaw_raw), yaw_float_to_toggle):
                selected_yaws_for_pitch.pop(i)
                found_and_removed = True
                break

        if not found_and_removed:
            selected_yaws_for_pitch.append(yaw_angle_to_toggle) # Add as the original type (could be float or string)
            selected_yaws_for_pitch.sort(key=float) # Keep sorted

        settings["yaws"] = selected_yaws_for_pitch # Update the stored list
        self._update_yaw_button_states() # Reflect change in button appearance

        if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
            self.draw_yaw_selector() # Redraw canvas to show selection change
        if self.on_selection_change_callback:
            self.on_selection_change_callback()


    def _update_yaw_button_states(self):
        key = self.current_pitch_key_var.get()
        if not key or key not in self.pitch_settings:
            # If no valid pitch, reset all buttons to default appearance
            for btn_info in self.yaw_buttons:
                btn_info["button"].config(relief=tk.RAISED, bg=AYS_BUTTON_NORMAL_BG)
            return

        settings = self.pitch_settings.get(key)
        if not settings: # Should not happen if key is valid
            for btn_info in self.yaw_buttons:
                btn_info["button"].config(relief=tk.RAISED, bg=AYS_BUTTON_NORMAL_BG)
            return

        selected_yaws = settings.get("yaws", [])
        ring_assignments = self.yaw_to_fixed_ring_assignment.get(key, {})

        # If ring assignments are missing but should exist (divisions > 0), try to precompute
        if not ring_assignments and settings.get("divisions", 0) > 0:
            self.precompute_ring_assignments_for_pitch(key)
            ring_assignments = self.yaw_to_fixed_ring_assignment.get(key, {})


        for btn_info in self.yaw_buttons:
            button_widget, button_yaw_angle = btn_info["button"], btn_info["yaw"]
            is_selected = any(math.isclose(float(button_yaw_angle), float(sel_yaw)) for sel_yaw in selected_yaws)

            bg_color = AYS_BUTTON_NORMAL_BG # Default background
            if is_selected:
                ring_data = ring_assignments.get(button_yaw_angle) # Match by the exact yaw value
                bg_color = ring_data["color"] if ring_data and "color" in ring_data else "lightgray" # Fallback color

            button_widget.config(relief=tk.SUNKEN if is_selected else tk.RAISED, bg=bg_color)

    def _apply_rotation(self, point, angle_rad, axis_char):
        x, y, z = point
        cos_angle, sin_angle = math.cos(angle_rad), math.sin(angle_rad)
        if axis_char == 'x':
            return x, y * cos_angle - z * sin_angle, y * sin_angle + z * cos_angle
        if axis_char == 'y':
            return z * sin_angle + x * cos_angle, y, z * cos_angle - x * sin_angle
        # Can add 'z' rotation if needed later
        return point # No change for unknown axis

    def _transform_and_project_point(self, local_point_world_scale, local_pitch_rad, local_yaw_rad):
        # Apply local pitch (around X-axis)
        p_pitched = self._apply_rotation(local_point_world_scale, -local_pitch_rad, 'x')
        # Apply local yaw (around Y-axis, after pitch)
        p_world_rotated = self._apply_rotation(p_pitched, local_yaw_rad, 'y')

        # Apply global view rotations
        p_global_y_rotated = self._apply_rotation(p_world_rotated, self.global_rotation_y_rad, 'y')
        p_global_xy_rotated = self._apply_rotation(p_global_y_rotated, self.global_rotation_x_rad, 'x')

        gx, gy, gz = p_global_xy_rotated
        current_c_center_x = self.canvas_actual_width / 2
        current_c_center_y = self.canvas_actual_height / 2

        # Simple orthographic projection for now (adjust gx, gy by scale if needed)
        # Perspective projection would involve dividing gx, gy by a factor of gz (or distance)
        screen_x = current_c_center_x + gx
        screen_y = current_c_center_y - gy # Canvas Y is inverted from typical 3D Y

        return screen_x, screen_y, gz # Return Z for depth sorting

    def precompute_ring_assignments_for_pitch(self, pitch_key_str):
        if pitch_key_str not in self.pitch_settings:
            return

        settings = self.pitch_settings[pitch_key_str]
        divisions = settings["divisions"]
        current_pitch_assignments = {}

        if divisions <= 0:
            self.yaw_to_fixed_ring_assignment[pitch_key_str] = {}
            return

        angle_step = 360.0 / divisions
        # These are all *potential* yaws based on divisions, not necessarily selected ones
        potential_yaws_for_pitch = [round(i * angle_step, 2) for i in range(divisions)]

        for i, yaw_angle in enumerate(potential_yaws_for_pitch):
            color_idx = i % len(AYS_FOV_RING_COLORS_BASE)
            # Layer index can be used for drawing order if needed, or just for variation
            layer_idx = i % AYS_MAX_YAW_DIVISIONS # Example: cycle through a smaller set of layers
            current_pitch_assignments[yaw_angle] = {
                "color": AYS_FOV_RING_COLORS_BASE[color_idx],
                "layer": layer_idx
            }
        self.yaw_to_fixed_ring_assignment[pitch_key_str] = current_pitch_assignments

    def _hex_to_darker_hex(self, hex_color_str, factor=0.7):
        if not isinstance(hex_color_str, str) or not hex_color_str.startswith('#') or len(hex_color_str) != 7:
            return hex_color_str # Invalid format, return original

        try:
            r = int(hex_color_str[1:3], 16)
            g = int(hex_color_str[3:5], 16)
            b = int(hex_color_str[5:7], 16)

            r = int(r * factor)
            g = int(g * factor)
            b = int(b * factor)

            # Clamp to 0-255
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            return f"#{r:02x}{g:02x}{b:02x}"
        except ValueError:
            return hex_color_str # Conversion error, return original

    def draw_yaw_selector(self): # pylint: disable=too-many-locals, too-many-statements, too-many-branches
        if not hasattr(self, 'yaw_canvas') or not self.yaw_canvas.winfo_exists():
            return
        self.yaw_canvas.delete("all") # Clear previous drawings

        pitch_key_str = self.current_pitch_key_var.get()
        canvas_width = self.canvas_actual_width
        canvas_height = self.canvas_actual_height
        canvas_center_x = canvas_width / 2
        canvas_center_y = canvas_height / 2

        # Determine scaling factor based on the smaller dimension of the canvas
        current_canvas_size_for_scaling = min(canvas_width, canvas_height)

        if current_canvas_size_for_scaling < AYS_MIN_CANVAS_DRAW_SIZE:
            self.yaw_canvas.create_text(canvas_center_x, canvas_center_y, text="Canvas too small", fill="red", font=("Arial", 10))
            return

        if not pitch_key_str or pitch_key_str not in self.pitch_settings:
            # Display placeholder info if no pitch is selected or settings are missing
            padding = 5
            info_text_unselected = S.get("ays_canvas_status_unselected")
            text_id_info_unselected = self.yaw_canvas.create_text(
                padding, padding, text=info_text_unselected, fill=AYS_COLOR_TEXT,
                font=("Arial", 9, "bold"), anchor="nw", justify="left"
            )
            try:
                bbox_info_unselected = self.yaw_canvas.bbox(text_id_info_unselected)
                if bbox_info_unselected:
                    self.yaw_canvas.create_rectangle(
                        bbox_info_unselected[0]-3, bbox_info_unselected[1]-2,
                        bbox_info_unselected[2]+3, bbox_info_unselected[3]+2,
                        fill=AYS_COLOR_CENTER_TEXT_BG, outline="darkgray", width=1.0
                    )
                    self.yaw_canvas.lift(text_id_info_unselected) # Bring text to front
            except tk.TclError: pass # bbox might fail if widget not ready

            self.yaw_canvas.create_text(canvas_center_x, canvas_center_y, text=S.get("ays_canvas_status_select_pitch"), fill=AYS_COLOR_TEXT, font=("Arial", 12))
        else:
            settings = self.pitch_settings.get(pitch_key_str)
            if not settings:
                self.yaw_canvas.create_text(canvas_center_x, canvas_center_y, text=S.get("ays_canvas_status_error"), fill="red", font=("Arial", 12))
                return

            base_pitch_deg = float(pitch_key_str)
            divisions = settings["divisions"]
            selected_yaws_for_pitch = settings.get("yaws", [])
            fov_degrees = settings.get("fov", AYS_DEFAULT_FOV_INTERNAL)

            fov_rad = math.radians(fov_degrees)
            world_radius_scale = current_canvas_size_for_scaling * 0.42 # Scale for the sphere representation

            # Draw reference sphere outline
            self.yaw_canvas.create_oval(
                canvas_center_x - world_radius_scale, canvas_center_y - world_radius_scale,
                canvas_center_x + world_radius_scale, canvas_center_y + world_radius_scale,
                outline="#FF0000", dash=(1,3)
            )

            pyramids_data_list = []
            base_pitch_rad = math.radians(base_pitch_deg)
            angle_step = 360.0 / divisions if divisions > 0 else 0
            apex_local = (0, 0, 0) # Apex of pyramid is at origin in its local space

            # Calculate pyramid base points based on FOV
            # d_plane is distance from apex to the center of the pyramid's base square plane
            # side_on_plane is half-length of the side of this base square
            tan_fov_half = math.tan(fov_rad / 2.0) if fov_rad > 0.001 else 0.0001 # Avoid tan(0) issues
            
            # Denominator for d_plane calculation, ensures base is within unit sphere for visualization
            d_plane_denominator_val = 1 + 2 * tan_fov_half**2
            if d_plane_denominator_val < 1e-9: d_plane_denominator_val = 1e-9 # Avoid division by zero or sqrt of negative
            
            d_plane_denominator = math.sqrt(d_plane_denominator_val)
            d_plane = world_radius_scale / d_plane_denominator if tan_fov_half > 1e-5 and d_plane_denominator > 1e-9 else world_radius_scale
            
            side_on_plane = d_plane * tan_fov_half
            corners_world_space = []
            if fov_rad > 0.001: # Only define corners if FOV is significant
                corners_world_space = [ # (x, y, z) in local pyramid coords before rotation. Z is 'forward'. Y is 'up'.
                    (-side_on_plane, side_on_plane, d_plane),  # Top-left
                    (side_on_plane, side_on_plane, d_plane),   # Top-right
                    (side_on_plane, -side_on_plane, d_plane),  # Bottom-right
                    (-side_on_plane, -side_on_plane, d_plane)  # Bottom-left
                ]

            ring_assignments = self.yaw_to_fixed_ring_assignment.get(pitch_key_str, {})
            if not ring_assignments and divisions > 0: # Precompute if missing
                self.precompute_ring_assignments_for_pitch(pitch_key_str)
                ring_assignments = self.yaw_to_fixed_ring_assignment.get(pitch_key_str, {})

            for i in range(divisions if divisions > 0 else 0):
                yaw_deg = round(i * angle_step, 2)
                is_selected = any(math.isclose(float(yaw_deg), float(sy)) for sy in selected_yaws_for_pitch)
                yaw_rad = math.radians(yaw_deg)

                # Project apex
                apex_proj_x, apex_proj_y, apex_proj_z = self._transform_and_project_point(apex_local, base_pitch_rad, yaw_rad)

                # Project corners
                corners_proj_coords = []
                sum_z_coords_for_avg_depth = 0
                if corners_world_space: # Only if FOV is defined
                    for cws_point in corners_world_space:
                        px, py, pz = self._transform_and_project_point(cws_point, base_pitch_rad, yaw_rad)
                        corners_proj_coords.append((px, py))
                        sum_z_coords_for_avg_depth += pz

                # Depth calculation for sorting
                # If FOV is defined, use average Z of corners. Otherwise, use Z of apex.
                avg_depth = sum_z_coords_for_avg_depth / 4 if corners_world_space and corners_proj_coords else apex_proj_z

                # Label position (usually center of pyramid base, or apex if no FOV)
                label_anchor_local = (0,0,d_plane) if corners_world_space else apex_local
                label_proj_x, label_proj_y, label_proj_z = self._transform_and_project_point(label_anchor_local, base_pitch_rad, yaw_rad)

                pyramids_data_list.append({
                    "yaw_deg": yaw_deg, "is_selected": is_selected,
                    "apex_proj": (apex_proj_x, apex_proj_y),
                    "corners_proj": corners_proj_coords,
                    "depth": avg_depth, # Use average depth of base for sorting
                    "label_proj_pos": (label_proj_x, label_proj_y),
                    "label_depth": label_proj_z # Use label's Z for label visibility
                })

            # Sort pyramids by depth (draw farthest first)
            pyramids_data_list.sort(key=lambda p: p["depth"])

            # Draw pyramids
            for p_data in pyramids_data_list:
                proj_apex_x, proj_apex_y = p_data["apex_proj"]
                proj_corners = p_data["corners_proj"]
                is_front_facing = True # Default for 0-FOV dots

                if len(proj_corners) == 4: # Check if it's a full pyramid (FOV > 0)
                    # Basic backface culling using Shoelace formula (or cross product concept)
                    # For a convex polygon, if vertices are ordered (e.g., CCW), the signed area indicates facing.
                    v0, v1, v2 = proj_corners[0], proj_corners[1], proj_corners[2]
                    area_signed = (v1[0] - v0[0]) * (v2[1] - v0[1]) - (v1[1] - v0[1]) * (v2[0] - v0[0])
                    is_front_facing = area_signed >= 0 # CCW order from definition implies front if area positive

                fill_color, outline_color, line_width = "", "", 1.0
                stipple_fill, stipple_line = "", ""
                ring_color_data = ring_assignments.get(p_data["yaw_deg"], {})
                base_button_color = ring_color_data.get("color", AYS_FOV_RING_COLORS_BASE[0]) # Fallback color

                if p_data["is_selected"]:
                    if is_front_facing:
                        fill_color = base_button_color
                        outline_color = AYS_C_FOV_BOUNDARY_LINE_COLOR
                        line_width = 1.5
                    else: # Selected but back-facing
                        fill_color = base_button_color # Still show base color
                        outline_color = self._hex_to_darker_hex(base_button_color, 0.65)
                        line_width = 1.0
                        stipple_fill = "gray25" # Indicate back-facing
                        stipple_line = "gray50"
                else: # Not selected
                    if is_front_facing:
                        fill_color = AYS_COLOR_SECTOR_DESELECTED_FILL
                        outline_color = AYS_COLOR_SECTOR_DESELECTED_OUTLINE
                    else: # Not selected and back-facing
                        fill_color = AYS_BACKFACE_FILL_COLOR
                        outline_color = AYS_FAR_SIDE_LINE_COLOR # Lighter outline for far side
                        stipple_fill = AYS_BACKFACE_STIPPLE
                        stipple_line = "gray50"
                        line_width = 0.8

                # Adjust appearance for non-selected front-facing based on depth (more stipple if further)
                # This is a visual aid and can be tuned.
                depth_ratio = (p_data["depth"] + world_radius_scale) / (2 * world_radius_scale) if world_radius_scale > 0 else 0.5
                if is_front_facing and not p_data["is_selected"]:
                    if depth_ratio < 0.3: # Very far (close to back)
                         stipple_fill = "gray75" if not stipple_fill else stipple_fill
                         outline_color = "darkgrey" if outline_color == AYS_COLOR_SECTOR_DESELECTED_OUTLINE else outline_color
                         stipple_line = "gray75"
                    elif depth_ratio < 0.6: # Moderately far
                         stipple_fill = "gray50" if not stipple_fill else stipple_fill
                         outline_color = "grey" if outline_color == AYS_COLOR_SECTOR_DESELECTED_OUTLINE else outline_color
                         stipple_line = "gray50"


                if len(proj_corners) == 4: # Draw base polygon
                    self.yaw_canvas.create_polygon(proj_corners, fill=fill_color, outline="", stipple=stipple_fill) # No outline for base, draw edges separately
                    # Draw base edges
                    for i_corner in range(4):
                        p1 = proj_corners[i_corner]
                        p2 = proj_corners[(i_corner + 1) % 4]
                        self.yaw_canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill=outline_color, width=line_width, stipple=stipple_line)

                    # Draw side lines from apex to base corners
                    side_line_effective_color = outline_color
                    side_line_effective_stipple = stipple_line
                    side_line_effective_width = line_width * 0.8 if line_width > 1 else line_width
                    for corner_pt in proj_corners:
                        self.yaw_canvas.create_line(proj_apex_x, proj_apex_y, corner_pt[0], corner_pt[1],
                                                    fill=side_line_effective_color, width=side_line_effective_width, stipple=side_line_effective_stipple)
                elif fov_rad <= 0.01: # Draw a small dot for zero/tiny FOV
                    dot_radius = 1.5
                    dot_effective_fill = outline_color if p_data["is_selected"] else "grey" # Use outline color for selected dot
                    self.yaw_canvas.create_oval(
                        proj_apex_x - dot_radius, proj_apex_y - dot_radius,
                        proj_apex_x + dot_radius, proj_apex_y + dot_radius,
                        fill=dot_effective_fill, outline=""
                    )

            # Draw labels on top, sorted by depth (closest first for labels)
            # Iterate in reverse of depth sort (closest drawn last, so on top)
            for p_data in reversed(pyramids_data_list):
                # Only draw label if it's reasonably on the front side (e.g. label_depth > -sphere_radius * 0.8)
                # This prevents labels from far-back pyramids cluttering the view.
                if p_data["label_depth"] > -world_radius_scale * 0.8 :
                    lx, ly = p_data["label_proj_pos"]
                    yaw_deg_val = p_data['yaw_deg']
                    label_text = f"{yaw_deg_val:.0f}°"
                    # Unique tag for text item and its background
                    label_item_tag = f"label_yaw_{str(yaw_deg_val).replace('.', '_')}"

                    text_item_id = self.yaw_canvas.create_text(
                        lx, ly, text=label_text, fill=AYS_LABEL_TEXT_COLOR,
                        font=("Arial", 7), anchor=tk.CENTER,
                        tags=(label_item_tag, AYS_CLICKABLE_LABEL_TAG) # Add general clickable tag
                    )
                    bg_rect_id = None
                    try:
                        bbox = self.yaw_canvas.bbox(text_item_id)
                        if bbox:
                            bg_rect_id = self.yaw_canvas.create_rectangle(
                                bbox[0]-1, bbox[1]-1, bbox[2]+1, bbox[3]+1, # Small padding
                                fill="white", outline="gray", width=0.5,
                                tags=(f"bg_{label_item_tag}", AYS_CLICKABLE_LABEL_TAG) # Also tag background
                            )
                            self.yaw_canvas.lift(text_item_id) # Ensure text is above its background
                    except tk.TclError: pass # bbox might fail

                    # Bind right-click to toggle selection to both text and its background
                    self.yaw_canvas.tag_bind(text_item_id, "<Button-3>",
                                             lambda e, y=yaw_deg_val: self._on_label_right_click(e, y))
                    if bg_rect_id:
                         self.yaw_canvas.tag_bind(bg_rect_id, "<Button-3>",
                                                  lambda e, y=yaw_deg_val: self._on_label_right_click(e, y))


            # Draw pitched equator line
            equator_front_points, equator_back_points = [], []
            num_equator_segments = 48 # Smoothness of the equator line
            local_pitch_rad_for_equator = math.radians(base_pitch_deg)

            for i in range(num_equator_segments + 1):
                local_yaw_rad_for_equator = (i / num_equator_segments) * 2 * math.pi
                # Points on a unit sphere in world space (before global view rotation)
                ex = math.cos(local_pitch_rad_for_equator) * math.sin(local_yaw_rad_for_equator) * world_radius_scale
                ey = math.sin(local_pitch_rad_for_equator) * world_radius_scale
                ez = math.cos(local_pitch_rad_for_equator) * math.cos(local_yaw_rad_for_equator) * world_radius_scale

                # Transform only by global view rotation (pitch/yaw for equator itself is (0,0))
                cx, cy, gz_depth = self._transform_and_project_point((ex, ey, ez), 0, 0)

                if gz_depth >= 0: # Point is on the front-facing hemisphere
                    equator_front_points.append((cx, cy))
                else: # Point is on the back-facing hemisphere
                    equator_back_points.append((cx, cy))

            if len(equator_back_points) > 1:
                self.yaw_canvas.create_line(equator_back_points, fill=AYS_COLOR_PITCHED_EQUATOR, dash=(1,2), width=1.0, stipple="gray75")
            if len(equator_front_points) > 1:
                self.yaw_canvas.create_line(equator_front_points, fill=AYS_COLOR_PITCHED_EQUATOR, dash=(2,2), width=1.5)


            # Display Info Text (pitch, FOV, divisions, total VPs)
            padding = 5
            total_vps = len(self.get_selected_viewpoints())
            current_pitch_fov = self.get_current_fov_for_selected_pitch()
            fov_display_str = f"{current_pitch_fov:.1f}°" if current_pitch_fov is not None else "N/A"

            info_text_content = S.get("ays_canvas_status_info_format", pitch=base_pitch_deg, fov_display=fov_display_str, divs=divisions, total_vps=total_vps)
            text_id_info = self.yaw_canvas.create_text(
                padding, padding, text=info_text_content, fill=AYS_COLOR_TEXT,
                font=("Arial", 9, "bold"), anchor="nw", justify=tk.LEFT
            )
            try:
                bbox_info = self.yaw_canvas.bbox(text_id_info)
                if bbox_info:
                    self.yaw_canvas.create_rectangle(
                        bbox_info[0]-3, bbox_info[1]-2, bbox_info[2]+3, bbox_info[3]+2,
                        fill=AYS_COLOR_CENTER_TEXT_BG, outline="darkgray", width=1.0
                    )
                    self.yaw_canvas.lift(text_id_info)
            except tk.TclError: pass


        # Display Help Text (bottom right or top right)
        help_text_padding = 5
        help_text_content = S.get("ays_canvas_help_text")
        help_text_x = canvas_width - help_text_padding # Anchor to right
        # help_text_y = canvas_height - help_text_padding # Anchor to bottom
        help_text_y = help_text_padding # Anchor to top
        self.yaw_canvas.create_text(help_text_x, help_text_y, text=help_text_content,
                                    fill=AYS_CANVAS_HELP_TEXT_COLOR, font=("Arial", 8), anchor="ne") # anchor to top-right


    def _on_label_right_click(self, event, yaw_angle): # pylint: disable=unused-argument
        if not self.controls_enabled: return "break" # Absorb event
        if self.is_dragging: return "break" # Don't interfere with drag
        self._toggle_yaw_selection(yaw_angle)
        return "break" # Absorb event to prevent canvas-level right click

    def _handle_canvas_right_click(self, event):
        if not self.controls_enabled: return "break"
        if self.is_dragging: return "break" # Don't process if it was the end of a drag

        # Check if the click was on a label's clickable surface.
        # If so, _on_label_right_click should have handled it.
        # This check prevents double-processing if the label binding didn't fully absorb.
        overlapping_items = self.yaw_canvas.find_overlapping(event.x-1, event.y-1, event.x+1, event.y+1)
        for item_id in reversed(overlapping_items): # Check topmost items first
            tags = self.yaw_canvas.gettags(item_id)
            if AYS_CLICKABLE_LABEL_TAG in tags:
                return "break" # Already handled by label's specific binding

        # If not on a label, proceed with cone selection logic
        self._perform_cone_selection_on_right_click(event)
        return "break" # Absorb the event


    def _perform_cone_selection_on_right_click(self, event):
        pitch_key_str = self.current_pitch_key_var.get()
        if not pitch_key_str or pitch_key_str not in self.pitch_settings:
            return

        settings = self.pitch_settings.get(pitch_key_str)
        if not settings: return

        divisions = settings["divisions"]
        if divisions <= 0: return # No cones to select

        click_x, click_y = event.x, event.y
        target_yaw_to_toggle = -1 # Initialize to invalid
        current_pitch_fov_deg = settings.get("fov", AYS_DEFAULT_FOV_INTERNAL)
        current_pitch_fov_rad = math.radians(current_pitch_fov_deg)
        tan_fov_half = math.tan(current_pitch_fov_rad / 2.0) if current_pitch_fov_rad > 0.001 else 0.0001

        canvas_width = self.canvas_actual_width
        canvas_height = self.canvas_actual_height
        current_canvas_size_for_scaling = min(canvas_width, canvas_height)
        if current_canvas_size_for_scaling < AYS_MIN_CANVAS_DRAW_SIZE:
            current_canvas_size_for_scaling = AYS_MIN_CANVAS_DRAW_SIZE # Use min for calculations if too small

        world_radius = current_canvas_size_for_scaling * 0.42 # Consistent with drawing scale
        d_plane_denominator_val = 1 + 2 * tan_fov_half**2
        if d_plane_denominator_val < 1e-9: d_plane_denominator_val = 1e-9
        d_plane_denominator = math.sqrt(d_plane_denominator_val)
        d_plane = world_radius / d_plane_denominator if tan_fov_half > 1e-5 and d_plane_denominator > 1e-9 else world_radius


        hit_test_data = []
        base_pitch_rad = math.radians(float(pitch_key_str))
        angle_step = 360.0 / divisions

        for i in range(divisions):
            yaw_deg_iter = round(i * angle_step, 2)
            yaw_rad = math.radians(yaw_deg_iter)

            # For hit testing, we can use the projected center of the pyramid's base (or apex for 0 FOV)
            label_anchor_point_world_scaled = (0, 0, d_plane) if current_pitch_fov_rad > 0.001 else (0,0,0)
            proj_x, proj_y, proj_z_depth = self._transform_and_project_point(
                label_anchor_point_world_scaled, base_pitch_rad, yaw_rad
            )
            hit_test_data.append({
                "yaw_deg": yaw_deg_iter,
                "proj_center_x": proj_x, "proj_center_y": proj_y,
                "depth": proj_z_depth
            })

        # Sort by depth (closest to viewer first for hit testing)
        hit_test_data.sort(key=lambda p: p["depth"], reverse=True)

        min_dist_sq_to_hit = float('inf')

        # Define a click radius threshold - make it somewhat proportional to FOV for better feel
        # Base radius when FOV is small, larger when FOV makes cones appear bigger
        base_click_radius = current_canvas_size_for_scaling * 0.08 # 8% of canvas size as base
        # Scale factor based on sin of half FOV (0 for 0 deg, 1 for 180 deg FOV)
        # Max factor of 1, min factor for click radius around 0.5 to avoid too small target
        fov_scale_factor_for_click = math.sin(current_pitch_fov_rad / 2.0) if current_pitch_fov_rad > 0.01 else 0.1
        click_radius_threshold_sq = (base_click_radius * max(0.5, fov_scale_factor_for_click * 2))**2


        for cone_data in hit_test_data:
            # Optimization: if cone is too far back, don't consider it for clicking
            if cone_data["depth"] < -world_radius * 0.3: # Heuristic: 30% behind center
                continue

            dist_sq = (click_x - cone_data["proj_center_x"])**2 + (click_y - cone_data["proj_center_y"])**2

            if dist_sq < click_radius_threshold_sq: # Click is within threshold of this cone's center
                if dist_sq < min_dist_sq_to_hit: # This is the closest hit so far
                    min_dist_sq_to_hit = dist_sq
                    target_yaw_to_toggle = cone_data["yaw_deg"]
                # Since sorted by depth, first one to pass threshold might be good enough
                # if we don't need the absolute closest among overlapping.
                # For now, let's find the absolute closest among those within threshold.

        if target_yaw_to_toggle != -1:
            self._toggle_yaw_selection(target_yaw_to_toggle)


    def get_selected_viewpoints(self):
        viewpoints = []
        for pitch_key_str, settings_val in self.pitch_settings.items():
            try:
                pitch_angle_float = float(pitch_key_str)
                selected_yaws_raw = settings_val.get("yaws", [])
                current_fov_for_pitch = settings_val.get("fov", AYS_DEFAULT_FOV_INTERNAL)

                for yaw_raw in selected_yaws_raw:
                    viewpoints.append({
                        "pitch": pitch_angle_float,
                        "yaw": float(yaw_raw), # Ensure yaw is float
                        "fov": current_fov_for_pitch
                    })
            except ValueError:
                # Log or handle error if pitch_key_str or yaw_raw isn't a valid float
                print(f"Warning: Invalid value encountered for pitch key '{pitch_key_str}' in pitch_settings. Skipping.")
                continue
        return viewpoints

    def set_pitches_externally(self, pitches_string):
        self._parse_and_set_initial_pitches(pitches_string, initial_load=False) # Not an initial load
        self._select_initial_pitch(initial_load=False) # Reselect, not initial

    def enable_controls(self):
        self.controls_enabled = True
        self.pitch_to_add_combo.config(state="readonly") # Readonly is the "enabled" state for this
        self.add_pitch_button.config(state=tk.NORMAL)
        self.remove_pitch_button.config(state=tk.NORMAL)
        self.pitch_listbox.config(state=tk.NORMAL)

        has_pitch_selection = bool(self.pitch_listbox.curselection())
        slider_entry_state = tk.NORMAL if has_pitch_selection else tk.DISABLED

        self.selected_pitch_slider.config(state=slider_entry_state)
        self.selected_pitch_entry.config(state=slider_entry_state)
        self.selected_pitch_fov_slider.config(state=slider_entry_state)
        self.selected_pitch_fov_entry.config(state=slider_entry_state)
        self.yaw_divisions_scale.config(state=slider_entry_state)

        self.pitch_reset_button.config(state=tk.NORMAL)
        self.fov_reset_button.config(state=tk.NORMAL)

        for item in self.yaw_buttons:
            item["button"].config(state=tk.NORMAL)
        # Refresh canvas as controls are enabled
        if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
            self.draw_yaw_selector()


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
        # Refresh canvas as controls are disabled (e.g., to show a "disabled" state)
        if hasattr(self, 'yaw_canvas') and self.yaw_canvas.winfo_exists():
            self.draw_yaw_selector()

    def get_num_active_pitches(self):
        return len(self.pitch_settings)

    def get_current_fov_for_selected_pitch(self):
        pitch_key = self.current_pitch_key_var.get()
        if pitch_key and pitch_key in self.pitch_settings:
            return self.pitch_settings[pitch_key].get("fov", AYS_DEFAULT_FOV_INTERNAL)
        return None

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Advanced Yaw Selector Test")
    root.geometry("750x650")

    # Mock S and initial language for testing standalone
    class MockS:
        def __init__(self):
            self.language = 'ja'
            self.data = {
                'ja': {
                    "ays_add_pitch_button_label": "追加", "ays_remove_pitch_button_label": "削除",
                    "ays_output_pitch_list_label": "出力ピッチ:", "ays_pitch_reset_button_label": "P.リセット",
                    "ays_fov_reset_button_label": "FOVリセット", "ays_yaw_selection_label": "ヨー選択:",
                    "ays_pitch_adjust_label_format": "ピッチ調整:", "ays_fov_adjust_label_format": "FOV調整 ({min_fov}°〜{max_fov}°):",
                    "ays_yaw_divisions_label_format": "水平分割 ({max_divisions}):",
                    "ays_pitch_to_add_combo_tooltip": "追加するピッチ",
                    "ays_add_pitch_button_tooltip_format": "ピッチ追加 (最大{max_entries})",
                    "ays_remove_pitch_button_tooltip": "ピッチ削除",
                    "ays_pitch_listbox_tooltip": "ピッチリスト",
                    "ays_pitch_reset_button_tooltip_format": "ピッチをデフォルト ({default_pitches}) に",
                    "ays_fov_reset_button_tooltip_format": "FOVをデフォルト ({default_fov}) に",
                    "ays_yaw_buttons_tooltip": "ヨーボタン", "ays_pitch_slider_tooltip": "ピッチスライダー",
                    "ays_pitch_entry_tooltip": "ピッチ入力", "ays_fov_slider_tooltip_format": "FOVスライダー ({min_fov}°〜{max_fov}°)",
                    "ays_fov_entry_tooltip": "FOV入力", "ays_yaw_divisions_scale_tooltip": "水平分割スケール",
                    "ays_canvas_status_unselected": "未選択", "ays_canvas_status_error": "エラー",
                    "ays_canvas_status_select_pitch": "ピッチ選択",
                    "ays_canvas_status_info_format": "P:{pitch},FOV:{fov_display},Div:{divs},VP:{total_vps}",
                    "ays_canvas_help_text": "左ドラッグ:回転 右クリック:選択",
                    "error_title": "エラー", "warning_title": "警告", "info_title": "情報",
                    "ays_error_pitch_parse_invalid_string_format": "無効なピッチ文字列: {pitches_str}",
                    "ays_warning_pitch_limit_exceeded_format": "ピッチ上限超過({max_entries})",
                    "ays_warning_add_pitch_limit_format": "追加上限超過({max_entries})",
                    "ays_warning_add_pitch_select_pitch": "ピッチ未選択",
                    "ays_info_pitch_already_exists": "ピッチ重複",
                    "ays_error_add_pitch_invalid_value": "無効なピッチ値",
                    "ays_warning_remove_pitch_select_pitch": "削除ピッチ未選択",
                    "ays_info_cannot_remove_last_pitch": "最終ピッチ削除不可",
                    "ays_error_remove_pitch_internal_error": "削除内部エラー",
                    "ays_error_pitch_entry_invalid_numeric": "ピッチ数値エラー",
                    "ays_warning_pitch_entry_duplicate_format": "ピッチ{pitch_value}重複",
                    "ays_error_fov_entry_invalid_numeric": "FOV数値エラー",
                    "ays_info_reset_fov_no_pitch_selected": "リセットFOVピッチ未選択",
                    "ays_error_key_not_found_in_settings_format": "キー{key}エラー",
                 },
                'en': { # Add English for testing switch
                    "ays_add_pitch_button_label": "Add", "ays_remove_pitch_button_label": "Remove",
                    "ays_output_pitch_list_label": "Output Pitches:", "ays_pitch_reset_button_label": "P.Reset",
                    "ays_fov_reset_button_label": "FOV Reset", "ays_yaw_selection_label": "Yaw Select:",
                    "ays_pitch_adjust_label_format": "Pitch Adjust:", "ays_fov_adjust_label_format": "FOV Adjust ({min_fov}° to {max_fov}°):",
                    "ays_yaw_divisions_label_format": "Divisions ({max_divisions}):",
                    "ays_pitch_to_add_combo_tooltip": "Pitch to add",
                    "ays_add_pitch_button_tooltip_format": "Add pitch (max {max_entries})",
                    "ays_remove_pitch_button_tooltip": "Remove pitch",
                    "ays_pitch_listbox_tooltip": "Pitch list",
                    "ays_pitch_reset_button_tooltip_format": "Reset pitches to default ({default_pitches})",
                    "ays_fov_reset_button_tooltip_format": "Reset FOV to default ({default_fov})",
                    "ays_yaw_buttons_tooltip": "Yaw buttons", "ays_pitch_slider_tooltip": "Pitch slider",
                    "ays_pitch_entry_tooltip": "Pitch entry", "ays_fov_slider_tooltip_format": "FOV slider ({min_fov}° to {max_fov}°)",
                    "ays_fov_entry_tooltip": "FOV entry", "ays_yaw_divisions_scale_tooltip": "Divisions scale",
                    "ays_canvas_status_unselected": "Unselected", "ays_canvas_status_error": "Error",
                    "ays_canvas_status_select_pitch": "Select Pitch",
                    "ays_canvas_status_info_format": "P:{pitch},FOV:{fov_display},Div:{divs},VP:{total_vps}",
                    "ays_canvas_help_text": "L-drag:Rotate R-Clk:Select",
                    "error_title": "Error", "warning_title": "Warning", "info_title": "Info",
                    "ays_error_pitch_parse_invalid_string_format": "Invalid pitch string: {pitches_str}",
                    "ays_warning_pitch_limit_exceeded_format": "Pitch limit exceeded ({max_entries})",
                    "ays_warning_add_pitch_limit_format": "Add limit exceeded ({max_entries})",
                    "ays_warning_add_pitch_select_pitch": "No pitch selected",
                    "ays_info_pitch_already_exists": "Pitch exists",
                    "ays_error_add_pitch_invalid_value": "Invalid pitch value",
                    "ays_warning_remove_pitch_select_pitch": "No pitch selected to remove",
                    "ays_info_cannot_remove_last_pitch": "Cannot remove last pitch",
                    "ays_error_remove_pitch_internal_error": "Remove internal error",
                    "ays_error_pitch_entry_invalid_numeric": "Pitch numeric error",
                    "ays_warning_pitch_entry_duplicate_format": "Pitch {pitch_value} duplicate",
                    "ays_error_fov_entry_invalid_numeric": "FOV numeric error",
                    "ays_info_reset_fov_no_pitch_selected": "No pitch selected for FOV reset",
                    "ays_error_key_not_found_in_settings_format": "Key {key} error",
                }
            }
        def get(self, key, *args, **kwargs):
            return self.data[self.language].get(key, key).format(*args, **kwargs)
        def set_language(self, lang):
            self.language = lang if lang in self.data else 'en'

    S_original = S # Store original S
    S_mock_instance = MockS()
    # Replace global S with mock for standalone test
    globals()['S'] = S_mock_instance


    selector_widget_instance_main_test = [None]

    def switch_lang_test_main():
        new_lang = 'en' if S.language == 'ja' else 'ja'
        S.set_language(new_lang) # S is now S_mock_instance
        if selector_widget_instance_main_test[0]:
            selector_widget_instance_main_test[0].update_ui_texts_for_language_switch()
        root.title(f"AYS Test ({new_lang.upper()}) - {S.get('ays_canvas_status_select_pitch')}") # S is S_mock_instance
        # handle_update_from_selector_main_test() # Update info label if needed

    lang_button_main = tk.Button(root, text="Switch Language (JA/EN)", command=switch_lang_test_main)
    lang_button_main.pack(pady=5)

    info_label_var_main = tk.StringVar(value="Selection info will appear here.")
    def handle_update_from_selector_main_test():
        if selector_widget_instance_main_test[0] is None: return
        vps = selector_widget_instance_main_test[0].get_selected_viewpoints()
        pk_str_main = selector_widget_instance_main_test[0].current_pitch_key_var.get()
        divs_main = selector_widget_instance_main_test[0].current_yaw_divisions_var.get()
        current_pitch_fov_text = "N/A"
        pitch_for_display = 0.0
        if pk_str_main:
            try: pitch_for_display = float(pk_str_main)
            except ValueError: pass
        if pk_str_main and pk_str_main in selector_widget_instance_main_test[0].pitch_settings:
            fov_val = selector_widget_instance_main_test[0].pitch_settings[pk_str_main].get('fov', AYS_DEFAULT_FOV_INTERNAL)
            current_pitch_fov_text = f"{fov_val:.1f}°"

        txt_main = S.get("ays_canvas_status_info_format", pitch=pitch_for_display, fov_display=current_pitch_fov_text, divs=divs_main, total_vps=len(vps)) + "\n"
        if vps:
            txt_main += "Sample Viewpoints:\n"
            for _, vp_item in enumerate(vps[:min(len(vps),3)]):
                txt_main += f" P:{vp_item['pitch']:.1f}°, Y:{vp_item['yaw']:.1f}°, F:{vp_item['fov']:.1f}°\n"
            if len(vps) > 3:
                txt_main += f" ...and {len(vps)-3} more.\n"
        else:
            txt_main += "No Viewpoints selected."
        info_label_var_main.set(txt_main)

    selector_widget_instance_main_test[0] = AdvancedYawSelector(
        root,
        initial_pitches_str=AYS_DEFAULT_PITCHES_STR,
        on_selection_change_callback=handle_update_from_selector_main_test
    )
    selector_widget_instance_main_test[0].pack(expand=True,fill=tk.BOTH,padx=10,pady=10)
    idl_main=tk.Label(root,textvariable=info_label_var_main,justify=tk.LEFT,anchor="nw",relief=tk.SUNKEN,bd=1,height=8,font=("Consolas",9))
    idl_main.pack(fill=tk.X,padx=10,pady=(0,10))

    root.update_idletasks()
    if selector_widget_instance_main_test[0]:
        handle_update_from_selector_main_test() # Initial update

    root.mainloop()

    globals()['S'] = S_original # Restore original S if script continues after mainloop