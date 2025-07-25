import sys
import os
import re

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, simpledialog, messagebox, Menu, font
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

# Get the absolute path of the directory containing the current script.
dir_path = os.path.dirname(os.path.realpath(__file__))

# Insert folder paths for modules
sys.path.insert(0, dir_path + "/denaro")
sys.path.insert(0, dir_path + "/denaro/wallet")
sys.path.insert(0, dir_path + "/denaro/wallet/utils")

import wallet_client
from denaro.wallet.utils.wallet_generation_util import sha256
from denaro.wallet.utils.tkinter_utils.custom_auto_complete_combobox import AutocompleteCombobox
from denaro.wallet.utils.tkinter_utils.custom_dialog import CustomDialog
from denaro.wallet.utils.tkinter_utils.dialogs import Dialogs
from denaro.wallet.utils.tkinter_utils.custom_popup import CustomPopup
from denaro.wallet.utils.thread_manager import WalletThreadManager

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
        self.denaro_price_text.grid(row=0, column=1, sticky='nw', padx=5, pady=5)
        self.total_balance_text.grid(row=1, column=1, sticky='nw', padx=5,)
        self.total_value_text.grid(row=1, column=1, sticky='sw', padx=5, pady=(0, 5))  # Ensuring it stays in the same cell

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
        self.denaro_price_text = tb.Label(self.balance_frame, text="DNR/USD Price:", foreground='white', background='black')        
        self.total_balance_text = tb.Label(self.balance_frame, text="Total balance:", foreground='white', background='black')
        self.total_value_text = tb.Label(self.balance_frame, text="Total Value:", foreground='white', background='black')

        # Accounts frame
        self.accounts_frame = tb.Frame(self)
        
        # TreeView and scrollbar
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
        
        for col in ["Balance", "Pending", "Value"]:
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
        address_pattern = r'^[DE][1-9A-HJ-NP-Za-km-z]{44}$'
        if re.match(address_pattern, content):
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
        self.prev_currency_code = None
        self.currency_code_valid = False
        self.currency_code = ""
        self.currency_symbol = ""

        self.keep_save_button_disabled = False

        self.create_widgets()  # Create and place widgets
        self.configure_layout() # Configure the grid layout of the AccountPage
        self.update_save_button_state()

        # Dynamically identify selectable widgets
        self.root.selectable_widgets.extend(self.root.gui_utils.identify_selectable_widgets(self))


    def configure_layout(self):
        # Position the currency code related widgets
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
        
        # Ensure the denaro_node_frame columns do not affect the overall layout
        self.denaro_node_frame.columnconfigure(0, weight=1)
        self.denaro_node_frame.columnconfigure(1, weight=0)  # Minimal weight to colon column
        self.denaro_node_frame.columnconfigure(2, weight=1)

        # Save config button
        self.save_config_frame.grid(row=4, column=0, sticky='we', padx=10)
        self.node_validation_msg_label.pack(padx=5, anchor='w')
        self.save_config_button.pack(pady=10, side='right')


    def create_widgets(self):
        # Settings Page Layout
        #######################################################################################        
        #Currency code
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

        self.denaro_node_frame = tb.LabelFrame(self, text="Denaro Node Config:",width=20)
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
        
        # Save config button
        self.save_config_frame = tb.Frame(self)
        self.node_validation_msg_label = tb.Label(self.save_config_frame, text="")
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

        if not self.currency_code_combobox['values'][0] == self.separators[0]:
            self.root.gui_utils.add_combobox_separator_at_index(self.currency_code_combobox, self.separators[0], 0)
        if not self.currency_code_combobox['values'][162] == self.separators[1]:
            self.root.gui_utils.add_combobox_separator_at_index(self.currency_code_combobox, self.separators[1], 162)
        self.on_node_field_change()


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

        currency_code = self.currency_code_combobox.get().strip()
        node_address = self.denaro_node_address_entry.get().strip()
        node_port = self.denaro_node_port_entry.get().strip()

        # Construct the address:port string conditionally including the port
        node = f"{node_address}:{node_port}" if node_port else node_address
        node_validation = not self.disable_node_validation_var.get()

        currency_code_changed = (currency_code != current_config.get('default_currency'))
        node_changed = (node != current_config.get('default_node', ''))
        node_validation_changed = (str(node_validation) != current_config.get('node_validation', ''))
        #fields_empty = not node_address  # Only check if address is empty since port is optional
        #print(currency_code_changed, node_changed, not fields_empty)
        settings_changed = self.currency_code_valid and (currency_code_changed or node_changed or node_validation_changed) and not self.keep_save_button_disabled
        return settings_changed
    

class BlankPage(BasePage):
    def __init__(self, parent, root):
        super().__init__(parent, root)
        ttk.Label(self, text="TBA").pack(expand=True)


class DenaroWalletGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.wallet_client_version = f"{wallet_client.wallet_client_version} GUI"
        self.title(self.wallet_client_version)
        self.geometry("1024x576")
        self.minsize(780, 390)
        icon = tk.PhotoImage(file="./denaro/gui_assets/denaro_logo.png")
        self.iconphoto(True, icon)

        self.pages = {}
        self.current_page = None
        self.selectable_widgets = []
        self.active_button = None
        self.styles = tb.Style()
        self.stored_data = StoredData()
        self.gui_utils = GUIUtils(self)
        self.wallet_thread_manager = WalletThreadManager(self)
        atexit.register(self.wallet_thread_manager.stop_all_threads)
        self.wallet_operations = WalletOperations(self)
        self.dialogs = Dialogs(self)
        self.custom_popup = CustomPopup(self)
        self.config_handler = ConfigHandler(self)

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
        
        self.config_handler.update_config_values()
        

    def create_menus(self):
        # Context Menu for Textboxes
        self.textboxes_context_menu = tb.Menu(self, tearoff=0)
        self.textboxes_context_menu.add_command(label="Cut", command=self.gui_utils.cut_text)
        self.textboxes_context_menu.add_command(label="Copy", command=self.gui_utils.copy_selection)
        self.textboxes_context_menu.add_command(label="Paste", command=self.gui_utils.paste_text)
        self.textboxes_context_menu.add_command(label="Delete", command= lambda: self.gui_utils.cut_text(delete=True))
        self.textboxes_context_menu.add_command(label="Select All", command=self.gui_utils.select_all_text)       
        
        # Context Menu for Treeview
        self.treeview_context_menu = tb.Menu(self, tearoff=0)
        self.treeview_context_menu.add_command(label="Copy", command=self.gui_utils.copy_selection)
        self.treeview_context_menu.add_command(label="Send", command=lambda: (self.gui_utils.address_context_menu_selection(set_address_combobox=True, show_send_page=True)))
        self.treeview_context_menu.add_command(label="Address Info", command=self.dialogs.address_info)
        self.treeview_context_menu.add_command(label="View on Explorer",  command=lambda: self.gui_utils.address_context_menu_selection(view_explorer=True))

        #Menu Bar
        self.menu_bar = tb.Menu(self, tearoff=0)
        self.file_menu = tb.Menu(self.menu_bar, tearoff=0)
        self.wallet_menu = tb.Menu(self.file_menu, tearoff=0)
        self.help_menu = tb.Menu(self.menu_bar, tearoff=0)

        self.menu_bar.add_cascade(label="File", menu=self.file_menu)
        self.file_menu.add_cascade(label="Load Wallet", menu=self.wallet_menu)
        self.file_menu.add_command(label="Create Wallet", command=self.dialogs.create_wallet_dialog)
        self.file_menu.add_command(label="Restore Wallet")
        self.file_menu.add_command(label="Backup Wallet")
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Generate Address", command = lambda: self.wallet_thread_manager.start_thread("generate_address", self.wallet_operations.generate_address, args=(), ), state='disabled')
        self.file_menu.add_command(label="Import Address")
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Close Wallet", command=self.gui_utils.close_wallet)
        
        self.menu_bar.add_cascade(label="Help", menu=self.help_menu)
        self.help_menu.add_command(label="About", command=self.dialogs.about_wallet_dialog)


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
        # Adjust this method to dynamically show pages
        self.button_frame = tb.Frame(self.left_frame_inner, padding=(0,0), style="gray.TFrame")
        self.button_frame.pack(fill=tk.X)
        button = tb.Button(self.button_frame, text=name, style="menuButtonInactive.TButton", command=lambda name=name: [self.show_page(name), self.gui_utils.activate_button(button)])
        button.pack(fill=tk.X, pady=(0, 2))
     

    def show_page(self, page_name):
        button = self.gui_utils.find_button_by_text(self.left_frame_inner, page_name)
        if button != self.active_button:
            self.gui_utils.activate_button(button)

        if self.current_page:
            self.current_page.forget()        

        page = self.pages.get(page_name)

        if not page:
            if page_name == "Account":
                page = AccountPage(self.page_container, self)
            elif page_name == "Send":
                page = SendPage(self.page_container, self)
            elif page_name == "Settings":
                page = SettingsPage(self.page_container, self)
            else:
                page = BlankPage(self.page_container, self)
            
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

    def update_config_values(self):  
        if self.config_values:
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
    

    def save_config(self):
        #self.root.settings_page.node_validation_msg_label.config(text="")
        
        if not self.root.settings_page.denaro_node_address_entry.get().strip():
            self.root.settings_page.denaro_node_address_entry.delete(0, 'end')
            self.root.settings_page.denaro_node_address_entry.insert(0, "https://denaro-node.gaetano.eu.org")
            self.root.settings_page.denaro_node_port_entry.delete(0, 'end')
        
        node, string_valid, node_validation_enabled = self.root.settings_page.validate_node_fields()
        
        if string_valid:
            # Configuration saving logic needs to consider the optional port in validation
            if self.root.settings_page.check_setting_changes():

                if self.config_values['default_currency'] != self.root.stored_data.currency_code:
                    self.config_values['default_currency'] = self.root.stored_data.currency_code
                
                if self.config_values['default_node'] != node:
                    self.config_values['default_node'] = node
                    self.root.stored_data.node_valid = False
                    self.root.stored_data.node_validation_performed = False

                if self.config_values['node_validation'] != str(not node_validation_enabled):
                    self.config_values['node_validation'] = str(not node_validation_enabled)
                    self.root.stored_data.node_valid = False
                    self.root.stored_data.node_validation_performed = False
                
                temp_config = wallet_client.read_config(disable_err_msg = True)
                
                if temp_config != self.config_values:                    
                    wallet_client.write_config(config=self.config_values)

                new_config = wallet_client.read_config(disable_err_msg = True)

                if new_config == self.config_values: 
                    self.root.custom_popup.add_popup(timeout=5000, prompt=[{"label_config":"text='Settings saved to config file.', background='#2780e3', anchor='center', font='Calibri 10 bold'", "grid_config":"sticky='nsew'"}], 
                                                                   grid_layout_config=[{"grid_row_config":"index=0, weight=1"}, {"grid_column_config":"index=0, weight=1"}])
                else:
                    self.root.custom_popup.add_popup(timeout=5000, prompt=[{"label_config":"text='Settings not saved to config file.', background='#2780e3', anchor='center', font='Calibri 10 bold'", "grid_config":"sticky='nsew'"}], 
                                                                   grid_layout_config=[{"grid_row_config":"index=0, weight=1"}, {"grid_column_config":"index=0, weight=1"}])

                self.update_config_values()

        else:
            self.root.settings_page.keep_save_button_disabled = True
            self.root.settings_page.update_save_button_state()

class EventHandler:
    def __init__(self, root):
        self.root = root
        self.thread_event = None
        self.price_timer_step = 0
        self.price_timer = 31
        self.stop_loading_wallet = False
        self.stop_getting_balance = False

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

        self.event_listener()
        self.progress_bar_listener()

    def event_listener(self):
        """Updates certain GUI elements based on what event is taking place"""
        self.thread_event = list(self.root.wallet_thread_manager.threads.keys())
        #print(self.thread_event)
            
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
            self.set_currency_combobox_state('normal')

        if self.root.stored_data.wallet_deleted:
            self.root.stored_data.operation_mode = None
            self.root.gui_utils.close_wallet()


        if self.root.stored_data.input_listener_time_remaining == 0:
            if 'input_listener_timer' in self.thread_event:
                self.root.wallet_thread_manager.stop_thread("input_listener_timer") 
        
        self.update_operation_mode_status()
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
            #print("Disabling balance button")
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
            self.set_currency_combobox_state('disabled')

        if 'create_wallet' not in self.thread_event:
            if 'generate_address' not in self.thread_event:
                if str(self.root.file_menu.entryconfig('Create Wallet')['state'][4]) == 'disabled':
                    self.set_all_file_menu_items('normal')
        else:
            if str(self.root.file_menu.entryconfig('Create Wallet')['state'][4]) == 'normal':
                self.set_all_file_menu_items('disabled')

        if 'generate_address' not in self.thread_event:
            if 'create_wallet' not in self.thread_event:
                if str(self.root.file_menu.entryconfig('Generate Address')['state'][4]) == 'disabled':
                    self.set_all_file_menu_items('normal')
        else:
            if str(self.root.file_menu.entryconfig('Generate Address')['state'][4]) == 'normal':
                self.set_all_file_menu_items('disabled')

    def update_wallet_not_loaded_state(self):
        if self.root.stored_data.operation_mode is None:
            self.update_status_bar("No Wallet Loaded")

        self.set_send_page_state('disabled')

        if 'create_wallet' not in self.thread_event:
            self.set_menu_item_state('Load Wallet', 'normal')
            self.set_menu_item_state('Create Wallet', 'normal')
            self.set_menu_item_state('Restore Wallet', 'normal')
            self.set_menu_item_state('Backup Wallet', 'disabled')
            self.set_menu_item_state('Generate Address', 'disabled')
            self.set_menu_item_state('Import Address', 'disabled')
            self.set_menu_item_state('Close Wallet', 'disabled')
        else:
            if str(self.root.file_menu.entryconfig('Create Wallet')['state'][4]) == 'normal':
                self.set_all_file_menu_items('disabled') 

    def update_wallet_load_balance_state(self):
        entries_length = len(self.root.stored_data.wallet_data["entry_data"]["entries"])
        imported_entries_length = len(self.root.stored_data.wallet_data["entry_data"].get("imported_entries", []))
        combined_length = entries_length + imported_entries_length
        status_message = "Wallet Loaded" if combined_length == self.root.stored_data.entry_count else "Wallet Partially Loaded"
        
        if self.root.stored_data.operation_mode is None:
            self.update_status_bar(status_message)

        if str(self.root.account_page.refresh_balance_button["state"]) == "disabled":
            #print("Enabling balance button")
            self.root.account_page.refresh_balance_button.config(state='normal')
            self.previous_states['balance_button'] = 'normal'

        if self.root.stored_data.operation_mode is None and self.root.progress_bar["value"] != 0:
            #print("Resetting progress bar")
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
           # print(f"Updating DNR price timer: {self.price_timer}")
            self.root.gui_utils.update_dnr_price(self.price_timer)
            self.price_timer_step = 0
        if self.price_timer <= 0:
            self.price_timer = 31

    def update_status_bar(self, message):
        if self.previous_states['status_bar'] != message:
            #print(f"Updating status bar: {message}")
            self.root.gui_utils.update_status_bar(message)
            self.previous_states['status_bar'] = message

    def set_send_page_state(self, state):
        if self.previous_states['send_page'] != state:
            #print(f"Setting send page state: {state}")
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
            #print(f"Setting currency combobox state: {state}")
            self.root.settings_page.currency_code_combobox.config(state=state)
            self.previous_states['currency_combobox'] = state
    
    def set_all_file_menu_items(self, state):
        self.set_menu_item_state('Load Wallet', state)
        self.set_menu_item_state('Create Wallet', state)
        self.set_menu_item_state('Restore Wallet', state)
        self.set_menu_item_state('Backup Wallet', state)
        self.set_menu_item_state('Generate Address', state)
        self.set_menu_item_state('Import Address', state)
        self.set_menu_item_state('Close Wallet', state)

    def set_menu_item_state(self, item, state):
        current_state = str(self.root.file_menu.entryconfig(item)['state'][4])
        if current_state != state:
            #print(f"Setting menu item '{item}' state: {state}")
            self.root.file_menu.entryconfig(item, state=state)


            if item == 'Load Wallet':
                self.previous_states['load_wallet_menu_item'] = state
            elif item == 'Create Wallet':
                self.previous_states['create_wallet_menu_item'] = state
            elif item == 'Restore Wallet':
                self.previous_states['restore_wallet_menu_item'] = state
            elif item == 'Backup Wallet':
                self.previous_states['backup_wallet_menu_item'] = state
            elif item == 'Generate Address':
                self.previous_states['generate_address_menu_item'] = state
            elif item == 'Import Address':
                self.previous_states['import_address_menu_item'] = state
            elif item == 'Close Wallet':
                self.previous_states['close_wallet_menu_item'] = state


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
        textboxes_context_menu = self.root.textboxes_context_menu
        treeview_context_menu = self.root.treeview_context_menu

        self.root.current_event = event
        widget = event.widget

        try:
            if isinstance(widget, (tk.Entry, AutocompleteCombobox)):
                try:
                    if str(widget["state"]) == "readonly":
                        textboxes_context_menu.entryconfig("Cut", state="disabled")
                        textboxes_context_menu.entryconfig("Paste", state="disabled")
                        textboxes_context_menu.entryconfig("Delete", state="disabled")
                    else:
                        textboxes_context_menu.entryconfig("Cut", state="normal")
                        textboxes_context_menu.entryconfig("Paste", state="normal")
                        textboxes_context_menu.entryconfig("Delete", state="normal")
                except tk.TclError:
                    textboxes_context_menu.entryconfig("Cut", state="normal")
                    textboxes_context_menu.entryconfig("Paste", state="normal")
                    textboxes_context_menu.entryconfig("Delete", state="normal")
                finally:
                    self.root.current_event = event
                    textboxes_context_menu.tk_popup(event.x_root + 1, event.y_root + 1)
            
            elif isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
                textboxes_context_menu.entryconfig("Cut", state="disabled")
                textboxes_context_menu.entryconfig("Paste", state="disabled")
                textboxes_context_menu.entryconfig("Delete", state="disabled")
                self.root.current_event = event
                textboxes_context_menu.tk_popup(event.x_root+1, event.y_root+1)
            
            elif isinstance(widget,ttk.Treeview):
                row_id = widget.identify_row(self.root.current_event.y)
                col_id = int(widget.identify_column(self.root.current_event.x).replace('#', '')) - 1
                treeview_context_menu.entryconfig("Copy", state="normal" if len(row_id) > 0 else "disabled")
                treeview_context_menu.entryconfig("Send", state="normal" if len(row_id) > 0 and col_id == 0 else "disabled")
                treeview_context_menu.entryconfig("Address Info", state="normal" if len(row_id) > 0 and col_id == 0 else "disabled")
                treeview_context_menu.entryconfig("View on Explorer", state="normal" if len(row_id) > 0 and col_id == 0 else "disabled")
                self.root.account_page.accounts_tree.selection_set(row_id)
                self.root.current_event = event
                treeview_context_menu.tk_popup(event.x_root+1, event.y_root+1)
                #row_id = widget.identify_row(current_event.y)
                ##col_id = int(widget.identify_column(current_event.x).replace('#', '')) - 1
                #if len(row_id) > 0:
                    
            else:
                # Hide the menu if the widget is neither Treeview nor Entry
                textboxes_context_menu.unpost()
                treeview_context_menu.unpost()
        finally:
            self.root.grab_release()
    

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
                    url = f"https://explorer.denaro.is/address/{item['values'][0]}"
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
            elif col == "Value":
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
        for col_name in ["Balance", "Pending", "Value"]:
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
        """Ask for user consent before opening a URL in the web browser."""
        if self.root.dialogs.confirmation_prompt(title="Open Link", msg="Do you want to open this link in your browser?", msg_2=url if show_link else None, is_callback=False):
            webbrowser.open_new(url)


    def on_link_enter(self, event):
        event.widget.config(cursor="hand2")
    

    def on_link_leave(self, event):
        event.widget.config(cursor="")
    

    def activate_button(self, new_active_button):
        if self.root.active_button is not None:
            self.root.active_button.config(style="menuButtonInactive.TButton")  # Reset the old active button to default color
        new_active_button.config(style='TButton')  # Set new active button color
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
        self.root.account_page.total_balance_text.config(text=f"Total Balance:")
        self.root.settings_page.currency_code_combobox.config(state='disabled')
        
        self.root.progress_bar.config(maximum=0,value=0)
        self.root.wallet_thread_manager.start_thread("load_balance", self.get_balance_data, args=(self.root.stored_data.wallet_file,), )
        
        if self.root.progress_bar["value"] != 0:
            self.root.progress_bar.config(maximum=0, value=0)


    def get_balance_data(self, stop_signal=None, file_path=None):
        self.root.event_handler.stop_getting_balance = stop_signal
        if self.root.stored_data.wallet_data:
            node, _ , _ = self.root.settings_page.validate_node_fields()
            self.root.stored_data.balance_loaded = wallet_client.checkBalance(file_path, password=None, node=node, to_json=True, currency_code=self.root.stored_data.currency_code, currency_symbol=self.root.stored_data.currency_symbol, address_data=json.dumps(self.root.stored_data.wallet_data), from_gui=True, callback_object=self.callbacks,stop_signal=stop_signal)
            

    def update_balance_data(self, balance_data=None, stop_signal=None):
            # Create a dictionary for quick lookup of Treeview items by address
            accounts_tree = self.root.account_page.accounts_tree
            treeview_items = {accounts_tree.item(child)["values"][0]: child for child in accounts_tree.get_children()}
    
            def process_entries(entry):
                address = entry['address']
                currency = entry['balance']['currency']
                amount = entry['balance']['amount']
                value = entry['balance'][f'{self.root.stored_data.currency_code.lower()}_value']
                pending_balance = entry['balance']['pending_balance']

                if address in treeview_items:
                    # Update existing entry
                    accounts_tree.item(treeview_items[address], values=(address, f"{amount} {currency}", f"{pending_balance} {currency}", value))
                else:
                    # Insert new entry
                    accounts_tree.insert('', tk.END, values=(address, f"{amount} {currency}", f"{pending_balance} {currency}", value))
                if stop_signal.is_set():
                    return

            # Process regular addresses
            process_entries(list(balance_data["balance_data"]['addresses'])[-1])
    
            # Check if 'imported_addresses' exists and process them
            if 'imported_addresses' in balance_data["balance_data"] and balance_data["balance_data"]['imported_addresses']:
                process_entries(list(balance_data["balance_data"]['imported_addresses'])[-1])
            
            self.root.account_page.total_balance_text.config(text=f"Total Balance: {self.root.stored_data.total_balance} DNR")
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

            if self.root.stored_data.disable_tx_confirmation_dialog or self.root.callbacks.tx_confirmation(sender=sender, receiver=receiver, amount=amount):
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
                    hyperlink_url = f"http://explorer.denaro.is/transaction/{transaction_hash}"
                    hyperlink_text = f"Denaro Explorer link: {hyperlink_url}"
                    tx_str = (f'\nTransaction successfully pushed to node. \n'
                                f'Transaction hash: {transaction_hash}\n'
                                f'{hyperlink_text}\n')
                    print(tx_str)
                    msg_str += f'[{datetime.now()}]{tx_str}'
                msg_str += "\n----------------------------------------------------------------"
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
            if self.callbacks.post_confirmation_prompt(title="Wallet Created", msg="New wallet has been created. Would you like to open it?"):
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
            if self.callbacks.post_confirmation_prompt(title="Wallet Created", msg="New wallet has been created. Would you like to open it?"):
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
                self.callbacks.post_show_address_info(entry_data=result[1], entry_type='entries')
                
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

    
    
    def post_ask_string(self, title, msg, show=None):
        # Reset the event and result
        self.root.wallet_thread_manager.dialog_event.clear()
        self.root.stored_data.ask_string_result = None
        # Add the ask_string task to the queue
        self.root.wallet_thread_manager.request_queue.put(lambda: self.root.dialogs.ask_string(title, msg, show, is_callback=True))
        # Wait for the dialog to complete
        self.root.wallet_thread_manager.dialog_event.wait()
        # Return the result
        result = self.root.stored_data.ask_string_result
        self.root.stored_data.ask_string_result = None
        return result
    
    def post_password_dialog(self, title, msg, show=None):
        # Reset the event and result
        self.root.wallet_thread_manager.dialog_event.clear()
        self.root.stored_data.ask_string_result = None
        # Add the ask_string task to the queue
        self.root.wallet_thread_manager.request_queue.put(lambda: self.root.dialogs.password_dialog(title, msg, show, is_callback=True))
        # Wait for the dialog to complete
        self.root.wallet_thread_manager.dialog_event.wait()
        # Return the result
        result = self.root.stored_data.ask_string_result
        self.root.stored_data.ask_string_result = None
        return result
    

    def post_confirmation_prompt(self, title, msg):
        # Reset the event and result
        self.root.wallet_thread_manager.dialog_event.clear()
        self.root.stored_data.ask_bool_result = None
        # Add the ask_string task to the queue
        self.root.wallet_thread_manager.request_queue.put(lambda: self.root.dialogs.confirmation_prompt(title, msg, is_callback=True))
        # Wait for the dialog to complete
        self.root.wallet_thread_manager.dialog_event.wait()
        # Return the result
        result = self.root.stored_data.ask_bool_result
        self.root.stored_data.ask_bool_result = None
        return result
    
    def tx_confirmation(self, sender=None, receiver=None, amount=None):
        # Reset the event and result
        self.root.wallet_thread_manager.dialog_event.clear()
        self.root.stored_data.ask_string_result = None
        # Add the ask_string task to the queue
        self.root.wallet_thread_manager.request_queue.put(lambda: self.root.dialogs.tx_confirmation_dialog(sender, receiver, amount, is_callback=True))
        # Wait for the dialog to complete
        self.root.wallet_thread_manager.dialog_event.wait()
        # Return the result
        result = self.root.stored_data.ask_string_result
        self.root.stored_data.ask_string_result = None
        return result
    

    def post_messagebox(self, title, msg):
        # Reset the event and result
        self.root.wallet_thread_manager.dialog_event.clear()
        self.root.stored_data.ask_bool_result = None
        # Add the ask_string task to the queue
        self.root.wallet_thread_manager.request_queue.put(lambda: self.root.dialogs.messagebox(title, msg, is_callback=True))
        # Wait for the dialog to complete
        self.root.wallet_thread_manager.dialog_event.wait()
        # Return the result
        result = self.root.stored_data.ask_bool_result
        self.root.stored_data.ask_bool_result = None
        return result
    

    def post_show_address_info(self, entry_data=None, entry_type=None):
        # Reset the event
        self.root.wallet_thread_manager.dialog_event.clear()
        # Add the ask_string task to the queue
        self.root.wallet_thread_manager.request_queue.put(lambda: self.root.dialogs.address_info(entry_data=entry_data, entry_type=entry_type))
        # Wait for the dialog to complete
        #self.root.wallet_thread_manager.dialog_event.wait()
    
    
    def post_password_dialog_with_confirmation(self, title=None, msg=None):
        # Reset the event and result
        self.root.wallet_thread_manager.dialog_event.clear()
        self.root.stored_data.ask_string_result = None
        # Add the password_dialog_with_confirmation task to the queue
        self.root.wallet_thread_manager.request_queue.put(lambda: self.root.dialogs.password_dialog_with_confirmation(title=title, msg=msg, is_callback=True))
        # Wait for the dialog to complete
        self.root.wallet_thread_manager.dialog_event.wait()
        # Return the result
        result = self.root.stored_data.ask_string_result
        self.root.stored_data.ask_string_result = None
        return result
    

    def post_input_listener_dialog(self):
        # Reset the event and result
        self.root.wallet_thread_manager.dialog_event.clear()
        self.root.stored_data.ask_bool_result = None
        # Add the input_listener task to the queue
        self.root.wallet_thread_manager.request_queue.put(lambda: self.root.dialogs.input_listener_dialog(is_callback=True))
        # Wait for the dialog to complete
        #self.root.wallet_thread_manager.dialog_event.wait()
        ## Return the result
        #result = self.root.stored_data.ask_bool_result
        #self.root.stored_data.ask_bool_result = None
        #return result
    
    
    def post_backup_mnemonic_dialog(self, mnemonic=None):
        # Reset the event and result
        self.root.wallet_thread_manager.dialog_event.clear()
        self.root.stored_data.ask_bool_result = None
        # Add the ask_string task to the queue
        self.root.wallet_thread_manager.request_queue.put(lambda: self.root.dialogs.backup_mnemonic_dialog(is_callback=True, mnemonic=mnemonic))
        # Wait for the dialog to complete
        self.root.wallet_thread_manager.dialog_event.wait()
        # Return the result
        result = self.root.stored_data.ask_bool_result
        self.root.stored_data.ask_bool_result = None
        return result
    

    def post_2FA_QR_dialog(self, qr_window_data):
        self.root.wallet_thread_manager.request_queue.put(
            lambda: self.root.dialogs.show_2FA_QR_dialog(
                qr_window_data=qr_window_data,
                from_gui=True
            )
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

        self.root.stored_data = StoredData()
        
        if preserve_wallet_data:
            self.root.stored_data.wallet_file = wallet_file
            self.root.stored_data.wallet_authenticated = wallet_authenticated
        
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
    
    
if __name__ == "__main__":
    app = DenaroWalletGUI()
    app.mainloop()