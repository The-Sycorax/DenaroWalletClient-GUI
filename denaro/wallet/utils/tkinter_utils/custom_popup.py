import tkinter as tk
from tkinter import ttk
import ttkbootstrap as tb
from ttkbootstrap.constants import *

class PopupHandler:
    def __init__(self, master, x, y, on_destroy_callback, timeout=30000, prompt=None, grid_layout_config=None, adjust_callback=None):
        self.master = master

        self.frame = tb.Frame(master, style="gray.TFrame", borderwidth=4, relief="groove")
        self.frame.grid_propagate(False)
        
        self.entry_variables = {}        
        self.checkbox_variables = {}
        
        

        for item_index, item in enumerate(grid_layout_config):
            if 'grid_column_config' in item:
                grid_column_config = self.parse_config_string(item.get('grid_column_config', ''))
                self.frame.grid_columnconfigure(**grid_column_config)
            if 'grid_row_config' in item:
                grid_row_config = self.parse_config_string(item.get('grid_row_config', ''))
                self.frame.grid_rowconfigure(**grid_row_config)
       
        row_count = 0
        # Loop through each item in prompt
        for item_index, item in enumerate(prompt):
            
            # Parse grid config
            grid_config = self.parse_config_string(item.get('grid_config', ''))
            if 'row' in grid_config:
                row = row = int(grid_config['row'])
                del grid_config['row']
            else:
                row = row_count

            if 'separator_config' in item:
                # Parse separator config
                separator_config = self.parse_config_string(item.get('separator_config', ''))
                #Create separator and apply configurations
                separator = ttk.Separator(self.frame, **separator_config)
                separator.grid(row=row, **grid_config)

            if 'label_config' in item:
                # Parse label config
                label_config = self.parse_config_string(item.get('label_config', ''))
                #Create label and apply configurations
                label = ttk.Label(self.frame, **label_config)
                label.grid(row=row, **grid_config)

            if 'entry_config' in item:
                # Parse entry config
                entry_config = self.parse_config_string(item.get('entry_config', ''))
                #Create entry and apply configurations
                entry_text = tk.StringVar()
                self.entry_variables[item_index] = entry_text

                entry = ttk.Entry(self.frame, textvariable=entry_text, **entry_config)
                #entry_text.trace_add("write", lambda name, index, mode, sv=entry_text: self.check_entry(sv))

                #entry.focus_set()
                entry.grid(row=row, **grid_config)
                
                # Handle bindings if present
                #if 'binds' in item:
                #    for bind in item['binds']:
                #        event, callback_str = bind.get('bind_config', '').split(', ')
                #        callback = self.resolve_callback(callback_str)
                #        entry.bind(event, callback)
            
            if 'button_config' in item:
                button_config = self.parse_config_string(item.get('button_config', ''))
                
                #if 'command' in button_config:
                #    # Extract and remove the 'command' string from button_config
                #    command_str = button_config.pop('command')
                #    command = self.resolve_command(command_str)
                #else:
                command = None
                
                button = ttk.Button(self.frame, **button_config, command=command)
                button.grid(row=row, **grid_config)
            
            if 'checkbox_config' in item:
                checkbox_config = self.parse_config_string(item.get('checkbox_config', ''))
                checkbox_var = tk.BooleanVar()
                self.checkbox_variables[item_index] = checkbox_var
                checkbox = ttk.Checkbutton(self.frame, variable=checkbox_var, **checkbox_config)
                checkbox.grid(row=row, **grid_config)

            # Increment the row count for the next element
            row_count += 1
        
        self.width = 240
        self.height = 100
        self.x = x
        self.y = self.master.winfo_height()  # Start animation from off-screen (below the window)
        self.frame.place(x=x, y=y, width=self.width, height=self.height)
        
        self.target_y = y  # Final position
        self.animating = False
        self.animation_after_id = None

        self.on_destroy_callback = on_destroy_callback
        self.adjust_callback = adjust_callback

        self.animate_to_target()
        
        self.destruction_after_id = self.master.after(timeout, lambda: (self.destroy_popup(), self.adjust_callback()))  # 15000 milliseconds = 15 seconds

    def animate_to_target(self):
        if self.animating and self.animation_after_id:
            self.master.after_cancel(self.animation_after_id)
        self.animating = True
        self._animate_step()

    def _animate_step(self):
        if not self.frame.winfo_exists():
            return  # Stop if the frame no longer exists
    
        step = (self.target_y - self.y) / 20
        if abs(step) < 0.5 and step != 0:
            step = 0.5 if step > 0 else -0.5
    
        self.y += step
        self.frame.place(x=self.x, y=int(self.y))
    
        if (step > 0 and self.y >= self.target_y) or (step < 0 and self.y <= self.target_y):
            self.y = self.target_y
            self.frame.place(x=self.x, y=int(self.y))
            self.animating = False
        else:
            self.animation_after_id = self.master.after(10, self._animate_step)

    def destroy_popup(self, event=None):
        if self.animation_after_id:
            self.master.after_cancel(self.animation_after_id)
        if self.destruction_after_id:
            self.master.after_cancel(self.destruction_after_id)  # Cancel the scheduled destruction if it's being destroyed early
        self.frame.destroy()
        self.adjust_callback()
        self.on_destroy_callback(self)

    def update_position(self, x, y):
        self.x = x
        if y < -self.height:
            self.destroy_popup()
        else:
            self.target_y = y
            if not self.animating:
                self.animate_to_target()
    
    def on_frame_click(self, event):
        self.destroy_popup()

    def parse_config_string(self, config_str):
        config_dict = {}
        if config_str:
            config_parts = config_str.split(', ')
            for part in config_parts:
                key, value = part.split('=')
                # Directly assign the value without eval, handling specific cases as needed
                if value.startswith("'") and value.endswith("'"):
                    config_dict[key] = value.strip("'")
                elif value.startswith('"') and value.endswith('"'):
                    config_dict[key] = value.strip('"')
                else:
                    config_dict[key] = value  # Adjust as necessary for non-string values
        return config_dict
    
class CustomPopup:
    def __init__(self, root):
        self.root = root
        self.popups = []
        self.root.bind('<Configure>', self.on_window_resize)

    def add_popup(self, timeout, prompt=None, grid_layout_config=None,):
        start_x = self.root.winfo_width() - 249
        # Calculate the y position for the new popup to appear just above the bottom edge
        start_y = self.root.winfo_height() - 130 - 100 * len(self.popups)
        
        popup = PopupHandler(self.root, start_x, start_y, self.remove_popup, timeout, prompt, grid_layout_config, adjust_callback=self.adjust_popups_position)
        
        popup.frame.bind("<Button-1>", lambda event: (popup.destroy_popup(), self.adjust_popups_position()))
        for widget in popup.frame.children.values():
            widget.bind("<Button-1>", lambda event: (popup.destroy_popup(), self.adjust_popups_position()))

        self.popups.append(popup)

    def remove_popup(self, popup):
        if popup in self.popups:
            self.popups.remove(popup)

    def on_window_resize(self, event):
        self.adjust_popups_position()

    def adjust_popups_position(self):
        start_x = self.root.winfo_width() - 249
        valid_popups = []
        for i, popup in enumerate(reversed(self.popups)):
            new_y = self.root.winfo_height() - 130 - 100 * i
            # Check if the popup would be out of the visible area
            if new_y < -popup.height:
                popup.destroy_popup()
            else:
                popup.update_position(start_x, new_y)
                valid_popups.append(popup)
        # Update the list of popups to exclude any that were destroyed
        self.popups = list(reversed(valid_popups))