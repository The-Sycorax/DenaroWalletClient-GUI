import sys
import os
import re

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, font
from tktooltip import ToolTip

import ttkbootstrap as tb
from ttkbootstrap.constants import *
from PIL import ImageTk, Image

import atexit

import time
import json
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, field
from typing import Optional
import webbrowser
from datetime import datetime
import logging
import threading

# Get the absolute path of the directory containing the current script.
dir_path = os.path.dirname(os.path.realpath(__file__))

# Insert folder paths for modules
sys.path.insert(0, dir_path + "/denaro")
sys.path.insert(0, dir_path + "/denaro/wallet")
sys.path.insert(0, dir_path + "/denaro/wallet/utils")

import wallet_client
from denaro.wallet.utils.wallet_generation_util import sha256, generate_bip39_mnemonic_pattern
from denaro.wallet.utils.thread_manager import WalletThreadManager
from denaro.wallet.utils.tkinter_utils.custom_auto_complete_combobox import AutocompleteCombobox
from denaro.wallet.utils.tkinter_utils.custom_dialog import CustomDialog
from denaro.wallet.utils.tkinter_utils.dialogs import Dialogs
from denaro.wallet.utils.tkinter_utils.custom_popup import CustomPopup
from denaro.wallet.utils.tkinter_utils.mutually_exclusive_checkbox import MutuallyExclusiveCheckbox
import denaro.wallet.utils.tkinter_utils.universal_language_translator as universal_language_translator

# Patterns for SENSITIVE data that must be redacted from logs and securely deleted.
sensitive_patterns = [
    re.compile(wallet_client.ADDRESS_PATTERN), # Denaro Wallet Address
    re.compile(generate_bip39_mnemonic_pattern()),  # 12-word BIP39 Mnemonic
    re.compile(r'^(0x)?[0-9a-fA-F]{32,}$'),    # Long Hex (Private Keys, Hashes)
]
        
# Patterns for NON-SENSITIVE data that should simply not be translated.
non_translatable_patterns = [
    re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?$'),     # IP Addresses
    re.compile(r'^(https?://|ftp://|www\.)[^\s]+$'),                # URLs
    re.compile(r'^Denaro Wallet Client v[0-9\.\-a-zA-Z]+\sGUI.*$'), # Title
]

class BasePage(ttk.Frame):
    def __init__(self, parent, root, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.root = root        
        #self.create_widgets()

    #def create_widgets(self):
    #    pass


class AccountPage(BasePage):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        
        if self.root.disable_exchange_rate_features:
            self.column_sort_order = {"Balance": False, "Pending": False}
        else:
            self.column_sort_order = {"Balance": False, "Pending": False, "Value": False}

        self.create_widgets()  # Create and place widgets
        self.configure_layout() # Configure the grid layout of the AccountPage
        # Dynamically identify selectable widgets
        self.root.selectable_widgets.extend(self.root.gui_utils.identify_selectable_widgets(self))


    def configure_layout(self):
        # Grid and column layout for page
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Balance frame
        self.balance_frame.grid_rowconfigure(0, weight=1)
        self.balance_frame.grid_rowconfigure(1, weight=1)
        self.balance_frame.grid_columnconfigure(0, weight=0)  # Logo column
        self.balance_frame.grid_columnconfigure(1, weight=1)  # Text column
        self.balance_frame.grid(row=0, column=0, sticky='ew')
        
        # Logo placement
        self.logo_container.grid(row=0, column=0, rowspan=2, sticky='nw')
    
        # Balance and value labels
        

        if self.root.disable_exchange_rate_features:
            self.total_balance_text.grid(row=0, column=1, sticky='nw', padx=5,)
        else:
            self.denaro_price_text.grid(row=0, column=1, sticky='nw', padx=5, pady=5)
            self.total_balance_text.grid(row=1, column=1, sticky='nw', padx=5,)
            self.total_value_text.grid(row=1, column=1, sticky='sw', padx=5, pady=(0, 5))

        # Accounts frame
        self.accounts_frame.grid_columnconfigure(0, weight=1)
        self.accounts_frame.grid_rowconfigure(0, weight=1)
        self.accounts_frame.grid(row=1, column=0, sticky='nsew')
        
        # TreeView and scrollbar
        self.accounts_tree.grid(row=0, column=0, sticky='nsew')
        self.accounts_tree_scrollbar.grid(row=0, column=1, sticky='ns')
        
        # Refresh balance button
        self.refresh_balance_button.grid(row=1, column=2, sticky='w', padx=5, pady=5)
    

    def create_widgets(self):
        # Balance and accounts view for the "Account" page
        self.balance_frame = tb.Frame(self, style='balance_frame.TFrame')
        
        # Logo container frame
        self.logo_container = tb.Frame(self.balance_frame, borderwidth=2, relief="solid", padding=1, style='balance_frame.TFrame')
        logo = Image.open("./denaro/gui_assets/denaro_logo.png")
        logo = logo.resize((60, 60), Image.LANCZOS)
        logo = ImageTk.PhotoImage(logo)
        self.logo_label = tb.Label(self.logo_container, image=logo, background='black')
        self.logo_label.image = logo
        self.logo_label.pack(padx=1, pady=1)  # Padding inside the container
        
        #Balance and value labels
        self.total_balance_text = tb.Label(self.balance_frame, text="Total balance:", foreground='white', background='black')
        
        if not self.root.disable_exchange_rate_features:
            self.denaro_price_text = tb.Label(self.balance_frame, text="DNR/USD Price:", foreground='white', background='black')        
            self.total_value_text = tb.Label(self.balance_frame, text="Total Value:", foreground='white', background='black')

        # Accounts frame
        self.accounts_frame = tb.Frame(self)
        
        # TreeView and scrollbar
        if self.root.disable_exchange_rate_features:
            self.columns = ("Address", "Balance", "Pending")
        else:
            self.columns = ("Address", "Balance", "Pending", "Value")
            
        self.accounts_tree = ttk.Treeview(self.accounts_frame, columns=self.columns, show='headings', selectmode='browse')
        self.accounts_tree_scrollbar = ttk.Scrollbar(self.accounts_frame, orient="vertical", command=self.accounts_tree.yview)
        self.accounts_tree.configure(yscrollcommand=self.accounts_tree_scrollbar.set)
        
        # Bind the click event to the Treeview widget
        self.accounts_tree.bind("<Button-1>", self.root.gui_utils.on_treeview_click)
        
        # Create a font object for measuring text width
        self.treeview_font = font.nametofont("TkDefaultFont")
        
        # Calculate minimum width for each column based on the title
        self.column_min_widths = {}
        for col in self.columns:
            self.accounts_tree.heading(col, text=col)
            title_width = self.treeview_font.measure(col) + 40  # Extra space for padding
            self.column_min_widths[col] = title_width
            self.accounts_tree.column(col, minwidth=self.column_min_widths[col], stretch=tk.YES)    

        # Configure the striped row tags
        self.accounts_tree.tag_configure('oddrow', background='white')  # Light gray color for odd rows
        self.accounts_tree.tag_configure('evenrow', background='#cee0e7')  # A slightly different shade for even row 
        
        if self.root.disable_exchange_rate_features:
            heading_names = ["Balance", "Pending"]
        else:
            heading_names = ["Balance", "Pending", "Value"]
        
        for col in heading_names:
            self.accounts_tree.heading(col, text=col+" ⥮", command=lambda _col=col: self.root.gui_utils.sort_treeview_column(self.accounts_tree, _col))
     
        # Refresh balance button
        self.refresh_balance_button = tb.Button(self.balance_frame, text="Refresh Balance", state='disabled')
        self.refresh_balance_button.config(command=lambda: self.root.gui_utils.refresh_balance())


class SendPage(BasePage):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        self.create_widgets()  # Create and place widgets
        self.configure_layout() # Configure the grid layout of the AccountPage
        # Dynamically identify selectable widgets
        self.root.selectable_widgets.extend(self.root.gui_utils.identify_selectable_widgets(self))


    def configure_layout(self):
        # Grid and column layout for page
        for i in range(4):
            self.grid_rowconfigure(i, weight=0)        
        self.grid_rowconfigure(6, weight=1)  # Allow the tx_log row to expand
        self.grid_columnconfigure(0, weight=0)  # Adjust if you want the first column to also expand
        self.grid_columnconfigure(1, weight=1)  # Ensure column 1 can expand
        self.grid_columnconfigure(2, weight=1)  # Ensure column 2 can expand, for tx_log and valid_recipient_address
        
        # Send from
        self.send_from_label.grid(row=0, column=0, sticky='w', padx=10, pady=5)
        self.send_from_combobox.grid(row=0, column=1, sticky='w', padx=5, pady=5)
        
        # Amount        
        self.amount_label.grid(row=1, column=0, sticky='w', padx=10, pady=0)
        self.amount_inner_frame.grid(row=1, column=1, sticky='w', padx=5, pady=0)
        self.amount_entry.pack(side='left')
        self.half_amount_button.pack(side='left', padx=(5, 0), pady=0)
        self.max_amount_button.pack(side='left', padx=(5, 0), pady=0)

        #self.amount_entry.grid(row=1, column=1, sticky='w', padx=5, pady=0)
        #self.max_amount_button.grid(row=1, column=2)
        
        # Recipient
        self.recipient_label.grid(row=2, column=0, sticky='w', padx=10, pady=5)
        self.recipient_inner_frame.grid(row=2, column=1, sticky='w', padx=5, pady=5)
        self.recipient_entry.pack(side='left')
        self.valid_recipient_address.pack(side='left', padx=(5, 0))
        
        # Transaction message
        self.message_label.grid(row=3, column=0, sticky='w', padx=10, pady=5)
        self.message_inner_frame.grid(row=3, column=1, sticky='w', padx=5, pady=5)   
        self.message_entry.pack(side='left')
        self.max_message_entry_length_message.pack(side='left', padx=(5, 0))

        #self.message_entry.grid(row=3, column=1, sticky='w', padx=5, pady=5)
        
        #Send button
        self.send_button.grid(row=4, column=0, padx=0, pady=10)
        
        #Transaction log
        self.tx_log_label.grid(row=5, column=0, sticky='w', padx=10, pady=5)
        self.tx_log.grid(row=6, column=0, columnspan=3, sticky='nsew')

        #Clear transaction log button
        self.clear_tx_log.grid(row=5, column=0, columnspan=4,sticky='e', padx=5, pady=5)


    def create_widgets(self):
        # Send from
        self.send_from_label = tb.Label(self, text="Send From:")        
        self.send_from_combobox_text = tk.StringVar()
        self.send_from_combobox_text.trace_add("write", self.check_send_params)
        self.send_from_combobox = ttk.Combobox(self, textvariable=self.send_from_combobox_text, width=50, state='disabled')
        self.send_from_combobox['values'] = []
        
        # Amount
        self.amount_inner_frame = tb.Frame(self)
        self.amount_label = tb.Label(self, text="Amount:")        
        vcmd = self.register(self.validate_send_amount_input)        
        self.amount_entry_text = tk.StringVar()
        self.amount_entry_text.trace_add("write", self.check_send_params)
        self.amount_entry = tb.Entry(self.amount_inner_frame, validate="key", validatecommand=(vcmd, '%P'), textvariable=self.amount_entry_text, width=10,state='disabled')
        self.half_amount_button = tb.Button(self.amount_inner_frame, text="Half", state='disabled')
        self.half_amount_button.config(command=lambda: self.set_send_amount(half=True))
        self.max_amount_button = tb.Button(self.amount_inner_frame, text="Max", state='disabled')
        self.max_amount_button.config(command=lambda: self.set_send_amount())

        # Recipient
        self.recipient_inner_frame = tb.Frame(self)        
        self.recipient_label = tb.Label(self, text="Recipient Address:")        
        self.recipient_entry_text = tb.StringVar()
        self.recipient_entry_text.trace_add("write", self.check_send_params)
        self.recipient_entry = tb.Entry(self.recipient_inner_frame, validate="focusout", textvariable=self.recipient_entry_text, width=50, state='disabled')        
        self.valid_recipient_address = tb.Label(self.recipient_inner_frame)
        
        # Transaction message
        self.message_inner_frame = tb.Frame(self)
        self.message_label = tb.Label(self, text="Transaction Message:")
        self.message_entry_text = tb.StringVar()    
        self.message_entry_text.trace_add("write", self.check_send_params)
        self.message_entry = tb.Entry(self.message_inner_frame, width=30, textvariable=self.message_entry_text, state='disabled')
        self.max_message_entry_length_message = tb.Label(self.message_inner_frame)

        # Send button
        self.send_button = tb.Button(self, text="Send", state='disabled')
        self.send_button.config(command=lambda: self.root.wallet_operations.tx_auth())
        
        #Transaction log
        self.tx_log_label = tb.Label(self, text="Log:")
        self.tx_log = scrolledtext.ScrolledText(self)        
        tx_log_separator = f'----------------------------------------------------------------\n'
        self.tx_log.insert(tk.INSERT, tx_log_separator)
        self.tx_log.config(state='disabled')

        #Clear transaction log button
        self.clear_tx_log = tb.Button(self, text="Clear")
        self.clear_tx_log.config(command=lambda: (self.clear_tx_log.focus_set(), self.tx_log.config(state='normal'), self.tx_log.delete('1.0', tk.END), self.tx_log.insert(tk.INSERT, tx_log_separator), self.tx_log.config(state='disabled')))


    def check_send_params(self, *args):

        if self.recipient_entry.get() and self.validate_recipient_address(self.recipient_entry.get()):
            self.valid_recipient_address.config(text="Valid Denaro Address ✓", foreground='green')
            if self.send_from_combobox.get() and self.amount_entry.get():
                if float(self.amount_entry.get()) != 0.0 and self.root.stored_data.wallet_loaded:
                    self.send_button.config(state='normal')
                else:
                    self.send_button.config(state='disabled')
            else:
                self.send_button.config(state='disabled')
        else:
            if self.recipient_entry.get():
                self.valid_recipient_address.config(text="Invalid Denaro Address ✖", foreground='red')
            else:
                self.valid_recipient_address.config(text="", foreground='')
            self.send_button.config(state='disabled')
        
        if self.send_from_combobox.get() == "":
            self.max_amount_button.config(state='disabled')
            self.half_amount_button.config(state='disabled')
        else:
            self.max_amount_button.config(state='normal')
            self.half_amount_button.config(state='normal')

        message_extension = wallet_client.transaction_message_extension
        max_message_length = 255 - len(message_extension) + 3

        max_len_str = f'{abs(len(self.message_entry_text.get()))}/{max_message_length}'
        if len(self.message_entry_text.get()) >= int(max_message_length):
            self.max_message_entry_length_message.config(text=f"{max_message_length}/{max_message_length} (Max Message Length Reached)", foreground='red')
            self.message_entry_text.set(self.message_entry_text.get()[:int(max_message_length)])
        if len(self.message_entry_text.get()) < int(max_message_length):
            self.max_message_entry_length_message.config(text=max_len_str, foreground='')


    def validate_recipient_address(self, content):
        if re.match(wallet_client.ADDRESS_PATTERN, content):
            return True
        return False
    

    def validate_send_amount_input(self, P):
        # P is the value of the entry if the edit is allowed
        if P.strip() == "":
            # Allow the empty string so that it can clear the entry field
            return True
        try:
            float(P)
            return True
        except ValueError:
            return False 
    

    def set_send_amount(self, half=False):
        """
        Set the maximum amount to send based on the balance of the selected address.
        
        This function retrieves the sender address from the combobox, then searches through the stored
        balance data to find the matching address. It sets the amount entry text to the balance of the
        selected address. If the `half` parameter is True, it will set the amount to half of the current amount.
        """
        sender = self.send_from_combobox.get()
        
        # Define the decimal places
        decimal_places = Decimal('0.000000')
        
        # Handle halving the current amount if requested
        if half and self.amount_entry_text.get():
            try:
                current_amount = Decimal(self.amount_entry_text.get())
                if current_amount != Decimal('0.000000'):
                    balance_amount = (current_amount / 2).quantize(decimal_places, rounding=ROUND_DOWN)
                    self.amount_entry_text.set(str(balance_amount))
                    return
            except ValueError as e:
                print(f"Error converting current amount: {e}")
                return
        
        # Check if balance data is available
        if not half and self.root.stored_data.balance_data:
            balance_data = self.root.stored_data.balance_data['balance_data']
            
            # Combine 'addresses' and 'imported_addresses' into one list for iteration
            all_addresses = balance_data.get('addresses', []) + balance_data.get('imported_addresses', [])
            
            # Loop through all addresses to find the sender address
            for address in all_addresses:
                if sender == address['address']:
                    # Convert balance to Decimal and set the amount with controlled decimal places
                    try:
                        balance_amount = Decimal(address['balance']['amount']).quantize(decimal_places, rounding=ROUND_DOWN)
                        self.amount_entry_text.set(str(balance_amount))
                    except ValueError as e:
                        print(f"Error converting balance amount for address {sender}: {e}")
                    break  # Exit the loop once the sender address is found


class SettingsPage(BasePage):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        # Currency related attributes
        self.prev_currency_code = None
        self.currency_code_valid = False
        self.currency_code = ""
        self.currency_symbol = ""

        # --- Language related attributes ---
        self.prev_language = None
        self.language_valid = False
        self.language = ""
        # ----------------------------------------

        # --- Translation module change handling flags ---
        self._is_updating_translation_module = False
        # ----------------------------------------

        self.keep_save_button_disabled = False

        self.create_widgets()  # Create and place widgets
        self.configure_layout() # Configure the grid layout of the AccountPage
        self.update_save_button_state()

        # Dynamically identify selectable widgets
        self.root.selectable_widgets.extend(self.root.gui_utils.identify_selectable_widgets(self))


    def configure_layout(self):
        # Position the currency code related widgets
        if not self.root.disable_exchange_rate_features:
            self.currency_code_inner_frame.grid(row=0, column=0, sticky='ew', padx=10)
            self.currency_code_label.pack(side='left', padx=5, pady=5)
            self.currency_code_combobox.pack(side='left', padx=5, pady=5)
            self.valid_currency_code.pack(side='left', padx=5, pady=5)

        # Position the Denaro Node widgets within the denaro_node_frame
        self.denaro_node_frame.grid(row=1, column=0, sticky='w', padx=15, pady=10, ipady=5)        
        # Address label and entry
        self.denaro_node_address_label.grid(row=1, column=0, sticky='w', padx=5, pady=(10, 0))
        self.denaro_node_address_frame.grid(row=2, column=0, sticky='ew', padx=5)
        self.denaro_node_address_entry.pack(side='left', fill='x', expand=True)        
        # Colon (:) label
        self.denaro_node_colon.grid(row=2, column=1, sticky='ew')  # Ensure it sticks to east-west to center the colon        
        # Port label and entry
        self.denaro_node_port_label.grid(row=1, column=2, sticky='w', padx=5, pady=(10, 0))
        self.denaro_node_port_frame.grid(row=2, column=2, sticky='ew', padx=5)
        self.denaro_node_port_entry.pack(side='left', fill='x', expand=True)        
        # Node validation checkbox
        self.disable_node_validation_checkbox.grid(row=3, column=0, sticky='w', padx=5, pady=10)
        self.test_connection_button.grid(row=3, column=2, sticky='e', padx=5, pady=10)
        self.node_validation_msg_label.grid(row=3, column=0, sticky='w', padx=5, pady=(75,0))
        
        # Ensure the denaro_node_frame columns do not affect the overall layout
        self.denaro_node_frame.columnconfigure(0, weight=1)
        self.denaro_node_frame.columnconfigure(1, weight=0)
        self.denaro_node_frame.columnconfigure(2, weight=1)
        
        # --- Position the language translation settings frame ---
        self.language_translation_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=5)
        
        # Translation Module section
        self.translation_module_section_label.pack(fill='x', padx=5, pady=(5, 2))
        self.translation_module_frame.pack(fill='x', padx=(25, 5), pady=2)
        self.argostranslate_checkbox.pack(side='left', padx=5, pady=2)
        self.deep_translator_checkbox.pack(side='left', padx=5, pady=2)
        
        # Translation module label (below checkboxes)
        self.translation_module_label.pack(fill='x', padx=(25, 5), pady=(0, 5))
        
        # Language selection widgets inside the frame
        self.language_frame.pack(fill='x', padx=5, pady=5)
        self.language_label.pack(side='left', padx=5, pady=5)
        self.language_combobox.pack(side='left', padx=5, pady=5)
        self.valid_language_label.pack(side='left', padx=5, pady=5)
        
        # Language cache widgets
        self.language_cache_frame.pack(fill='x', padx=5, pady=5)
        self.language_cache_label.pack(side='left', padx=5, pady=5)
        self.language_cache_combobox.pack(side='left', padx=5, pady=5)
        self.clear_cache_button.pack(side='left', padx=5, pady=5)
        # ---------------------------------------------

        # Save config button
        self.save_config_frame.grid(row=3, column=0, sticky='we', padx=10)
        self.save_config_button.pack(pady=10, side='right')


    def create_widgets(self):
        # Settings Page Layout
        #######################################################################################        
        #Currency code
        if not self.root.disable_exchange_rate_features:
            self.currency_code_inner_frame = tb.Frame(self)
            self.currency_code_label = tb.Label(self.currency_code_inner_frame, text="Default Currency:")  
            self.valid_currency_code = tb.Label(self.currency_code_inner_frame)
    
            #Initialize currency code function
            wallet_client.is_valid_currency_code()
            
            #Get list of valid codes
            self.currency_codes = list(wallet_client.is_valid_currency_code.valid_codes.keys())
    
            # Create custom Combobox
            self.currency_code_combobox = AutocompleteCombobox(self.currency_code_inner_frame, width=20, completevalues=self.currency_codes, state='normal')        
            
            # Add separators at specific indices
            self.separators = ["--- Fiat Currencies ---", "--- Crypto Currencies ---"]        
            self.root.gui_utils.add_combobox_separator_at_index(self.currency_code_combobox, self.separators[0], 0)  # Adds the first separator
            self.root.gui_utils.add_combobox_separator_at_index(self.currency_code_combobox, self.separators[1], 162)  # Adds the second separator        
            self.currency_code_combobox.current(147)
            self.last_valid_selection = self.currency_code_combobox.current()        
            self.currency_code_combobox.bind('<<ComboboxSelected>>', self.root.gui_utils.on_currency_code_combobox_select)
            
            # Validate currency code on init
            self.after(100, self.validate_currency_code)
            #Validate currency code on each write
            self.currency_code_combobox.var.trace_add("write", self.validate_currency_code)

        self.denaro_node_frame = tb.LabelFrame(self, text="Denaro Node Configuration", width=20)
        self.denaro_node_address_label = tb.Label(self.denaro_node_frame, text="Address")        
        self.denaro_node_address_frame = tb.Frame(self.denaro_node_frame)
        self.denaro_node_address_entry = tb.Entry(self.denaro_node_address_frame, validate="focusout", width=30)#, state='disabled')
        self.denaro_node_address_entry_text = tb.StringVar()        
        self.denaro_node_address_entry_text.trace_add("write", self.on_node_field_change)
        self.denaro_node_address_entry["textvariable"] = self.denaro_node_address_entry_text

        self.denaro_node_colon = tb.Label(self.denaro_node_frame, text=":")        
        
        self.denaro_node_port_label = tb.Label(self.denaro_node_frame, text="Port")
        self.denaro_node_port_frame = tb.Frame(self.denaro_node_frame)  
        self.denaro_node_port_entry = tb.Entry(self.denaro_node_port_frame, validate="focusout", width=30)
        self.denaro_node_port_entry_text = tb.StringVar()
        self.denaro_node_port_entry_text.trace_add("write", self.on_node_field_change)
        self.denaro_node_port_entry["textvariable"] = self.denaro_node_port_entry_text       
        
        self.disable_node_validation_checkbox = tk.Checkbutton(self.denaro_node_frame, text='Disable Node Validation')
        self.disable_node_validation_var = tk.BooleanVar()
        self.disable_node_validation_var.trace_add("write", self.on_node_field_change)
        self.disable_node_validation_checkbox["variable"] = self.disable_node_validation_var

        self.test_connection_button = tb.Button(self.denaro_node_frame, text="Test Connection")
        self.test_connection_button.config(command=lambda: self.test_node_connection())
        self.node_validation_msg_label = tb.Label(self.denaro_node_frame, text="")

        
        # --- Language Translation Settings LabelFrame ---
        self.language_translation_frame = tb.LabelFrame(self, text="Language Translation Settings")
        
        # --- Translation Module section ---
        self.translation_module_section_label = tb.Label(self.language_translation_frame, text="Translation Module:")
        self.translation_module_frame = tb.Frame(self.language_translation_frame)
        with self.root.translation_engine.no_translate():
            self.argostranslate_checkbox = MutuallyExclusiveCheckbox(
                self.translation_module_frame, 
                text='Argos Translate',
                callback=self.on_translation_module_change
            )
        with self.root.translation_engine.no_translate():
            self.deep_translator_checkbox = MutuallyExclusiveCheckbox(
                self.translation_module_frame, 
                text='Deep Translator',
                callback=self.on_translation_module_change
            )
        # Bind the checkboxes together for mutual exclusivity
        MutuallyExclusiveCheckbox.bind_group(self.argostranslate_checkbox, self.deep_translator_checkbox)
        
        self.translation_module_label = tb.Label(self.language_translation_frame, text="", foreground='gray')
        # ------------------------------------------

        # --- Language widget creation ---
        self.language_frame = tb.Frame(self.language_translation_frame)
        self.language_label = tb.Label(self.language_frame, text="Language:")
        
        # The combobox uses the display names (the dictionary values)
        #with translation_engine.no_translate():
        self.language_display_names = list(self.root.translation_engine.language_map.values())
        self.language_combobox = AutocompleteCombobox(self.language_frame, width=20, completevalues=self.language_display_names, state='normal')
    
        # Validate language on init
        self.after(100, self.validate_language)
        # Validate language on each write
        self.language_combobox.var.trace_add("write", self.validate_language)
        
        self.valid_language_label = tb.Label(self.language_frame)
        # ------------------------------------------

        # --- Language cache widgets ---
        self.language_cache_frame = tb.Frame(self.language_translation_frame)
        self.language_cache_label = tb.Label(self.language_cache_frame, text="Language Cache:")
        self.language_cache_combobox = tb.Combobox(self.language_cache_frame, state='readonly', width=30)
        self.language_cache_combobox.bind('<<ComboboxSelected>>', lambda e: self.update_clear_cache_button_state())
        self.clear_cache_button = tb.Button(self.language_cache_frame, text="Clear", command=self.clear_language_cache)
        self.update_language_cache_list()
        # ------------------------------------------

        # Save config button
        self.save_config_frame = tb.Frame(self)
        self.save_config_button = tb.Button(self.save_config_frame, text="Save Settings", state='disabled')
        self.save_config_button.config(command=lambda: self.root.config_handler.save_config())
        #######################################################################################
        # End of Settings Page Layout


    def validate_currency_code(self, *args):
        self.current_selection = self.currency_code_combobox.get()
        # Check if the combo box selection has changed since the last check
        if self.current_selection != self.prev_currency_code:
            self.currency_code_valid, self.currency_symbol = wallet_client.is_valid_currency_code(code=self.current_selection, get_return=True) if self.current_selection else (False, "$")
            self.root.stored_data.currency_symbol = self.currency_symbol
            if self.currency_code_valid:
                self.valid_currency_code.config(text="Valid Currency Code ✓", foreground='green')
                #self.save_config_button.config(state='normal')
                self.currency_code = self.current_selection
                self.root.stored_data.currency_code = self.current_selection
                
                self.last_valid_selection = self.currency_code_combobox.current()
                self.root.account_page.denaro_price_text.config(text=f'DNR/{self.currency_code_combobox.get()} Price: {self.root.stored_data.currency_symbol}')
            else:
                self.valid_currency_code.config(text="Invalid Currency Code ✖", foreground='red')
                #self.save_config_button.config(state='disabled')
                self.currency_code = "USD"
                self.root.account_page.denaro_price_text.config(text=f'DNR/USD Price: {self.root.stored_data.currency_symbol}')                
            self.root.event_handler.price_timer = 0    
            # Update last valid selection
            #last_valid_selection = currency_code_combobox.current()
            self.prev_currency_code = self.current_selection        
            self.update_save_button_state() # Update button state on validation change

        if not self.currency_code_combobox['values'][0] == self.separators[0]:
            self.root.gui_utils.add_combobox_separator_at_index(self.currency_code_combobox, self.separators[0], 0)
        if not self.currency_code_combobox['values'][162] == self.separators[1]:
            self.root.gui_utils.add_combobox_separator_at_index(self.currency_code_combobox, self.separators[1], 162)


    # --- Language validation method ---
    def validate_language(self, *args):
        # The value from the combobox is the display name (e.g., "Deutsch")
        current_display_name = self.language_combobox.get()
    
        # Use the display name for the change-check to prevent re-validation loops
        if current_display_name != self.prev_language:
            # Validate that the display name is one of the valid options
            if current_display_name in self.root.translation_engine.language_map.values():
                self.language_valid = True
                self.valid_language_label.config(text="Valid Language ✓", foreground='green')                
                # Find the corresponding language code (e.g., "de") to store internally
                for code, name in self.root.translation_engine.language_map.items():
                    if name == current_display_name:
                        # self.language now holds the language code
                        self.language = code
                        break
            else:
                self.language_valid = False
                self.valid_language_label.config(text="Invalid Language ✖", foreground='red')
                # Fallback to the English language code
                self.language = "en"
    
            # prev_language should track the display name
            self.prev_language = current_display_name
            self.update_save_button_state()


    def _set_translation_module_state(self, module, update_prev_state=True):
        """Helper method to set translation module checkbox state"""
        self._is_updating_translation_module = True
        try:
            if module == 'argostranslate':
                self.argostranslate_checkbox.set(True)
                self.update_translation_module_label('argostranslate')
            elif module == 'deep-translator':
                self.deep_translator_checkbox.set(True)
                self.update_translation_module_label('deep-translator')
            else:
                # Uncheck both (translation disabled)
                self.argostranslate_checkbox.set(False)
                self.deep_translator_checkbox.set(False)
                self.update_translation_module_label(None)
        finally:
            self._is_updating_translation_module = False

    def on_translation_module_change(self, checkbox, is_checked):
        """Handle changes to translation module checkboxes"""
        # Prevent recursive calls during programmatic updates
        if self._is_updating_translation_module:
            return
        
        argostranslate_checked = self.argostranslate_checkbox.get()
        deep_translator_checked = self.deep_translator_checkbox.get()
        
        # Handle normal state: one checkbox is checked
        if argostranslate_checked:
            self.update_translation_module_label('argostranslate')
            self.language_combobox.config(state='normal')
            self.update_save_button_state()
        elif deep_translator_checked:
            self.update_translation_module_label('deep-translator')
            self.language_combobox.config(state='normal')
            self.update_save_button_state()
        else:
            # Both are unchecked - show confirmation if user manually unchecked one
            # But only if translation is currently enabled (not already disabled)
            current_translation_module = self.root.config_handler.config_values.get('translation_module')
            translation_already_disabled = (current_translation_module is None or current_translation_module == '')
            
            # Determine which module was just unchecked
            module_to_restore = 'argostranslate' if checkbox is self.argostranslate_checkbox else 'deep-translator'
            
            # If translation is already disabled, just update the UI state without showing dialog
            if translation_already_disabled:
                self.update_translation_module_label(None)
                self.language_combobox.config(state='disabled')
                self.update_save_button_state()
                return
            
            def on_user_confirmation(confirmed):
                if not confirmed:
                    # User canceled - restore the checkbox that was just unchecked
                    self._is_updating_translation_module = True
                    try:
                        self._set_translation_module_state(module_to_restore)
                        self.language_combobox.config(state='normal')
                    finally:
                        self._is_updating_translation_module = False
                else:
                    # User confirmed - translation is disabled
                    self.update_translation_module_label(None)
                    self.language_combobox.config(state='disabled')
                    self.update_save_button_state()
            
            # Show confirmation dialog
            self.root.dialogs.confirmation_prompt(
                title="Disable Language Translation",
                msg="Leaving the Translation Module unset will disable language translation and set the current language to English once the settings are saved.\nDo you want to continue?",
                on_complete=on_user_confirmation
            )

    def update_translation_module_label(self, module):
        """Update the translation module label based on selected module"""
        if module == 'argostranslate':
            self.translation_module_label.config(
                text="Argos Translate uses PyTorch and can be resource intensive on slower systems.",
                foreground='green'
            )
        elif module == 'deep-translator':
            self.translation_module_label.config(
                text="Deep Translator may reduce privacy as it uses the Internet and Google Translate.",
                foreground='green'
            )
        else:
            self.translation_module_label.config(text="", foreground='gray')

    def update_language_cache_list(self):
        """Update the language cache combobox with available cache files"""
        cache_dir = "language_cache"
        cache_files = []
        if os.path.exists(cache_dir):
            for filename in os.listdir(cache_dir):
                if filename.endswith('.json'):
                    cache_files.append(filename)
        cache_files.sort()
        self.language_cache_combobox['values'] = cache_files
        if cache_files:
            self.language_cache_combobox.current(0)
            self.update_clear_cache_button_state()
        else:
            self.clear_cache_button.config(state='disabled')
    
    def update_clear_cache_button_state(self):
        """Update the Clear Language Cache button state based on selected cache file content"""
        selected_file = self.language_cache_combobox.get()
        if not selected_file:
            self.clear_cache_button.config(state='disabled')
            return
        
        cache_dir = "language_cache"
        cache_file_path = os.path.join(cache_dir, selected_file)
        
        if os.path.exists(cache_file_path):
            try:
                with open(cache_file_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    if cache_data and len(cache_data) > 0:
                        # Cache has content - enable button
                        self.clear_cache_button.config(state='normal')
                    else:
                        # Cache is empty - disable button
                        self.clear_cache_button.config(state='disabled')
            except (json.JSONDecodeError, ValueError, IOError):
                # If file is invalid JSON or can't be read, disable button
                self.clear_cache_button.config(state='disabled')
        else:
            # File doesn't exist - disable button
            self.clear_cache_button.config(state='disabled')

    def clear_language_cache(self):
        """Clear the selected language cache file"""
        selected_file = self.language_cache_combobox.get()
        if not selected_file:
            return
        
        cache_dir = "language_cache"
        cache_file_path = os.path.join(cache_dir, selected_file)
        
        if os.path.exists(cache_file_path):
            try:
                # Check if cache file has content before clearing
                cache_has_content = False
                try:
                    with open(cache_file_path, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                        if cache_data and len(cache_data) > 0:
                            cache_has_content = True
                except (json.JSONDecodeError, ValueError):
                    # If file is invalid JSON or empty, consider it already cleared
                    cache_has_content = False
                
                # Clear the file contents but don't delete it
                with open(cache_file_path, 'w', encoding='utf-8') as f:
                    json.dump({}, f, indent=2, ensure_ascii=False)
                
                # Update the cache in the translation engine if it's the current cache
                if hasattr(self.root.translation_engine, 'cache_file') and self.root.translation_engine.cache_file == cache_file_path:
                    self.root.translation_engine.cache = {}
                    self.root.translation_engine.reverse_cache = {}
                
                # Update button state after clearing
                self.update_clear_cache_button_state()
                
                # Show popup notification only if cache had content
                if cache_has_content:
                    self.root.custom_popup.add_popup(
                        timeout=5000,
                        prompt=[{"label_config":"text='Language Cache Cleared', background='#2780e3', anchor='center', font='Calibri 10 bold'", "grid_config":"sticky='nsew'"}], 
                        grid_layout_config=[{"grid_row_config":"index=0, weight=1"}, {"grid_column_config":"index=0, weight=1"}]
                    )
            except Exception as e:
                # Silently fail - the button should be disabled if there are no files anyway
                pass

    def validate_node_fields(self, *args):
        check_connection = False
        try:
            if args[1]:
                check_connection = True
        except Exception:
            pass

        address = self.denaro_node_address_entry.get().strip()
        port = self.denaro_node_port_entry.get().strip()
        # Construct the address:port string conditionally including the port
        node = f"{address}:{port}" if port else address
        node_validation_enabled = self.disable_node_validation_var.get()

        _ , node_str, string_valid, return_msg = wallet_client.Verification.validate_node_address([node, False], from_gui=True, check_connection=check_connection, referer="validate_node_fields")
        
        if return_msg != "":
            self.node_validation_msg_label.config(text=return_msg)

            if "ERROR" in return_msg:                
                self.node_validation_msg_label.config(foreground='#ff0000')
            else:
                self.node_validation_msg_label.config(foreground='#008000')
                if 'fade_node_validation_msg_label' in self.root.event_handler.thread_event and 'node_validation_msg_label' in self.root.gui_utils.fade_text_widgets:
                    self.root.gui_utils.fade_text_widgets['node_validation_msg_label']['step'] = 1
                else:
                    self.root.wallet_thread_manager.start_thread("fade_node_validation_msg_label", self.root.gui_utils.fade_text, args=(self.node_validation_msg_label, 'node_validation_msg_label', 5,),)

        if node_str is None:
            node_str = node
        
        if check_connection:
            self.test_connection_button.config(state='normal')

        return node_str, string_valid, node_validation_enabled
                

    def test_node_connection(self):
         self.test_connection_button.config(state='disabled')
         
         if 'fade_node_validation_msg_label' in self.root.event_handler.thread_event:
            self.root.wallet_thread_manager.stop_thread('fade_node_validation_msg_label')

         self.node_validation_msg_label.config(foreground='#008000')
         self.node_validation_msg_label.config(text="Testing connection to node. Please wait...")
         if self.node_validation_msg_label['text'] == "Testing connection to node. Please wait...":
            self.root.update()
            time.sleep(1)
            self.root.wallet_thread_manager.start_thread("validate_node_fields",  self.validate_node_fields, args=(True,),)


    def on_node_field_change(self, *args):
        # Resets the flag to re-enable save button upon field change
        if self.keep_save_button_disabled:
            self.keep_save_button_disabled = False
        self.update_save_button_state()
    

    def update_save_button_state(self):
        # Dynamically updates the 'Save Settings' button state based on validation
        if self.check_setting_changes():
            self.save_config_button.config(state='normal')
        else:
            self.save_config_button.config(state='disabled')


    def check_setting_changes(self):
        # Checks for changes in settings compared to the current configuration
        current_config = self.root.config_handler.config_values
        
        language_selection = self.language_combobox.get().strip()
        
        # Find the corresponding ISO code (e.g., "es") for the selected display name
        selected_language_code = None
        for code, name in self.root.translation_engine.language_map.items():
            if name == language_selection:
                selected_language_code = code
                break
        
        # Compare the selected ISO code with the one stored in the config
        language_changed = (selected_language_code != current_config.get('language'))
        
        if not self.root.disable_exchange_rate_features:
            currency_code = self.currency_code_combobox.get().strip()
            currency_code_changed = (currency_code != current_config.get('default_currency'))

        node_address = self.denaro_node_address_entry.get().strip()
        node_port = self.denaro_node_port_entry.get().strip()

        # Construct the address:port string conditionally including the port
        node = f"{node_address}:{node_port}" if node_port else node_address
        node_changed = (node != current_config.get('default_node', ''))
        node_validation = not self.disable_node_validation_var.get()
        node_validation_changed = (str(node_validation) != current_config.get('node_validation', ''))
        
        # Check translation module changes
        current_translation_module = current_config.get('translation_module')
        if self.argostranslate_checkbox.get():
            new_translation_module = 'argostranslate'
        elif self.deep_translator_checkbox.get():
            new_translation_module = 'deep-translator'
        else:
            # Both are unchecked - translation is disabled
            new_translation_module = None
        
        # Check if translation module changed
        if new_translation_module is None:
            # Translation is disabled - check if it was previously enabled
            translation_module_changed = (current_translation_module is not None and current_translation_module != '')
        else:
            # Translation is enabled - check if it changed
            translation_module_changed = (current_translation_module != new_translation_module)
        
        # --- UPDATED: Final check for enabling save button ---
        if self.root.disable_exchange_rate_features:
            # Check for changes and ensure language is valid
            settings_changed = self.language_valid and (node_changed or node_validation_changed or language_changed or translation_module_changed) and not self.keep_save_button_disabled
        else:
            # Check for changes and ensure BOTH currency and language are valid
            settings_changed = (self.currency_code_valid and self.language_valid) and \
                               (currency_code_changed or node_changed or node_validation_changed or language_changed or translation_module_changed) and \
                               not self.keep_save_button_disabled
        # --------------------------------------------------------
        return settings_changed
    

class BlankPage(BasePage):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        ttk.Label(self, text="TBA").pack(expand=True)


class DenaroWalletGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_handler = ConfigHandler(self)
        self.language = self.config_handler.config_values.get('language', 'en')
        translation_module = self.config_handler.config_values.get('translation_module', 'deep-translator')
        self.translation_engine = universal_language_translator.activate_tkinter_translation(target_language=self.language, translation_module=translation_module, sensitive_patterns=sensitive_patterns, non_translatable_patterns=non_translatable_patterns)

        self.wallet_client_version = f"{wallet_client.wallet_client_version} GUI"
        self.title(self.wallet_client_version)
        self.geometry("1024x576")
        self.minsize(780, 390)
        icon = tk.PhotoImage(file="./denaro/gui_assets/denaro_logo.png")
        self.iconphoto(True, icon)

        self.pages = {}
        self.sidebar_buttons = {}
        self.current_page = None
        self.selectable_widgets = []
        self.active_button = None
        self.disable_exchange_rate_features = True

        self.styles = tb.Style()
        self.stored_data = StoredData()
        self.gui_utils = GUIUtils(self)
        self.wallet_thread_manager = WalletThreadManager(self)
        atexit.register(self.wallet_thread_manager.stop_all_threads)
        self.wallet_operations = WalletOperations(self)
        self.dialogs = Dialogs(self)
        self.custom_popup = CustomPopup(self)
        
        self.menu_items = {}
        self.create_menus()             
        self.configure_styles()
        self.create_main_content_area()
        self.create_sidebar()
        self.create_status_bar()
        self.configure_layout()
        self.show_page("Account")
        self.setup_bindings()   

        self.account_page = self.pages.get("Account")
        self.send_page = self.pages.get("Send")
        self.settings_page = self.pages.get("Settings")
        self.event_handler = EventHandler(self)
        self.callbacks = Callbacks(self)

        self.translation_engine.event_handler = self.event_handler
        self.translation_engine.log.info("Event handler registered with translation engine.")

        self.config_handler.update_config_values()
        
    def _add_menu_item(self, parent_menu, item_type, key, **kwargs):
        # ... implementation from previous step ...
        add_method = getattr(parent_menu, f"add_{item_type}")
        add_method(**kwargs)
        if key and item_type != 'separator':
            index = parent_menu.index('end')
            self.menu_items[key] = (parent_menu, index)

    def set_menu_item_state(self, item_key, state):
        """Sets the state of a menu item using its stable key."""
        if item_key in self.menu_items:
            menu, index = self.menu_items[item_key]
            current_state = str(menu.entrycget(index, 'state'))
            if current_state != state:
                menu.entryconfig(index, state=state)
        else:
            print(f"WARNING: Attempted to configure unknown menu item key: '{item_key}'")

    def get_menu_item_state(self, item_key):
        """Gets the state of a menu item using its stable key."""
        if item_key in self.menu_items:
            menu, index = self.menu_items[item_key]
            return str(menu.entrycget(index, 'state'))
        else:
            print(f"WARNING: Attempted to get state of unknown menu item key: '{item_key}'")
            return None
                
    def create_menus(self):
        # Context Menu for Textboxes
        self.textboxes_context_menu = tb.Menu(self, tearoff=0)
        self._add_menu_item(self.textboxes_context_menu, 'command', 'ctx_cut',    label="Cut",        command=self.gui_utils.cut_text)
        self._add_menu_item(self.textboxes_context_menu, 'command', 'ctx_copy',   label="Copy",       command=self.gui_utils.copy_selection)
        self._add_menu_item(self.textboxes_context_menu, 'command', 'ctx_paste',  label="Paste",      command=self.gui_utils.paste_text)
        self._add_menu_item(self.textboxes_context_menu, 'command', 'ctx_delete', label="Delete",     command=lambda: self.gui_utils.cut_text(delete=True))
        self._add_menu_item(self.textboxes_context_menu, 'separator', None) # No key needed for separators
        self._add_menu_item(self.textboxes_context_menu, 'command', 'ctx_select_all', label="Select All", command=self.gui_utils.select_all_text)
        
        # Context Menu for Treeview
        self.treeview_context_menu = tb.Menu(self, tearoff=0)
        self._add_menu_item(self.treeview_context_menu, 'command', 'tree_copy',     label="Copy",             command=self.gui_utils.copy_selection)
        self._add_menu_item(self.treeview_context_menu, 'command', 'tree_send',     label="Send",             command=lambda: self.gui_utils.address_context_menu_selection(set_address_combobox=True, show_send_page=True))
        self._add_menu_item(self.treeview_context_menu, 'command', 'tree_addr_info',label="Address Information",     command=self.dialogs.address_info)
        self._add_menu_item(self.treeview_context_menu, 'command', 'tree_explorer', label="View on Explorer", command=lambda: self.gui_utils.address_context_menu_selection(view_explorer=True))
        
        # Menu Bar
        self.menu_bar = tb.Menu(self, tearoff=0)
        self.file_menu = tb.Menu(self.menu_bar, tearoff=0)
        self.wallet_menu = tb.Menu(self.file_menu, tearoff=0) # This is for the "Load Wallet" cascade
        self.help_menu = tb.Menu(self.menu_bar, tearoff=0)
        
        # Build the File menu
        self._add_menu_item(self.menu_bar, 'cascade', 'file_menu', label="File", menu=self.file_menu)
        self._add_menu_item(self.file_menu, 'cascade', 'load_wallet_menu', label="Load Wallet", menu=self.wallet_menu)
        self._add_menu_item(self.file_menu, 'command', 'create_wallet', label="Create Wallet", command=self.dialogs.create_wallet_dialog)
        self._add_menu_item(self.file_menu, 'command', 'restore_wallet', label="Restore Wallet") # Add command later
        self._add_menu_item(self.file_menu, 'command', 'backup_wallet', label="Backup Wallet", state='disabled')
        self._add_menu_item(self.file_menu, 'separator', None)
        self._add_menu_item(self.file_menu, 'command', 'generate_address', label="Generate Address", command=lambda: self.wallet_thread_manager.start_thread("generate_address", self.wallet_operations.generate_address, args=()), state='disabled')
        self._add_menu_item(self.file_menu, 'command', 'import_address', label="Import Address", state='disabled')
        self._add_menu_item(self.file_menu, 'separator', None)
        self._add_menu_item(self.file_menu, 'command', 'close_wallet', label="Close Wallet", command=self.gui_utils.close_wallet, state='disabled')
        
        # Build the Help menu
        self._add_menu_item(self.menu_bar, 'cascade', 'help_menu', label="Help", menu=self.help_menu)
        self._add_menu_item(self.help_menu, 'command', 'about', label="About", command=self.dialogs.about_wallet_dialog)
        
        # Final configuration
        self.config(menu=self.menu_bar)
        self.gui_utils.update_wallet_menu()
    

    def setup_bindings(self):
        # Keyboard shortcuts for text operations
        self.bind_class("TEntry", "<Control-x>", self.gui_utils.cut_text)
        self.bind_class("TEntry","<Control-c>", self.gui_utils.copy_selection)
        self.bind_class("TEntry", "<Control-v>", self.gui_utils.paste_text)
        self.bind_class("TEntry", "<Control-a>", self.gui_utils.select_all_text)
        self.bind_class("Text", "<Control-a>", self.gui_utils.select_all_text)
        self.bind_class("Text","<Control-c>", self.gui_utils.copy_selection)
        
        # Bind the click events for Entry
        self.bind_class("TEntry","<Button-3>", self.gui_utils.show_context_menu)
        self.bind_class("TEntry","<Button-1>", self.textboxes_context_menu.unpost())
        
        # Bind the click events for AutocompleteCombobox
        self.bind_class("AutocompleteCombobox","<Button-3>", self.gui_utils.show_context_menu)
        self.bind_class("AutocompleteCombobox","<Button-1>", self.textboxes_context_menu.unpost())

        # Bind the click events for ScrolledText
        self.bind_class("Text","<Button-3>", self.gui_utils.show_context_menu)
        self.bind_class("Text","<Button-1>", self.textboxes_context_menu.unpost())
        
        self.bind_class("Treeview","<Button-3>", self.gui_utils.show_context_menu)
        self.bind_class("Treeview","<Button-1>", self.treeview_context_menu.unpost())
        self.bind_class("Treeview","<Double-Button-1>", self.gui_utils.on_treeview_double_click)

        # Binds for stop button
        self.stop_button.bind("<Enter>", func=lambda e: self.stop_button.config(image=self.stop_button_hover_image))
        self.stop_button.bind("<Leave>", func=lambda e: self.stop_button.config(image=self.stop_button_image))
        self.stop_button.bind("<Button-1>", self.gui_utils.on_stop_button_click)
        ToolTip(self.stop_button, msg="Stop current operation.", delay=1)

        # Bind click event to the root window
        self.bind("<Button-1>", self.gui_utils.on_root_click)
    

    def configure_styles(self):
        
        #Frame styles
        self.styles.configure("blue.TFrame", background="#3fb6d1")
        self.styles.configure("gray.TFrame", background="gray")
        self.styles.configure("mainContent.TFrame", background="white")
        self.styles.configure("balance_frame.TFrame", background="black")        
        
        #Status Bar styles
        self.styles.configure("status_bar_frame.TFrame", background="orange")
        self.styles.configure("statusBar.progressBar.Striped.Horizontal.TProgressbar", troughcolor="orange")        
        
        #Treeview style
        self.styles.configure("Treeview.Heading", background="#2780e3", foreground="black", font=("Calibri", 11), relief="groove")
        self.styles.configure("Treeview", rowheight=30)
        self.styles.map("Treeview", background=[("selected", "#3f5cd1")])        
        
        #Button styles
        self.styles.configure("TButton", background="#2780e3")    
        self.styles.map("TButton", background=[("disabled", "#cccccc"), ("active", "#2780e3")], foreground=[("disabled", "gray")])
        self.styles.configure("menuButtonInactive.TButton", background="gray", forground="gray")        
        
        self.styles.configure("stop_button.TButton", background="orange",borderwidth=0, highlightthickness=0, padx=0, pady=0)
        self.styles.map("stop_button.TButton", background=[("active", "orange")], foreground=[("disabled", "gray")])

        self.config(background='gray')


    def create_main_content_area(self):
        # Page container frame
        self.page_container = tb.Frame(self, style="mainContent.TFrame")
        
        self.pages["Account"] = AccountPage(self.page_container, self)
        self.pages["Send"] = SendPage(self.page_container, self)
        self.pages["Settings"] = SettingsPage(self.page_container, self)
        
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")   


    def create_sidebar(self):
        # Create left sidebar
        self.grid_columnconfigure(0, weight=0)  # Column for sidebar
        self.left_frame_outer = tb.Frame(self, width=150,style="blue.TFrame")        
        self.left_frame_inner = tb.Frame(self.left_frame_outer,style="gray.TFrame")
        
        # Sidebar buttons
        button_names = ["Account", "Send", "Receive", "History", "Advanced", "Settings"]
        for name in button_names:
            self.create_sidebar_button(name)

        # Toggle button frame        
        self.toggle_button_frame = tb.Frame(self, width=20,style="gray.TFrame")        
        self.toggle_button = tb.Button(self.toggle_button_frame, text="◄")
        self.toggle_button.config(command = lambda: self.gui_utils.toggle_sidebar())


    def create_sidebar_button(self, name):
        button_frame = tb.Frame(self.left_frame_inner, padding=(0,0), style="gray.TFrame")
        button_frame.pack(fill=tk.X)
        
        # The command is now simpler, it only needs to show the page.
        button = tb.Button(button_frame, text=name, style="menuButtonInactive.TButton", 
                           command=lambda page_name=name: self.show_page(page_name))
        button.pack(fill=tk.X, pady=(0, 2))
        
        # Store the button in our dictionary using its stable name as the key.
        self.sidebar_buttons[name] = button
     

    def show_page(self, page_name):
        # Instant lookup from our dictionary. No more searching by text!
        button = self.sidebar_buttons.get(page_name)
    
        # We still call activate_button to handle the visual style change.
        if button and button != self.active_button:
            self.gui_utils.activate_button(button)
    
        # The rest of the function remains the same.
        if self.current_page:
            self.current_page.forget()        
    
        page = self.pages.get(page_name)
    
        if not page:
            # Simplified this logic slightly
            page_class_map = {
                "Account": AccountPage,
                "Send": SendPage,
                "Settings": SettingsPage
            }
            page_class = page_class_map.get(page_name, BlankPage)
            page = page_class(self.page_container, self)
            
            self.pages[page_name] = page
            page.grid(row=0, column=0, sticky="nsew")
    
        self.current_page = page
        page.tkraise()


    def create_status_bar(self):
        # Place the status bar at the bottom of the main window or outside the page container
        self.status_bar_frame = tb.Frame(self.page_container, style='status_bar_frame.TFrame')
        self.status_bar_label = tb.Label(self.status_bar_frame, text="Status: No Wallet Loaded", background='orange')
        
        self.stop_button_image = Image.open("./denaro/gui_assets/stop_button.png")
        self.stop_button_image = self.stop_button_image.resize((17, 17), Image.LANCZOS)
        self.stop_button_image = ImageTk.PhotoImage(self.stop_button_image)

        self.stop_button_hover_image = Image.open("./denaro/gui_assets/stop_button_hover.png")
        self.stop_button_hover_image = self.stop_button_hover_image.resize((17, 17), Image.LANCZOS)
        self.stop_button_hover_image = ImageTk.PhotoImage(self.stop_button_hover_image)

        # Create a small circular button with an image to the left of the progress bar
        self.stop_button = tb.Button(self.status_bar_frame, image=self.stop_button_image, padding=0, style='stop_button.TButton')
        #self.small_button.config(width=self.small_button_image.width())

        self.progress_bar = tb.Progressbar(self.status_bar_frame, maximum=0, length=200, value=0, style='statusBar.progressBar.Striped.Horizontal.TProgressbar')
    

    def configure_layout(self):
        self.grid_columnconfigure(1, weight=1)  # Column for main content
        self.grid_rowconfigure(1, weight=1)     # Row for main content
        self.grid_rowconfigure(0, weight=0)     # Row for toggle button frame

        self.left_frame_outer.grid(row=0, column=0,rowspan=2, sticky='ns')  # Span two rows
        self.left_frame_inner.place(width=150)
        
        
        self.toggle_button_frame.grid(row=0, column=1, sticky='nsew')
        self.toggle_button.pack(side='left')

        self.page_container.grid(row=1, column=1, sticky='nsew')
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_rowconfigure(1, weight=0)
        self.page_container.grid_columnconfigure(0, weight=1)
        
        self.status_bar_frame.grid(row=1, column=0, sticky='ew')  # Adjust grid positioning as needed
        self.status_bar_label.pack(side=tk.LEFT)        
        self.progress_bar.pack(side=tk.RIGHT, padx=(5,15))
        self.stop_button.pack(side=tk.RIGHT)


class ConfigHandler:

    def __init__(self, root):
        self.root = root
        self.config_values = wallet_client.read_config(disable_err_msg = True)
        
        if self.config_values.get('disable_exchange_rate_features') == "True":
            self.root.disable_exchange_rate_features = True
        if self.config_values.get('disable_exchange_rate_features') == "False":
            self.root.disable_exchange_rate_features = False


    def update_config_values(self):  
        if self.config_values:
            if not self.root.disable_exchange_rate_features:
                if 'default_currency' in self.config_values:
                    self.root.stored_data.currency_code = self.config_values.get('default_currency')
                    self.root.settings_page.currency_code_combobox.set(self.root.stored_data.currency_code)
                    self.root.settings_page.validate_currency_code()
            
            if 'default_node' in self.config_values:
                default_node = self.config_values.get('default_node')
                self.root.stored_data.default_node = default_node
                
                self.root.settings_page.denaro_node_address_entry.delete(0, 'end')
                self.root.settings_page.denaro_node_port_entry.delete(0, 'end')

                # Split the address from the port, if present
                port_number = re.compile(r'^(?:http[s]?://)?(?:[\w\-\.]+)(?::(\d+))').search(default_node)
                
                if port_number and port_number.group(1):               
                    default_node, _, node_port = default_node.rpartition(':')  # rpartition always returns a 3-tuple
                    if not node_port:  # If no port is specified, rpartition will return the entire string as the address
                        node_port = ''  # Default or empty string if no port is specified                    
                    self.root.settings_page.denaro_node_port_entry.insert(0, node_port)
            
                self.root.settings_page.denaro_node_address_entry.insert(0, default_node)
                
            if 'node_validation' in self.config_values:
                self.root.stored_data.node_validation = self.config_values.get('node_validation')
                if self.root.stored_data.node_validation == "True":
                    self.root.settings_page.disable_node_validation_var.set(False)
                if self.root.stored_data.node_validation == "False":
                    self.root.settings_page.disable_node_validation_var.set(True)
            
            # --- NEW: Handle Language Setting on Load ---
            if 'language' in self.config_values:
                # The config stores the language code (e.g., "de")
                language_code = self.config_values.get('language')
                    
                # Look up the display name (e.g., "Deutsch") from the map
                # Provide the English display name as a fallback if the code is invalid
                display_name = self.root.translation_engine.language_map.get(language_code, "English")
                    
                # Set the combobox to the display name
                self.root.settings_page.language_combobox.set(display_name)
                # Call validation to sync the internal state (sets self.language to the code)
                self.root.settings_page.validate_language()
                    
            else:
                # If no language is set in config, default to English
                self.root.settings_page.language_combobox.set("English")
                self.root.settings_page.validate_language()
            # --------------------------------------------
            
            # --- Handle Translation Module Setting on Load ---
            self.root.settings_page._is_updating_translation_module = True
            try:
                translation_module = self.config_values.get('translation_module')
                if translation_module in ('argostranslate', 'deep-translator'):
                    # Translation is enabled - set the appropriate module
                    self.root.settings_page._set_translation_module_state(translation_module)
                    self.root.settings_page.language_combobox.config(state='normal')
                else:
                    # Translation is disabled (no translation_module or invalid value)
                    self.root.settings_page._set_translation_module_state(None)
                    self.root.settings_page.language_combobox.config(state='disabled')
                    # Reset language to English when translation is disabled
                    self.config_values['language'] = 'en'
                    self.root.settings_page.language_combobox.set("English")
                    self.root.settings_page.validate_language()
                    # Update translation engine to English
                    self.root.translation_engine.set_language('en')
            finally:
                self.root.settings_page._is_updating_translation_module = False
            # --------------------------------------------
            
            # Update save button state after loading config to reflect current state
            self.root.settings_page.update_save_button_state()


    def language_update_worker(self, stop_signal):
        """
        This worker runs on a background thread so that the main GUI thread dose not
        get blocked. It shows the language update in realtime.
        """
        # Get translation module from config (don't use default - if missing, translation is disabled)
        translation_module = self.config_values.get('translation_module')
        # Only update if translation module is set (translation is enabled)
        if translation_module:
            if self.root.translation_engine.translation_module != translation_module:
                # Reinitialize translation engine with new module
                self.root.translation_engine.translation_module = translation_module
                self.root.translation_engine._initialize_backends()
        
        # Refresh translation module label before translation starts
        # This ensures the label is visible during the translation process
        def refresh_translation_module_label_before():
            if self.root.settings_page.argostranslate_checkbox.get():
                self.root.settings_page.update_translation_module_label('argostranslate')
            elif self.root.settings_page.deep_translator_checkbox.get():
                self.root.settings_page.update_translation_module_label('deep-translator')
        self.root.after_idle(refresh_translation_module_label_before)
        
        self.root.translation_engine.set_language(self.config_values['language'])
        
        # Update the language cache list on the GUI thread after language change
        # This ensures new cache files are shown in the combobox
        self.root.after_idle(self.root.settings_page.update_language_cache_list)
        
        # Refresh translation module label after translation completes
        # This ensures the label doesn't disappear after translation
        def refresh_translation_module_label_after():
            if self.root.settings_page.argostranslate_checkbox.get():
                self.root.settings_page.update_translation_module_label('argostranslate')
            elif self.root.settings_page.deep_translator_checkbox.get():
                self.root.settings_page.update_translation_module_label('deep-translator')
        self.root.after_idle(refresh_translation_module_label_after)
    
    
    def save_node_config(self, node, node_validation_enabled):
        """
        Updates the self.config_values dictionary with all node settings.
        """
        if self.config_values.get('default_node') != node:
            self.config_values['default_node'] = node
            self.root.stored_data.node_valid = False
            self.root.stored_data.node_validation_performed = False
    
        if self.config_values.get('node_validation') != str(not node_validation_enabled):
            self.config_values['node_validation'] = str(not node_validation_enabled)
            self.root.stored_data.node_valid = False
            self.root.stored_data.node_validation_performed = False
    
        if not self.root.disable_exchange_rate_features:
            if self.config_values.get('default_currency') != self.root.stored_data.currency_code:
                self.config_values['default_currency'] = self.root.stored_data.currency_code
    
    def save_translation_module_config(self):
        """
        Updates the self.config_values dictionary with translation module settings.
        """
        current_translation_module = self.config_values.get('translation_module')
        
        # Determine new translation module from checkbox states
        if self.root.settings_page.argostranslate_checkbox.get():
            new_translation_module = 'argostranslate'
        elif self.root.settings_page.deep_translator_checkbox.get():
            new_translation_module = 'deep-translator'
        else:
            # Both are unchecked - translation is disabled
            new_translation_module = None
        
        # Check if translation module changed
        if new_translation_module is None:
            # Translation is disabled - check if it was previously enabled
            translation_module_changed = (current_translation_module is not None and current_translation_module != '')
        else:
            # Translation is enabled - check if it changed from previous state
            translation_module_changed = (current_translation_module != new_translation_module)
        
        # Validate argostranslate installation if it's being selected
        if new_translation_module == 'argostranslate' and translation_module_changed:
            try:
                import argostranslate
            except ImportError:
                # Set flag BEFORE reverting to prevent change callback from firing
                # This prevents the "Disable Translation" dialog from showing when we revert
                self.root.settings_page._is_updating_translation_module = True
                try:
                    # Revert to previous setting - don't change the translation module
                    if current_translation_module == 'argostranslate':
                        self.root.settings_page._set_translation_module_state('argostranslate', update_prev_state=True)
                    elif current_translation_module == 'deep-translator':
                        self.root.settings_page._set_translation_module_state('deep-translator', update_prev_state=True)
                    else:
                        # No previous translation module - revert to deep-translator (default)
                        self.root.settings_page._set_translation_module_state('deep-translator', update_prev_state=True)
                finally:
                    # Clear flag after reverting - the callback won't fire because state is back to original
                    self.root.settings_page._is_updating_translation_module = False
                
                # Show dialog after reverting
                self.root.dialogs.messagebox(
                    "Argos Translate Not Installed",
                    "Argos Translate is not installed. Please install it via pip:\n\n"
                    "pip install argostranslate\n\n"
                    "After installation, please restart the wallet client and set the translation module to Argos Translate."
                )
                
                # Don't update config - keep the previous translation module
                # Continue with save for other settings
                return
        
        # Update translation module in config
        if translation_module_changed:
            if new_translation_module is None:
                # Translation is disabled - remove the key from config
                if 'translation_module' in self.config_values:
                    del self.config_values['translation_module']
                # Reset language to English when translation is disabled
                self.config_values['language'] = 'en'
                self.root.settings_page.language_combobox.set("English")
                self.root.settings_page.validate_language()
                # Update translation engine to English immediately
                self.root.translation_engine.set_language('en')
            else:
                self.config_values['translation_module'] = new_translation_module
                # Update translation module in engine if it changed
                self.root.translation_engine.translation_module = new_translation_module
                self.root.translation_engine._initialize_backends()
    

    def show_save_confirmation_popup(self, new_config):
        """
        Displays the final confirmation popup after saving settings.
        """
        if new_config:
            if new_config == self.config_values:
                message = "Settings saved to config file."
            else:
                message = "Settings not saved to config file."
    
            self.root.custom_popup.add_popup(
                timeout=5000,
                prompt=[{"label_config":"text='{}', background='#2780e3', anchor='center', font='Calibri 10 bold'".format(message), "grid_config":"sticky='nsew'"}], 
                grid_layout_config=[{"grid_row_config":"index=0, weight=1"}, {"grid_column_config":"index=0, weight=1"}]
            )


    def save_config(self):
        # --- Step 1: Perform initial validation ---
        if not self.root.settings_page.denaro_node_address_entry.get().strip():
            self.root.settings_page.denaro_node_address_entry.delete(0, 'end')
            self.root.settings_page.denaro_node_address_entry.insert(0, "http://localhost:3006")
            self.root.settings_page.denaro_node_port_entry.delete(0, 'end')
        
        node, string_valid, node_validation_enabled = self.root.settings_page.validate_node_fields()
        
        # node fields not valid, so exit early.
        if not string_valid:
            self.root.settings_page.keep_save_button_disabled = True
            self.root.settings_page.update_save_button_state()
            return
        
        # Nothing to save, so exit early.
        if not self.root.settings_page.check_setting_changes():
            return
        
        # Save translation module configuration
        self.save_translation_module_config()
        
        # Language HAS changed. Dispatch to the background worker thread.
        if self.config_values.get('language') != self.root.settings_page.language:
            self.config_values['language'] = self.root.settings_page.language
            self.root.wallet_thread_manager.start_thread(name="language_update_orchestrator", target=self.language_update_worker)

        # Update the rest of the config dictionary and write to disk
        self.save_node_config(node, node_validation_enabled)
        wallet_client.write_config(config=self.config_values)
        new_config = wallet_client.read_config(disable_err_msg=True)
    
        # Update config_values to the newly read config
        self.config_values = new_config
    
        #  Safely queue the final UI feedback on the main GUI thread
        self.show_save_confirmation_popup(new_config)

        # Finally, for good measure update all config values 
        self.update_config_values()
        
        # Update save button state after config is reloaded
        self.root.settings_page.update_save_button_state()



class EventHandler:
    def __init__(self, root):
        self.root = root
        self.thread_event = None
        self.price_timer_step = 0
        self.price_timer = 31
        self.stop_loading_wallet = False
        self.stop_getting_balance = False
        self.translation_wait_dialog_event = None

        # This previous_states dictionary is perfectly fine as it uses stable keys.
        self.previous_states = {
            'send_page': None,
            'balance_button': None,
            'load_wallet_menu_item': None,
            'create_wallet_menu_item': None,
            'restore_wallet_menu_item': None,
            'backup_wallet_menu_item': None,
            'generate_address_menu_item': None,
            'import_address_menu_item': None,
            'close_wallet_menu_item': None,
            'currency_combobox': None,
            'status_bar': None,
            'progress_bar': None
        }

        # This list of keys will make our code much cleaner.
        self.file_menu_keys = [
            'load_wallet_menu', 'create_wallet', 'restore_wallet', 'backup_wallet',
            'generate_address', 'import_address', 'close_wallet'
        ]

        self.event_listener()
        self.progress_bar_listener()

    # event_listener, progress_bar_listener, and many others don't need changes
    # because they don't reference menu items by string. We will only change
    # the methods that do.
    def event_listener(self):
        """Updates certain GUI elements based on what event is taking place"""
        self.thread_event = list(self.root.wallet_thread_manager.threads.keys())
            
        if 'load_wallet' in self.thread_event:
            self.set_loading_wallet_state()
            if self.root.stored_data.operation_mode is None:
                self.update_status_bar("Loading Wallet")
        else:
            self.update_wallet_state()

        if 'load_balance' in self.thread_event:
            if self.root.stored_data.operation_mode is None:
                self.update_status_bar("Getting Balance Data")
        else:
            if not self.root.disable_exchange_rate_features:
                self.set_currency_combobox_state('normal')

        if self.root.stored_data.wallet_deleted:
            self.root.stored_data.operation_mode = None
            self.root.gui_utils.close_wallet()


        if self.root.stored_data.input_listener_time_remaining == 0:
            if 'input_listener_timer' in self.thread_event:
                self.root.wallet_thread_manager.stop_thread("input_listener_timer") 
        
        self.update_operation_mode_status()

        if not self.root.disable_exchange_rate_features:
            self.update_price_timer()

        self.root.after(100, self.event_listener)

    def progress_bar_listener(self):
        progress_bar_goal = self.root.progress_bar['value'] + 10
        if self.root.stored_data.progress_bar_increment:
            for _ in range(10):  # Example: Update progress bar 10 times
                self.root.progress_bar['value'] += 10  # Increment the progress bar value by 10
                self.root.progress_bar.update_idletasks()  # Update the UI
                time.sleep(0.01)
                if self.root.progress_bar['value'] == progress_bar_goal:
                    self.root.stored_data.progress_bar_increment = False
        
        self.root.after(10, self.progress_bar_listener)

    def set_loading_wallet_state(self):
        if self.previous_states['balance_button'] != 'disabled':
            self.root.account_page.refresh_balance_button.config(state='disabled')
            self.previous_states['balance_button'] = 'disabled'

        self.set_send_page_state('disabled')
        self.set_all_file_menu_items('disabled')
       
    def update_wallet_state(self):
        if self.root.stored_data.wallet_loaded:
            self.update_wallet_loaded_state()
        else:
            self.update_wallet_not_loaded_state()

    def update_wallet_loaded_state(self):
        if str(self.root.send_page.send_from_combobox["state"]) == "disabled" and not self.root.stored_data.operation_mode == 'send':
            self.set_send_page_state('normal')
            self.root.send_page.check_send_params()

        if 'load_balance' not in self.thread_event:
            self.update_wallet_load_balance_state()
        else:
            if not self.root.disable_exchange_rate_features:
                self.set_currency_combobox_state('disabled')
        
        create_wallet_state = self.root.get_menu_item_state('create_wallet')
        generate_address_state = self.root.get_menu_item_state('generate_address')

        if 'create_wallet' not in self.thread_event and 'generate_address' not in self.thread_event:
            if create_wallet_state == 'disabled' or generate_address_state == 'disabled':
                self.set_all_file_menu_items('normal')
        else:
            if create_wallet_state == 'normal' or generate_address_state == 'normal':
                self.set_all_file_menu_items('disabled')

    def update_wallet_not_loaded_state(self):
        if self.root.stored_data.operation_mode is None:
            self.update_status_bar("No Wallet Loaded")

        self.set_send_page_state('disabled')
        
        if 'create_wallet' not in self.thread_event:
            # Note: The key for the 'Load Wallet' cascade is 'load_wallet_menu'
            self.root.set_menu_item_state('load_wallet_menu', 'normal') 
            self.root.set_menu_item_state('create_wallet', 'normal')
            self.root.set_menu_item_state('restore_wallet', 'normal')
            self.root.set_menu_item_state('backup_wallet', 'disabled')
            self.root.set_menu_item_state('generate_address', 'disabled')
            self.root.set_menu_item_state('import_address', 'disabled')
            self.root.set_menu_item_state('close_wallet', 'disabled')
        else:
            if self.root.get_menu_item_state('create_wallet') == 'normal':
                self.set_all_file_menu_items('disabled') 

    def update_wallet_load_balance_state(self):
        entries_length = len(self.root.stored_data.wallet_data["entry_data"]["entries"])
        imported_entries_length = len(self.root.stored_data.wallet_data["entry_data"].get("imported_entries", []))
        combined_length = entries_length + imported_entries_length
        status_message = "Wallet Loaded" if combined_length == self.root.stored_data.entry_count else "Wallet Partially Loaded"
        
        if self.root.stored_data.operation_mode is None:
            self.update_status_bar(status_message)

        if str(self.root.account_page.refresh_balance_button["state"]) == "disabled":
            self.root.account_page.refresh_balance_button.config(state='normal')
            self.previous_states['balance_button'] = 'normal'

        if self.root.stored_data.operation_mode is None and self.root.progress_bar["value"] != 0:
            self.root.progress_bar.config(maximum=0, value=0)

    def update_operation_mode_status(self):
        operation_mode_status = {
            'send': "Sending Transaction",
            'wallet_annihilation': "Wallet Annihilation in progress.",
            'create_wallet': "Creating new wallet.",
            'generate_address': "Generating address."
        }
        status = operation_mode_status.get(self.root.stored_data.operation_mode)
        if status:
            self.update_status_bar(status)

    def update_price_timer(self):
        self.price_timer_step += 1
        if self.price_timer_step >= 10:
            self.price_timer -= 1
            self.root.gui_utils.update_dnr_price(self.price_timer)
            self.price_timer_step = 0
        if self.price_timer <= 0:
            self.price_timer = 31

    def update_status_bar(self, message):
        if self.previous_states['status_bar'] != message:
            self.root.gui_utils.update_status_bar(message)
            self.previous_states['status_bar'] = message

    def set_send_page_state(self, state):
        if self.previous_states['send_page'] != state:
            self.root.send_page.amount_entry.config(state=state)
            self.root.send_page.recipient_entry.config(state=state)
            self.root.send_page.message_entry.config(state=state)
            self.root.send_page.send_button.config(state=state)
            self.root.send_page.max_amount_button.config(state=state)
            self.root.send_page.half_amount_button.config(state=state)
            self.root.send_page.send_from_combobox.config(state='readonly' if state == 'normal' else state)
            self.previous_states['send_page'] = state

    def set_currency_combobox_state(self, state):
        if self.previous_states['currency_combobox'] != state:
            self.root.settings_page.currency_code_combobox.config(state=state)
            self.previous_states['currency_combobox'] = state

    def set_all_file_menu_items(self, state):
        """Sets all tracked file menu items to a given state using their keys."""
        for key in self.file_menu_keys:
            self.root.set_menu_item_state(key, state)

    def show_translation_wait_dialog(self, use_queue=False):
        """
        Displays a non-blocking translation wait dialog. This is meant  to indicate
        that the interface is in the process of language translation. State is
        managed by the translation engine.
        """
        self.root.translation_engine.log.debug("Showing translation wait dialog.")
        self.translation_wait_dialog_event = threading.Event()
        title = "Processing"
        message = "Translating user interface, please wait..."
        
        if use_queue:
            # Create the dialog by posting to to queue
            self.root.wallet_operations.callbacks.post_messagebox_wait(
                title, 
                message, 
                self.translation_wait_dialog_event
            )
        else:
            # Create the dialog directly instead of posting to queue
            self.root.dialogs.messagebox_wait(
                title, 
                message, 
                modal=False,  # Important: non-modal so it doesn't block
                close_event=self.translation_wait_dialog_event
            )

        # Force the dialog to render immediately
        self.root.update_idletasks()

        
    def close_translation_wait_dialog(self):
        """Closes the translation wait dialog dialog if open."""
        if self.translation_wait_dialog_event:
            self.root.translation_engine.log.debug("Closing translation wait dialog.")
            self.root.after(100, self.translation_wait_dialog_event.set)
            self.translation_wait_dialog_event = None


class GUIUtils:
    def __init__(self, root):
        self.root = root
        self.fade_text_widgets = {}


    def toggle_sidebar(self):
        self.root.toggle_button.focus_set()
        if self.root.left_frame_outer.winfo_viewable():
            self.root.toggle_button.config(state="disabled")
    
            def toggle_sidebar_collapse(current_width=None):
                min_width = 1
                if current_width is None:
                    current_width = self.root.left_frame_outer.winfo_width()
                step = max(10, current_width // 10)  # Increase step size for larger widths
                new_width = max(min_width, current_width - step)
    
                if current_width > min_width:
                    self.root.left_frame_outer.config(width=new_width)                
                    self.root.after(20, toggle_sidebar_collapse, new_width)  # Slightly longer interval
                else:
                    self.root.left_frame_outer.grid_remove()
                    self.root.toggle_button.config(state="normal", text="►")
            toggle_sidebar_collapse()
        else:
            self.root.left_frame_outer.grid()
            self.root.left_frame_outer.config(width=1)  # Start with the minimum width
            self.root.toggle_button.config(state="disabled")
    
            def toggle_sidebar_expand(current_width=None):
                max_width = 150  # Target width for the sidebar
                if current_width is None:
                    current_width = self.root.left_frame_outer.winfo_width()
    
                step = max(10, (max_width - current_width) // 10)  # Increase step size for larger gaps
                new_width = min(max_width, current_width + step)
    
                if current_width < max_width:
                    self.root.left_frame_outer.config(width=new_width)
                    self.root.after(20, toggle_sidebar_expand, new_width)  # Slightly longer interval
                else:
                    self.root.toggle_button.config(state="normal", text="◄")
            toggle_sidebar_expand()
        

        #Old Function
        #def toggle_sidebar():
        #    toggle_button.focus_set()
        #    if left_frame_outer.winfo_viewable():
        #        toggle_button.config(state="disabled")
        #        def toggle_sidebar_collapse():
        #            min_width = 1
        #            step = 5  # Width change per step
        #            left_frame_outer_width = left_frame_outer.winfo_width()
        #        
        #            if left_frame_outer_width > min_width:
        #                new_width = max(min_width, left_frame_outer_width - step)
        #                left_frame_outer.config(width=new_width)
        #                root.after(10, toggle_sidebar_collapse)
        #            else:
        #                left_frame_outer.grid_remove()
        #                toggle_button.config(state="normal", text=">>")
        #        toggle_sidebar_collapse()
        #    else:
        #        left_frame_outer.grid()
        #        toggle_button.config(state="disabled")
        #        def toggle_sidebar_expand():
        #            max_width = 150  # Desired width when fully open
        #            step = 5  # Width change per step
        #            left_frame_outer_width = left_frame_outer.winfo_width()
        #        
        #            if left_frame_outer_width < max_width:
        #                new_width = min(max_width, left_frame_outer_width + step)
        #                left_frame_outer.config(width=new_width)
        #                root.after(10, toggle_sidebar_expand)
        #            else:
        #                toggle_button.config(state="normal", text="<<")
        #        toggle_sidebar_expand()


    def show_context_menu(self, event):
        # Get references to the context menus from the root window
        textboxes_context_menu = self.root.textboxes_context_menu
        treeview_context_menu = self.root.treeview_context_menu
    
        self.root.current_event = event
        widget = event.widget
    
        try:
            if isinstance(widget, (tk.Entry, AutocompleteCombobox)):
                # Determine the state based on widget properties
                can_modify = str(widget.cget("state")) != "readonly"
                
                # Use the stable keys and the helper method on the root window
                self.root.set_menu_item_state('ctx_cut', 'normal' if can_modify else 'disabled')
                self.root.set_menu_item_state('ctx_paste', 'normal' if can_modify else 'disabled')
                self.root.set_menu_item_state('ctx_delete', 'normal' if can_modify else 'disabled')
                
                # The 'Copy' and 'Select All' commands are always available for any selectable text
                self.root.set_menu_item_state('ctx_copy', 'normal')
                self.root.set_menu_item_state('ctx_select_all', 'normal')
    
                textboxes_context_menu.tk_popup(event.x_root + 1, event.y_root + 1)
            
            elif isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
                # For read-only text widgets, only copy and select all are available
                self.root.set_menu_item_state('ctx_cut', 'disabled')
                self.root.set_menu_item_state('ctx_paste', 'disabled')
                self.root.set_menu_item_state('ctx_delete', 'disabled')
                self.root.set_menu_item_state('ctx_copy', 'normal')
                self.root.set_menu_item_state('ctx_select_all', 'normal')
    
                textboxes_context_menu.tk_popup(event.x_root + 1, event.y_root + 1)
            
            elif isinstance(widget, ttk.Treeview):
                row_id = widget.identify_row(event.y)
                # Make sure we clicked on an actual item
                has_selection = len(row_id) > 0
                
                # Check if we clicked on the 'Address' column (column 0)
                col_id_str = widget.identify_column(event.x)
                col_id = int(col_id_str.replace('#', '')) - 1
                is_address_column = (col_id == 0)
    
                # Use the stable keys and the helper method on the root window
                self.root.set_menu_item_state('tree_copy', 'normal' if has_selection else 'disabled')
                self.root.set_menu_item_state('tree_send', 'normal' if has_selection and is_address_column else 'disabled')
                self.root.set_menu_item_state('tree_addr_info', 'normal' if has_selection and is_address_column else 'disabled')
                self.root.set_menu_item_state('tree_explorer', 'normal' if has_selection and is_address_column else 'disabled')
                
                # This logic remains the same
                if has_selection:
                    widget.selection_set(row_id)
                
                treeview_context_menu.tk_popup(event.x_root + 1, event.y_root + 1)
    
            else:
                # Hide the menus if the widget is not recognized
                textboxes_context_menu.unpost()
                treeview_context_menu.unpost()
                
        except Exception as e:
            # It's good practice to catch potential errors and log them
            print(f"Error in show_context_menu: {e}")
        finally:
            # This is generally not needed and can sometimes cause issues.
            # self.root.grab_release()
            pass
    

    def cut_text(self, event=None, delete=False):
        widget = event.widget if event else self.root.current_event.widget
        if widget.selection_present():
            widget.clipboard_clear()
            if not delete:
                widget.clipboard_append(widget.selection_get())
            widget.delete("sel.first", "sel.last")
    

    def select_all_text(self, event=None):
        widget = event.widget if event else self.root.current_event.widget
        if isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
            # ScrolledText copy functionality
            widget.tag_add(tk.SEL, "1.0", tk.END)
            # Set INSERT mark at the end of the text, ensuring visibility and focus.
            widget.mark_set(tk.INSERT, tk.END)
            widget.see(tk.INSERT)
            widget.focus()
        else:
            widget.select_range(0, tk.END)
        # Return 'break' to prevent the class binding from propagating to the default text widget behavior
        return "break"
    

    def copy_selection(self, event=None):
        widget = event.widget if event else self.root.current_event.widget
        if isinstance(widget, ttk.Treeview):
            # Treeview copy functionality
            row_id = widget.identify_row(self.root.current_event.y)
            col_id = int(widget.identify_column(self.root.current_event.x).replace('#', '')) - 1
            if len(row_id) > 0:            
                item = widget.item(row_id)
                try:
                    clipboard_text = item['values'][col_id]
                except IndexError:
                    clipboard_text = ''
                self.root.clipboard_clear()
                self.root.clipboard_append(clipboard_text)
        elif isinstance(widget, tk.Entry):
            # Textbox copy functionality
            if widget.selection_present():
                clipboard_text = widget.selection_get()
                self.root.clipboard_clear()
                self.root.clipboard_append(clipboard_text)
        elif isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
            # ScrolledText copy functionality
            try:
                clipboard_text = widget.selection_get()
                self.root.clipboard_clear()
                self.root.clipboard_append(clipboard_text)
            except tk.TclError:
                return
        else:
            return
    

    def paste_text(self, event=None):
        widget = event.widget if event else self.root.current_event.widget
        try:
            # Get text from clipboard
            clipboard_text = self.root.clipboard_get()
            # Check if there is text selected in the textbox
            if widget.selection_present():
                # Get the start and end indices of the selected text
                start_index = widget.index("sel.first")
                end_index = widget.index("sel.last")
                # Delete the selected text
                widget.delete(start_index, end_index)
                # Insert the clipboard text at the start index
                widget.insert(start_index, clipboard_text)
            else:
                # If no text is selected, insert at the cursor position
                widget.insert(tk.INSERT, clipboard_text)
        except tk.TclError:
            # Clipboard does not contain text or other error
            pass

    def address_context_menu_selection(self, event=None, show_send_page=False, set_address_combobox=False, view_explorer=False):
        if event:
            widget = event.widget 
        else:
            widget = self.root.current_event.widget
            event = self.root.current_event
        
        if isinstance(widget, ttk.Treeview):
            row_id = widget.identify_row(event.y)
            col_id = int(widget.identify_column(event.x).replace('#', '')) - 1
            if len(row_id) > 0 and col_id == 0:            
                item = widget.item(row_id)
                if set_address_combobox:
                    self.root.send_page.send_from_combobox.set(item['values'][0])
                if show_send_page:
                    self.root.show_page("Send")
                if view_explorer:
                    url = f"https://denaro-explorer.aldgram-solutions.fr/address/{item['values'][0]}"
                    self.open_link(url, show_link=True)


    def on_root_click(self, event):
        """
        Clears selections if the click occurred outside selectable widgets and not clicking on a Treeview's or ScrolledText's scrollbar.
        """
        widget = event.widget
        clicked_on_scrollbar = False
        
        for sel_widget in self.root.selectable_widgets:
            # Check for element scrollbars
            if isinstance(sel_widget, (ttk.Treeview, scrolledtext.ScrolledText)):
                widget_container = sel_widget.master
                for child in widget_container.winfo_children():
                    if child == widget and isinstance(child, tk.Scrollbar):
                        clicked_on_scrollbar = True
                        break
                    
        # Clear selections if the click is not on a scrollbar of a Treeview or ScrolledText
        if not clicked_on_scrollbar:
            # Clear selection in all Entry widgets except the one being clicked, if it is an Entry
            for entry_widget in [w for w in self.root.selectable_widgets if isinstance(w, tk.Entry)]:
                if widget != entry_widget:
                    entry_widget.select_clear()
                    # Ensure widget is a Tkinter widget before setting focus
                    if isinstance(widget, tk.Misc):
                        widget.focus_set()

            # Invoke global deselect
            self.global_deselect(except_widget=widget)


    def on_treeview_click(self, event):
        """
        Clears selection if clicked on an unpopulated row area within the Treeview.
        """
        row_id = event.widget.identify_row(event.y)
        if not row_id:
            # Clicked on an empty area, clear the selection
            event.widget.selection_remove(event.widget.selection())
    

    def on_treeview_double_click(self, event=None):
        self.address_context_menu_selection(event, set_address_combobox=True, show_send_page=True)


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
        for widget in self.root.selectable_widgets:
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
    

    def update_wallet_menu(self):
        # Clear existing items from the wallet menu
        self.root.wallet_menu.delete(0, 'end')
        # Add a command to load wallets from a file dialog
        self.root.wallet_menu.add_command(label="Load From File...", command=self.root.wallet_operations.load_wallet)
        # Add a separator for better visual distinction
        self.root.wallet_menu.add_separator()
        # Populate the wallet menu with files and folders
        with self.root.translation_engine.no_translate():
            self.populate_wallet_menu('./wallets', self.root.wallet_menu)

    def populate_wallet_menu(self, path, menu):
        # List all files and directories at the given path
        wallet_client.ensure_wallet_directories_exist()
        items = os.listdir(path)
        # Sort items in alphabetical order
        items.sort()
        # Iterate over sorted items
        for item in items:
            full_path = os.path.join(path, item)
            # Check if the current item is a directory
            if os.path.isdir(full_path):
                # Create a new menu for the folder
                folder_menu = tk.Menu(menu, tearoff=0)
                # Add the folder menu as a cascade to the parent menu
                menu.add_cascade(label=item, menu=folder_menu)
                # Recursively populate the folder menu with its contents
                self.populate_wallet_menu(full_path, folder_menu)
            else:
                # For files, add a command to the current menu
                menu.add_command(label=item, command=lambda file=full_path: self.root.wallet_operations.load_wallet(file))  
    

    def add_combobox_separator_at_index(self, combobox, separator, index):
        """ Add a separator to the Combobox values at a specific index """
        values = list(combobox['values'])
        values.insert(index, separator)
        combobox['values'] = values
    

    def on_currency_code_combobox_select(self, event):
        """ Event handler for the Combobox selection. """
        if self.root.settings_page.currency_code_combobox.get() in self.root.settings_page.separators:
            # Reset to the last valid selection if a separator is selected
            self.root.settings_page.currency_code_combobox.current(self.root.settings_page.last_valid_selection)
        else:
            # Update the last valid selection        
            self.root.settings_page.last_valid_selection = self.root.settings_page.currency_code_combobox.current()
            self.root.settings_page.currency_code = self.root.settings_page.currency_code_combobox.get()
    

    def refresh_balance(self):
        self.root.account_page.refresh_balance_button.focus_set()
        self.root.account_page.refresh_balance_button.config(state='disabled')

        for item in self.root.account_page.accounts_tree.get_children():
            # Retrieve the current row's data
            row_data = self.root.account_page.accounts_tree.item(item, 'values')
            # Update the row data except the column to preserve
            new_row_data = [row_data[self.root.account_page.columns.index("Address")] if col == "Address" else "" for col in self.root.account_page.columns]
            # Set the item's new data
            self.root.account_page.accounts_tree.item(item, values=new_row_data)
        self.root.stored_data.balance_data = []
        self.root.stored_data.balance_loaded = None
        self.root.wallet_operations.load_balance()
    

    def on_stop_button_click(self, event=None):        
        self.root.wallet_thread_manager.stop_specific_threads(names=['load_wallet', 'load_balance'])
        if self.root.progress_bar["value"] != 0:
            self.root.progress_bar.config(maximum=0, value=0)
    

    def sort_treeview_column(self, tree, col):
        """
        Sorts TreeView column by integer values, removing " DNR" from "Balance" and "Pending" columns before sorting.
        """
        current_heading = tree.heading(col)['text']
        # Remove existing sort order indicator if present
        if " ↾" in current_heading or " ⇂" in current_heading or " ⥮" in current_heading:
            base_name = current_heading[:-2]
        else:
            base_name = current_heading

    
        if not self.root.stored_data.wallet_loaded:
            for column in self.root.account_page.column_sort_order:
                self.root.account_page.column_sort_order[column] = False
                # Update the sorted column heading with the new sort order indicator
                tree.heading(col, text=base_name+" ⥮")
                return
    
        #if not self.root.stored_data.balance_loaded:
        #    return
    
        for column in self.root.account_page.column_sort_order:
            if column != col:
                self.root.account_page.column_sort_order[column] = not self.root.account_page.column_sort_order[col]
    
        reverse = self.root.account_page.column_sort_order[col] = not self.root.account_page.column_sort_order[col]
    
        l = []
        for k in tree.get_children(''):
            value = tree.set(k, col)
            # Remove formatting specific to each column
            if col in ["Balance", "Pending"]:
                # Since every value ends with " DNR", remove it to parse the numeric value
                numeric_part = value.replace(" DNR", "")
                try:
                    # Convert the numeric part to an integer
                    numeric_value = float(numeric_part)
                except ValueError:
                    # If conversion fails, print an error and skip this value
                    continue
            
            if not self.root.disable_exchange_rate_features:
                if col == "Value":
                    try:
                        # Remove the "$" and commas, then convert to float for "Value"
                        numeric_value = float(value.replace(self.root.stored_data.currency_symbol, "").replace(",", ""))
                    except ValueError:
                        continue
            
            # Append the numeric value along with the item's ID for sorting
            l.append((numeric_value, k))
        
        # Sort the list by numeric values
        l.sort(key=lambda t: t[0], reverse=reverse)
    
        # Reorder items in the TreeView based on the sorted list
        for index, (val, k) in enumerate(l):
            if index % 2 == 0:
                column_tag = 'evenrow'
            else:
                column_tag = 'oddrow'
            tree.item(k, tags=column_tag)
            tree.move(k, '', index)
        
        # Update headings with sort order indicator
        sort_order_char = " ↾" if reverse else " ⇂"
    
        # Update the sorted column heading with the new sort order indicator
        tree.heading(col, text=f"{base_name}{sort_order_char}", command=lambda _col=col: self.sort_treeview_column(tree, _col))
    
        # Reset other column headings to remove sort indicators
        if self.root.disable_exchange_rate_features:
            heading_names = ["Balance", "Pending"]
        else:
            heading_names = ["Balance", "Pending", "Value"]

        for col_name in heading_names:
            if col_name != col:
                # Retrieve the original heading without sort order indicator
                other_heading = tree.heading(col_name)['text']
                if " ↾" in other_heading or " ⇂" in other_heading or " ⥮" in current_heading:
                    other_base_name = other_heading[:-2]
                else:
                    other_base_name = other_heading
                tree.heading(col_name, text=other_base_name, command=lambda _col=col_name: self.sort_treeview_column(tree, _col))
                title_width = self.root.account_page.treeview_font.measure(other_base_name) + 40
                self.root.account_page.column_min_widths[col_name] = title_width
            else:
                if " ↾" not in current_heading and " ⇂" not in current_heading and not " ⥮" in current_heading:
                    title_width = self.root.account_page.treeview_font.measure(current_heading) + 20  # Extra space for padding
                    self.root.account_page.column_min_widths[col] = title_width


    def update_status_bar(self, text):
        text=f"Status: {text}"
        if not self.root.status_bar_label["text"] == text:
            self.root.status_bar_label.config(text=text)


    def update_dnr_price(self, timer_value):

        # Find the position where the countdown timer starts.
        base_text_end_pos = self.root.account_page.denaro_price_text["text"].rfind(' (Updating in: ')  # Find the last occurrence of the countdown start

        if base_text_end_pos != -1:
            # If found, keep only the text before the countdown timer.
            base_text = self.root.account_page.denaro_price_text["text"][:base_text_end_pos]
        else:
            # If not found, assume the entire text is base text.
            base_text = self.root.account_page.denaro_price_text["text"]
    
        update_price_str = f' (Updating in: {timer_value}s)'
        # Update the label with base text and the new countdown timer.
        
        self.root.account_page.denaro_price_text.config(text=f'{base_text}{update_price_str}')
    
        if timer_value == 30:
            formatted_price_str = self.root.wallet_operations.get_dnr_price()
            self.root.account_page.denaro_price_text.config(text=f'DNR/{self.root.stored_data.currency_code} Price: {self.root.stored_data.currency_symbol}{formatted_price_str}{update_price_str}')
    

    def open_link(self, url, show_link=False):
        """
        Asks for user consent asynchronously before opening a URL.
        """
        def on_user_consent(was_confirmed):
            if was_confirmed:
                webbrowser.open_new(url)
        
        # Call the universal dialog method in async/callback mode directly from the GUI thread.
        self.root.dialogs.confirmation_prompt(
            title="Open Link",
            msg="Do you want to open this link in your browser?",
            msg_2=url if show_link else None,
            on_complete=on_user_consent
        )


    def on_link_enter(self, event):
        event.widget.config(cursor="hand2")
    

    def on_link_leave(self, event):
        event.widget.config(cursor="")
    

    def activate_button(self, new_active_button):
        # ADD THIS GUARD CLAUSE at the top.
        if not new_active_button:
            return
    
        if self.root.active_button is not None:
            self.root.active_button.config(style="menuButtonInactive.TButton")
        new_active_button.config(style='TButton')
        self.root.active_button = new_active_button
    

    def find_button_by_text(self, button_frame, text):
        """
        Function to find a button with the given text in the sidebar.
        :param left_frame: The frame containing the buttons.
        :param text: The text of the button to find.
        :return: The button widget if found, None otherwise.
        """
        for frame in button_frame.winfo_children():
            for widget in frame.winfo_children():
                if isinstance(widget, tb.Button) and widget.cget("text") == text:
                    return widget
        return None
    

    def fade_text(self, stop_signal=None, widget=None, widget_name=None, timeout=0, target_color='#FFFFFF'):
        """
        Gradually fades the label's current foreground color to the target color in 20 steps.
        
        Args:
        stop_signal (bool): A signal to stop the fade effect externally.
        widget (Widget): The widget to apply the fade effect on.
        widget_name (str): The unique name identifier for the widget.
        target_color (str): The target color in hex format to which the text should fade.
        """

        # Initialize fade_text_widgets if this is the first time for this widget_name
        if widget_name not in self.fade_text_widgets:
            self.fade_text_widgets[widget_name] = {"widget": widget, "step": 0}
        
            if timeout > 0:
                time.sleep(timeout)

        # Continuously update the fade effect until the maximum step is reached or stop_signal is set
        while True:            
            # Break if stop signal is set
            if stop_signal and stop_signal.is_set():
                if widget_name in self.fade_text_widgets:
                    self.fade_text_widgets.pop(widget_name, None)
                break
            
            try:
                if widget_name in self.fade_text_widgets:
                    # Fetch the current step value from fade_text_widgets to allow external control
                    current_step = self.fade_text_widgets[widget_name]["step"]
            
                    # Break if the maximum step has been reached
                    if current_step > 20:
                        # Clean up after the fade is complete
                        self.fade_text_widgets.pop(widget_name, None)
                        break
            
                    # Get the current foreground color of the label
                    current_color = widget.cget("foreground")
                    
                    # Convert the current and target colors to RGB tuples
                    current_color_rgb = self.color_to_rgb(str(current_color))
                    target_color_rgb = self.color_to_rgb(target_color)
                    
                    # Calculate the new RGB values by incrementing each component towards the target color
                    new_rgb = tuple(
                        min(255, int(color + (target - color) * (current_step / 20)))
                        for color, target in zip(current_color_rgb, target_color_rgb)
                    )
                    
                    # Convert the new RGB tuple back to hex format
                    new_color = '#{:02x}{:02x}{:02x}'.format(*new_rgb)
                    
                    # Update the label's foreground color to the calculated new color
                    widget.config(foreground=new_color)
                    
                    # Increment the step value in fade_text_widgets
                    self.fade_text_widgets[widget_name]["step"] = current_step + 1
                    
                    # Update the GUI to keep it responsive
                    self.root.update_idletasks()
                    
                    # Wait for 100 milliseconds before the next iteration
                    time.sleep(0.1)
                else:
                    break
            except tk.TclError:
                self.fade_text_widgets.pop(widget_name, None)
                break
        
    
    def color_to_rgb(self, color):
        """
        Converts a color (name, hex string, or RGB tuple) to an RGB tuple.
        
        Args:
        color (str or tuple): The color, which may be a named color, a hex string, or an RGB tuple.
        
        Returns:
        tuple: An (R, G, B) tuple representing the color.
        """
        # Handle case where color is already an RGB tuple
        if isinstance(color, tuple):
            return color
    
        # Handle color names by converting them to RGB using tkinter's color lookup
        try:
            rgb_color = self.winfo_rgb(color)  # Returns a tuple of (r, g, b), but in 16-bit (0-65535 range)
            return tuple(c // 256 for c in rgb_color)  # Convert 16-bit values to 8-bit (0-255 range)
        except:
            # Assume it's a hex string if color lookup fails
            color = color.lstrip('#')
            return tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
    

    def close_wallet(self):
        if self.root.stored_data.operation_mode != 'send':
            self.root.title(self.root.wallet_client_version)
            self.root.account_page.refresh_balance_button.config(state='disabled')
            self.root.wallet_thread_manager.stop_specific_threads(names=['load_wallet', 'load_balance'])
            self.root.wallet_operations.callbacks.clear_wallet_data(preserve_wallet_data=False)
            self.root.wallet_operations.callbacks.clear_page_data()
        else:
            self.root.dialogs.messagebox("Error", "Can not close wallet while a transaction is taking place.")
            return
        




class WalletOperations:
    def __init__(self, root):
        self.root = root
        self.callbacks = Callbacks(self.root)
        self.update_wallet_data()
 
    #Load Wallet Methods
    def load_wallet(self, file_path=None):
        if self.root.progress_bar["value"] != 0:
            self.root.progress_bar.config(maximum=0, value=0)
        try:
            try:
                self.root.tk.call('tk_getOpenFile', '-foobarbaz')
            except tk.TclError:
                pass
         
            self.root.tk.call('set', '::tk::dialog::file::showHiddenBtn', '1')
            self.root.tk.call('set', '::tk::dialog::file::showHiddenVar', '0')
        except:
            pass
        file_path = file_path if file_path else filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if file_path:
            if self.root.stored_data.operation_mode != 'send':
                if self.root.stored_data.operation_mode != 'wallet_annihilation':
                    self.root.wallet_thread_manager.stop_thread("load_balance")
                    self.root.wallet_thread_manager.start_thread("load_wallet", self.get_wallet_data, args=(file_path, self.load_balance), )
                    
                else:
                    messagebox.showerror("Error", "Can not load a wallet file while wallet annihilation is taking place.")
                    return
            else:
                messagebox.showerror("Error", "Can not load a wallet file while a transaction is taking place.")
                return


    def get_wallet_data(self, stop_signal=None, file_path=None, callback=None):
        self.root.event_handler.stop_loading_wallet = stop_signal
        result = wallet_client.decryptWalletEntries(file_path, password="", from_gui=True, callback_object=self.callbacks, stop_signal=stop_signal)
        #print("decryptWalletEntries result: ",result)
        if result:
            time.sleep(1)
            self.root.stored_data.wallet_file = file_path
            if not self.root.stored_data.wallet_loaded:
                self.root.stored_data.wallet_loaded = result
            #print("sending thread callback")
            if callback:
                callback()
        else:
            if not self.root.stored_data.wallet_loaded and self.root.stored_data.wallet_data != {"entry_data": {}}:
                self.root.stored_data.wallet_file = file_path
                self.root.stored_data.wallet_loaded = True
            self.root.stored_data.operation_mode = None
        return
    

    def update_wallet_data(self):
        # Check if the wallet data has been updated
        if getattr(self.root.stored_data, 'wallet_data_updated', False) and self.root.stored_data.wallet_data:            
            # Get temp address value
            temporary_address = self.root.stored_data.temporary_address
            self.root.stored_data.wallet_addresses.extend([temporary_address])
            # Reset temp address value
            self.root.stored_data.temporary_address = None
            
            # Update send from combobox
            self.root.send_page.send_from_combobox['values'] = (*self.root.send_page.send_from_combobox['values'], temporary_address)
            
            # Define extra space for certain columns
            extra_space = 30   
            
            # Calculate the width for each column based on content
            for col_index, col in enumerate(self.root.account_page.columns):
                column_width = max([self.root.account_page.treeview_font.measure(str(row[col_index])) for row in self.root.stored_data.formatted_data], default=0)
                if col == "Address":
                    column_width += extra_space
                else:
                    column_width += 150                
                column_width = max(column_width, self.root.account_page.column_min_widths.get(col, 0))
                self.root.account_page.accounts_tree.column(col, width=column_width, stretch=tk.YES)

            if len(self.root.stored_data.formatted_data) % 2 == 0:
                column_tag = 'evenrow'
            else:
                column_tag = 'oddrow'
            
            self.root.account_page.accounts_tree.insert('', tk.END, values=(temporary_address),tags=(column_tag,))
            
            # Reset flag
            self.root.stored_data.wallet_data_updated = False

        self.root.after(100, self.update_wallet_data)


    #Load Balance Methods
    def load_balance(self):
        self.root.account_page.refresh_balance_button.config(state='disabled')

        if not self.root.disable_exchange_rate_features:
            current_heading = self.root.account_page.accounts_tree.heading('Value')['text']
            if " ↾" in current_heading or " ⇂" in current_heading or " ⥮" in current_heading:
                base_name = current_heading[-7:]
            else:
                base_name = "Value"

            self.root.account_page.accounts_tree.heading('Value', text=f"{self.root.stored_data.currency_code} {base_name}")

            title_width = self.root.account_page.treeview_font.measure(f"{self.root.stored_data.currency_code} {base_name}") + 30  # Extra space for padding
            #self.root.account_page.column_min_widths["Value"] = title_width
            self.root.account_page.accounts_tree.column('Value', minwidth=title_width, stretch=tk.YES)
    
            self.root.account_page.total_value_text.config(text=f"Total {self.root.stored_data.currency_code} Value:")
        
            self.root.settings_page.currency_code_combobox.config(state='disabled')

        self.root.account_page.total_balance_text.config(text=f"Total Balance:")
        
        self.root.progress_bar.config(maximum=0,value=0)
        self.root.wallet_thread_manager.start_thread("load_balance", self.get_balance_data, args=(self.root.stored_data.wallet_file,), )
        
        if self.root.progress_bar["value"] != 0:
            self.root.progress_bar.config(maximum=0, value=0)


    def get_balance_data(self, stop_signal=None, file_path=None):
        self.root.event_handler.stop_getting_balance = stop_signal
        if self.root.stored_data.wallet_data:
            node, _ , _ = self.root.settings_page.validate_node_fields()
            self.root.stored_data.balance_loaded = wallet_client.checkBalance(file_path, password=None, node=node, to_json=True, currency_code=self.root.stored_data.currency_code if not self.root.disable_exchange_rate_features else "", currency_symbol=self.root.stored_data.currency_symbol if not self.root.disable_exchange_rate_features else "", address_data=json.dumps(self.root.stored_data.wallet_data), from_gui=True, callback_object=self.callbacks,stop_signal=stop_signal)
            

    def update_balance_data(self, balance_data=None, stop_signal=None):
            # Create a dictionary for quick lookup of Treeview items by address
            accounts_tree = self.root.account_page.accounts_tree
            treeview_items = {accounts_tree.item(child)["values"][0]: child for child in accounts_tree.get_children()}
    
            def process_entries(entry):
                address = entry['address']
                amount = entry['balance']['amount']
                pending_balance = entry['balance']['pending_balance']
                
                if not self.root.disable_exchange_rate_features:
                    currency = entry['balance']['currency']
                    value = entry['balance'][f'{self.root.stored_data.currency_code.lower()}_value']

                if address in treeview_items:
                    # Update existing entry
                    if self.root.disable_exchange_rate_features:
                        accounts_tree.item(treeview_items[address], values=(address, f"{amount} DNR", f"{pending_balance} DNR"))
                    else:
                        accounts_tree.item(treeview_items[address], values=(address, f"{amount} {currency}", f"{pending_balance} {currency}", value))
                else:
                    # Insert new entry
                    if self.root.disable_exchange_rate_features:
                        accounts_tree.insert('', tk.END, values=(address, f"{amount} DNR", f"{pending_balance} DNR"))
                    else:
                        accounts_tree.insert('', tk.END, values=(address, f"{amount} {currency}", f"{pending_balance} {currency}", value))
                if stop_signal.is_set():
                    return

            # Process regular addresses
            process_entries(list(balance_data["balance_data"]['addresses'])[-1])
    
            # Check if 'imported_addresses' exists and process them
            if 'imported_addresses' in balance_data["balance_data"] and balance_data["balance_data"]['imported_addresses']:
                process_entries(list(balance_data["balance_data"]['imported_addresses'])[-1])
            
            self.root.account_page.total_balance_text.config(text=f"Total Balance: {self.root.stored_data.total_balance} DNR")
            
            if not self.root.disable_exchange_rate_features:
                self.root.account_page.total_value_text.config(text=f"Total {self.root.stored_data.currency_code} Value: {self.root.stored_data.total_balance_value}")
    

    #Gets DNR Price
    def get_dnr_price(self):
        price = wallet_client.get_price_info(currency_code=self.root.stored_data.currency_code)
        formatted_price = Decimal(str(price))
        self.root.stored_data.price_data = formatted_price
        formatted_price_str = "{:.8f}".format(formatted_price)
        return formatted_price_str
    

    #Transaction Methods
    def tx_auth(self):
        self.root.send_page.send_button.focus_set()
        self.root.stored_data.operation_mode = "send"
        self.root.send_page.send_from_combobox.config(state='disabled')
        self.root.send_page.amount_entry.config(state='disabled')
        self.root.send_page.recipient_entry.config(state='disabled')
        self.root.send_page.message_entry.config(state='disabled')
        self.root.send_page.send_button.config(state='disabled')
        self.root.send_page.max_amount_button.config(state='disabled')
        self.root.send_page.half_amount_button.config(state='disabled')
        
        if 'load_wallet' not in self.root.event_handler.thread_event:
            self.root.wallet_thread_manager.start_thread("load_wallet", self.get_wallet_data, args=(self.root.stored_data.wallet_file, self.send_transaction), )
        

    def send_transaction(self):
        if self.root.stored_data.wallet_authenticated:
            sender = self.root.send_page.send_from_combobox.get()
            receiver = self.root.send_page.recipient_entry.get()
            amount = self.root.send_page.amount_entry.get()
            message = self.root.send_page.message_entry.get()
            user_confirmation = False

            if not self.root.stored_data.disable_tx_confirmation_dialog:
                result = self.callbacks.post_tx_confirmation(sender=sender, receiver=receiver, amount=amount)
                
                if result is not None:
                    user_confirmation, disable_tx_confirmation_dialog = result
                else:
                    self.root.stored_data.operation_mode = None
                    return

                if disable_tx_confirmation_dialog:
                    self.root.stored_data.disable_tx_confirmation_dialog = True

            if self.root.stored_data.disable_tx_confirmation_dialog or user_confirmation:
                for entry in self.root.stored_data.wallet_data["entry_data"]:
                    if entry != "master_mnemonic":
                        for entry_data in self.root.stored_data.wallet_data["entry_data"][entry]:
                            if entry_data["address"] == sender:
                                private_key = entry_data["private_key"]
                                break
                
                msg_str = ""  # Reinitialize msg_str for each transaction
                node, _ , _ = self.root.settings_page.validate_node_fields()
                transaction, msg_str = wallet_client.prepareTransaction(filename=None, password=None, totp_code=None, amount=amount, sender=sender, private_key=private_key, receiver=receiver, message=message, node=node, from_gui=True)
                self.root.send_page.tx_log.config(state='normal')
        
                if transaction:
                    transaction_hash = sha256(transaction.hex())
                    hyperlink_url = f"https://denaro-explorer.aldgram-solutions.fr/address/transaction/{transaction_hash}"
                    hyperlink_text = f"Denaro Explorer link: {hyperlink_url}"
                    tx_str = (f'\nTransaction successfully pushed to node. \n'
                                f'Transaction hash: {transaction_hash}\n'
                                f'{hyperlink_text}\n')
                    print(tx_str)
                    msg_str += f'[{datetime.now()}]{tx_str}'
                msg_str += "\n----------------------------------------------------------------"

                with self.root.translation_engine.no_translate():
                    self.root.send_page.tx_log.insert(tk.END, f'\n{msg_str}\n')
        
                if transaction:
                    hyperlink_tag = f"hyperlink-{transaction_hash}"
                    start = self.root.send_page.tx_log.search(hyperlink_url, "1.0", tk.END)
                    if start:
                        end = f"{start}+{len(hyperlink_url)}c"
                        self.root.send_page.tx_log.tag_add(hyperlink_tag, start, end)
                        self.root.send_page.tx_log.tag_config(hyperlink_tag, foreground="blue", underline=True)
                        self.root.send_page.tx_log.tag_bind(hyperlink_tag, "<Enter>", self.root.gui_utils.on_link_enter)
                        self.root.send_page.tx_log.tag_bind(hyperlink_tag, "<Leave>", self.root.gui_utils.on_link_leave)
                        self.root.send_page.tx_log.tag_bind(hyperlink_tag, "<Button-1>", lambda e, url=hyperlink_url: self.root.gui_utils.open_link(url))        
                self.root.send_page.tx_log.config(state='disabled')
                self.root.send_page.tx_log.yview(tk.END)
        self.root.stored_data.operation_mode = None
    

    def get_entry_data(self, address=None):
        for entry_type, entries in self.root.stored_data.wallet_data["entry_data"].items():
            if entry_type not in ["key_data", "master_mnemonic"]:
                for entry in entries:
                    if entry["address"] == address:
                        #is_import = entry_type == "imported_entries"
                        return entry, entry_type
    

    # Note: Add progress bar increments when creating wallet in generateAddressHelper
    def create_wallet(self, stop_signal=None, filename=None, password=None, deterministic=False, encrypt=False, use2FA=False):
        if stop_signal and stop_signal.is_set():
            return
        
        mnemonic = None
        
        filename = self.callbacks.save_file_dialog(os.path.basename(filename)+'.json')

        if isinstance(filename, tuple):
                return None
            
        if filename == '' or filename is None:
            return None

        if deterministic:
            mnemonic = wallet_client.generate_mnemonic()
            if self.callbacks.post_backup_mnemonic_dialog(mnemonic=mnemonic) == False:
                self.callbacks.post_messagebox(title="Info", msg="Operation canceled. Wallet has not been created.")
                return
            
        result = wallet_client.generateAddressHelper(filename=filename, password=password, new_wallet=True, deterministic=deterministic, encrypt=encrypt, use2FA=use2FA, mnemonic=mnemonic, from_gui=True, callback_object=self.callbacks)
        
        self.root.gui_utils.update_wallet_menu()
        
        if self.root.progress_bar["value"] != 0:
            self.root.progress_bar.config(maximum=0, value=0)
        
        self.root.stored_data.operation_mode = None
        
        if result is None:
            return
        
        if result[0]:
            self.root.stored_data.wait_finished = True
            time.sleep(1)
            if self.callbacks.post_confirmation_prompt(title="Wallet Created", msg="New wallet has been created.\nWould you like to open it?"):
                self.load_wallet(file_path=result[1])

            #if deterministic:
            #    if self.callbacks.post_backup_mnemonic_dialog(mnemonic=result[2]):
            #        if self.callbacks.post_confirmation_prompt(title="Recovery Phrase Confimed", msg="Recovery phrase has been confirmed. Would you like to open the walet?"):
            #            self.load_wallet(file_path=result[1])
            #    else:
            #        if self.callbacks.post_confirmation_prompt(title="Wallet Created", msg="New wallet has been created. Would you like to open it?"):
            #            self.load_wallet(file_path=result[1])
            #else:
            #    
            #    if self.callbacks.post_confirmation_prompt(title="Wallet Created", msg="New wallet has been created. Would you like to open it?"):
            #        self.load_wallet(file_path=result[1])
    
    
    def restore_wallet(self, stop_signal=None, filename=None, mnemonic=None, password=None, encrypt=False, use2FA=False):

        if stop_signal and stop_signal.is_set():
            return
        
        filename = self.callbacks.save_file_dialog(os.path.basename(filename)+'.json')

        if isinstance(filename, tuple):
                return None
            
        if filename == '' or filename is None:
            return None
        
        result = wallet_client.generateAddressHelper(filename=filename, password=password, new_wallet=True, deterministic=True, encrypt=encrypt, use2FA=use2FA, mnemonic=mnemonic, from_gui=True, callback_object=self.callbacks)

        self.root.gui_utils.update_wallet_menu()
        
        if self.root.progress_bar["value"] != 0:
            self.root.progress_bar.config(maximum=0, value=0)
        
        self.root.stored_data.operation_mode = None
        
        if result is None:
            return
        
        if result[0]:
            self.root.stored_data.wait_finished = True
            time.sleep(1)
            if self.callbacks.post_confirmation_prompt(title="Wallet Created", msg="New wallet has been created.\nWould you like to open it?"):
                self.load_wallet(file_path=result[1])


    def generate_address(self, stop_signal=None):
        if stop_signal and stop_signal.is_set():
            return
        
        file_path = self.root.stored_data.wallet_file

        self.root.wallet_thread_manager.stop_specific_threads(names=['load_wallet', 'load_balance'])
        
        if self.root.progress_bar["value"] != 0:
            self.root.progress_bar.config(maximum=0, value=0)

        result = wallet_client.generateAddressHelper(filename=file_path, new_wallet=False, from_gui=True, callback_object=self.callbacks, stop_signal=stop_signal)
        
        self.root.stored_data.operation_mode = None

        if result is None:
            return
        
        if result[0]:
            if self.callbacks.post_confirmation_prompt("Info", msg="An address has been successfully generated and added to the wallet file.\nWould you like to display address information?"):
                self.callbacks.post_show_address_info(entry_data=result[1], entry_type='entries', wait=True)
                
            if self.callbacks.post_confirmation_prompt(title="Wallet Reload Required", msg="The wallet file must be reloaded to reflect the new changes.\nWould you like to reload it now?"):
                if self.root.stored_data.operation_mode != 'send':
                    self.root.gui_utils.close_wallet()
                    self.load_wallet(file_path=file_path)
                else:
                    messagebox.showerror("Error", "Can not reload wallet while a transaction is taking place.")
                    return
                
        
class Callbacks:
    def __init__(self, root):
        self.root = root
       
    def post_ask_string(self, title, msg, show=None, modal=True):
        dialog_lambda = lambda result_queue: self.root.dialogs.ask_string(
            title, msg, show, modal=modal, result_queue=result_queue
        )
        return self.root.wallet_thread_manager.post_and_wait(dialog_lambda)


    def post_confirmation_prompt(self, title, msg, msg_2=None, modal=True):
        dialog_lambda = lambda result_queue: self.root.dialogs.confirmation_prompt(
            title, msg, msg_2, modal=modal, result_queue=result_queue
        )
        return self.root.wallet_thread_manager.post_and_wait(dialog_lambda)


    def post_password_dialog(self, title, msg, modal=True):
        dialog_lambda = lambda result_queue: self.root.dialogs.password_dialog(
            title, msg, modal=modal, result_queue=result_queue
        )
        return self.root.wallet_thread_manager.post_and_wait(dialog_lambda)


    def post_password_dialog_with_confirmation(self, title, msg, modal=True):
        dialog_lambda = lambda result_queue: self.root.dialogs.password_dialog_with_confirmation(
            title, msg, modal=modal, result_queue=result_queue
        )
        return self.root.wallet_thread_manager.post_and_wait(dialog_lambda)


    def post_tx_confirmation(self, sender, receiver, amount, modal=True):
        dialog_lambda = lambda result_queue: self.root.dialogs.tx_confirmation_dialog(
            sender, receiver, amount, modal=modal, result_queue=result_queue
        )
        return self.root.wallet_thread_manager.post_and_wait(dialog_lambda)


    def post_backup_mnemonic_dialog(self, mnemonic, modal=True):
        dialog_lambda = lambda result_queue: self.root.dialogs.backup_mnemonic_dialog(
            mnemonic, modal=modal, result_queue=result_queue
        )
        return self.root.wallet_thread_manager.post_and_wait(dialog_lambda)


    def post_input_listener_dialog(self, close_event, modal=True):
        dialog_lambda = lambda result_queue: self.root.dialogs.input_listener_dialog(
             modal=modal, result_queue=result_queue,
             close_event=close_event
         )
        return self.root.wallet_thread_manager.post_and_wait(dialog_lambda)


    def post_messagebox(self, title, msg, modal=True):
        dialog_lambda = lambda result_queue: self.root.dialogs.messagebox(
            title, msg, modal=modal, result_queue=result_queue
        )
        return self.root.wallet_thread_manager.post_and_wait(dialog_lambda)


    def post_messagebox_wait(self, title, message, close_event, modal=True):
        self.root.wallet_thread_manager.request_queue.put(lambda: self.root.dialogs.messagebox_wait(title, message,
             modal=modal, close_event=close_event))


    # =========================================================================
    # == GUI THREAD NON-BLOCKING API
    # =========================================================================

    def post_about_wallet_dialog(self, modal=True):
        self.root.wallet_thread_manager.request_queue.put(
            lambda: self.root.dialogs.about_wallet_dialog(modal=modal)
        )


    def post_create_wallet_dialog(self, modal=True):
        self.root.wallet_thread_manager.request_queue.put(
            lambda: self.root.dialogs.create_wallet_dialog(modal=modal)
        )


    def post_show_address_info(self, event=None, entry_data=None, entry_type=None, wait=False, modal=True):
        if wait:
            dialog_lambda = lambda result_queue: self.root.dialogs.address_info(
                event=event,
                entry_data=entry_data,
                entry_type=entry_type,
                result_queue=result_queue,
                modal=modal
            )
            return self.root.wallet_thread_manager.post_and_wait(dialog_lambda)
        else:
            self.root.wallet_thread_manager.request_queue.put(
                lambda ed=entry_data, et=entry_type, ev=event: self.root.dialogs.address_info(
                    event=ev, entry_data=ed, entry_type=et, modal=modal
                )
            )
            return None
        
    def post_2FA_QR_dialog(self, qr_window_data, modal=True):
        self.root.wallet_thread_manager.request_queue.put(
            lambda: self.root.dialogs.show_2FA_QR_dialog(qr_window_data, from_gui=True, modal=modal)
        )
    
    
    def save_file_dialog(self, initialfile):
        return filedialog.asksaveasfilename(filetypes=[("JSON files", "*.json")], initialfile=initialfile, initialdir='./wallets', confirmoverwrite=False)
        
    
    def set_wallet_data(self, wallet_data, is_import=False, stop_signal=None):
        # Wait if wallet_data_updated is True, indicating an ongoing GUI update
        while getattr(self.root.stored_data, 'wallet_data_updated', False):
            # Check for stop signal during wait to exit if needed
            if stop_signal and stop_signal.is_set():
                #print("Stop signal received while waiting. Exiting function.")
                return False
            time.sleep(0.1)  # Brief pause to wait for GUI update to complete
        
        # Check stop signal again before proceeding with data update
        if stop_signal and stop_signal.is_set():
            #print("Stop signal received. Exiting function.")
            return False
        try:
            # Proceed with updating the wallet data based on the import flag
            if is_import:
                wallet_data.pop("is_import", None)  # Remove 'is_import' if present
                self.root.stored_data.imported_entries.append(wallet_data)
                # Update the stored wallet data for imported entries
                self.root.stored_data.wallet_data["entry_data"]["imported_entries"] = self.root.stored_data.imported_entries
            else:
                self.root.stored_data.generated_entries.append(wallet_data)
                # Update the stored wallet data for generated entries
                self.root.stored_data.wallet_data["entry_data"]["entries"] = self.root.stored_data.generated_entries
    
            # Extend formatted data with the new entry
            self.root.stored_data.formatted_data.extend([(wallet_data["address"], "", "", "")])
            # Temporarily store the new address for potential immediate use
            self.root.stored_data.temporary_address = wallet_data["address"]
    
            # Set the flag to True to indicate that new wallet data has been added
            self.root.stored_data.wallet_data_updated = True
    
        except Exception as e:
            #print(f"Error updating wallet data: {e}")
            return False
        return True
    

    def set_balance_data(self, balance_data, total_balance, total_value, stop_signal=None):
        self.root.stored_data.balance_data = balance_data
        self.root.stored_data.total_balance = total_balance
        self.root.stored_data.total_balance_value = total_value
        if balance_data:
            self.root.wallet_operations.update_balance_data(balance_data, stop_signal=stop_signal)


    def configure_progress_bar(self, max_value):
        self.root.progress_bar.config(maximum=max_value*100)


    def get_operation_mode(self):
        return self.root.stored_data.operation_mode
    

    def clear_wallet_data(self, preserve_wallet_data=True):
        if preserve_wallet_data:
            wallet_file = self.root.stored_data.wallet_file
            wallet_authenticated = self.root.stored_data.wallet_authenticated
        
        currency_code = self.root.stored_data.currency_code
        currency_symbol = self.root.stored_data.currency_symbol
        price_data = self.root.stored_data.price_data
        warning_agreed = self.root.stored_data.warning_agreed

        self.root.stored_data = StoredData()
        
        if preserve_wallet_data:
            self.root.stored_data.wallet_file = wallet_file
            self.root.stored_data.wallet_authenticated = wallet_authenticated
        
        self.root.stored_data.warning_agreed = warning_agreed
        self.root.stored_data.currency_code = currency_code
        self.root.stored_data.currency_symbol = currency_symbol
        self.root.stored_data.price_data = price_data

        self.clear_page_data()
    

    def clear_balance_data(self):
        self.root.stored_data.balance_data = []


    def clear_page_data(self):
        self.root.account_page.accounts_tree.delete(*self.root.account_page.accounts_tree.get_children())
        self.root.send_page.send_from_combobox.set('')
        self.root.send_page.send_from_combobox['values'] = []

        self.root.send_page.amount_entry_text.set('')
        self.root.send_page.recipient_entry_text.set('')
        self.root.send_page.message_entry_text.set('')

        self.root.account_page.total_balance_text.config(text=f"Total Balance:")
        
        if not self.root.disable_exchange_rate_features:
            self.root.account_page.total_value_text.config(text=f"Total Value:")
            self.root.account_page.accounts_tree.heading('Value', text=f"Value")
        
        self.root.progress_bar.config(maximum=0,value=0)

                # Remove existing sort order indicator if present
        for column in self.root.account_page.column_sort_order:
            current_heading = self.root.account_page.accounts_tree.heading(column)['text']
            if " ↾" in current_heading or " ⇂" in current_heading or " ⥮" in current_heading:
                base_name = current_heading[:-2]
            else:
                base_name = current_heading
            base_name += " ⥮"
            self.root.account_page.column_sort_order[column] = False
            # Update the sorted column heading with the new sort order indicator
            self.root.account_page.accounts_tree.heading(column, text=base_name)
            title_width = self.root.account_page.treeview_font.measure(base_name) + 20  # Extra space for padding
            self.root.account_page.column_min_widths[column] = title_width
        
        if not self.root.disable_exchange_rate_features:
            self.root.account_page.accounts_tree.column('Value', minwidth=title_width, stretch=tk.YES)


@dataclass
class StoredData:
    wallet_file: Optional[str] = None
    wallet_data: dict = field(default_factory=lambda: {"entry_data": {}})
    generated_entries: dict = field(default_factory=lambda: [])
    imported_entries: dict = field(default_factory=lambda: [])
    formatted_data: dict = field(default_factory=lambda: [])
    temporary_address: Optional[str] = None
    wallet_addresses: dict = field(default_factory=lambda: [])
    wallet_authenticated : bool = False
    master_mnemonic: str = ""
    ask_string_result: Optional[str] = None
    ask_bool_result: Optional[bool] = None
    wallet_loaded: bool = False
    entry_count: int = 0
    wallet_data_updated: bool = False
    wallet_deleted: bool = False

    balance_data: dict = field(default_factory=lambda: [])
    total_balance: Decimal = Decimal(0)
    total_balance_value: Optional[str] = None
    currency_code: Optional[str] = None
    currency_symbol: Optional[str] = None
    balance_loaded: bool = False    
    price_data: Optional[str] = None

    operation_mode: Optional[str] = None
    disable_tx_confirmation_dialog: bool = False
    
    progress_bar_increment: bool = False

    input_listener_time_remaining: Optional[str] = None
    input_listener_submit: Optional[bool] = False

    confirm_mnemonic_back_button_press: Optional[bool] = False
    wait_finished: Optional[bool] = False

    default_node: Optional[str] = None
    node_validation: Optional[str] = None
    node_valid: Optional[bool] = None
    node_validation_performed: bool = False

    warning_agreed: Optional[bool] = False
    
    
if __name__ == "__main__":
    app = DenaroWalletGUI()
    app.mainloop()