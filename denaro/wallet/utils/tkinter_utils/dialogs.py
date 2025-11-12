import tkinter as tk
from tkinter import ttk
import ttkbootstrap as tb
from .custom_dialog import CustomDialog
from PIL import ImageTk, Image
import _tkinter
from tkinter import font

class Dialogs:

    def __init__(self, root):
        self.root = root
        self.dialog_functions = DialogFunctions(self.root, self)
        self.translation_engine = root.translation_engine    

    # =========================================================================
    # == INTERNAL HELPER METHOD
    # =========================================================================

    def create_dialog(self, prompt, title, result_queue=None, on_complete=None, result_processor=None, modal=True, **kwargs):
        """
        A centralized, internal helper to create and run a 'CustomDialog' instance.
        
        It funnels the dialog result into exactly one of three delivery modes:
            1.**Synchronous (blocking):** If a 'result_queue' (e.g., 'queue.Queue')
                is provided, the method returns immediately, but the caller can block
                by calling 'result_queue.get()' to wait for the dialog's result.
            
            2.**Asynchronous (callback):** If an 'on_complete' function is provided,
                the method returns immediately. The 'on_complete' function will be
                called with the final result when the user closes the dialog.
            
            3.**Fire-and-forget:** If neither is provided, the dialog is displayed
                and no action is taken after it closes.
    
        It also decouples raw dialog output from the final desired result via the
        `result_processor` function.
    
        Args:
            prompt (list): The configuration list for the dialog's widgets.
            
            title (str): The title of the dialog window.
            
            result_queue (queue.Queue, optional): A queue to put the final result
                into for synchronous operations.
            
            on_complete (callable, optional): A callback function that takes one
                argument (the final result) for asynchronous operations.
            
            result_processor (callable, optional): A function that takes the raw
                dialog result and transforms it into its final form. If None, a
                default processor is used which extracts the value from the first
                widget. The result is always `None` if the dialog is canceled.
            
            modal (bool): If True, the dialog will be modal.
            
            **kwargs: Additional keyword arguments passed directly to the
                CustomDialog constructor.
        """
        # Define a default result processor if none is given.
        if result_processor is None:
            def default_processor(res):
                # Assumes the standard result format: [[value1], [value2], ...]
                return res[0][0] if res and res[0] else None
            result_processor = default_processor
    
        def process_and_finish(raw_result, was_canceled=False):
            # 1. On cancel, the result is always None. Otherwise, process it.
            final_result = None if was_canceled else result_processor(raw_result)
            
            # 2. Finish the operation based on the mode.
            if result_queue:
                result_queue.put(final_result)
            elif on_complete:
                on_complete(final_result)
            # If neither, do nothing.
        
        # Create callbacks that route the dialog's raw result to our processor.
        on_submit_callback = lambda res: process_and_finish(res, was_canceled=False)
        on_cancel_callback = lambda res: process_and_finish(res, was_canceled=True)
    
        CustomDialog(
            parent=self.root,
            title=title,
            prompt=prompt,
            on_submit=on_submit_callback,
            on_cancel=on_cancel_callback,
            modal=modal,
            **kwargs
        )
    
    def create_dialog_with_checks(self, prompt, title, **kwargs):
        """
        A smart wrapper that prepares and runs a dialog.
            
        Its primary role is to perform a pre-flight check to determine if strings within
        the dialog requires a significant number of new language translations. If so, it
        displays an intermediate "messagebox_wait" dialog via self.translation_engine to
        inform the user of the pending operation, preventing the UI from appearing frozen.
    
        The process is as follows:
          1. It inspects the 'prompt' and 'title' arguments, extracting all user-facing
             strings from various configuration keys.

          2. It then queries the `translation_engine` to count how many of these strings
             are new and require language translation.

          3. If the count exceeds a threshold, it initiates a translation batch, schedules
             the main dialog creation using 'root.after()'. This small delay allows the Tkinter 
             event loop to process and render the "messagebox_wait" dialog before the main 
             (potentially blocking) work begins. Otherwise, it creates the dialog immediately.

        The 'try...finally' block ensures that the translation batch is always
        properly closed, even if an error occurs.
    
        Args:
            prompt (list): The configuration list for the dialog's widgets.
            
            title (str): The title of the dialog window.
            
            **kwargs: Keyword arguments passed transparently to the underlying
                'create_dialog' method.
        """
        texts_to_check = [title]
    
        # Define all the places where text might be found in a prompt item.
        keys_for_single_strings = {
            'config': ['text', 'label', 'message'],
            'insert': ['string'],
            'tooltip_config': ['text']
        }
        keys_for_string_lists = {
            'config': ['values'] # For widgets like Combobox
        }
    
        for item in prompt:
            # Respect the 'translate' flag for the entire item
            if item.get('translate', True):
                
                # --- Check for single strings ---
                for top_level_key, inner_keys in keys_for_single_strings.items():
                    data_str = item.get(top_level_key)
                    if data_str and isinstance(data_str, str):
                        data_dict = CustomDialog.parse_config_string(data_str)
                        for inner_key in inner_keys:
                            if inner_key in data_dict:
                                texts_to_check.append(data_dict[inner_key])
    
                # --- Check for lists of strings ---
                for top_level_key, inner_keys in keys_for_string_lists.items():
                    data_str = item.get(top_level_key)
                    if data_str and isinstance(data_str, str):
                        data_dict = CustomDialog.parse_config_string(data_str)
                        for inner_key in inner_keys:
                            if inner_key in data_dict and isinstance(data_dict[inner_key], (list, tuple)):
                                texts_to_check.extend(data_dict[inner_key])
        
        new_translations_count = self.translation_engine.count_new_translations(texts_to_check)
        show_wait_dialog = new_translations_count >= self.translation_engine.wait_dialog_threshold
    
        def do_blocking_work():
            """Contains the main dialog creation, to be run after any prep work."""
            try:
                # This is the primary operation we are preparing for.
                self.create_dialog(prompt, title, **kwargs)
            finally:
                # Ensure the batch is closed, regardless of success or failure.
                if show_wait_dialog:
                    self.translation_engine.end_translation_batch()
    
        if show_wait_dialog:
            # Signal the translation engine to expect a batch of requests.
            self.translation_engine.begin_translation_batch()
            
            # Force the UI to update now, so the wait dialog can appear.
            self.root.update_idletasks()
            
            # Schedule the dialog creation to run after a short delay. This gives
            # the event loop time to render the wait dialog before we block it.
            self.root.after(50, do_blocking_work)
        else:
            # If no wait is needed, run the work immediately.
            do_blocking_work()
    

    def messagebox(self, title, msg, modal=True, result_queue=None, on_complete=None):
        prompt = [
            {"type": "label", 
             "config":"text='{}', wraplength=500, justify='left'".format(msg), 
             "grid_config":"column=0"},                                    

            {"type": "button",
             "config":"text='Okay'",
             "command":"command_str=self.submit_entry",
             "grid_config":"row=2, column=0, sticky='we', padx=(0, 5), pady=(10, 0)"}]

        # A messagebox just needs to unblock the thread, the return value is not important.
        self.create_dialog_with_checks(prompt=prompt, title=title, result_queue=result_queue, on_complete=on_complete, result_processor=lambda r: True, modal=modal)
    
    def messagebox_wait(self, title, message, modal=True, result_queue=None, on_complete=None, close_event=None):
        """
        A universal dialog that waits for an external close_event (cancel).
        """

        prompt = [
            {"type": "label",
             "widget_name": "label_1",
             "config":"text='{}', wraplength=500, justify='left'".format(message), 
             "grid_config": "row=0, column=0, padx=20, pady=20",
             "command": "command_str='should_close_loop', args='(self, self.callbacks[\"close_event\"])', self.widget_references[\"label_1\"], execute_on_load=True",
             "frameless": True}
            ]
        
        dialog_callbacks = {
            "should_close_loop": self.dialog_functions.should_close_loop,
            "close_event": close_event
        }
        
        self.create_dialog(
            prompt=prompt,
            title=title,
            result_queue=result_queue,
            on_complete=on_complete,
            result_processor=lambda r: True,
            callbacks=dialog_callbacks,
            modal=modal,
        )
        

    def address_info(self, event=None, entry_data=None, entry_type=None, modal=True, result_queue=None, on_complete=None):
        
        if not entry_data:
            widget = event.widget if event else self.root.current_event.widget
            if isinstance(widget, ttk.Treeview):
                # Treeview copy functionality
                row_id = widget.identify_row(self.root.current_event.y)
                col_id = int(widget.identify_column(self.root.current_event.x).replace('#', '')) - 1
                if len(row_id) > 0:            
                    item = widget.item(row_id)
                    address = item['values'][col_id]
                    entry_data, entry_type = self.root.wallet_operations.get_entry_data(address)        
    
        
        if not entry_data:
            # If we still don't have data, we can't proceed.
            # We must handle the queue/callback to prevent deadlocks.
            if result_queue: result_queue.put(None)
            if on_complete: on_complete(None)
            return
        
        entry_type = "Generated Address" if entry_type == 'entries' else "Imported Address"
        
        prompt=[
                {"type":"label", "config":"text='Address Information', font='Helvetica 16 bold'", 
                 "grid_config":"column=0, columnspan=2"},
                                
                {"type":"frame", 
                 "widget_name":"frame_1", 
                 "grid_config":"column=0, sticky='w'"},
                                 
                {"type":"label", 
                 "config":"text='ID:', font='Helvetica 12 bold'",
                 "parent":"frame_1",
                 "pack_config":"side='left'"},
                                    
                {"type":"entry", 
                 "config":"style='addressInfo.TEntry', state='readonly', font='Helvetica 12 bold'",
                 "parent":"frame_1",
                 "insert":"string='{}'".format(entry_data['id']),
                 "style_map_config":"style='addressInfo.TEntry', lightcolor='[(\"focus\", \"white\")]'",
                 "variables": {"expand_entry_width": True},
                 "pack_config":"side='left'"},
                                
                {"type":"frame", 
                 "widget_name":"frame_2", 
                 "grid_config":"column=0, sticky='w'"},
                                 
                {"type":"label", 
                 "config":"text='Type:', font='Helvetica 12 bold'",
                 "parent":"frame_2",
                 "pack_config":"side='left'"},
                                    
                {"type":"entry", 
                 "config":"style='addressInfo.TEntry', state='readonly', font='Helvetica 12 bold'",
                 "parent":"frame_2",
                 "insert":"string='{}'".format(entry_type),
                 "variables": {"expand_entry_width": True},
                 "pack_config":"side='left'"},

                {"type":"separator", 
                 "config":"orient='horizontal'", 
                 "grid_config":"column=0, columnspan=2, sticky='we', pady=(0, 5)"},
                                 
                {"type":"frame", 
                 "widget_name":"frame_3", 
                 "grid_config":"column=0, sticky='w'"},
                                 
                {"type":"label", 
                 "config":"text='Address:', font='Helvetica 12 bold'",
                 "parent":"frame_3",
                 "pack_config":"side='left'"},
                                    
                {"type":"entry", 
                 "config":"style='addressInfo.TEntry', state='readonly', font='Helvetica 12 bold'",
                 "parent":"frame_3",
                 "insert":"string='{}'".format(entry_data['address']),
                 "variables": {"expand_entry_width": True},
                 "pack_config":"side='left'",
                 "translate": False},

                {"type":"frame", 
                 "widget_name":"frame_4", 
                 "grid_config":"column=0, sticky='w'"},
                                 
                {"type":"label", 
                 "config":"text='Public Key:', font='Helvetica 12 bold'",
                 "parent":"frame_4",
                 "pack_config":"side='left'"},
                                    
                {"type":"entry", 
                 "config":"style='addressInfo.TEntry', state='readonly', font='Helvetica 12 bold'",
                 "parent":"frame_4",
                 "insert":"string='{}'".format(entry_data['public_key']),
                 "variables": {"expand_entry_width": True},
                 "pack_config":"side='left'",
                 "translate": False},

                {"type":"frame", 
                 "widget_name":"frame_5", 
                 "grid_config":"column=0, sticky='w'"},
                                 
                {"type":"label", 
                 "config":"text='Private Key:', font='Helvetica 12 bold'",
                 "parent":"frame_5",
                 "pack_config":"side='left'"},

                {"type":"entry",
                 "widget_name":"private_key",
                 "config":"style='addressInfo.TEntry', state='readonly', font='Helvetica 12 bold'", 
                 "parent":"frame_5",
                 "insert":"string='{}'".format(f"{entry_data['private_key']}"),
                 "variables": {"expand_entry_width": True},
                 "pack_config":"side='left'",
                 "translate": False},
                                
                {"type":"frame", 
                 "widget_name":"frame_6", 
                 "grid_config":"row=6, column=1, sticky='w'"},
                                 
                {"type":"button",
                 "widget_name":"private_key_toggle",
                 "class":"KeyToggle",
                 "style_config":"style='toggle1.TButton', background='white', borderwidth=0, highlightthickness=0, padx=0, pady=0",
                 "style_map_config":"style='toggle1.TButton', background=[(\"active\",\"white\")], foreground=[(\"disabled\",\"gray\")]",
                 "config":"style='toggle1.TButton', padding=0",                                  
                 "command": "command_str='set_key_visibility', args='(self.widget_references[\"private_key_toggle\"], self.widget_references[\"private_key\"],)', execute_on_load=True, first=True",
                 "binds":[{"bind_config":"event='<Button-1>', callback_str='toggle_key_visibility', args='(self.widget_references[\"private_key_toggle\"], self.widget_references[\"private_key\"],)'"}],
                 "parent":"frame_6",
                 "pack_config":"side='left', padx=(5, 0), pady=(0, 5)"},

                {"type":"frame", 
                 "widget_name":"frame_7", 
                 "grid_config":"column=0, sticky='w'",
                 "hidden":False if "mnemonic" in entry_data else True},
                                 
                {"type":"label", 
                 "config":"text='Mnemonic:', font='Helvetica 12 bold'",
                 "parent":"frame_7",
                 "pack_config":"side='left'"},

                {"type":"entry",
                 "widget_name":"mnemonic",
                 "config":"style='addressInfo.TEntry', state='readonly', font='Helvetica 12 bold'", 
                 "parent":"frame_7",
                 "insert":"string='{}'".format(f"{entry_data['mnemonic']}" if "mnemonic" in entry_data else ""),
                 "variables": {"expand_entry_width": True},
                 "pack_config":"side='left'",
                 "translate": False},
                                
                {"type":"frame", 
                 "widget_name":"frame_8", 
                 "grid_config":"row=8, column=1, sticky='w'",
                 "hidden":False if "mnemonic" in entry_data else True},
                                 
                {"type":"button",
                 "widget_name":"mnemonic_toggle",
                 "class":"KeyToggle",
                 "style_config":"style='toggle1.TButton', background='white', borderwidth=0, highlightthickness=0, padx=0, pady=0",
                 "style_map_config":"style='toggle1.TButton', background=[(\"active\",\"white\")], foreground=[(\"disabled\",\"gray\")]",
                 "config":"style='toggle1.TButton', padding=0",                                  
                 "command": "command_str='set_key_visibility', args='(self.widget_references[\"mnemonic_toggle\"], self.widget_references[\"mnemonic\"],)', execute_on_load=True, first=True",
                 "binds":[{"bind_config":"event='<Button-1>', callback_str='toggle_key_visibility', args='(self.widget_references[\"mnemonic_toggle\"], self.widget_references[\"mnemonic\"],)'"}],
                 "parent":"frame_8",
                 "pack_config":"side='left', padx=(5, 0), pady=(0, 5)"},
                                    
                {"type":"button", 
                 "config":"text='Close'",
                 "command":"command_str=self.cancel",
                 "grid_config":"column=0, columnspan=2, sticky='ew'"}
            ]
            
        dialog_callbacks = {
            "set_key_visibility": self.dialog_functions.set_key_visibility,
            "toggle_key_visibility": self.dialog_functions.toggle_key_visibility
        }

        self.create_dialog_with_checks(
            prompt=prompt,
            title="Address Information",
            result_queue=result_queue,
            on_complete=on_complete,
            result_processor=lambda r: True, # Return True on close
            callbacks=dialog_callbacks,
            classes={"KeyToggle": KeyToggle},
            modal=modal
        )
            

    def show_recovery_warning_dialog(self, result_queue=None, on_complete=None, modal=True):
        """
        Shows a single, persistent, multi-page security warning dialog with
        complete and correct layout for all widgets.
        """
        page_titles = ["Wallet File", "Wallet Security", "Recovery Phrase", "Disclaimer & Agreement"]

        prompt = [
            {"type": "frame",
             "class": "PageIndicators",
             "widget_name": "indicators",
             "class_config": f"pages={page_titles}",
             "grid_config": "column=0, sticky='ew', pady=(0, 15)"},
            
            {"type": "frame",
             "class": "PageManager",
             "widget_name": "page_manager",
             "grid_config": "column=0, sticky='nsew'"},

            # =========================================================================
            # == PAGE 1: Wallet File
            # =========================================================================
            {"type": "frame", "widget_name": "page_1", "parent": "page_manager"},
            
            {"type": "label", "parent": "page_1",
             "config": "text='1. The Wallet File', font='Helvetica 12 bold'",
             "grid_config": "sticky='w'"},
            
            {"type": "label", "parent": "page_1",
             "config": "text='The file you are about to create is a digital vault containing the cryptographic keys to a Denaro wallet. It is strongly recommended to make multiple, secure, offline backups of this file.', justify='left', anchor='w', wraplength=600",
             "grid_config": "sticky='w', pady=(5,20)"},
            
            {"type": "frame", "widget_name": "actions_1", "parent": "page_1",
             "grid_config": "sticky='ew', pady=(20,0)"},
            
            {"type": "button", "parent": "actions_1",
             "config": "text='Cancel'", "command": "command_str=self.cancel",
             "pack_config":"side='left', fill='x', expand=True, padx=(0,5)"},
            
            {"type": "button", "parent": "actions_1",
             "config": "text='Next'", "command": "command_str='go_to_next_page', args='(self,)', execute_on_load=False, first=False",
             "pack_config":"side='left', fill='x', expand=True, padx=(5,0)"},

            # =========================================================================
            # == PAGE 2: Security
            # =========================================================================
            {"type": "frame", "widget_name": "page_2", "parent": "page_manager"},
            
            {"type": "label", "parent": "page_2",
             "config": "text='2. Wallet Security', font='Helvetica 12 bold'",
             "grid_config": "sticky='w'"},
            
            {"type": "label", "parent": "page_2",
             "config": "text=\"If you choose to encrypt your wallet file, a password is required. Your password is the ONLY way to decrypt that specific file. This software has no password recovery feature.\n\nTwo-Factor Authentication (2FA) can be added as an extra layer of security. If you enable it, accessing your wallet file will require BOTH your password AND a 6-digit code from your authenticator app.\n\nIf you lose either your password or your 2FA device, the wallet client cannot recover the data stored in your wallet file. In this scenario, A 12-word Recovery Phrase is the only way to potentially restore the cryptographic keys nessessary for accessing your funds.\", justify='left', anchor='w', wraplength=600",
             "grid_config": "sticky='w', pady=(5,10)"},
            
            {"type": "label", "parent": "page_2",
             "config": "text='SECURITY WARNING:', font='Helvetica 10 bold', foreground='red'",
             "grid_config": "sticky='w'"},
            
            {"type": "label", "parent": "page_2",
             "config": "text=\"After 10 consecutive failed password attempts, the 'Wallet Annihilation' feature will automatically be triggered. This is a security measure designed to prevent against unauthorized access to a wallet file. It will permanently delete the wallet file and securely erase any of it's data lingering in system memory. This action is irreversible.\", justify='left', anchor='w', wraplength=600",
             "grid_config": "sticky='w', pady=(0,20)"},
            
            {"type": "frame", "widget_name": "actions_2", "parent": "page_2",
             "grid_config": "sticky='ew', pady=(20,0)"},
            
            {"type": "button", "parent": "actions_2",
             "config": "text='Back'", "command": "command_str='go_to_previous_page', args='(self,)', execute_on_load=False, first=False",
             "pack_config":"side='left', fill='x', expand=True, padx=(0,5)"},
            
            {"type": "button", "parent": "actions_2",
             "config": "text='Next'", "command": "command_str='go_to_next_page', args='(self,)', execute_on_load=False, first=False",
             "pack_config":"side='left', fill='x', expand=True, padx=(5,0)"},

            # =========================================================================
            # == PAGE 3: Recovery
            # =========================================================================
            {"type": "frame", "widget_name": "page_3", "parent": "page_manager"},
            
            {"type": "label", "parent": "page_3",
             "config": "text='3. Recovery Phrase', font='Helvetica 12 bold'",
             "grid_config": "sticky='w'"},
            
            {"type": "label", "parent": "page_3",
             "config": "text='A 12-word Recovery Phrase (a.k.a. Mnemonic Phrase or Seed Phrase) is used to generate the cryptographic keys that control access to your funds. This allows you to also recover your funds.\n\nThis wallet client supports two wallet types:', justify='left', anchor='w', wraplength=600",

             "grid_config": "sticky='w', pady=(5,0)"},

            {"type": "frame", "widget_name": "bullet_frame_1", "parent": "page_3", "grid_config": "sticky='w', padx=(10, 0), pady=(5,0)"},
            {"type": "label", "config": "text='•'", "parent": "bullet_frame_1", "pack_config": "side='left', anchor='n'"},
            {"type": "label", "config": "text='Deterministic Wallets use a single Master Recovery Phrase to generate all addresses in the wallet.', justify='left', wraplength=600", "parent": "bullet_frame_1", "pack_config": "side='left'"},
            
            {"type": "frame", "widget_name": "bullet_frame_2", "parent": "page_3", "grid_config": "sticky='w', padx=(10, 0), pady=(5,0)"},
            {"type": "label", "config": "text='•'", "parent": "bullet_frame_2", "pack_config": "side='left', anchor='n'"},
            {"type": "label", "config": "text='Non-Deterministic Wallets provide a unique Recovery Phrase for each individual address generated.', justify='left', wraplength=600", "parent": "bullet_frame_2", "pack_config": "side='left'"},

            {"type": "label", "parent": "page_3",
             "config": "text='It is recommended to write down every phrase that you are given and store it securely offline.', justify='left', anchor='w', wraplength=600",
             "grid_config": "sticky='w', pady=(10,20)"},
            
            {"type": "frame", "widget_name": "actions_3", "parent": "page_3",
             "grid_config": "sticky='ew', pady=(20,0)"},
            
            {"type": "button", "parent": "actions_3",
             "config": "text='Back'", "command": "command_str='go_to_previous_page', args='(self,)', execute_on_load=False, first=False",
             "pack_config":"side='left', fill='x', expand=True, padx=(0,5)"},
            
            {"type": "button", "parent": "actions_3",
             "config": "text='Next'", "command": "command_str='go_to_next_page', args='(self,)', execute_on_load=False, first=False",
             "pack_config":"side='left', fill='x', expand=True, padx=(5,0)"},

            # =========================================================================
            # == PAGE 4: Disclaimer & Agreement
            # =========================================================================
            {"type": "frame", "widget_name": "page_4", "parent": "page_manager"},
            
            {"type": "label", "parent": "page_4",
             "config": "text='Disclaimer and Agreement', font='Helvetica 12 bold'",
             "grid_config": "sticky='w'"},
            
            {"type": "label", "parent": "page_4",
             "config": "text='This software is open source and is provided \"as is\" under the MIT License without guarantees or warranties of any kind. Users are solely responsible for the security and management of their assets.', wraplength=600, justify='left'",
             "grid_config": "sticky='w', pady=(5,0)"},
            
            {"type": "label", "parent": "page_4",
             "config": "text=\"Neither The-Sycorax nor contributors of this project assume liability for any loss of funds incurred through the use of this software. The use of this software implies acceptance of all associated risks, including financial loss.\", wraplength=600, justify='left'",
             "grid_config": "sticky='w', pady=(5,15)"},
            
            {"type": "separator", "parent": "page_4",
             "config": "orient='horizontal'",
             "grid_config": "sticky='we', pady=(5, 5)"},

            {"type": "label", "parent": "page_4", 
             "config": "text=\"I accept that I am solely responsible for securing my wallet file, password, and any recovery phrase, and that the developers assume no liability for any loss of funds incurred through the use of this software.\n\", wraplength=650, justify='left'",
             "grid_config": "column=0, sticky='w', pady=(5,0)"}, 
            
            {"type": "checkbox",
             "widget_name": "agree_checkbox", "parent": "page_4", 
             "config": "text='I have read, understood, and agree to these terms.'",
             "command": "command_str='deferred_toggle', args='(self,)', execute_on_load=False, first=False",
             "style_config": "style='agree.TCheckbutton', wraplength=600",
              "grid_config": "column=0, sticky='w'"},
            
            {"type": "frame", "widget_name": "actions_4", "parent": "page_4",
             "grid_config": "sticky='ew', pady=(20,0)"},
            
            {"type": "button", "parent": "actions_4",
             "config": "text='Back'", "command": "command_str='go_to_previous_page', args='(self,)', execute_on_load=False, first=False",
             "pack_config": "side='left', fill='x', expand=True, padx=(0,5)"},
            
            {"type": "button", "widget_name": "continue_button",
             "config": "text='Continue', state='disabled'",
             "parent": "actions_4", "command": "command_str=self.submit_entry",
             "pack_config": "side='left', fill='x', expand=True, padx=(5,0)"},

            {"type": "label",
             "command": "command_str='initial_page_setup', args='(self,)', execute_on_load=False, first=False, execute_on_load=True"}
        ]

        dialog_callbacks = {
            "go_to_next_page": self.dialog_functions.go_to_next_page,
            "go_to_previous_page": self.dialog_functions.go_to_previous_page,
            "deferred_toggle": self.dialog_functions.deferred_toggle_bridge,
            "initial_page_setup": self.dialog_functions.initial_page_setup
        }

        self.create_dialog_with_checks(prompt=prompt, title="Security Warnings & Terms",
            result_queue=result_queue, on_complete=on_complete, modal=modal,
            result_processor=lambda r: True if r else None,
            classes={"PageIndicators": PageIndicators, "PageManager": PageManager},
            callbacks=dialog_callbacks)
        
    def create_wallet_dialog(self, result_queue=None, on_complete=None, modal=True):
        """
        Orchestrates the full, multi-step workflow for creating a wallet,
        now with correctly sequenced error message boxes.
        """
        def final_handler(result):
            """The single point of exit for the entire workflow."""
            if result_queue: result_queue.put(result)
            if on_complete: on_complete(result)

        def on_warning_agreed(user_agreed):
            """Called after the warning dialog."""
            if user_agreed:
                self.root.stored_data.warning_agreed = True
                self.configure_wallet_step(on_complete=on_wallet_name_provided, modal=modal)
            else:
                final_handler(None)

        def on_wallet_name_provided(result):
            """Called after the user provides a wallet name and options."""
            if result is None:
                final_handler(None)
                return
            
            entry_values, checkbox_values, _ = result
            filename = entry_values[0] if entry_values else ""
            
            if not filename:
                # Define what to do AFTER the error messagebox closes.
                def on_error_closed(_):
                    # Restart the name entry step.
                    self.configure_wallet_step(on_complete=on_wallet_name_provided, modal=modal)

                # Show the messagebox in ASYNC/CALLBACK mode.
                self.messagebox(
                    title='Error',
                    msg='No wallet name provided.',
                    on_complete=on_error_closed
                )
                return # Stop here and wait for the callback.

            def start_thread_with_password(password):
                is_encrypted = checkbox_values[2]
                if is_encrypted and not password:
                    final_handler(None)
                    return
                enable_2fa = is_encrypted and checkbox_values[1]
                self.root.wallet_thread_manager.start_thread("create_wallet", self.root.wallet_operations.create_wallet, 
                    args=(filename, password, checkbox_values[0], is_encrypted, enable_2fa))
                final_handler(True)

            if checkbox_values[2]:
                self.password_dialog_with_confirmation(
                    title='Create Wallet',
                    msg='Please choose a password for wallet encryption.',
                    on_complete=start_thread_with_password,
                    modal=modal
                )
            else:
                start_thread_with_password(None)

        
        # 1. Check pre-conditions.
        if self.root.stored_data.operation_mode == 'send':
            # Define what to do AFTER this error messagebox closes.
            def on_error_closed(_):
                # End the workflow.
                final_handler(None)

            # Show the messagebox in ASYNC/CALLBACK mode.
            self.messagebox(
                title="Error",
                msg="Cannot create a new wallet while a transaction is taking place.",
                on_complete=on_error_closed
            )
            # Stop here and wait for the callback.
            return
            
        self.root.gui_utils.close_wallet()

        if not self.root.stored_data.warning_agreed:
            self.show_recovery_warning_dialog(on_complete=on_warning_agreed, modal=modal)
        else:
            on_warning_agreed(True)

    
    def configure_wallet_step(self, on_complete, modal=True):
        """A private helper for the second step of the create wallet workflow."""
        prompt = [     
                    {"type":"label", "config":"text='Create Wallet', font='Helvetica 14 bold'", 
                     "grid_config":"column=0"},

                    {'type': 'separator', 
                     "config":"orient='horizontal'", 
                     "grid_config":"column=0, columnspan=2, sticky='we'"},
                                 
                    {"type":"label", 
                     "config":"text='Wallet Name: ', font='Helvetica 10 bold'",
                     "grid_config":"column=0, sticky='w', pady=(20, 0)"},
                                    
                    {"type":"entry", 
                     "config":"state='normal'",
                     #"variables":[{"set_var":"name='disable_context_menu_items', value=True"}],
                     "grid_config":"column=0, sticky='we', padx=(25, 0), pady=(5, 0)"},

                    {"type":"label", 
                     "config":"text='Wallet Options:', font='Helvetica 10 bold'", 
                     "grid_config":"column=0, sticky='w', pady=(20, 0)"},

                    {"type":"checkbox", 
                     "widget_name":"deterministic_checkbox", 
                     "config":"text='Deterministic Address Generation'",
                     "grid_config":"column=0, sticky='w', padx=(25, 0), pady=(5, 0)"},                                 

                    {"type":"checkbox", 
                     "widget_name":"2fa_checkbox", 
                     "config":"text='Two-Factor Authentication', state='disabled'",
                     "grid_config":"row=7, column=0, sticky='w', padx=(25, 0), pady=(10, 0)"},

                    {"type":"checkbox", 
                     "widget_name":"encrypt_checkbox", 
                     "config":"text='Encryption'",
                     "command": "command_str='enable_2fa_checkbox', args='(self.widget_references[\"encrypt_checkbox\"], self.widget_references[\"2fa_checkbox\"],)', execute_on_load=False",
                     "grid_config":"row=6, column=0, sticky='w', padx=(25, 0), pady=(10, 0)"},        

                    {"type":"frame", 
                     "widget_name":"frame_1", 
                     "grid_config":"column=0, sticky='we', pady=(20, 0)"},                              

                    {'type': 'button', 
                     "config":"text='Cancel', width=20", 
                     "command":"command_str=self.cancel", 
                     "parent":"frame_1",
                     "pack_config":"side='left', expand=True, fill=x, padx=(0, 5)"},

                    {'type': 'button', 
                     "config":"text='Continue', width=20", 
                     "command":"command_str=self.submit_entry", 
                     "parent":"frame_1",
                     "pack_config":"side='right', expand=True, fill=x, padx=(5, 0)"},
                ]

        self.create_dialog_with_checks(prompt=prompt, title="Create New Wallet", on_complete=on_complete,
            result_processor=lambda r: r, # Return raw result tuple
            modal=modal,
            callbacks={"enable_2fa_checkbox": self.dialog_functions.enable_2fa_checkbox})
 

    def password_dialog_with_confirmation(self, title, msg, modal=True, result_queue=None, on_complete=None):
        """
        A non-blocking workflow to get a confirmed password.
        Instead of returning a value, it calls `on_complete(password)` when done.
        `password` will be None if the user cancels.
        """
        def get_passwords_step():
            prompt = [
                        {"type":"label", 
                        "config":"text={}".format(msg), 
                        "grid_config":"column=0, sticky='w', pady=(20, 0)"}, 

                        {"type":"label", 
                        "config":"text='Enter Password:', font='Helvetica 10 bold'", 
                        "grid_config":"column=0, sticky='w', pady=(20, 0)"}, 
                                
                        {"type":"frame", 
                         "widget_name":"frame_1", 
                         "grid_config":"column=0, columnspan=2, sticky='nswe', pady=(0, 0)"}, 
                                                 
                        {"type":"entry", 
                         "widget_name":"password_1_entry", 
                         "config":"font='Helvetica 12 bold', show='*'", 
                         "binds":[{"bind_config":"event='<Tab>', callback_str='focus_next_widget'"}, {"bind_config":"event='<space>', callback_str='focus_next_widget'"}], 
                         "parent":"frame_1", 
                         "pack_config":"side='left', expand=True, fill='x'"}, 

                        {"type":"button", 
                         "widget_name":"password_1_entry_toggle", 
                         "class":"KeyToggle", 
                         "style_config":"style='toggle1.TButton', background='white', borderwidth=0, highlightthickness=0, padx=0, pady=0", 
                         "style_map_config":"style='toggle1.TButton', background=[(\"active\",\"white\")], foreground=[(\"disabled\",\"gray\")]", 
                         "config":"style='toggle1.TButton', padding=0", 
                         "command": "command_str='set_entry_visibility', args='(self.widget_references[\"password_1_entry_toggle\"], self.widget_references[\"password_1_entry\"],)', execute_on_load=True, first=True", 
                         "binds":[{"bind_config":"event='<Button-1>', callback_str='toggle_entry_visibility', args='(self.widget_references[\"password_1_entry_toggle\"], self.widget_references[\"password_1_entry\"],)'"}], 
                         "parent":"frame_1", 
                         "pack_config":"side='left', padx=(5, 0), pady=(0, 5)"}, 
                                
                        {"type":"label", 
                        "config":"text='Confirm Password:', font='Helvetica 10 bold'", 
                        "grid_config":"column=0, sticky='w', pady=(20, 0)"},
                                
                        {"type":"frame", 
                         "widget_name":"frame_2", 
                         "grid_config":"column=0, columnspan=2, sticky='nswe', pady=(0, 0)"}, 
                                                 
                        {"type":"entry", 
                         "widget_name":"password_2_entry", 
                         "config":"font='Helvetica 12 bold', show='*'", 
                         "binds":[{"bind_config":"event='<Tab>', callback_str='focus_next_widget'"}, {"bind_config":"event='<space>', callback_str='focus_next_widget'"}], 
                         "parent":"frame_2", 
                         "pack_config":"side='left', expand=True, fill='x'"}, 

                        {"type":"button", 
                         "widget_name":"password_2_entry_toggle", 
                         "class":"KeyToggle", 
                         "style_config":"style='toggle1.TButton', background='white', borderwidth=0, highlightthickness=0, padx=0, pady=0", 
                         "style_map_config":"style='toggle1.TButton', background=[(\"active\",\"white\")], foreground=[(\"disabled\",\"gray\")]", 
                         "config":"style='toggle1.TButton', padding=0", 
                         "command": "command_str='set_entry_visibility', args='(self.widget_references[\"password_2_entry_toggle\"], self.widget_references[\"password_2_entry\"],)', execute_on_load=True, first=True", 
                         "binds":[{"bind_config":"event='<Button-1>', callback_str='toggle_entry_visibility', args='(self.widget_references[\"password_2_entry_toggle\"], self.widget_references[\"password_2_entry\"],)'"}], 
                         "parent":"frame_2", 
                         "pack_config":"side='left', padx=(5, 0), pady=(0, 5)"},
    
                        {"type":"frame", 
                         "widget_name":"frame_3", 
                         "grid_config":"column=0, sticky='we', pady=(20, 0)"},                              
    
                        {'type': 'button', 
                         "config":"text='Submit', width=20", 
                         "command":"command_str=self.submit_entry", 
                         "parent":"frame_3",
                         "pack_config":"side='left', expand=True, fill=x, padx=(0, 5)"},
    
                        {'type': 'button', 
                         "config":"text='Cancel', width=20", 
                         "command":"command_str=self.cancel", 
                         "parent":"frame_3",
                         "pack_config":"side='right', expand=True, fill=x, padx=(5, 0)"},                                  
                    ]

            def handle_result(result):
                # This function is the callback for the password entry dialog.
                if result is None:
                    # User canceled the password entry. End the workflow.
                    if result_queue: result_queue.put(None)
                    if on_complete: on_complete(None)
                    return
                
                pass1, pass2 = result

                if not pass1:
                    # Define what to do AFTER the messagebox closes.
                    # The argument '_' is the result from the messagebox, which we ignore.
                    def on_messagebox_closed(_):
                        get_passwords_step() # Re-show the password dialog.

                    # Show the messagebox in ASYNC/CALLBACK mode.
                    self.messagebox(
                        title='Error',
                        msg='No password provided.',
                        on_complete=on_messagebox_closed
                    )
                    return # Stop here and wait for the callback.

                if pass1 != pass2:
                    # Define what to do AFTER the messagebox closes.
                    def on_messagebox_closed(_):
                        get_passwords_step() # Re-show the password dialog.
                    
                    # Show the messagebox in ASYNC/CALLBACK mode.
                    self.messagebox(
                        title='Error', 
                        msg='Passwords do not match.',
                        on_complete=on_messagebox_closed
                    )
                    return # Stop here and wait for the callback.
                                
                # If we reach here, the passwords are valid and match.
                # Finish the workflow based on the original calling mode.
                if result_queue: result_queue.put(pass1)
                if on_complete: on_complete(pass1)
            
            self.create_dialog_with_checks(prompt=prompt, title=title, on_complete=handle_result,
                result_processor=lambda res: (res[0][0], res[0][1]),
                callbacks={"focus_next_widget":self.dialog_functions.focus_next_widget, "set_entry_visibility":self.dialog_functions.set_entry_visibility, "toggle_entry_visibility":self.dialog_functions.toggle_entry_visibility}, classes={"KeyToggle": KeyToggle}, modal=modal)
            
        # Start the first step of this sub-workflow
        get_passwords_step()

    def password_dialog(self, title, msg, modal=True, result_queue=None, on_complete=None):
        """
        Shows a dialog to ask for a single password entry.
        It returns the entered string or None if canceled.
        """
        # Define the UI layout for the password dialog.
        prompt = [
                    {'type': 'label', 
                     "config":"text={}".format(msg), 
                     "grid_config":"column=0, columnspan=2"},

                    {"type":"frame", 
                     "widget_name":"frame_1", 
                     "grid_config":"column=0, columnspan=2, sticky='nswe', pady=(10, 0)"}, 
                                                 
                    {"type":"entry", 
                     "widget_name":"password_entry", 
                     "config":"font='Helvetica 12 bold', show='*'", 
                     "parent":"frame_1", 
                     "pack_config":"side='left', expand=True, fill='x'"}, 

                    {"type":"button", 
                     "widget_name":"password_entry_toggle", 
                     "class":"KeyToggle", 
                     "style_config":"style='toggle1.TButton', background='white', borderwidth=0, highlightthickness=0, padx=0, pady=0", 
                     "style_map_config":"style='toggle1.TButton', background=[(\"active\",\"white\")], foreground=[(\"disabled\",\"gray\")]", 
                     "config":"style='toggle1.TButton', padding=0", 
                     "command": "command_str='set_entry_visibility', args='(self.widget_references[\"password_entry_toggle\"], self.widget_references[\"password_entry\"],)', execute_on_load=True, first=True", 
                     "binds":[{"bind_config":"event='<Button-1>', callback_str='toggle_entry_visibility', args='(self.widget_references[\"password_entry_toggle\"], self.widget_references[\"password_entry\"],)'"}], 
                     "parent":"frame_1", 
                     "pack_config":"side='left', padx=(5, 0), pady=(0, 5)"}, 

                    #{'type': 'entry', 
                    # "config":"{}".format(f"show={show}" if show else ''), 
                    # "binds":[{"bind_config":"event='<Return>',  callback_str='lambda e:self.submit_entry'"}],
                    # "grid_config":"column=0, columnspan=2, sticky='we', pady=(10, 0)"},

                    {'type': 'button', 
                     "config":"text='Submit'", 
                     "command":"command_str=self.submit_entry", 
                     "grid_config":"row=2, column=0, sticky='ew', padx=(0, 5), pady=(10, 0)"},

                    {'type': 'button', 
                     "config":"text='Cancel'", 
                     "command":"command_str=self.cancel", 
                     "grid_config":"row=2, column=1, sticky='ew', padx=(5, 0), pady=(10, 0)"}
             ]

        # Define the special callbacks and classes needed for this dialog.
        dialog_callbacks = {
            "set_entry_visibility": self.dialog_functions.set_entry_visibility,
            "toggle_entry_visibility": self.dialog_functions.toggle_entry_visibility
        }
        dialog_classes = {
            "KeyToggle": KeyToggle
        }

        # Call the helper. The default result processor is perfect for this,
        # as it just needs to extract the single entry's value.
        # We pass the callbacks and classes dicts as keyword arguments.
        self.create_dialog_with_checks(prompt=prompt, title=title, result_queue=result_queue, on_complete=on_complete,
                                    callbacks=dialog_callbacks, classes=dialog_classes, modal=modal)

    def confirmation_prompt(self, title, msg, msg_2=None, modal=True, result_queue=None, on_complete=None):
        """
        Shows a Yes/No confirmation dialog. Uses the helper method with a
        custom result processor to return a clean boolean value.
        """
        # Define the UI layout for the dialog.
        prompt = [
                    {"type": "label", 
                     "config":"text={}, justify='center', wraplength=500".format(msg), 
                     "grid_config":"column=0"},
                                            
                    {"type":"frame", 
                     "widget_name":"frame_1", 
                     "grid_config":"column=0",
                     "hidden":False if msg_2 else True},
                                            
                    {"type":"entry",
                     "config":"style='addressInfo.TEntry', state='readonly', font='Helvetica 10 bold', justify='center'", 
                     "style_map_config":"style='addressInfo.TEntry', lightcolor='[(\"focus\", \"white\")]'",
                     "insert":"string='{}'".format(msg_2),
                     "variables": {"expand_entry_width": True},
                     "parent":"frame_1",
                     "pack_config":"side='left', padx=(5, 5)"},
                                            
                    {"type":"frame", 
                     "widget_name":"frame_2", 
                     "grid_config":"column=0, sticky='we'"},                                            
                                            
                    {"type": "button", 
                     "config":"text='Yes'", 
                     "parent":"frame_2",
                     "command":"command_str=self.submit_entry", 
                     "pack_config":"side='left', fill='x', expand=True, padx=(5, 0), pady=(0, 5)"},                                            
                                            
                    {"type": "button", 
                     "config":"text='No'",
                     "parent":"frame_2",
                     "command":"command_str=self.cancel", 
                     "pack_config":"side='left', fill='x', expand=True, padx=(5, 0), pady=(0, 5)"}
                    ]
        
        # Define a custom function to process the result.
        # CustomDialog with `true_on_submit` returns ([True], (), ()) on 'Yes'.
        # We want to convert this to a simple boolean `True`.
        def confirmation_processor(res): return res and res[0] and res[0][0] is True
        self.create_dialog_with_checks(prompt=prompt, title=title, result_queue=result_queue,
                                    on_complete=on_complete, result_processor=confirmation_processor, true_on_submit=True, modal=modal)
        

    def ask_string(self, title, msg, show, modal=True, result_queue=None, on_complete=None):
        prompt = [
            {'type': 'label', "config":f"text='{msg}'", "grid_config":"column=0, columnspan=2"},
            {'type': 'entry', "config":f"show='*'" if show else "", "grid_config":"column=0, columnspan=2, sticky='we', pady=(10, 0)"},
            {'type': 'button', "config":"text='Submit'", "command":"command_str='self.submit_entry'", "grid_config":"row=2, column=0, sticky='ew', padx=(0, 5), pady=(10, 0)"},
            {'type': 'button', "config":"text='Cancel'", "command":"command_str='self.cancel'", "grid_config":"row=2, column=1, sticky='ew', padx=(5, 0), pady=(10, 0)"}
        ]
        # We use the default result processor here, so we don't need to pass one.
        self.create_dialog_with_checks(prompt=prompt, title=title, result_queue=result_queue, on_complete=on_complete, modal=modal)


    def tx_confirmation_dialog(self, sender, receiver, amount, modal=True, result_queue=None, on_complete=None):
        """
        Shows a transaction confirmation dialog. Returns a tuple:
        (was_confirmed: bool, disable_dialog: bool).
        Returns None if canceled.
        """

        prompt = [
                    {'type': 'label',
                     "config": "text='Are you sure you want to execute this transaction?', font='Helvetica 12 bold', anchor='center'",
                     "pack_config": "side='top', fill='x', pady=(0, 10)"},
                
                    # --- From Row ---
                    {'type': 'frame',
                     'widget_name': 'from_row_frame',
                     'pack_config': "side='top', fill='x'"},
                
                    {'type': 'label',
                     'parent': 'from_row_frame',
                     "config": "text='From:'",
                     "pack_config": "side='left'"},
                    
                    {'type': 'label',
                     'parent': 'from_row_frame',
                     "config": "text='{}'".format(sender),
                     "pack_config": "side='left', padx=(5, 0)",
                     "translate": False},
                
                    # --- To Row ---
                    {'type': 'frame',
                     'widget_name': 'to_row_frame',
                     'pack_config': "side='top', fill='x'"},
                
                    {'type': 'label',
                     'parent': 'to_row_frame',
                     "config": "text='To:'",
                     "pack_config": "side='left'"},
                
                    {'type': 'label',
                     'parent': 'to_row_frame',
                     "config": "text='{}'".format(receiver),
                     "pack_config": "side='left', padx=(5, 0)",
                     "translate": False},
                
                    # --- Separator ---
                    {'type': 'separator',
                     "config": "orient='horizontal'",
                     "pack_config": "side='top', fill='x', pady=(10, 0)"},
                
                    # --- NEW Amount Row ---
                    # Create a frame to hold the two amount labels side-by-side.
                    {'type': 'frame',
                     'widget_name': 'amount_row_frame',
                     'pack_config': "side='top', fill='x', pady=(5, 0)"},
                
                    # First label: "Amount:"
                    {'type': 'label',
                     'parent': 'amount_row_frame',
                     "config": "text='Amount:', font='Helvetica 12 bold'",
                     "pack_config": "side='left'"},
                
                    # Second label: The actual amount value
                    {'type': 'label',
                     'parent': 'amount_row_frame',
                     "config": "text='{} DNR', font='Helvetica 12 bold".format(amount),
                     "pack_config": "side='left', padx=(5, 0)",
                     "translate": False},
                
                    # --- Checkbox ---
                    {'type': 'checkbox',
                     "config": "text='Do not show this dialog box for future transactions (This session only)'",
                     "pack_config": "side='top', anchor='w', pady=(10, 0)"},
                
                    # --- Button Row ---
                    {'type': 'frame',
                     'widget_name': 'button_frame',
                     'pack_config': "side='top', fill='x', pady=(10, 0)"},
                     
                    {'type': 'button',
                     'parent': 'button_frame',
                     "config": "text='Yes'",
                     "command": "command_str=self.submit_entry",
                     "pack_config": "side='left', expand=True, fill='x', padx=(0, 5)"},
                
                    {'type': 'button',
                     'parent': 'button_frame',
                     "config": "text='No'",
                     "command": "command_str=self.cancel",
                     "pack_config": "side='left', expand=True, fill='x', padx=(5, 0)"}
                ]
        
        # Define a custom processor to handle the two return values.
        def tx_processor(raw_result):
            # The raw_result will be ([True], (True/False,), ()) on 'Yes'
            # or None on 'No'/cancel.
            if raw_result is None:
                return None

            # Extract the data
            was_confirmed = raw_result[0] and raw_result[0][0] is True
            
            # The checkbox value is in the second tuple.
            disable_dialog = raw_result[1] and raw_result[1][0] is True
            
            # Return the clean, packaged tuple.
            return (was_confirmed, disable_dialog)

        # Call the helper, passing our custom processor.
        self.create_dialog_with_checks(prompt=prompt, title="Confirm Transaction", result_queue=result_queue, on_complete=on_complete, result_processor=tx_processor, true_on_submit=True, modal=modal)
        

    def input_listener_dialog(self, modal=True, result_queue=None, on_complete=None, close_event=None):
        """
        A universal dialog that listens for a keypress (submit) or an external
        close_event (cancel).
        """
        prompt = [
                    {"type": "label",
                     "widget_name": "countdown_label",
                     "config": "text='Initializing countdown...'",
                     # This command is attached to the visible label.
                     # We pass the callback name as a string, not the result of a call.
                     "grid_config": "row=0, column=0, padx=20, pady=20",
                     "command": "command_str='start_loops', args='(self, self.widget_references[\"countdown_label\"], self.callbacks[\"get_active_listener_close_event\"])', execute_on_load=True"},
        
                    {"type": "self.master",
                     "binds": [{"bind_config": "event='<KeyRelease>', callback_str='self.submit_entry'"}]},
                ]
        
        dialog_callbacks = {
            "start_loops": self.dialog_functions.start_input_listener_loops,
            "get_active_listener_close_event": self.dialog_functions.get_active_listener_close_event
        }
        
        # On keypress (submit), the result is True.
        self.create_dialog_with_checks(
            prompt=prompt,
            title='Wallet Annihilation',
            result_queue=result_queue,
            on_complete=on_complete,
            result_processor=lambda r: True, # On keypress, result is True
            callbacks=dialog_callbacks,
            modal=modal
        )
        

    def backup_mnemonic_dialog(self, mnemonic, modal=True, result_queue=None, on_complete=None):
        """
        Orchestrates the entire mnemonic backup workflow.
        
        Args:
            modal (bool): If True, all dialogs in this workflow will block interaction
                          with other windows.
        """
        word_list = mnemonic.split()

        def final_handler(result):
            """The single point of exit for the entire workflow."""
            if result_queue: result_queue.put(result)
            if on_complete: on_complete(result)

        def run_confirmation_step(attempt=None):
            """Helper to start/restart the confirmation step."""
            # Pass the modal flag down to the next step.
            self.confirm_mnemonic_step(word_list, on_complete=handle_confirmation_result, previous_attempt=attempt, modal=modal)

        def handle_show_result(user_clicked_next):
            """Called after the user views the mnemonic."""
            if user_clicked_next:
                run_confirmation_step()
            else:
                final_handler(False)

        def handle_confirmation_result(result):
            """Called after the user attempts to confirm the mnemonic."""
            if result == "BACK":
                # Pass the modal flag when going back to the previous step.
                self.show_mnemonic_step(mnemonic, on_complete=handle_show_result, modal=modal)
            elif result is True:
                final_handler(True)
            elif isinstance(result, list): # Incorrect attempt
                def on_error_closed(_):
                    # Pass the modal flag when retrying.
                    run_confirmation_step(attempt=result)

                # Pass the modal flag to the error messagebox.
                self.messagebox(
                    title="Error",
                    msg="Recovery phrase is not correct.",
                    on_complete=on_error_closed,
                    modal=modal 
                )
            else: # result is None (user canceled)
                final_handler(False)

        # Pass the initial modal flag to the first step.
        self.show_mnemonic_step(mnemonic, on_complete=handle_show_result, modal=modal)


    def show_mnemonic_step(self, mnemonic, modal=True, on_complete=None):
        """
        A non-blocking step that shows the mnemonic dialog.
        The prompt is now generated dynamically.
        """
        word_list = mnemonic.split()
        
        prompt = [
            {"type": "label", "config": "text='The words below is the recovery phrase of the wallet.'", "grid_config": "column=0"},
            {"type": "label", "config": "text='They enable you to access your Denaro and restore your wallet.'", "grid_config": "column=0"},
            {"type": "label", "config": "text='Please write them down in the order shown.'", "grid_config": "column=0"},
            {"type": "separator", "config": "orient='horizontal'", "grid_config": "column=0, sticky='we', pady=(5, 5)"},
        ]
        
        # --- DYNAMIC PROMPT GENERATION ---
        # Loop to create the 12 read-only entry fields
        for i in range(12):
            word_num = i + 1
            frame_num = (i // 2) + 2 # Puts two entries per frame
            
            # Create a new frame for every two entries
            if i % 2 == 0:
                prompt.append({"type": "frame", "widget_name": f"frame_show_{frame_num}", "grid_config": f"column=0, pady=(10, 0)"})
            
            # Add padding to the second item in each row for spacing
            side_pad = 20 if i % 2 != 0 else 0
            
            # Label for the word number
            prompt.append({"type": "label",
                           "config": f"text='{word_num}: ', font='Helvetica 12 bold'",
                           "parent": f"frame_show_{frame_num}",
                           "pack_config": f"side='left', padx=({side_pad}, 0)"})
            
            # The read-only entry field with the word
            prompt.append({
                "type": "entry",
                "config": "style='addressInfo.TEntry', state='readonly', font='Helvetica 12 bold'",
                "style_map_config": "style='addressInfo.TEntry', lightcolor='[(\"focus\", \"white\")]'",
                "parent": f"frame_show_{frame_num}",
                "insert": f"string='{word_list[i]}'",
                "pack_config": "side='left'",
                "translate": False
            })

        # Add the final separator and action buttons
        prompt.extend([
            {"type": "separator", "config":"orient='horizontal'", "grid_config":"column=0, sticky='we', pady=(15, 0)"},
            {"type": "frame", "widget_name":"frame_copy", "grid_config":"column=0, sticky='w', pady=(10, 0)"},
            {"type": "label", "widget_name":"copied_mnemonic_label", "config":"text='', font='Helvetica 11 bold'", "parent":"frame_copy", "pack_config":"side='right', padx=(10, 0)"},
            {"type": "button", "config":"text='Copy to clipboard'", "parent":"frame_copy",
             "binds":[{"bind_config":f"event='<Button-1>', callback_str='copy_mnemonic_to_clipboard', args='(\"{mnemonic}\", self.widget_references[\"copied_mnemonic_label\"],)'"}],
             "pack_config":"side='left'"},
            
            {"type": "frame", "widget_name":"frame_actions", "grid_config":"column=0, sticky='we', pady=(10, 0)"},
            {"type": "button", "config":"text='Cancel'", "parent":"frame_actions", "command":"command_str=self.cancel", "pack_config":"side='left', padx=(0, 5), fill='x', expand=True"},
            {"type": "button", "config":"text='Next'", "parent":"frame_actions", "command":"command_str=self.submit_entry", "pack_config":"side='left', padx=(5, 0), fill='x', expand=True"}
        ])
        
        self.create_dialog_with_checks(
            prompt=prompt, 
            title='Recovery Phrase Backup', 
            on_complete=on_complete,
            result_processor=lambda r: True, # We just need to know if they clicked Next
            callbacks={"copy_mnemonic_to_clipboard": self.dialog_functions.copy_mnemonic_to_clipboard},
            modal=modal
        )


    def confirm_mnemonic_step(self, original_word_list, modal=True, on_complete=None, previous_attempt=None):
        """
        A non-blocking step that asks the user to confirm the mnemonic.
        Dynamically generates the prompt to pre-fill entries and adds a show/hide button.
        """
        
        # --- DYNAMIC PROMPT GENERATION ---
        prompt = [
                    {"type": "label",
                     "config":"text='Please confirm your recovery phrase.'",
                     "grid_config":"column=0"},

                    {"type": "separator",
                     "config":"orient='horizontal'",
                     "grid_config":"column=0, sticky='we', pady=(5, 5)"}
                ]

        # Loop to create the 12 entry fields
        for i in range(12):
            word_num = i + 1
            frame_num = (i // 2) + 2
            
            if i % 2 == 0:
                prompt.append({"type": "frame",
                               "widget_name": f"frame_{frame_num}",
                               "grid_config":f"column=0, sticky='we', pady=(10, 0)"})
            
            side_pad = 50 if i % 2 != 0 else 0
            prompt.append({"type": "label",
                           "config":f"text='{word_num}: '",
                           "parent": f"frame_{frame_num}",
                           "pack_config":f"side='left', padx=({side_pad}, 0)"})

            entry_dict = {
                "type": "entry",
                "widget_name": f"word_{word_num}",
                "config":"font='Helvetica 12 bold', show='*'",
                "binds":[{"bind_config":"event='<Tab>', callback_str='focus_next_widget'"}, {"bind_config":"event='<space>', callback_str='focus_next_widget'"}],
                "parent": f"frame_{frame_num}", "pack_config":"side='left'",
                "translate": False
            }

            if previous_attempt and i < len(previous_attempt):
                entry_dict["insert"] = f"string='{previous_attempt[i]}'"
            
            prompt.append(entry_dict)

                                                
            toggle_dict = {
                "type": "button",
                "widget_name": f"word_{word_num}_toggle",
                "class": "KeyToggle",
                "style_config":"style='toggle1.TButton', background='white', borderwidth=0, highlightthickness=0, padx=0, pady=0", 
                "style_map_config":"style='toggle1.TButton', background=[(\"active\",\"white\")], foreground=[(\"disabled\",\"gray\")]",
                "config":"style='toggle1.TButton', padding=0",
                "command": f"command_str='set_entry_visibility', args='(self.widget_references[\"word_{word_num}_toggle\"], self.widget_references[\"word_{word_num}\"],)', execute_on_load=True, first=True",
                "binds":[{"bind_config":f"event='<Button-1>', callback_str='toggle_entry_visibility', args='(self.widget_references[\"word_{word_num}_toggle\"], self.widget_references[\"word_{word_num}\"],)'"}],
                "parent": f"frame_{frame_num}", "pack_config":"side='left', padx=(5, 0)"
            }

            prompt.append(toggle_dict)

        prompt.extend([
            {"type": "separator",
             "config":"orient='horizontal'",
             "grid_config":"column=0, sticky='we', pady=(15, 0)"},
            
            {"type": "frame",
             "widget_name": "frame_show_all",
             "grid_config":"column=0, sticky='we', pady=(10, 0)"},
           
            {"type": "button",
             "widget_name": "show_all_toggle",
             "config": "text='Show All'",
             "parent": "frame_show_all",
             "binds":[{"bind_config":"event='<Button-1>', callback_str='toggle_all_mnemonic_visibility', args='(self.widget_references[\"show_all_toggle\"], self,)'"}],
             "pack_config": "expand=True, fill='x'"},

            {"type": "frame",
             "widget_name": "frame_final",
             "grid_config":"column=0, sticky='we', pady=(5, 0)"},

            {"type": "button",
             "config": "text='Back'",
             "parent": "frame_final",
             "command": "command_str=self.cancel",
             "binds": [{"bind_config": "event='<Button-1>', callback_str='confirm_mnemonic_back_button_press'"}],
             "pack_config": "side='left', expand=True, fill='x'"},

            {"type": "button",
             "config": "text='Finish'",
             "parent": "frame_final",
             "command": "command_str=self.submit_entry",
             "pack_config": "side='left', padx=(5, 0), expand=True, fill='x'"}
        ])
        
        def on_submit(result):
            # First, check if the "Back" button was the source of the submission.
            if self.root.stored_data.confirm_mnemonic_back_button_press:
                self.root.stored_data.confirm_mnemonic_back_button_press = False # Reset the flag
                on_complete("BACK") # Signal to the orchestrator to go back.
                return
            
            if result is None:
                on_complete(None) # Signal a full cancellation of the workflow.
                return

            entered_words = list(result[0])
            if entered_words == original_word_list:
                on_complete(True)
            else:
                on_complete(entered_words)

        dialog_callbacks = {
            "focus_next_widget": self.dialog_functions.focus_next_widget,
            "set_entry_visibility": self.dialog_functions.set_entry_visibility,
            "toggle_entry_visibility": self.dialog_functions.toggle_entry_visibility,
            "confirm_mnemonic_back_button_press": self.dialog_functions.confirm_mnemonic_back_button_press,
            "toggle_all_mnemonic_visibility": self.dialog_functions.toggle_all_mnemonic_visibility
        }

        self.create_dialog_with_checks(prompt=prompt, title='Confirm Recovery Phrase', on_complete=on_submit,
                                    result_processor=lambda r: r,
                                    callbacks=dialog_callbacks, classes={"KeyToggle": KeyToggle}, modal=modal)
    
    def about_wallet_dialog(self, modal=True, result_queue=None, on_complete=None):

        prompt=[
                {"type":"frame", 
                 "widget_name":"frame_1", 
                 "grid_config":"row=0, column=0, sticky='w', padx=(0, 10)"},
                                    
                {"type":"label", 
                  "widget_name":"label_1",
                  "config":"",
                  "parent":"frame_1",
                  "command": "command_str='set_label_image', args='(self.widget_references[\"label_1\"],\"./denaro/gui_assets/denaro_logo.png\",120,120,)', execute_on_load=True",
                  "pack_config":"side='left'"},
                                    
                {"type":"frame", 
                 "widget_name":"frame_2", 
                 "grid_config":"row=0, column=1, sticky='w', padx=(0, 10)"},

                {'type': 'label', 
                 "widget_name":"label_2",
                 "parent":"frame_2",
                 "config":"text='{}', anchor='w', justify='left'".format(f'\n{self.root.wallet_client_version}'), 
                 "grid_config":"row=0, column=1, sticky='w'",
                 "translate": False},
                                    
                {"type":"frame", 
                 "widget_name":"frame_3",
                 "parent":"frame_2", 
                 "class":"HyperlinkLabel",
                 "class_config":"text=\"Copyright © 2023-2025 The-Sycorax (https://github.com/The-Sycorax)\", link_text=\"\", url=\"https://github.com/The-Sycorax\"",
                 "grid_config":"row=1, column=1, sticky='w'",
                 "translate": False},

                {"type":"frame", 
                 "widget_name":"frame_4",
                 "parent":"frame_2", 
                 "class":"HyperlinkLabel",
                 "class_config":"text=\"\nThe source code for this wallet client is available at: https://github.com/The-Sycorax/DenaroWalletClient-GUI\", link_text=\"\", url=\"https://github.com/The-Sycorax/DenaroWalletClient-GUI\"",
                 "grid_config":"row=2, column=1, sticky='w'"},

                {"type":"frame", 
                 "widget_name":"frame_4",
                 "parent":"frame_2", 
                 "class":"HyperlinkLabel",
                 "class_config":"text=\"The source code for the Denaro cryptocurrency is available at: https://github.com/denaro-coin/denaro\", link_text=\"\", url=\"https://github.com/denaro-coin/denaro\"",
                 "grid_config":"row=3, column=1, sticky='w'"},

                {'type': 'label', 
                 "parent":"frame_2",
                 "config":"text='{}', justify='left'".format('\nThis is experimental software.'), 
                 "grid_config":"row=4, column=1, sticky='w'"},

                {"type":"frame", 
                 "widget_name":"frame_5",
                 "parent":"frame_2", 
                 "class":"HyperlinkLabel",
                 "class_config":"text=\"Distributed under the MIT software license, see the accompanying LICENSE file or https://opensource.org/licenses/MIT\", link_text=\"\", url=\"https://opensource.org/licenses/MIT\"",
                 "grid_config":"row=5, column=1, sticky='w'"},

                {'type': 'button', 
                 "config":"text='Close'", 
                 "command":"command_str=self.submit_entry", 
                 "grid_config":"row=6, column=1, sticky='e', padx=(0, 10), pady=(75, 10)"}
            ]
        
        self.create_dialog_with_checks(prompt=prompt, title="About", result_queue=result_queue, on_complete=on_complete,
            callbacks={"set_label_image":self.dialog_functions.set_label_image, "set_hyperlink":self.dialog_functions.set_hyperlink},
            classes={"HyperlinkLabel": HyperlinkLabel}, modal=modal)

    def show_2FA_QR_dialog(self, qr_window_data, from_gui=False, modal=True):
        """
        Creates and manages the 2FA QR Code dialog. This is a non-blocking,
        fire-and-forget dialog with a self-contained lifecycle.
        
        Args:
            qr_window_data (_2FA_QR_Dialog): The data/state object for the dialog.
            from_gui (bool): Flag indicating the execution context.
        """
        # Determine the parent window for the dialog.
        # - In GUI mode, the parent is the main application window.
        # - In non-GUI mode, parent is None, making CustomDialog create a temp root.
        parent = self.root if from_gui else None

        # Create a controller for the dialog's specific logic.
        dialog_functions = DialogFunctions(qr_window_data, self, from_gui=from_gui)
        
        # The prompt is fully declarative and robust.
        prompt = [
            # --- Top Row ---
            # 1. Create a frame to hold the top row's three widgets.
            {"type": "frame",
             "widget_name": "top_row_frame",
             "pack_config": "side='top', fill='x'"},
        
            # 2. Pack the first label against the left side of the frame.
            {"type": "label",
             "parent": "top_row_frame",
             "config": "text='Closing in', foreground='red', font='Helvetica 12'",
             "pack_config": "side='left', padx=(5,0), pady=5"},
        
            # 3. Pack the countdown label next to it, also on the left.
            {"type": "label",
             "parent": "top_row_frame",
             "widget_name": "countdown_label",
             "config": "text=': 60s', foreground='red', font='Helvetica 12'",
             "pack_config": "side='left', padx=(0,5), pady=5",
             "translate": False},
        
            # 4. Pack the button against the right side of the frame.
            {"type": "button",
             "parent": "top_row_frame",
             "widget_name": "reveal_button",
             "config": "text='Reveal 2FA Token'",
             "pack_config": "side='right', padx=5, pady=5",
             "command": "command_str='handle_click'"},
        
            # --- QR Code Label ---
            # This is a simple vertical element, so no frame is needed.
            {"type": "label",
             "widget_name": "qr_label",
             # It will center by default since it doesn't fill the space.
             "pack_config": "side='top', pady=10"},
        
            # --- Secret Entry ---
            # This spans the full width (sticky='ew' -> fill='x')
            {"type": "entry",
             "widget_name": "secret_entry",
             "style_map_config":"style='addressInfo.TEntry', lightcolor='[(\"focus\", \"white\")]'",
             "config": "style='addressInfo.TEntry', state='readonly', font='Helvetica 12 bold', justify='center'",
             "variables": {"expand_entry_width": True},
             "pack_config": "side='top', fill='x', pady=5, padx=10",
             "binds": [{"bind_config": "event='<Button-3>', callback_str='self.callbacks[\"handle_context_menu\"]'"},
                       {"bind_config": "event='<Double-1>', callback_str='self.callbacks[\"handle_double_click\"]'"},
                       {"bind_config": "event='<Control-c>', callback_str='self.callbacks[\"handle_copy\"]'"},
                       {"bind_config": "event='<Control-a>', callback_str='self.callbacks[\"handle_select_all\"]'"}]},
        
            # --- Message Label ---
            # Also spans the full width. We use fill='x' so wraplength works correctly.
            {"type": "label",
             "widget_name": "message_label",
             "config": "text='To enable 2FA, scan the QR code with an authenticator app, then provide the one-time code.', wraplength=400, justify='center'",
             "pack_config": "side='top', fill='x', padx=10, pady=10"},
        
            # --- Setup Trigger ---
            # This is a non-visual widget. Just packing it is enough for the command to execute.
            {"type": "label",
             "widget_name": "setup_trigger",
             "config": "",
             "command": "command_str='initial_setup', args='(self,)', execute_on_load=True",
             "pack_config": "side='top'"}
        ]

        # Map the string names in the prompt to the actual functions.
        callbacks = {
            "initial_setup": dialog_functions._2FA_initial_setup,
            "handle_click": dialog_functions._2FA_handle_click,
            "handle_context_menu": dialog_functions._2FA_handle_context_menu,
            "handle_copy": dialog_functions._2FA_context_copy,
            "handle_select_all": dialog_functions._2FA_context_select_all,
            "handle_double_click": dialog_functions._2FA_handle_double_click
        }

        # Create the dialog. This call is now correctly non-blocking.
        # It does not return a result and does not use the result_queue system.
        CustomDialog(
            parent=parent,
            title=f"2FA QR Code for {qr_window_data.filename}",
            prompt=prompt,
            callbacks=callbacks,
            modal=modal
        )
        
                
class DialogFunctions:
    def __init__(self, root, parent, from_gui=False, dialogs_instance=None):
        self.root = root
        self.parent = parent
        self.from_gui = from_gui
        self.dialogs = dialogs_instance
        self.active_listener_close_event = None


    def set_key_visibility(self, widget=None, entry=None, first=False):
        #self.print_variable_values(entry)
        if first:
            #widget.setvar(name='visibility_on', value='True')
            #self.toggle_key_visibility(widget, entry)
            entry.pack_forget()
        visibility_on = widget.visibility_on
        if visibility_on:
             visibility_img = Image.open("./denaro/gui_assets/visibility_on.png")
             visibility_img = visibility_img.resize((32, 32), Image.LANCZOS)
             visibility_img = ImageTk.PhotoImage(visibility_img)
             widget.config(image=visibility_img)
             widget.visibility_img = visibility_img
        else:
            visibility_img = Image.open("./denaro/gui_assets/visibility_off.png")
            visibility_img = visibility_img.resize((32, 32), Image.LANCZOS)
            visibility_img = ImageTk.PhotoImage(visibility_img)
            widget.config(image=visibility_img)
            widget.visibility_img = visibility_img


    def toggle_key_visibility(self, widget=None, entry=None, state=None):
        visibility_on = widget.visibility_on
        if visibility_on:
            widget.visibility_on = False
            self.set_key_visibility(widget, entry)
            entry.pack_forget()
        else:
            widget.visibility_on = True
            self.set_key_visibility(widget, entry)
            entry.pack(side='left')


    def set_entry_visibility(self, widget=None, entry=None, first=False):
        if first:
            #widget.setvar(name='visibility_on', value='True')
            #self.toggle_key_visibility(widget, entry)
            entry.config(show='*')
        visibility_on = widget.visibility_on
        if visibility_on:
             visibility_img = Image.open("./denaro/gui_assets/visibility_on.png")
             visibility_img = visibility_img.resize((24, 24), Image.LANCZOS)
             visibility_img = ImageTk.PhotoImage(visibility_img)
             widget.config(image=visibility_img)
             widget.visibility_img = visibility_img
        else:
            visibility_img = Image.open("./denaro/gui_assets/visibility_off.png")
            visibility_img = visibility_img.resize((24, 24), Image.LANCZOS)
            visibility_img = ImageTk.PhotoImage(visibility_img)
            widget.config(image=visibility_img)
            widget.visibility_img = visibility_img


    def toggle_entry_visibility(self, widget=None, entry=None, state=None):
        visibility_on = widget.visibility_on

        if visibility_on:
            widget.visibility_on = False
            self.set_entry_visibility(widget, entry)
            entry.config(show='*')
        else:
            widget.visibility_on = True
            self.set_entry_visibility(widget, entry)
            entry.config(show='')


    def toggle_all_mnemonic_visibility(self, button=None, dialog=None, state=None):
        """
        Toggles the 'show' property for all 12 mnemonic entry fields at once
        by directly setting their state, ensuring consistency.
        """
        # Initialize the shared visibility state on the dialog if it doesn't exist.
        if not hasattr(dialog, 'mnemonic_entries_shown'):
            dialog.mnemonic_entries_shown = False

        # Toggle the shared state for the whole group.
        dialog.mnemonic_entries_shown = not dialog.mnemonic_entries_shown

        # Determine the target state based on the new shared state.
        if dialog.mnemonic_entries_shown:
            new_show_char = ''  # Show text
            new_visibility_state = True
            if button: button.config(text="Hide All")
        else:
            new_show_char = '*'  # Hide text
            new_visibility_state = False
            if button: button.config(text="Show All")

        # Loop through all 12 entries and FORCE their state to match the new shared state.
        for i in range(1, 13):
            entry_widget = dialog.widget_references.get(f'word_{i}')
            toggle_widget = dialog.widget_references.get(f'word_{i}_toggle')

            if entry_widget and toggle_widget:
                # 1. Set the entry's visibility directly.
                entry_widget.config(show=new_show_char)
                
                # 2. Update the individual toggle's internal state to match.
                toggle_widget.visibility_on = new_visibility_state
                
                # 3. Call set_entry_visibility to update the toggle's icon.
                self.set_entry_visibility(widget=toggle_widget, entry=entry_widget)


    def toggle_continue_button_state(self, checkbox=None, continue_button=None):
        """
        The CORE LOGIC. Enables or disables a button based on a checkbox.
        """
        if checkbox and continue_button:
            if checkbox.instate(['selected']):
                continue_button.state(['!disabled'])
            else:
                continue_button.state(['disabled'])


    def deferred_toggle_bridge(self, dialog_instance, state=None):
        """
        This function is called by the checkbox command. It receives the
        CustomDialog instance, performs the widget lookups at runtime, and
        then calls the core logic function.
        """
        try:
            # Look up the widgets now, when the command is actually executed.
            checkbox = dialog_instance.widget_references.get("agree_checkbox")
            button = dialog_instance.widget_references.get("continue_button")
            
            # Call the original function with the resolved widgets.
            self.toggle_continue_button_state(checkbox=checkbox, continue_button=button)
        except Exception as e:
            print(f"Error in deferred_toggle_bridge: {e}")


    def enable_2fa_checkbox(self, encryption_checkbox=None, _2fa_checkbox=None, state=None):
        # Get the state of the encryption checkbox
        encryption_state = encryption_checkbox.instate(['selected'])    
        # If encryption_checkbox is selected, enable _2fa_checkbox
        if encryption_state:
            _2fa_checkbox.state(['!disabled'])
        else:
            # If encryption_checkbox is not selected, disable and deselect _2fa_checkbox
            _2fa_checkbox.state(['disabled'])
            _2fa_checkbox.state(['!selected'])


    def get_active_listener_close_event(self):
        """Returns the stored event object for the dialog's prompt string."""
        return self.active_listener_close_event


    def start_input_listener_loops(self, dialog, label, get_close_event_func, first=False):
        """
        A single starter function that kicks off BOTH the close listener
        and the view updater loops on the GUI thread.
        """
        dialog.master.focus_set()

        # Call the function that was passed in to get the actual event object.
        close_event = get_close_event_func()

        # Start the loop that checks for the external close signal.
        self.should_close_loop(dialog=dialog, close_event=close_event)
        # Start the loop that updates the countdown text.
        self.update_view_loop(dialog, label)


    def should_close_loop(self, dialog, close_event=None, label=None, event=None, state=None):
        """The recurring check for the controller's close signal."""
        try:
            if not dialog.dialog.winfo_exists(): return

            if close_event.is_set():
                dialog.cancel() # Triggers on_cancel, puts None in the queue.
                return

            dialog.dialog.after(50, lambda: self.should_close_loop(dialog, close_event=close_event, label=label))
        except tk.TclError:
            pass


    def update_view_loop(self, dialog, label):
        """
        The recurring loop that reads the shared timer state and updates the label.
        """
        try:
            if not dialog.dialog.winfo_exists():
                return

            # Read the time remaining from the shared state controlled by wait_for_input.
            time_remaining = self.root.stored_data.input_listener_time_remaining
            
            msg = f"Existing wallet data will be erased in {time_remaining} seconds.\nPress any key to cancel operation..."
            label.config(text=msg)

            # Schedule the next update.
            dialog.dialog.after(100, lambda: self.update_view_loop(dialog, label))
        except tk.TclError:
            pass


    def input_listener_thread_target(self, stop_signal, interrupt_queue):
        """The target for the secondary worker thread (Thread B)."""
        close_event = self.get_active_listener_close_event()
        result = self.root.wallet_operations.callbacks.post_input_listener_dialog(close_event=close_event)
        interrupt_queue.put(result)


    def setup_input_listener_thread(self, close_event, interrupt_queue):
        """The bridge function that stores context and starts Thread B."""
        self.active_listener_close_event = close_event
        self.root.wallet_thread_manager.start_thread(
            name="input_listener_blocker",
            target=self.input_listener_thread_target,
            args=(interrupt_queue,)
        )


    def confirm_mnemonic_back_button_press(self, state=None):
        self.root.stored_data.confirm_mnemonic_back_button_press = True


    def focus_next_widget(self, event, state=None):
        # Find the next widget in the focus order
        next_widget = event.widget.tk_focusNext()
        # Loop to skip over non-entry widgets (like buttons)
        while next_widget and isinstance(next_widget, tb.Button):
            next_widget = next_widget.tk_focusNext()
        # If a valid next widget is found, focus it
        if next_widget:
            next_widget.focus()
        return "break"


    def copy_mnemonic_to_clipboard(self, mnemonic=None, label=None, event=None, state=None):
        self.root.clipboard_clear()
        self.root.clipboard_append(mnemonic)
        label.config(text='Copied', foreground='#008000')

        if 'fade_copied_mnemonic_label' in self.root.event_handler.thread_event:
            self.root.wallet_thread_manager.stop_thread('fade_copied_mnemonic_label')

        #if 'fade_copied_mnemonic_label' in self.root.event_handler.thread_event and 'copied_mnemonic_label' in self.root.gui_utils.fade_text_widgets:
        #        self.root.gui_utils.fade_text_widgets['copied_mnemonic_label']['step'] = 1
        #        return
        #else:
        self.root.wallet_thread_manager.start_thread("fade_copied_mnemonic_label", self.root.gui_utils.fade_text, args=(label, 'copied_mnemonic_label', 1.25),)


    def set_label_image(self, label=None, image_path=None, width=None, height=None, state=None):
        image = Image.open(image_path)
        image = image.resize((width, height), Image.LANCZOS)
        image = ImageTk.PhotoImage(image)
        label.config(image=image)
        label.image = image


    def set_hyperlink(self, label=None, hyperlink_url=None, state=None):
        hyperlink_tag = f"hyperlink-{hyperlink_url}"
        start = self.root.send_page.tx_log.search(hyperlink_url, "1.0", tk.END)
        end = f"{start}+{len(hyperlink_url)}c"
        label.tag_add(hyperlink_tag, start, end)
        label.tag_config(hyperlink_tag, foreground="blue", underline=True)
        label.tag_bind(hyperlink_tag, "<Enter>", self.root.gui_utils.on_link_enter)
        label.tag_bind(hyperlink_tag, "<Leave>", self.root.gui_utils.on_link_leave)
        label.tag_bind(hyperlink_tag, "<Button-1>", lambda e, url=hyperlink_url: self.root.gui_utils.open_link(url))


    #2FA Dialog functions
    def _2FA_initial_setup(self, dialog_instance, first=None):
        if self.root.is_closing: return

        self.root.dialog_instance = dialog_instance
        refs = self.root.dialog_instance.widget_references
        secret_entry = refs.get('secret_entry')

        self.root.context_menu = tk.Menu(self.root.dialog_instance.dialog, tearoff=0)
        self.root.context_menu.add_command(label="Copy", command=self._2FA_context_copy)
        self.root.context_menu.add_command(label="Select All", command=self._2FA_context_select_all)

        secret_entry.config(takefocus=0)
        secret_entry.config(state='normal')
        secret_entry.insert(0, " " * len(self.root.totp_secret))
        secret_entry.config(state='readonly')

        qr_width = 300
        resized_image = self.root.qr_img.resize((qr_width, qr_width), Image.Resampling.LANCZOS)
        self.root.tk_image = ImageTk.PhotoImage(resized_image)
        refs['qr_label'].config(image=self.root.tk_image)
        
        self.root.dialog_instance.cancel = self._2FA_on_close
        self._2FA_update_timer()


    def _2FA_update_timer(self):
        if self.root.is_closing: return
        if self.root.close_window: self._2FA_on_close(); return
        
        if self.root.countdown > 0:
            try:
                if self.root.dialog_instance and self.root.dialog_instance.dialog.winfo_exists():
                    countdown_label = self.root.dialog_instance.widget_references.get('countdown_label')
                    if countdown_label: 
                        with self.parent.root.translation_engine.no_translate():
                            countdown_label.config(text=f": {self.root.countdown}s")
                    self.root.countdown -= 1
                    self.root._timer_id = self.root.dialog_instance.dialog.after(1000, self._2FA_update_timer)
            except tk.TclError:
                self.root.is_closing = True
                return
        else:
            self._2FA_on_close()


    def _2FA_handle_click(self):
        if self.root.is_closing: return
        self.root.reveal_secret = not self.root.reveal_secret
        refs = self.root.dialog_instance.widget_references
        secret_entry, reveal_btn = refs.get('secret_entry'), refs.get('reveal_button')
        
        secret_entry.config(state='normal')
        secret_entry.delete(0, 'end')
        if self.root.reveal_secret:
            with self.parent.root.translation_engine.no_translate():
                secret_entry.insert(0, self.root.totp_secret)
            reveal_btn.config(text="Hide 2FA Token")
            secret_entry.config(takefocus=1)
        else:
            secret_entry.insert(0, " " * len(self.root.totp_secret))
            reveal_btn.config(text="Reveal 2FA Token")
            secret_entry.config(takefocus=0)
            secret_entry.select_clear()
            self._2FA_hide_context_menu()
        secret_entry.config(state='readonly')


    def _2FA_handle_double_click(self, event):
        if not self.root.reveal_secret:
            return "break"


    def _2FA_handle_context_menu(self, event):
        if self.root.is_closing: return
        if not self.root.reveal_secret: return "break"
        if not self.from_gui:
            try: 
                self.root.context_menu.post(event.x_root, event.y_root)
            except tk.TclError:
                pass


    def _2FA_hide_context_menu(self):
        if self.root.is_closing: return
        try: self.root.context_menu.unpost()
        except tk.TclError: pass


    def _2FA_context_copy(self, event=None):
        if self.root.is_closing or not self.root.reveal_secret: return "break"
        secret_entry = self.root.dialog_instance.widget_references.get('secret_entry')
        if secret_entry: secret_entry.event_generate("<<Copy>>")


    def _2FA_context_select_all(self, event=None):
        if self.root.is_closing or not self.root.reveal_secret: return "break"
        secret_entry = self.root.dialog_instance.widget_references.get('secret_entry')
        if secret_entry:
            secret_entry.focus_set()
            secret_entry.select_range(0, 'end')
        return "break"


    def _2FA_on_close(self, event=None):
        if self.root.is_closing: return
        self.root.is_closing = True
        try:
            if self.root.dialog_instance and self.root.dialog_instance.dialog.winfo_exists():
                if self.root._timer_id:
                    self.root.dialog_instance.dialog.after_cancel(self.root._timer_id)
                    self.root._timer_id = None
                self.root.dialog_instance.close_dialog()
        except tk.TclError: pass
        
        self.root.data_manipulation_util.secure_delete([
            self.root.qr_img, self.root.totp_secret, self.root.tk_image
        ])


    def initial_page_setup(self, dialog, state=None):
        """
        Called once after the dialog is built. It links the PageManager to its
        pages and the dialog instance, then shows the first page.
        """
        page_manager = dialog.widget_references.get('page_manager')
        if not page_manager: return

        page_manager.dialog_instance = dialog
        page_manager.parent_window = dialog.dialog.master

        for name, widget in dialog.widget_references.items():
            if name.startswith('page_'):
                try:
                    page_num = int(name.replace('page_', ''))
                    page_manager.add_page(page_num, widget)
                except (ValueError, TypeError):
                    continue
        
        page_manager.show_page(1)


    def go_to_next_page(self, dialog, state=None):
        """Tells the page manager to show the next page."""
        page_manager = dialog.widget_references.get('page_manager')
        if page_manager:
            page_manager.show_page(page_manager.current_page + 1)

    def go_to_previous_page(self, dialog, state=None):
        """Tells the page manager to show the previous page."""
        page_manager = dialog.widget_references.get('page_manager')
        if page_manager:
            page_manager.show_page(page_manager.current_page - 1)

     #DEBUG FUNCTIONS
    def get_config(self, widget):
        options = {}
        for i in widget.keys():
            value = widget.cget(i)
            options[i] = value.string if type(value) is _tkinter.Tcl_Obj else value
        return options, widget.winfo_parent()
    
    #def print_variable_values(self, widget):
    #        # Retrieve all variable names associated with the widget
    #    variable_names = widget.tk.splitlist(widget.tk.call('info', 'vars'))
    #    
    #    # Print the values of these variables
    #    for var_name in variable_names:
    #        try:
    #            # Check if the variable is not an array
    #            value = widget.getvar(var_name)
    #            print(f"Variable '{var_name}' has value: {value}")
    #        except tk.TclError as e:
    #            pass  


class KeyToggle:
    def __init__(self, base_class, master=None, **kwargs):
        # Dynamically create a new class that inherits from both KeyToggle and the base_class
        self.__class__ = type(self.__class__.__name__, (self.__class__, base_class), {})
        base_class.__init__(self, master, **kwargs)  # Initialization of the base class
        self.visibility_on = False


class HyperlinkLabel:
    """
    A class that creates a label-like widget with a portion of the text behaving as a hyperlink.
    Uses grid without extra spacing to keep the text segments tightly together.
    """
    def __init__(self, base_class, master=None, class_config=None, **kwargs):
        """
        :param base_class: The base Tk widget class to inherit from (e.g., tk.Label).
        :param master: The parent widget.
        :param class_config: Dictionary containing at least:
            'url':        The URL to open when the hyperlink is clicked
            'text':       The full text to display
            'link_text':  The portion of 'text' that should be clickable
        :param kwargs: Additional parameters to pass to the base class initializer.
        """
        # Dynamically create a new class that inherits from this and the base_class
        self.__class__ = type(self.__class__.__name__, (self.__class__, base_class), {})
        base_class.__init__(self, master, **kwargs)
        self.root = self.winfo_toplevel().master


        # Retrieve parameters
        self.url = class_config.get('url')
        self.text = class_config.get('text', "")
        self.link_text = class_config.get('link_text', "")

        # If link_text is empty, fall back to the URL as link_text
        if not self.link_text:
            self.link_text = self.url

        # Split the full text into before_link and after_link segments
        if self.link_text in self.text:
            before_link, after_link = self.text.split(self.link_text, 1)
        else:
            before_link, after_link = self.text, ""

        # Label for the text before the hyperlink
        if before_link:
            before_label = tb.Label(self, text=before_link, border=0, borderwidth=0)
            # Grid with no padding
            before_label.grid(row=0, column=0, sticky="w", padx=(2,0), pady=0)
        
        if '\n' in before_link:
            self.link_text = f'\n{self.link_text}'
        # Label for the hyperlink portion
        self.link_label = tb.Label(self, text=self.link_text, foreground="blue", cursor="hand2", underline=False, border=0, borderwidth=0)
        self.link_label.grid(row=0, column=1, sticky="w", padx=0, pady=0)

        # Bind hover and click events
        self.link_label.bind("<Enter>", self.on_enter)
        self.link_label.bind("<Leave>", self.on_leave)
        self.link_label.bind("<Button-1>", lambda e, url=self.url: self.root.gui_utils.open_link(url, show_link=True))

        # Label for the text after the hyperlink
        if after_link:
            after_label = tb.Label(self, text=after_link, border=0, borderwidth=0)
            after_label.grid(row=0, column=2, sticky="w", padx=0, pady=0)

        self.grid_columnconfigure(0, pad=0)
        self.grid_columnconfigure(1, pad=0)
        self.grid_columnconfigure(2, pad=0)

    def on_enter(self, event):
        """
        Change the hyperlink color and cursor on hover.
        """
        event.widget.config(foreground="red", cursor="hand2")

    def on_leave(self, event):
        """
        Revert the hyperlink color and cursor when the mouse leaves.
        """
        event.widget.config(foreground="blue", cursor="arrow")


class PageManager:
    """
    A custom widget class that acts as a container for multiple "pages" (frames).
    It manages showing one page at a time.
    """
    def __init__(self, base_class, master=None, class_config=None, **kwargs):
        self.__class__ = type(self.__class__.__name__, (self.__class__, base_class), {})
        base_class.__init__(self, master, **kwargs)

        self.pages = {}
        self.current_page = 0
        self.dialog_instance = None
        self.parent_window = None

    def add_page(self, page_num, page_frame):
        """Adds a page (frame) to the manager's collection."""
        self.pages[page_num] = page_frame
        page_frame.grid(row=0, column=0, sticky="nsew")
        page_frame.grid_remove()

    def show_page(self, page_num):
        """Shows the specified page and hides all others."""
        if page_num in self.pages:
            self.current_page = page_num
            for num, page in self.pages.items():
                if num == page_num:
                    page.grid()
                else:
                    page.grid_remove()
            
            if self.dialog_instance:
                self.dialog_instance.widget_references['indicators'].set_page(page_num)
                self.dialog_instance.dialog.update_idletasks()
                self.dialog_instance.center_dialog(self.parent_window)


class PageIndicators:
    """A custom widget that displays the step-by-step progress indicators."""
    def __init__(self, base_class, master=None, class_config=None, **kwargs):
        self.__class__ = type(self.__class__.__name__, (self.__class__, base_class), {})
        base_class.__init__(self, master, **kwargs)

        self.page_titles = class_config.get('pages', [])
        self.indicators = []

        style = ttk.Style()
        style.configure('completed.Indicator.TLabel', background='#28a745', foreground='#ffffff')
        style.configure('current.Indicator.TLabel', background='#2780e3', foreground='#ffffff')
        style.configure('future.Indicator.TLabel', background='#6c757d', foreground='#ffffff')

        for i, title in enumerate(self.page_titles):
            label = ttk.Label(self, text=f"{i+1}. {title}", style='future.Indicator.TLabel',
                              borderwidth=1, relief='solid', padding=(5, 5), anchor='center')
            label.pack(side='left', fill='x', expand=True, in_=self)
            self.indicators.append(label)

    def set_page(self, current_page):
        """Updates the visual state of the indicator labels."""

        for i, label in enumerate(self.indicators):
            page_num = i + 1
            check_text = ""
            style_name = ""

            if page_num < current_page:
                style_name = "completed.Indicator.TLabel"
                check_text = " ✓"
            elif page_num == current_page:
                style_name = "current.Indicator.TLabel"
            else:
                style_name = "future.Indicator.TLabel"
            
            label.config(style=style_name, text=f"{page_num}. {self.page_titles[i]}{check_text}")