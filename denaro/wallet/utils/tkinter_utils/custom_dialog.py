import tkinter as tk
import tkinter.ttk as ttk

from tkinter import scrolledtext
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import re
import _tkinter
import functools
from PIL import Image, ImageTk
import ast
from tkinter import font 
from tktooltip import ToolTip
import uuid
import contextlib

class CustomDialog:
    def __init__(self, parent=None, title=None, prompt=[], callbacks={}, classes={}, on_submit=None, on_cancel=None, modal=True, eval_context=None, **kwargs):
        self.callbacks = callbacks
        self.custom_args = kwargs
        self.classes = classes
        
        # Store the context dictionary for later use by resolve_command/resolve_callback.
        self.eval_context = eval_context if eval_context is not None else {}
        
        self.on_submit = on_submit
        self.on_cancel = on_cancel

        # Handle the case where there is no parent window.
        self._is_root_temp = False
        if parent is None:
            # Create a temporary, hidden root window.
            self.root = tk.Tk()
            self.root.withdraw()
            dialog_parent = self.root
            self._is_root_temp = True
        else:
            dialog_parent = parent

        self.dialog = tk.Toplevel(dialog_parent)
        self.dialog.title(title)
        
        # Hide the window right after creation. It exists in memory but is not visible.
        # This prevents the initial flicker at the wrong location.
        self.dialog.withdraw()
        
        self.styles = tb.Style()
        
        # Only set transient if a real parent exists.
        if parent:
            self.dialog.transient(parent)


        # Make the dialog not resizable
        self.dialog.resizable(False, False)


        self.master = tb.Frame(self.dialog)
        self.master.pack(padx=10, pady=5)
        
        self.entry_variables = {}        
        self.checkbox_variables = {}
        self.radio_variables = {}
        self.widget_references = {}
        self.selectable_widgets = []
        self.variable_manager = WidgetVariableManager()

        row_count = 0
        
        for item_index, item in enumerate(prompt):
            widget_id = str(uuid.uuid4())
            
            grid_config = self.parse_config_string(item.get('grid_config', ''))
            if grid_config:
                if 'row' in grid_config:
                    row = int(grid_config['row'])
                    del grid_config['row']
                else:
                    row = row_count 

            pack_config = self.parse_config_string(item.get('pack_config', ''))

            style_config = self.parse_config_string(item.get('style_config', ''))
            if style_config:
                self.styles.configure(**style_config)
            
            style_map_config = self.parse_config_string(item.get('style_map_config', ''))
            if style_map_config:
                self.styles.map(**style_map_config)

            widget_type = item.get('type')
                
            widget_parent = None
            if widget_type != 'self.dialog' and widget_type != 'self.master':
                if item.get('parent'):
                    widget_parent = self.widget_references.get(item.get('parent'), self.master)
                else:                    
                    widget_parent = self.master
          
            if 'variables' in item:
                variables = item.get('variables', {})
                self.variable_manager.update_variables(widget_id, variables)

            if widget_type:
                widget = self.create_widget(widget_type, widget_parent, row if grid_config else 0, grid_config, pack_config, item, item_index, widget_id)

                if 'widget_name' in item:
                    self.widget_references[item['widget_name']] = widget  

            command_config = self.parse_config_string(item.get('command', ''))         
            if command_config:
                command = self.resolve_command(**command_config)
                if command and widget_type != 'label': # Check for command existence
                    widget.config(command=command)

            if 'binds' in item:
                for bind in item['binds']:
                    bind_config = self.parse_config_string(bind.get('bind_config', ''))
                    event, callback = self.resolve_callback(**bind_config)
                    widget.bind(event, callback)
            
            if 'tooltip_config' in item:
                tooltip_config = self.parse_config_string(item.get('tooltip_config', ''))
                ToolTip(widget, **tooltip_config)

            if grid_config:
                row_count += 1
        
            frameless = item.get('frameless', False)
            if frameless:
                self.dialog.overrideredirect(True)

        self.dialog.update_idletasks()
        
        self.center_dialog(parent)
        
        self.dialog.deiconify()

        self.dialog.bind("<Return>", lambda event: self.submit_entry())
        self.dialog.bind("<Button-1>", self.on_root_click)
        
        self.selectable_widgets.extend(self.identify_selectable_widgets(self.dialog))
        self.result = None
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel)
        
        if parent:
            self.dialog.transient(parent)

        if modal:
            try:
                self.dialog.grab_set()
            except tk.TclError:
                pass
            

    def center_dialog(self, parent):
        """Center the dialog. If a parent is provided, center relative to it.
           Otherwise, center on the screen."""
        dialog_width = self.dialog.winfo_reqwidth()
        dialog_height = self.dialog.winfo_reqheight()

        if parent:
            # Center relative to the parent window
            parent_x = parent.winfo_x()
            parent_y = parent.winfo_y()
            parent_width = parent.winfo_width()
            parent_height = parent.winfo_height()
            x = parent_x + (parent_width // 2) - (dialog_width // 2)
            y = parent_y + (parent_height // 2) - (dialog_height // 2)
        else:
            # Center on the screen
            screen_width = self.dialog.winfo_screenwidth()
            screen_height = self.dialog.winfo_screenheight()
            x = (screen_width // 2) - (dialog_width // 2)
            y = (screen_height // 2) - (dialog_height // 2)
        
        self.dialog.geometry(f"+{x}+{y}")

    def validate_center(self, parent):
        """Check if the dialog is centered; if not, re-center."""
        self.dialog.update_idletasks()
        current_x, current_y = self.dialog.winfo_x(), self.dialog.winfo_y()
        dialog_width = self.dialog.winfo_width()
        dialog_height = self.dialog.winfo_height()
        
        if parent:
            expected_x = parent.winfo_x() + parent.winfo_width() // 2 - dialog_width // 2
            expected_y = parent.winfo_y() + parent.winfo_height() // 2 - dialog_height // 2
        else:
            screen_width = self.dialog.winfo_screenwidth()
            screen_height = self.dialog.winfo_screenheight()
            expected_x = (screen_width // 2) - (dialog_width // 2)
            expected_y = (screen_height // 2) - (dialog_height // 2)

        # Allow for a small tolerance (e.g., 1 pixel)
        if abs(current_x - expected_x) > 1 or abs(current_y - expected_y) > 1:
            self.dialog.geometry(f"+{expected_x}+{expected_y}")

    def create_widget(self, widget_type, widget_parent, row, grid_config, pack_config, item, item_index, widget_id):

        should_translate = item.get('translate', True)
                
        # Choose the context: either disable translation or do nothing.
        context = self.dialog.master.translation_engine.no_translate() if self.dialog.master and self.dialog.master.translation_engine and not should_translate else contextlib.nullcontext()

        with context:
            widget_map = {
                'separator': tb.Separator,
                'label': tb.Label,
                'entry': tb.Entry,
                'textarea': tk.Text,
                'button': tb.Button,
                'checkbox': tb.Checkbutton,
                'scrolledtext': scrolledtext.ScrolledText,
                'radiobutton': tb.Radiobutton,
                'combobox': tb.Combobox,
                'spinbox': tb.Spinbox,
                'progressbar': tb.Progressbar,
                'scale': tb.Scale,
                'listbox': tk.Listbox,
                'canvas': tk.Canvas,
                'frame': tb.Frame,
                'labelframe': tb.Labelframe,
                'panedwindow': tb.PanedWindow,
                'notebook': tb.Notebook,
                'treeview': tb.Treeview,
                'menubutton': tb.Menubutton,
                'message': tk.Message,
                'checkbutton': tb.Checkbutton,
                'radiobutton': tb.Radiobutton,
                'self.dialog': self.dialog,
                'self.master': self.master
            }
            
            custom_class_name = item.get('class')
            
            if custom_class_name and custom_class_name in self.classes:
                widget_class = self.classes.get(custom_class_name)
                #widget_class = self.classes[custom_class_name](widget_map[widget_type])
            else:
                widget_class = widget_map.get(widget_type)
                
            #widget_class = widget_map.get(widget_type)
            if widget_class:
                widget_config = self.parse_config_string(item.get('config', ''))
                
    
                # Handle special cases for widgets with additional setup
                if widget_type in ['entry', 'textarea', 'scrolledtext']: 
                    if custom_class_name and custom_class_name in self.classes:
                        class_config = None
                        if "class_config" in item:
                            class_config = self.parse_config_string(item.get('class_config',''))
                        
                        widget = widget_class(widget_map[widget_type], master=widget_parent, config=class_config)
                    else:
                        widget = widget_class(widget_parent)
    
                    if widget_type == 'entry':
                        
                        var = tk.StringVar()
                        self.entry_variables[item_index] = var
                        widget.config(textvariable=var)
                        #widget.focus_set()
                    
                    insert_config = self.parse_config_string(item.get('insert', ''))
    
                    if insert_config:
                        widget.insert(tk.END, **insert_config)
                        
                        if widget_type == 'entry':
                            if self.variable_manager.has_variable(widget_id, 'expand_entry_width'):
                                if self.variable_manager.has_variable(widget_id, 'entry_max_width'):
                                    max_width = self.variable_manager.get_variable(widget_id, 'entry_max_width')
                                else:
                                    max_width = 70
                                text_width = self.update_entry_width(widget, font_string=widget_config.get('font'))    
                                widget.config(width=text_width)
    
                        if widget_type == 'textarea' or widget_type == 'scrolledtext':
                            line_count = int(widget.index('end-1c').split('.')[0])
                            widget.config(height=line_count)
                
                elif widget_type == 'checkbox':
                    var = tk.BooleanVar()
                    self.checkbox_variables[item_index] = var
                    widget = widget_class(widget_parent, variable=var)
                
                elif widget_type == 'radiobutton':
                    var_name = widget_config.pop('variable')
                    if var_name not in self.radio_variables:
                        self.radio_variables[var_name] = tk.StringVar()
                    widget = widget_class(widget_parent, variable=self.radio_variables[var_name])
                
                elif widget_type == 'self.dialog':
                    widget = self.dialog
                
                elif widget_type == 'self.master':
                    widget = self.master
                
                else:
                    if custom_class_name and custom_class_name in self.classes:
                        class_config = None
                        if "class_config" in item:
                                class_config = self.parse_config_string(item.get('class_config',''))
                        widget = widget_class(widget_map[widget_type], master=widget_parent, class_config=class_config)
                    else:
                        widget = widget_class(widget_parent)
                                   
                # Handle layout config
                if widget_type != 'self.dialog' and widget_type != 'self.master':
                    if pack_config:
                        widget.pack(**pack_config)
                        if item.get('hidden'):
                            widget.pack_forget()
                            
                    if grid_config:
                        widget.grid(row=row, **grid_config)                
                        if item.get('hidden'):
                            widget.grid_remove()
                
                widget.config(**widget_config)
    
                return widget
        
    def get_config(self, widget):
        options = {}
        for i in widget.keys():
            value = widget.cget(i)
            options[i] = value.string if type(value) is _tkinter.Tcl_Obj else value
        return options, widget.winfo_parent()


    def update_entry_width(self, entry, font_string=None):
            # Parse the font string
        parts = font_string.split()
        family = " ".join(parts[:-2])  # Font family
        size = int(parts[-2])  # Font size
        style = parts[-1] if len(parts) > 2 else "normal"  # Font style
        weight = "bold" if "bold" in style else "normal"
        slant = "italic" if "italic" in style else "roman"
    
        # Create the font object
        custom_font = font.Font(family=family, size=size, weight=weight, slant=slant)
    
        # Measure the width of the text in the Entry widget
        text = entry.get()
        text_width = custom_font.measure(text)
        #text_width = min(max_width, text_width)
        return int(text_width / size) + 26  # Adding a little extra space
        #return adjust_width
    
    @staticmethod
    def parse_config_string(config_str=None):
        """
        Parses a configuration string into a dictionary. The string is expected to contain key-value pairs
        separated by commas. Values can be quoted strings, numbers, lists, or tuples.

        Args:
            config_str (str): The configuration string to parse.

        Returns:
            dict: A dictionary containing the parsed key-value pairs.
        """
        # Initialize an empty dictionary to store the key-value pairs
        config_dict = {}

        # Define a regular expression to match key-value pairs
        pattern = re.compile(r'(\w+)=((?:\'[^\']*\')|(?:\"[^\"]*\")|\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\}|[^,]+)')

        # Find all matches in the input string
        matches = pattern.findall(config_str)

        # Iterate over each match and process the key-value pairs
        for match in matches:
            key, value = match
            # Process the value based on its format
            if value.startswith("'") and value.endswith("'"):
                config_dict[key] = value.strip("'")
            elif value.startswith('"') and value.endswith('"'):
                config_dict[key] = value.strip('"')
            else:
                # Attempt to parse list-like, tuple-like, or dict-like structures
                try:
                    if value.startswith('[') and value.endswith(']'):
                        config_dict[key] = ast.literal_eval(value)
                    elif value.startswith('(') and value.endswith(')'):
                        config_dict[key] = ast.literal_eval(value)
                    elif value.startswith('{') and value.endswith('}'):
                        config_dict[key] = ast.literal_eval(value)
                    else:
                        # Attempt to convert the value to an integer or float if applicable
                        if '.' in value:
                            config_dict[key] = float(value)
                        else:
                            config_dict[key] = int(value)
                except (ValueError, SyntaxError):
                    # If conversion fails, keep the value as a string
                    config_dict[key] = value

        return config_dict
    
    
    def resolve_callback(self, event=None, callback_str=None, args=None):
        """
        Resolves a callback from a string. The callback can be a lambda or a direct reference to a function.
        The function can be one of self.callbacks or a local function.
    
        Args:
            event (str): The event that triggers the callback.
            callback_str (str): The string representation of the callback.
            args (str): The string representation of arguments for the callback.
    
        Returns:
            tuple: (event, callback function)
        """
        
        def parse_lambda(callback_str):
            """
            Helper function to parse a lambda expression from a string.
            """
            lambda_expr = callback_str.split("lambda e:", 1)[1].strip()
            return eval("lambda e: " + lambda_expr, {'self': self, 'functools': functools, **self.callbacks})
    
        # Handle lambda expressions
        if callback_str.startswith("lambda e:"):
            # Split the lambda expression to check if it refers to self.callbacks
            lambda_expr = callback_str.split("lambda e:", 1)[1].strip()
            func_name = lambda_expr.split('(')[0].strip()
            
            if func_name in self.callbacks:
                func = self.callbacks[func_name]
                if args:
                    evaluated_args = eval(args, {'self': self, 'functools': functools})
                    return event, lambda e: func(e, *evaluated_args)
                return event, lambda e: func(e)
            else:
                func = parse_lambda(callback_str)
                if args:
                    evaluated_args = eval(args, {'self': self, 'functools': functools})
                    return event, lambda e: func(e, *evaluated_args)
                return event, func
    
        # Handle non-lambda callbacks
        elif callback_str in self.callbacks:
            if args:
                evaluated_args = eval(args, {'self': self, 'functools': functools})
                return event, functools.partial(self.callbacks[callback_str], *evaluated_args)
            return event, self.callbacks[callback_str]
    
        # Return a direct function if no valid callback is found
        else:
            try:
                func = eval(callback_str, {'self': self, 'functools': functools})
                if args:
                    evaluated_args = eval(args, {'self': self, 'functools': functools})
                    return event, functools.partial(func, *evaluated_args)
                return event, func
            except (NameError, SyntaxError):
                return event, None

    
    
    def resolve_command(self, command_str=None, args=None, execute_on_load=False, first=False):
        self.first = False
        if command_str == "self.submit_entry":
            return self.submit_entry
        
        elif command_str == "self.cancel":
            return self.cancel
        
        elif command_str in self.callbacks:
            if args:
                # Evaluate the arguments in the context of the current instance
                evaluated_args = eval(args, globals(), locals())
                if eval(execute_on_load):
                    self.callbacks[command_str](*evaluated_args, first)
                    return lambda: None 
                else:
                    return functools.partial(self.callbacks[command_str], *evaluated_args, first)
            return self.callbacks[command_str]
    
        return None
        
    

    def close_dialog(self):
        """Private method to handle closing the dialog and the temporary root if it exists."""
        self.dialog.destroy()
        if self._is_root_temp:
            self.root.destroy()

    def submit_entry(self, event=None):
        checkbox_values = tuple(sv.get() for sv in self.checkbox_variables.values())
        radio_values = tuple(sv.get() for sv in self.radio_variables.values())
        entry_values = tuple(sv.get() for sv in self.entry_variables.values())

        if 'true_on_submit' in self.custom_args:
            self.result = [True], checkbox_values, radio_values
        else:
            self.result = entry_values, checkbox_values, radio_values
        
        if self.on_submit:
            self.on_submit(self.result)

        self.close_dialog()


    def cancel(self, event=None):
        checkbox_values = tuple(sv.get() for sv in self.checkbox_variables.values())
        radio_values = tuple(sv.get() for sv in self.radio_variables.values())
        self.result = [None], checkbox_values, radio_values
        
        if self.on_cancel:
            self.on_cancel(self.result)

        self.close_dialog()
    

    def identify_selectable_widgets(self, container):
        """
        Identifies widgets within the given container that have selection capabilities.
        """
        selectable_widgets = []
        for child in container.winfo_children():
            if isinstance(child, (tk.Entry, tk.Text, scrolledtext.ScrolledText, tb.Combobox, tb.Treeview)):
                selectable_widgets.append(child)
            selectable_widgets.extend(self.identify_selectable_widgets(child))  # Recursive call for nested containers
        return selectable_widgets


    def global_deselect(self, except_widget=None):
        """
        Clears selections in all selectable widgets except the one specified.
        """
        for widget in self.selectable_widgets:
            if widget != except_widget:
                if isinstance(widget, tk.Entry):
                    widget.select_clear()                
                elif isinstance(widget, tk.Text):
                    widget.tag_remove(tk.SEL, "1.0", tk.END)
                    widget.mark_set(tk.INSERT, "1.0")
                elif isinstance(widget, tb.Combobox):
                    widget.selection_clear()
                elif isinstance(widget, tb.Treeview):
                    for item in widget.selection():
                        widget.selection_remove(item)


    def on_root_click(self, event):
        """
        Clears selections if the click occurred outside selectable widgets and not clicking on a Treeview's or ScrolledText's scrollbar.
        """
        widget = event.widget
        clicked_on_scrollbar = False
        
        for sel_widget in self.selectable_widgets:
            # Check for element scrollbars
            if isinstance(sel_widget, (tb.Treeview, scrolledtext.ScrolledText)):
                widget_container = sel_widget.master
                for child in widget_container.winfo_children():
                    if child == widget and isinstance(child, tk.Scrollbar):
                        clicked_on_scrollbar = True
                        break
                    
        # Clear selections if the click is not on a scrollbar of a Treeview or ScrolledText
        if not clicked_on_scrollbar:
            # Clear selection in all Entry widgets except the one being clicked, if it is an Entry
            for entry_widget in [w for w in self.selectable_widgets if isinstance(w, tk.Entry)]:
                if widget != entry_widget:
                    entry_widget.select_clear()
                    # Ensure widget is a Tkinter widget before setting focus
                    if isinstance(widget, tk.Misc):
                        widget.focus_set()

            # Invoke global deselect
            self.global_deselect(except_widget=widget)


class WidgetVariableManager:
    def __init__(self):
        # Store variables in a dictionary, with each widget's unique ID as the key
        self.widget_variables = {}

    def set_variable(self, widget_id, variable_name, value):
        if widget_id not in self.widget_variables:
            self.widget_variables[widget_id] = {}
        self.widget_variables[widget_id][variable_name] = value

    def get_variable(self, widget_id, variable_name):
        return self.widget_variables.get(widget_id, {}).get(variable_name)

    def get_all_variables(self, widget_id):
        return self.widget_variables.get(widget_id, {})

    def update_variables(self, widget_id, variables):
        if widget_id not in self.widget_variables:
            self.widget_variables[widget_id] = {}
        self.widget_variables[widget_id].update(variables)
    
    def has_variable(self, widget_id, variable_name):
        """Check if a specific variable exists for a given widget ID."""
        return widget_id in self.widget_variables and variable_name in self.widget_variables[widget_id]