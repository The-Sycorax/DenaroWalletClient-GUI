import tkinter as tk
from tkinter import scrolledtext
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import re
import _tkinter
import functools
from PIL import Image, ImageTk
import ast
from tkinter import font 

class CustomDialog:
    def __init__(self, parent=None, title=None, prompt=[], callbacks={}, classes={}, **kwargs):
        self.callbacks = callbacks
        self.custom_args = kwargs
        self.classes = classes
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        
        self.styles = ttk.Style()

        # Position the dialog window relative to the parent window
        self.dialog.geometry("+{}+{}".format(parent.winfo_x() + 100, parent.winfo_y() + 100))

        # Make the dialog not resizable
        self.dialog.resizable(False, False)

        

        self.master = ttk.Frame(self.dialog)
        self.master.pack(padx=10, pady=5)
        
        
        self.entry_variables = {}        
        self.checkbox_variables = {}
        self.radio_variables = {}
        self.widget_references = {}

        self.selectable_widgets = []

        row_count = 0

        
       
        
        # Loop through each item in prompt
        for item_index, item in enumerate(prompt):
            
            # Parse grid config
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
            
            if widget_type:
                widget = self.create_widget(widget_type, widget_parent, row, grid_config, pack_config, item, item_index)
                if 'variable_name' in item:
                    self.widget_references[item['variable_name']] = widget
            
            # Handle widget variables
            if 'variables' in item:
                for var in item['variables']:
                    var_config = self.parse_config_string(var.get('set_var', ''))
                    widget.setvar(**var_config)

            # Handle widget command
            command_config = self.parse_config_string(item.get('command', ''))         
            if command_config:
                command = self.resolve_command(**command_config)
                if widget_type != 'label':
                    widget.config(command=command)

            # Handle widget binds
            if 'binds' in item:
                for bind in item['binds']:
                    bind_config = self.parse_config_string(bind.get('bind_config', ''))
                    event, callback = self.resolve_callback(**bind_config)
                    widget.bind(event, callback)

            # Increment the row count for the next element
            if grid_config:
                row_count += 1
        
        self.dialog.bind("<Return>", lambda event: self.submit_entry())
        self.dialog.bind("<Button-1>", self.on_root_click)
        
        self.selectable_widgets.extend(self.identify_selectable_widgets(self.dialog))
        self.result = None
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel)
        self.dialog.transient(parent)  # Make the dialog a transient window of the parent
        self.dialog.grab_set()  # Modal dialog
        self.dialog.wait_window()  # Wait for the dialog to be closed

    def create_widget(self, widget_type, widget_parent, row, grid_config, pack_config, item, item_index):
        widget_map = {
            'separator': ttk.Separator,
            'label': ttk.Label,
            'entry': ttk.Entry,
            'textarea': tk.Text,
            'button': ttk.Button,
            'checkbox': ttk.Checkbutton,
            'scrolledtext': scrolledtext.ScrolledText,
            'radiobutton': ttk.Radiobutton,
            'combobox': ttk.Combobox,
            'spinbox': ttk.Spinbox,
            'progressbar': ttk.Progressbar,
            'scale': ttk.Scale,
            'listbox': tk.Listbox,
            'canvas': tk.Canvas,
            'frame': ttk.Frame,
            'labelframe': ttk.Labelframe,
            'panedwindow': ttk.PanedWindow,
            'notebook': ttk.Notebook,
            'treeview': ttk.Treeview,
            'menubutton': ttk.Menubutton,
            'message': tk.Message,
            'checkbutton': ttk.Checkbutton,
            'radiobutton': ttk.Radiobutton,
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
                    widget = widget_class(widget_map[widget_type], master=widget_parent)
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
                        try:
                            if eval(widget.getvar(name='expand_entry_width')):
                                width = self.update_entry_width(widget)
    
                                #text_length = len(var.get())
                                #entry_width = text_length  # Adding a little extra space
                                widget.config(width=width)
                            else:
                                pass
                        except tk.TclError:
                            pass

                        

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
                    widget = widget_class(widget_map[widget_type], master=widget_parent)
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

            #print(self.get_config(widget))
           
            return widget
    
    def get_config(self, widget):
        options = {}
        for i in widget.keys():
            value = widget.cget(i)
            options[i] = value.string if type(value) is _tkinter.Tcl_Obj else value
        return options, widget.winfo_parent()


    def update_entry_width(self, entry):
        # Hacky as shit but gets the job done
        font_instance = font.Font(font=entry.cget("font"))
        text = entry.get()
        text_width = font_instance.measure(text)
        max_width = 70  # Set a maximum width in pixels
        text_width = min(max_width, text_width)
        return text_width  # Adding a little extra space
        #return adjust_width


    def parse_config_string(self, config_str):
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
        

    def submit_entry(self, event=None):
        checkbox_values = tuple(sv.get() for sv in self.checkbox_variables.values())
        radio_values = tuple(sv.get() for sv in self.radio_variables.values())
        entry_values = tuple(sv.get() for sv in self.entry_variables.values())

        if 'true_on_submit' in self.custom_args:
            self.result = [True], checkbox_values, radio_values
        else:
            self.result = entry_values, checkbox_values, radio_values
        self.dialog.destroy()


    def cancel(self, event=None):
        checkbox_values = tuple(sv.get() for sv in self.checkbox_variables.values())
        radio_values = tuple(sv.get() for sv in self.radio_variables.values())
        self.result = [None], checkbox_values, radio_values
        self.dialog.destroy()
    

    def identify_selectable_widgets(self, container):
        """
        Identifies widgets within the given container that have selection capabilities.
        """
        selectable_widgets = []
        for child in container.winfo_children():
            if isinstance(child, (tk.Entry, tk.Text, scrolledtext.ScrolledText, ttk.Combobox, ttk.Treeview)):
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
                elif isinstance(widget, ttk.Combobox):
                    widget.selection_clear()
                elif isinstance(widget, ttk.Treeview):
                    for item in widget.selection():
                        widget.selection_remove(item)


    def on_root_click(self, event):
        """
        Clears selections if the click occurred outside selectable widgets and not clicking on a Treeview's or ScrolledText's scrollbar.
        """
        widget = event.widget
        clicked_on_associated_scrollbar = False
        
        for sel_widget in self.selectable_widgets:
            # Check for element scrollbars
            if isinstance(sel_widget, (ttk.Treeview, scrolledtext.ScrolledText)):
                widget_container = sel_widget.master
                for child in widget_container.winfo_children():
                    if child == widget and isinstance(child, tk.Scrollbar):
                        clicked_on_associated_scrollbar = True
                        break
                    
        # Clear selections if the click is not on a scrollbar of a Treeview or ScrolledText
        if not clicked_on_associated_scrollbar:
            # Clear selection in all Entry widgets except the one being clicked, if it is an Entry
            for entry_widget in [w for w in self.selectable_widgets if isinstance(w, tk.Entry)]:
                if widget != entry_widget:
                    entry_widget.select_clear()
                    # Ensure widget is a Tkinter widget before setting focus
                    if isinstance(widget, tk.Misc):
                        widget.focus_set()

            # Invoke global deselect
            self.global_deselect(except_widget=widget)
