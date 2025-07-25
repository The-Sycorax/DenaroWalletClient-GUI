import os
import json
import base64
import binascii
import logging
import argparse
import sys
import threading
import gc
import re
import time
import shutil
import requests
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from collections import Counter, OrderedDict
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Get the absolute path of the directory containing the current script.
dir_path = os.path.dirname(os.path.realpath(__file__))

# Insert folder paths for modules
sys.path.insert(0, dir_path + "/denaro")
sys.path.insert(0, dir_path + "/denaro/wallet")
sys.path.insert(0, dir_path + "/denaro/wallet/utils")

from denaro.wallet.utils.wallet_generation_util import generate, generate_from_private_key, generate_mnemonic, string_to_point, sha256, is_valid_mnemonic
from denaro.wallet.utils.cryptographic_util import EncryptDecryptUtils, TOTP
from denaro.wallet.utils.verification_util import Verification
from denaro.wallet.utils.data_manipulation_util import DataManipulation
from denaro.wallet.utils.interface_util import UserPrompts
from denaro.wallet.utils.qr_code_util import QRCodeUtils, _2FA_QR_Dialog
from denaro.wallet.utils.transaction_utils.transaction_input import TransactionInput
from denaro.wallet.utils.transaction_utils.transaction_output import TransactionOutput
from denaro.wallet.utils.transaction_utils.transaction import Transaction
from denaro.wallet.utils.paper_wallet_util import PaperWalletGenerator

is_windows = os.name == 'nt'

if is_windows:
    import msvcrt
else:
    import termios, fcntl, readline

# Get the root logger
root_logger = logging.getLogger()

# Set the level for the root logger
root_logger.setLevel(logging.INFO if '-verbose' in sys.argv else logging.WARNING)

# Create a handler with the desired format
handler = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s: %(message)s')
handler.setFormatter(formatter)

# Clear any existing handlers from the root logger and add our handler
root_logger.handlers = []
root_logger.addHandler(handler)

wallet_client_version = "Denaro Wallet Client v0.0.7-beta"
transaction_message_extension = f"Sent From {wallet_client_version}"


# Filesystem Functions
def is_wallet_encrypted(data_segment):
    """
    Determines if a given segment of data appears to be encrypted.
    """
    # Try to decode the data as JSON.
    try:
        parsed_data = json.loads(data_segment)
        
        encrypted_indicators = ["hmac", "hmac_salt", "verification_salt", "verifier", "totp_secret"]
        
        # If any of the encrypted indicators are found, it seems encrypted.
        if any(key in parsed_data for key in encrypted_indicators):
            return True
        
        return False  # Data doesn't have encryption indicators, so it doesn't seem encrypted
    except json.JSONDecodeError:
        pass

    # If the above check fails, try to decode the data as base64 and then as UTF-8.
    try:
        decoded_base64 = base64.b64decode(data_segment)
        decoded_base64.decode('utf-8')  # Check if the decoded result can be further decoded as UTF-8
        return True  # Data seems encrypted as it's valid Base64 and can be decoded as UTF-8
    except (binascii.Error, UnicodeDecodeError):
        return False  # Data neither seems to be valid JSON nor valid Base64 encoded UTF-8 text
    
def ensure_wallet_directories_exist(custom = None):
    """
    Ensures the "./wallets" and  "./wallets/wallet_backups" directories exist
    Will create a custom directory if specified. 
    """
    os.makedirs("./wallets", exist_ok=True)
    os.makedirs(os.path.join("./wallets", 'wallet_backups'), exist_ok=True)

    if custom:
        os.makedirs(custom, exist_ok=True)

def get_normalized_filepath(filename):
    """
    Gets a normalized file path, ensuring the directory exists.
    
    Parameters:
        filename (str): The name of the file where the data will be saved.
        default_directory (str): The default directory where files will be saved if no directory is specified.
        
    Returns:
        str: A normalized filepath.
    """
    default_directory="./wallets"

    # Ensure the filename has a .json extension
    _, file_extension = os.path.splitext(filename)
    # Add .json extention to the filename if it's not present
    if file_extension.lower() != ".json":
        filename += ".json"

    # Check if the directory part is already specified in the filename
    # If not, prepend the default directory to the filename
    if not os.path.dirname(filename):
        filename = os.path.join(default_directory, filename)
    
    # Normalize the path to handle ".." or "." segments
    normalized_filepath = os.path.normpath(filename)
    
    # Ensure the directory to save the file in exists
    file_directory = os.path.dirname(normalized_filepath)
    if not os.path.exists(file_directory):
        os.makedirs(file_directory)
    
    return normalized_filepath

def _load_data(filename, new_wallet):
    """
    Loads wallet data from a specified file.
    Checks if wallet file exists.
    """    
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        return data, True
    except (FileNotFoundError, json.JSONDecodeError) as e:
        if new_wallet:
            return {}, False
        else:
            logging.error(f"Unable to read the wallet file or parse its content:\n{str(e)}")
            return None, False
 
# Wallet Helper Functions
def generate_encrypted_wallet_data(wallet_data, current_data, password, totp_secret, hmac_salt, verification_salt, stored_verifier, is_import=False):
    """Overview:
        The `generate_encrypted_wallet_data` function serves as a utility for constructing a fully encrypted representation 
        of the wallet's data. It works by individually encrypting fields like private keys or mnemonics and then organizing
        them in a predefined format. This function is vital in ensuring that sensitive wallet components remain confidential.
        
        Parameters:
        - wallet_data (dict): Contains essential wallet information like private keys or mnemonics.
        - current_data (dict): Existing wallet data, utilized to determine the next suitable ID for the entry.
        - password (str): The user's password, used for the encryption process.
        - totp_secret (str): The TOTP secret token used for Two-Factor Authentication.
        - hmac_salt (bytes): Salt for HMAC computation.
        - verification_salt (bytes): Salt for password verification.
        - stored_verifier (bytes): The stored hash of the password, used for verification.
        
        Returns:
        - dict: A structured dictionary containing the encrypted wallet data.
    """
    # Encrypt the wallet's private key
    encrypted_wallet_data = {
        "id": EncryptDecryptUtils.encrypt_data(str(len(current_data["wallet_data"]["entry_data"]["entries"] if not is_import else current_data["wallet_data"]["entry_data"]["imported_entries"]) + 1), password, totp_secret, hmac_salt, verification_salt, stored_verifier),
        "private_key": EncryptDecryptUtils.encrypt_data(wallet_data['private_key'], password, totp_secret, hmac_salt, verification_salt, stored_verifier)
    }
    
    # If the wallet is non-deterministic, encrypt the mnemonic
    if current_data["wallet_data"]["wallet_type"] == "non-deterministic" and not is_import:        
        encrypted_wallet_data["mnemonic"] = EncryptDecryptUtils.encrypt_data(wallet_data['mnemonic'], password, totp_secret, hmac_salt, verification_salt, stored_verifier)
        del encrypted_wallet_data["private_key"]
        # Ensure a specific order for the keys
        desired_key_order = ["id", "mnemonic"]
        ordered_entry = OrderedDict((k, encrypted_wallet_data[k]) for k in desired_key_order if k in encrypted_wallet_data)
        encrypted_wallet_data = ordered_entry
    result = encrypted_wallet_data
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

def generate_unencrypted_wallet_data(wallet_data, current_data, is_import=False):
    """Overview:
        Contrasting its encrypted counterpart, the `generate_unencrypted_wallet_data` function focuses on constructing 
        plaintext wallet data entries. While it doesn't encrypt data, it organizes the it in a structured manner, ensuring 
        easy storage and retrieval. This function is pivotal in scenarios where encryption isn't mandated, but structured 
        data organization is requisite.
        
        Parameters:
        - wallet_data (dict): The unencrypted wallet data.
        - current_data (dict): Existing wallet data, utilized to determine the next suitable ID for the entry.
        
        Returns:
        - dict: A structured dictionary containing the plaintext wallet data.
    """
    # Structure the data without encryption
    unencrypted_wallet_data = {
        "id": str(len(current_data["wallet_data"]["entry_data"]["entries"] if not is_import else current_data["wallet_data"]["entry_data"]["imported_entries"]) + 1),
        "private_key": wallet_data['private_key'],
        "public_key": wallet_data['public_key'],
        "address": wallet_data['address']
    }
    # For non-deterministic wallets, include the mnemonic
    if current_data["wallet_data"]["wallet_type"] == "non-deterministic" and not is_import:
        unencrypted_wallet_data["mnemonic"] = wallet_data['mnemonic']
        # Ensure a specific order for the keys
        desired_key_order = ["id", "mnemonic", "private_key", "public_key", "address"]
        ordered_entry = OrderedDict((k, unencrypted_wallet_data[k]) for k in desired_key_order if k in unencrypted_wallet_data)
        unencrypted_wallet_data = ordered_entry
    result = unencrypted_wallet_data
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

def handle_new_encrypted_wallet(password, totp_code, use2FA, filename, deterministic, from_gui=False, callback_object=None):
    """Overview:
        The `handle_new_encrypted_wallet` function facilitates the creation of a new encrypted wallet. It handles the 
        combination of user-provided credentials, cryptographic salts, and the option for Two-Factor Authentication (2FA) 
        to produce a secure and accessible wallet. The function can adapt to both deterministic and non-deterministic 
        wallet types based on user preference.
        
        Parameters:
        - password (str): The user's password intended for the encrypted wallet.
        - totp_code (str): Time-based One-Time Password for Two-Factor Authentication.
        - use2FA (bool): Indicates whether Two-Factor Authentication is enabled or not.
        - filename (str): The intended filename for storing the wallet data.
        - deterministic (bool): Specifies if the wallet is deterministic
        
        Returns:
        - tuple: Returns a tuple that encapsulates the wallet's structured data alongside essential cryptographic 
          components like salts and verifiers.
    """
    # Define the initial structure for the wallet data
    data = {
        "wallet_data": {
            "wallet_type": "deterministic" if deterministic else "non-deterministic",
            "version": "0.2.3",
            "entry_data": {
                "key_data": [],
                "entries": []
            },
            "hmac": "",
            "hmac_salt": "",
            "verification_salt": "",
            "verifier": "",
            "totp_secret": ""
        }
    }
    
    # Check if deterministic and adjust the data structure accordingly
    if not deterministic:
        del data["wallet_data"]["entry_data"]["key_data"]

    # Password is mandatory for encrypted wallets
    if not password:
        logging.error("Password is required for encrypted wallets.\n")
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None, None, None, None, None

    # Generate random salts for HMAC and password verification
    hmac_salt = os.urandom(16)
    data["wallet_data"]["hmac_salt"] = base64.b64encode(hmac_salt).decode()

    verification_salt = os.urandom(16)
    data["wallet_data"]["verification_salt"] = base64.b64encode(verification_salt).decode()

    # Hash the password with the salt for verification
    verifier = Verification.hash_password(password, verification_salt)
    data["wallet_data"]["verifier"] = base64.b64encode(verifier).decode('utf-8')

    # If no TOTP code is provided, set it to an empty string
    if not totp_code:
        totp_code = ""

    # Handle Two-Factor Authentication (2FA) setup if enabled
    if use2FA:
        #global close_qr_window
        # Generate a secret for TOTP
        totp_secret = TOTP.generate_totp_secret(False,verification_salt)

        totp_qr_data = f'otpauth://totp/{filename}?secret={totp_secret}&issuer=Denaro Wallet Client'
        # Generate a QR code for the TOTP secret
        qr_img = QRCodeUtils.generate_qr_with_logo(totp_qr_data, "./denaro/gui_assets/denaro_logo.png")
        
        qr_window_controller = _2FA_QR_Dialog(
            qr_img,
            filename,
            totp_secret,
            from_gui=from_gui,
            callback_object=callback_object
        )

        # If called from the GUI, now pass the controller object to the GUI thread.
        # The GUI will then take over management of this object.
        if from_gui and callback_object:
            callback_object.post_2FA_QR_dialog(qr_window_controller)

        # Threading is used to show the QR window to the user while allowing input in the temrinal
        #thread = threading.Thread(target=QRCodeUtils.show_qr_with_timer, args=(qr_img, filename, totp_secret,))
        #thread.start()

        # Encrypt the TOTP secret for storage
        encrypted_totp_secret = EncryptDecryptUtils.encrypt_data(totp_secret, password, "", hmac_salt, verification_salt, verifier)
        data["wallet_data"]["totp_secret"] = encrypted_totp_secret
        
        # Validate the TOTP setup
        if not UserPrompts.handle_2fa_validation(totp_secret, totp_code, from_gui=from_gui, callback_object=callback_object):
            
            #QRCodeUtils.close_qr_window(True)
            qr_window_controller.close_window = True
            
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None, None, None, None, None
        else:
            #QRCodeUtils.close_qr_window(True)
            #thread.join()
            qr_window_controller.close_window = True
    else:
        # If 2FA is not used, generate a predictable TOTP secret based on the verification salt.
        totp_secret = TOTP.generate_totp_secret(True,verification_salt)
        encrypted_totp_secret = EncryptDecryptUtils.encrypt_data(totp_secret, password, "", hmac_salt, verification_salt, verifier)
        data["wallet_data"]["totp_secret"] = encrypted_totp_secret
        totp_secret = ""

    result = data, totp_secret, hmac_salt, verification_salt, verifier
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

def handle_existing_encrypted_wallet(filename, data, password, totp_code, deterministic, from_gui=False, callback_object=None):
    """Overview:
        The `handle_existing_encrypted_wallet` function verifies access to an encrypted wallet by checking the provided password
        and decoding HMAC and verification salts from the wallet data. It conducts verification of the user's password against the
        stored verifier and the HMAC to ensure data integrity. If password verification fails, it updates the number of failed password
        attempts assocated with the wallet, it then logs an error for authentication failure or data corruption. For wallets with Two-Factor
        Authentication, it additionally manages TOTP verification. Upon successful verifications, it returns cryptographic components such as
        HMAC salt, verification salt, stored verifier, and TOTP secret.
    
        Parameters:
        - filename: The name of the wallet file
        - data: The wallet data
        - password: The user's password
        - totp_code: The TOTP code for 2FA
        - deterministic: Boolean indicating if the wallet is deterministic
        
        Returns:
        - A tuple containing HMAC salt, verification salt, stored verifier, and TOTP secret
    """
    # Fail if no password is provided for an encrypted wallet
    if not password:
        if from_gui:
            while not password:
                password = callback_object.post_password_dialog("Authentication Required", "The wallet file is encrypted and authentication is required to proceed.\nPlease enter the password for the wallet.", show='*')
                if password is None:
                    # If the user cancels the prompt, securely delete variables and return None
                    DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                    return None, None, None, None, None
        else:
            logging.error("Password is required for encrypted wallets.")
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None, None, None, None, None

    # Decode salts for verification
    verification_salt = base64.b64decode(data["wallet_data"]["verification_salt"])
    hmac_salt = base64.b64decode(data["wallet_data"]["hmac_salt"])

    # Verify the password and HMAC
    password_verified, hmac_verified, stored_verifier = Verification.verify_password_and_hmac(data, password, hmac_salt, verification_salt, deterministic)

    # Based on password verification, update or reset the number of failed attempts
    data, attempts_msg, warning_msg, warning_type, data_erased_msg = DataManipulation.update_or_reset_attempts(data, filename, hmac_salt, password_verified, deterministic, from_gui=from_gui, callback_object=callback_object)

    def handle_auth_error_messages():
        auth_error_msg = "Authentication failed or wallet data is corrupted."
        new_line = '\n\n'
        
        if attempts_msg and data:
            print(attempts_msg)        
        
        if warning_msg:
            if warning_type == '1':
                logging.warning(warning_msg)

            if warning_type == '2':
                logging.critical(warning_msg)
                
        logging.error(auth_error_msg)

        if from_gui:
            msg_ext = ''
            print()
            gui_error_msg = f"{attempts_msg+new_line if attempts_msg else ''}{'WARNING: ' if warning_type == '1' else ''}{'CRITICAL: ' if warning_type == '2' else ''}{warning_msg+new_line if warning_msg else ''}{data_erased_msg+new_line if data_erased_msg else ''}{auth_error_msg}"
                        
            if os.path.normpath(str(filename)) == os.path.normpath(str(callback_object.root.stored_data.wallet_file)):
                if callback_object.root.stored_data.wallet_loaded:
                    msg_ext = new_line+'To prevent unauthorized access, the wallet session has been closed.'
                callback_object.root.stored_data.wallet_deleted = True 

            callback_object.post_messagebox("Error", f"{gui_error_msg}{msg_ext}")

                     

    if data is None:
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        handle_auth_error_messages()
        return None, None, None, None, None
    else:
        DataManipulation._save_data(filename,data)

    # Verify the password and HMAC
    password_verified, hmac_verified, stored_verifier = Verification.verify_password_and_hmac(data, password, hmac_salt, verification_salt, deterministic)

    # Fail if either the password or HMAC verification failed
    if not (password_verified and hmac_verified):
        handle_auth_error_messages()
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None, None, None, None, None
    
    # If 2FA is enabled, handle the TOTP validation
    totp_secret, tfa_enabled = Verification.verify_totp_secret(password, data["wallet_data"]["totp_secret"], hmac_salt, verification_salt, stored_verifier)
    
    if tfa_enabled:
        tfa_valid = UserPrompts.handle_2fa_validation(totp_secret, totp_code, from_gui=from_gui, callback_object=callback_object)
        if not tfa_valid or not tfa_valid.get("valid"):
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None, None, None, None, None
    
    result = hmac_salt, verification_salt, stored_verifier, totp_secret, None if not from_gui else password
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

def parse_and_encrypt_mnemonic(words, password, totp_secret, hmac_salt, verification_salt, stored_verifier):
    """Overview:
        The `parse_and_encrypt_mnemonic` function is specifically designed to fortify the security of mnemonic phrases.
        It takes a string of mnemonic words, parses them, and encrypts each word individually. The function ensures 
        that each mnemonic word is securely encrypted, thereby enhancing the security of the mnemonic while protecting
        against potential threats. This heightened level of security is crucial given the critical nature of mnemonics
        in digital wallets.
        
        Parameters:
        - words (str): The mnemonic phrase.
        - password (str): The user's password, used for the encryption process.
        - totp_secret (str): The TOTP secret token used for Two-Factor Authentication.
        - hmac_salt (bytes): Salt for HMAC generation.
        - verification_salt (bytes): Salt for password verification.
        - stored_verifier (bytes): The stored hash of the password, used for verification.
                
        Returns:
        - list: A list encapsulating the encrypted representations of each mnemonic word.
    """
    # Split the mnemonic words by space
    word_list = words.split()
    
    # Ensure there are exactly 12 words in the mnemonic (standard mnemonic length)
    if len(word_list) != 12:
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        raise ValueError("Input should contain exactly 12 words")
    
    # Encrypt each word, and structure it in a dictionary with its ID
    encrypted_key_data = [
        EncryptDecryptUtils.encrypt_data(
            json.dumps({
                "id": EncryptDecryptUtils.encrypt_data(str(i+1), password, totp_secret, hmac_salt, verification_salt, stored_verifier), 
                "word": EncryptDecryptUtils.encrypt_data(word, password, totp_secret, hmac_salt, verification_salt, stored_verifier)
            }), 
            password, totp_secret, hmac_salt, verification_salt, stored_verifier
        ) for i, word in enumerate(word_list)
    ]
    result = encrypted_key_data
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

def decrypt_and_parse_mnemonic(encrypted_json, password, totp_secret, hmac_salt, verification_salt, stored_verifier, from_gui=False, callback_object=None, stop_signal=None):
    """Overview:
        Serving as the counterpart to `parse_and_encrypt_mnemonic`, this function plays an instrumental role in 
        key recovery operations. This function undertakes the task of decrypting each encrypted mnemonic word and
        assembling them back into their original, readable sequence. 
        
        Parameters:
        - encrypted_json (list): A list containing encrypted mnemonic words.
        - password (str): The user's password, used for the decryption process.
        - totp_secret (str): The TOTP secret token used for Two-Factor Authentication.
        - hmac_salt (bytes): Salt for HMAC computation.
        - verification_salt (bytes): Salt for password verification.
        - stored_verifier (bytes): The stored hash of the password, used for verification.
        
        Returns:
        - str: A string containing the decrypted sequence of mnemonic words.
    """
    decrypted_words = []

    for encrypted_index in encrypted_json:
        if from_gui:
            if stop_signal.is_set():
                break
            else:
                callback_object.root.stored_data.progress_bar_increment = True

        decrypted_data = EncryptDecryptUtils.decrypt_data(encrypted_index, password, totp_secret, hmac_salt, verification_salt, stored_verifier)
        word = json.loads(decrypted_data)["word"]
        decrypted_word = EncryptDecryptUtils.decrypt_data(word, password, totp_secret, hmac_salt, verification_salt, stored_verifier)
        decrypted_words.append(decrypted_word)
    
    if from_gui and stop_signal.is_set():
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None

    result =  " ".join(decrypted_words)
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

# Wallet Orchestrator Functions
def generateAddressHelper(filename=None, password=None, totp_code=None, new_wallet=False, encrypt=False, use2FA=False, deterministic=False, backup=None, disable_warning=False, overwrite_password=None, amount=1, private_key=None, is_import=False, mnemonic=None, from_gui=False, callback_object=None, stop_signal=None):
    """Overview:
        The `generateAddressHelper` function serves as a central orchestrator for facilitating the creation, 
        integration, and management of wallet data. This function is designed to accomodate different scenarios 
        for the generation and oversight of wallet addresses depending on the provided parameters. This function 
        can generate addresses for a new wallet or add addresses to an existing wallet. When considering address 
        generation, it can operate in a deterministic fashion, deriving addresses from a mnemonic phrase, or in a
        non-deterministic manner, generating addresses at random.
    
        When working with existing wallets, the function verifies if the wallet data is encrypted, if a password 
        is provided, and determines the method of address generation used for the wallet (deterministic or non-detministic).
        Depending on the characteristics of an existing wallet, the function adjusts subsequent operations accordingly.
        
        Security is paramount to the function's design. One of its features is the implementation of a unique
        double encryption technique. Initially, the individual JSON key-value pairs within the genrated wallet data 
        are encrypted with the use of helper functions and returned back to the `generateAddressHelper` function. 
        Afterwhich, the function encrypts the entire JSON entry that houses these encrypted pairs, effectively wrapping 
        the data in a second layer of encryption. 
        
        For users prioritizing additional layers of security, there's support for Two-Factor Authentication (2FA). 
        When 2FA is enabled, the function integrates the generated TOTP (Time-based One-Time Password) secret directly
        into the encryption and decryption processes, intertwining the 2FA token with the cryptographic operations, thereby
        adding an intricate layer of security. 
        
        To conclude its operations, the function ensures that any transient sensitive data, especially those retained in 
        memory, are securely eradicated, mitigating risks of unintended data exposure or leaks.
           
        Parameters:
        - filename: File path designated for the storage or retrieval of wallet data.
        - password (str): The user's password, used for the various cryptographic processes.
        - totp_code: An optional Time-based One-Time Password, used for Two-Factor Authentication.
        - new_wallet (bool, optional): Specifies if the operation involves creating a new wallet.
        - encrypt (bool, optional): Specifies if the wallet data should undergo encryption.
        - use2FA (bool, optional): Specifies if Two-Factor Authentication should be enabled.
        - deterministic (bool, optional): Specifies if deterministic address generation should
          be enabled for the wallet.
        
        Returns:
        - str: A string that represents a newly generated address.
    """
    # Initialize mnemonic to None
    #mnemonic = None

    #Make sure that the wallet directories exists
    ensure_wallet_directories_exist()
    
    #if from_gui:
    #    if new_wallet:
    #        filename = callback_object.save_file_dialog(os.path.basename(filename)+'.json')
    #        
    #        if isinstance(filename, tuple):
    #            return None
    #        
    #        if filename == '' or filename is None:
    #            return None
            
            
        #callback_object.configure_progress_bar(max_value=combined_length+include_mnemonic)        

    #Normalize filename
    filename = get_normalized_filepath(filename)

    # Load the existing or new wallet data from a file (filename)
    data, wallet_exists = _load_data(filename, new_wallet)    
    
    # If wallet dose not exist return None
    # This handles the case if using generateaddress for a wallet that dose not exist
    if not new_wallet and not wallet_exists:
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None
    
    if new_wallet:
        stored_encrypt_param = encrypt
        stored_deterministic_param = deterministic
    
    imported_entries = 0

    # Determine encryption status and wallet type for an existing wallet
    if wallet_exists or not new_wallet:
        # Convert part of the wallet data to a JSON string
        data_segment = json.dumps(data["wallet_data"])   

        # Check if the wallet data is encrypted and if a password is provided
        if is_wallet_encrypted(data_segment) and not password and not new_wallet and not from_gui:
            logging.error("Wallet is encrypted. A password is required to add additional addresses.")
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None
        
        if is_wallet_encrypted(data_segment):
            # If encrypted and password is provided, set encrypt flag to True
            encrypt = True

        if not is_wallet_encrypted(data_segment):
            encrypt = False

        # Check if the existing wallet type is deterministic
        if "wallet_type" in data["wallet_data"] and not new_wallet:
            deterministic = data["wallet_data"]["wallet_type"] == "deterministic"
        
        if "imported_entries" in data["wallet_data"]["entry_data"]:
            imported_entries = len(data["wallet_data"]["entry_data"]["imported_entries"])

        if len(data["wallet_data"]["entry_data"]["entries"]) + imported_entries > 255 and not new_wallet:
            if from_gui:
                callback_object.post_messagebox("Error", "Cannot proceed. Maximum wallet entries reached.")
            else:
                print("Cannot proceed. Maximum wallet entries reached.")
            return None
    
    #Handle backup and overwrite for an existing wallet
    if new_wallet and wallet_exists:
        if "wallet_type" in data["wallet_data"]:
            deterministic = data["wallet_data"]["wallet_type"] == "deterministic"
        if not UserPrompts.backup_and_overwrite_helper(data, filename, overwrite_password, encrypt, backup, disable_warning, deterministic, from_gui, callback_object):
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return
        else:
            if '-verbose' in sys.argv:
                print()
        
    if new_wallet:
        wallet_version = "0.2.3"
        if from_gui:
            callback_object.root.stored_data.operation_mode = 'create_wallet'
            
        logging.info("new_wallet is set to True.")
        encrypt = stored_encrypt_param    
        deterministic = stored_deterministic_param
    else:
        wallet_version = data['wallet_data']['version']
        logging.info("new_wallet is set to False.")

    # Handle different scenarios based on whether the wallet is encrypted
    if encrypt:
        logging.info("encrypt is set to True.")     
        if new_wallet:
            logging.info("Handling new encrypted wallet.")
            # Handle creation of a new encrypted wallet
            data, totp_secret, hmac_salt, verification_salt, stored_verifier = handle_new_encrypted_wallet(password, totp_code, use2FA, filename, deterministic, from_gui=from_gui, callback_object=callback_object)
            if not data:
                #logging.error(f"Error: Data from handle_new_encrypted_wallet is None!\nDebug: HMAC Salt: {hmac_salt}, Verification Salt: {verification_salt}, Stored Verifier: {stored_verifier}")
                DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                return None
        else:
            logging.info("Handling existing encrypted wallet.")
            # Handle operations on an existing encrypted wallet
            if from_gui:
                hmac_salt, verification_salt, stored_verifier, totp_secret, password = handle_existing_encrypted_wallet(filename, data, password, totp_code, deterministic, from_gui=from_gui, callback_object=callback_object)
            else:
                hmac_salt, verification_salt, stored_verifier, totp_secret, _ = handle_existing_encrypted_wallet(filename, data, password, totp_code, deterministic)

            if not hmac_salt or not verification_salt or not stored_verifier:
                #logging.error(f"Error: Data from handle_existing_encrypted_wallet is None!\nDebug: HMAC Salt: {hmac_salt}, Verification Salt: {verification_salt}, Stored Verifier: {stored_verifier}")
                DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                return None
    else:
        logging.info("encrypt is set to False.")
    
    logging.info(f"is_import is set to {is_import}")
    
    # Check if the user is importing a wallet entry
    if not is_import:
        # If deterministic flag is set, generate addresses in a deterministic way
        if deterministic:
            logging.info("deterministic is set to True.")
            if not password and not new_wallet and not wallet_version == "0.2.3":
                if from_gui:
                    while not password:
                        password = callback_object.post_password_dialog("Password Required", "The wallet type is deterministic and a password is required to derive addresses.\nPlease enter the password for the wallet:", show='*')
                        if password is None:
                            # If the user cancels the prompt, securely delete variables and return None
                            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                            return None
                else:                        
                    logging.error("The wallet type is deterministic and a password is required to derive addresses.")
                    DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                    return None
            if new_wallet:
                logging.info("Generating deterministic wallet data.")         
                # Generate the initial data for a new deterministic wallet
                if mnemonic:
                    wallet_data = generate(mnemonic_phrase=mnemonic, passphrase=password, deterministic=True, wallet_version=wallet_version)
                else:
                    wallet_data = generate(passphrase=password, deterministic=True, wallet_version=wallet_version)
                if encrypt:
                    logging.info("Data successfully generated for new encrypted deterministic wallet.")                   
                    logging.info("Parseing and encrypting master mnemonic.")
                    # Parse and encrypt the mnemonic words individually
                    data["wallet_data"]["entry_data"]["key_data"] = parse_and_encrypt_mnemonic(wallet_data["mnemonic"], password, totp_secret, hmac_salt, verification_salt, stored_verifier)
                else:
                    logging.info("Data successfully generated for new unencrypted deterministic wallet.")
                    # Structure for a new unencrypted deterministic wallet
                    data = {
                        "wallet_data": {
                            "wallet_type": "deterministic",
                            "version": "0.2.3",
                            "entry_data": {
                                "master_mnemonic": wallet_data["mnemonic"],
                                "entries":[]
                            }
                        }
                    }
            else:
                
                if from_gui:
                    callback_object.root.stored_data.operation_mode = 'generate_address'
            
                # Set the deterministic index value based on the length of the entries in the wallet 
                index = len(data["wallet_data"]["entry_data"]["entries"])
                if encrypt:
                    logging.info("Decrypting and parsing the master mnemonic.")
                    # Decrypt and parse the existing mnemonic for the deterministic wallet
                    mnemonic = decrypt_and_parse_mnemonic(data["wallet_data"]["entry_data"]["key_data"], password, totp_secret, hmac_salt, verification_salt, stored_verifier, from_gui=from_gui, callback_object=callback_object, stop_signal=stop_signal)
                    logging.info("Master mnemonic successfully decrypted.")
                    wallet_data = []
                    entries_generated = -1
                    logging.info("Generating deterministic wallet data.")
                    for _ in range(amount):
                        if index + entries_generated < 256:
                            entries_generated += 1
                            generated_data = generate(mnemonic_phrase=mnemonic, passphrase=password, index=index+entries_generated, deterministic=True, wallet_version=wallet_version)
                            wallet_data.append(generated_data)
                        if index + len(wallet_data) >= 256:
                            if from_gui:
                                callback_object.post_messagebox("Error", "Maximum wallet entries reached.")
                            else:
                                print("Maximum wallet entries reached.\n")
                            break
                    logging.info(f"{entries_generated + 1} address(es) successfully generated for existing encrypted determinsitic wallet.")
                else:
                    # Use the existing mnemonic directly if it's not encrypted
                    mnemonic = data["wallet_data"]["entry_data"]["master_mnemonic"]
                    logging.info("Validating password used for address derivation.")
                    # Verify if the provided passphrase correctly derives child keys.
                    # Derive the first child key using the master mnemonic and the given passphrase.
                    first_child_data = generate(mnemonic_phrase=mnemonic, passphrase=password, index=0, deterministic=True, wallet_version=wallet_version)
                    # Check if the derived child's private key matches the private key of the first entry in the stored wallet.
                    if first_child_data["private_key"] != data["wallet_data"]["entry_data"]["entries"][0]["private_key"]:
                        if not wallet_version == "0.2.3":
                            if from_gui:
                                callback_object.post_messagebox("Error", "Invalid password. Please try again.")
                            else:
                            # Log an error message if the private keys do not match, indicating that the provided passphrase is incorrect.
                                logging.error("Invalid password. To generate the address, please re-enter the correct password and try again.")
                            
                            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                            return None
                    else:
                        logging.info("Password validated.")
                        wallet_data = []
                        entries_generated = -1
                        logging.info("Generating deterministic wallet data.")
                        for _ in range(amount):
                            if index + entries_generated < 256:
                                entries_generated += 1
                                generated_data = generate(mnemonic_phrase=mnemonic, passphrase=password, index=index + entries_generated, deterministic=True, wallet_version=wallet_version)
                                wallet_data.append(generated_data)
                            if index + len(wallet_data) >= 256:
                                if from_gui:
                                    callback_object.post_messagebox("Error", "Maximum wallet entries reached.")
                                else:
                                    print("Maximum wallet entries reached.\n")
                                
                                break
                        logging.info(f"{entries_generated + 1} address(es) successfully generated for existing unencrypted determinsitic wallet.")
        else:
            logging.info("deterministic is set to False")
            # For non-deterministic wallets, generate a random wallet data        
            if not new_wallet:
                
                if from_gui:
                    callback_object.root.stored_data.operation_mode = 'generate_address'

                wallet_data = []
                entries_generated = -1
                logging.info("Generating non-deterministic wallet data.")
                for _ in range(amount):
                    if len(data["wallet_data"]["entry_data"]["entries"]) < 256:
                        generated_data = generate()
                        wallet_data.append(generated_data)
                        entries_generated += 1
                    if len(data["wallet_data"]["entry_data"]["entries"]) + len(wallet_data) >= 256:
                        
                        if from_gui:
                            callback_object.post_messagebox("Error", "Maximum wallet entries reached.")
                        else:
                            print("Maximum wallet entries reached.\n")
                        break
                if encrypt:
                    logging.info(f"{entries_generated + 1} address(es) successfully generated for existing encrypted non-determinsitic wallet.")
                else:
                    logging.info(f"{entries_generated + 1} address(es) successfully generated for existing unencrypted non-determinsitic wallet.")
            else:
                logging.info("Generating non-deterministic wallet data.")
                wallet_data = generate()
            if new_wallet and not encrypt:
                data = {
                    "wallet_data": {
                        "wallet_type": "non-deterministic",
                        "version": "0.2.3",
                        "entry_data": {
                            "entries":[]
                        }
                        
                    }
                }
                logging.info("Data successfully generated for new unencrypted non-deterministic wallet.")
            if new_wallet and encrypt:
                logging.info("Data successfully generated for new encrypted non-deterministic wallet.")
    else:
        if not new_wallet:
            
            if from_gui:
                callback_object.root.stored_data.operation_mode = 'import_address'

            # Initialize wallet_data dictionary
            wallet_data = []
            
            # Get number of wallet entries
            index = len(data["wallet_data"]["entry_data"]["entries"])
            
            # Return None if amount of wallet entries are 256 or more
            if len(data["wallet_data"]["entry_data"]["entries"]) >= 256:
                if from_gui:
                    callback_object.post_messagebox("Error", "Maximum wallet entries reached.")
                else:
                    logging.error("Maximum wallet entries reached.\n")
                DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                return None
            
            # Validate private key using regex pattern
            private_key_pattern = r'^(0x)?[0-9a-fA-F]{64}$'
            if not re.match(private_key_pattern, private_key):
                if from_gui:
                    callback_object.post_messagebox("Error", "The provided private key is not valid.")
                else:
                    logging.error("The provided private key is not valid.")
                DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                return None
            
            # Remove 0x prefix from private key if it exists 
            if private_key.startswith('0x'):
                private_key = private_key[2:]
              
            logging.info("Generating import data based on the provided private key.")

            # Generate wallet data from private key
            generated_data = generate_from_private_key(private_key_hex=private_key)

            if generated_data:
                logging.info("Data successfully generated from private key.")
            
            # Ensure imported_entries exists
            if not "imported_entries" in data["wallet_data"]["entry_data"]:
                data["wallet_data"]["entry_data"]["imported_entries"] = []

            # Append generated data to wallet_data
            wallet_data.append(generated_data)

    # Prepare data to be saved based on encryption status
    if encrypt:
        # Prepare encrypted data to be saved
        logging.info("Encrypting generated data.")        
        if new_wallet:
            encrypted_wallet_data = generate_encrypted_wallet_data(wallet_data, data, password, totp_secret, hmac_salt, verification_salt, stored_verifier)
            encrypted_data_entry = EncryptDecryptUtils.encrypt_data(json.dumps(encrypted_wallet_data), password, totp_secret, hmac_salt, verification_salt, stored_verifier)
            data["wallet_data"]["entry_data"]["entries"].append(encrypted_data_entry)
        else:
            for item in wallet_data:
                encrypted_wallet_data = generate_encrypted_wallet_data(item, data, password, totp_secret, hmac_salt, verification_salt, stored_verifier, is_import=is_import)
                encrypted_data_entry = EncryptDecryptUtils.encrypt_data(json.dumps(encrypted_wallet_data), password, totp_secret, hmac_salt, verification_salt, stored_verifier)
                if not is_import:
                    data["wallet_data"]["entry_data"]["entries"].append(encrypted_data_entry)
                else:
                    data["wallet_data"]["entry_data"]["imported_entries"].append(encrypted_data_entry)
        
        # Set HMAC message based on the encrypted wallet data
        if deterministic:
            hmac_msg = json.dumps(data["wallet_data"]["entry_data"]["entries"]).encode() + json.dumps(data["wallet_data"]["entry_data"]["key_data"]).encode()
        else:
            hmac_msg = json.dumps(data["wallet_data"]["entry_data"]["entries"]).encode()
        
        if "imported_entries" in data["wallet_data"]["entry_data"]:
            hmac_msg = json.dumps(data["wallet_data"]["entry_data"]["imported_entries"]).encode() + hmac_msg

        # Calculate HMAC for wallet's integrity verification
        computed_hmac = Verification.hmac_util(password=password,hmac_salt=hmac_salt,hmac_msg=hmac_msg,verify=False)
        data["wallet_data"]["hmac"] = base64.b64encode(computed_hmac).decode()
    else:
        # Prepare unencrypted data to be saved
        if new_wallet:
            unencrypted_data_entry = generate_unencrypted_wallet_data(wallet_data, data)
            data["wallet_data"]["entry_data"]["entries"].append(unencrypted_data_entry)       
        else:
            for item in wallet_data:
                unencrypted_data_entry = generate_unencrypted_wallet_data(item, data, is_import=is_import)
                if not is_import:
                    data["wallet_data"]["entry_data"]["entries"].append(unencrypted_data_entry)
                else:
                    data["wallet_data"]["entry_data"]["imported_entries"].append(unencrypted_data_entry)
    
    
    
    # Save the updated wallet data back to the file
    logging.info("Saving data to wallet file.")
    DataManipulation._save_data(filename, data)
    
    # Extract the newly generated address to be returned
    if "-verbose" in sys.argv:
        print("\n")
        print("\033[2A")
    
    if not from_gui:
        # Sgie warning and other info to user
        warning = 'WARNING: Never disclose your mnemonic phrase or private key! Anyone with access to these can steal the assets held in your account.'
        if not is_import:
            if amount == 1 and new_wallet:
                result = f"Successfully generated new wallet at: {filename}.\n\n{warning}\n{'Master Mnemonic' if deterministic else 'Mnemonic'}: {wallet_data['mnemonic']}\nPrivate Key: 0x{wallet_data['private_key']}\nAddress #{len(data['wallet_data']['entry_data']['entries'])}: {wallet_data['address']}"
            if amount == 1 and not new_wallet:
                n ='\n'
                result = f"Successfully generated and stored wallet entry.\n\n{warning}{n+'Mnemonic: ' + wallet_data[0]['mnemonic'] if not deterministic else ''}\nPrivate Key: 0x{wallet_data[0]['private_key']}\nAddress #{len(data['wallet_data']['entry_data']['entries'])}: {wallet_data[0]['address']}"
            elif amount > 1 and not new_wallet:
                result = f"Successfully generated and stored {entries_generated + 1} wallet entries."
        else:
            result = f"Successfully imported wallet entry.\n\n{warning}\nImported Private Key #{len(data['wallet_data']['entry_data']['imported_entries'])}: 0x{wallet_data[0]['private_key']}\nAddress: {wallet_data[0]['address']}"
    
    else:
        if new_wallet:
            if deterministic:
                result = True, filename, wallet_data['mnemonic']
            else:
                result = True, filename
        else:
            if not is_import:
                wallet_data[0]['id'] = len(data['wallet_data']['entry_data']['entries'])
                if deterministic:
                    del wallet_data[0]['mnemonic']    
            else:
                 wallet_data[0]['id'] = len(data['wallet_data']['entry_data']['imported_entries'])
            
            #callback_object.set_wallet_data(wallet_data[0], is_import=is_import, stop_signal=stop_signal)
            result = [True, wallet_data[0]]
        
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

 
def decryptWalletEntries(filename, password, totp_code=None, address=[], fields=[], to_json=False, from_gui = False, show=None, callback_object = None, stop_signal=None):
    """Overview:
        The `decryptWalletEntries` function decrypts wallet entries from an encrypted file. It supports both deterministic 
        and non-deterministic wallet types and executes multiple steps for processing wallet data.
        
        The function begins with initializing necessary directories and normalizing the input file path. The function then 
        proceeds to load wallet data from the specified file, checking both its existence and encryption status. If the data 
        is encrypted, it extracts essential cryptographic parameters such as HMAC salt, verification salt, stored verifier,
        and TOTP secret using the `handle_existing_encrypted_wallet` function. These parameters are crucial for the subsequent
        decryption process. The function then distinguishes between deterministic and non-deterministic wallets, applying specific
        decryption and data generation approaches respectively, based on the wallet type.
        
        The core decryption process involves iterating through each entry in the wallet data. The decryption relies on the 
        function `decrypt_data`, which performs the multi-layered decryption process, which includes the ChaCha20-Poly1305 
        and AES-GCM decryption layers.
    
        For deterministic wallets, the master mnemonic phrase is decrypted using the `decrypt_and_parse_mnemonic`function. 
        Following decryption, the master mnemonic is utilized, along with a user-defined password, and an entry id which, as 
        input parameters for the `generate` function. The `generate` function is used to deterministically produce additional
        wallet entry data, consisting of the private key, public key, and address. The entry id is used for the address derivation
        path when generating the requisite data, and is crucial in the process.
    
        Conversely, for non-deterministic wallets, each wallet entry has its own unique mnemonic phrase that must undergo the same 
        decryption process. Once decrypted, the mnemonic is passed to the generate function to derive the corresponding wallet 
        entry data: private key, public key, and address. 
        
        The procedures described for both deterministic and non-deterministic wallets facilitate the independent and secure
        generation of supplementary wallet data. This methodology was adopted as an alternative to directly storing the complete data
        set (private key, public key, and address) for every wallet entry. Instead, encrypted wallet files are designed to contain only
        the minimal data required to derive these core components. During testing, this approach has been shown to significantly reduce
        the file size of encrypted wallet files
    
        A key feature of this function is its filtering mechanism. The function can filter output based on specific addresses or fields.
        If one or more addresses are specified, the function filters the entries to include or exclude only those associated with that
        address. If one or more fields are specified (id, mneominc, private_key, public_key, address), then the `generate` function will
        only return those specified fields. This filtering is essential for targeted data retrieval and reducing processing load, especially
        for large wallets.   
        
        In addition to address-based and field-based filtering, this function can also filter entries based on their origin: distinguishing
        between generated and imported wallet entries. This capability is crucial for users who need to segregate entries based on how they
        were added to the wallet. When the show parameter is set to 'generated', the function processes only the entries that were internally
        generated within the wallet. Conversely, if the parameter is set to 'imported', the function focuses solely on wallet entries that were
        externally imported, such as those added through direct import of private keys. 
    
    
        Specific use cases, such as when only the 'mnemonic' field is requested for deterministic wallets or handling command-line 
        arguments for sending or generating paper wallets, are also included in the function's logic.

    Parameters:
        - filename (str): Path to the encrypted wallet file.
        - password (str): User's password for decryption.
        - totp_code (str, optional): TOTP for Two-Factor Authentication, required if TFA was enabled during encryption.
        - address (str, optional): Filter results by a specific address.
        - fields (list of str, optional): Fields to decrypt and return.
        - to_json (bool, optional): If True, outputs a JSON string; otherwise, returns a dictionary.
        - show (str, optional): Option to show 'imported', 'generated', or all entries.
    
    Returns:
        - dict or str: Decrypted wallet entries as a dictionary or a JSON string, formatted according to the 'pretty' 
        flag and filtered as per the specified criteria.
    """
    # Ensure the wallet directories exist
    ensure_wallet_directories_exist()

    # Normalize filename to a standard path format
    filename = get_normalized_filepath(filename)

    # Load existing wallet data from the file, handle non-existent wallet
    data, wallet_exists = _load_data(filename, False)
    if not wallet_exists:
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None

    # Check if wallet data is encrypted and initialize flags
    data_segment = json.dumps(data["wallet_data"])
    is_encrypted = is_wallet_encrypted(data_segment)
    deterministic = "wallet_type" in data["wallet_data"] and data["wallet_data"]["wallet_type"] == "deterministic"

    # Count total entries including imported ones
    index = len(data["wallet_data"]["entry_data"]["entries"])
    imported_entries_length = len(data["wallet_data"]["entry_data"].get("imported_entries", []))
    combined_length = index + imported_entries_length
    
    wallet_version = data['wallet_data']['version']
    
    # Extract cryptographic components for encrypted wallets
    if is_encrypted:
        if from_gui:
            hmac_salt, verification_salt, stored_verifier, totp_secret, password = handle_existing_encrypted_wallet(filename, data, password, totp_code, deterministic, from_gui=from_gui, callback_object=callback_object)
            
        else:
            hmac_salt, verification_salt, stored_verifier, totp_secret, _ = handle_existing_encrypted_wallet(filename, data, password, totp_code, deterministic)
            
        if not all([hmac_salt, verification_salt, stored_verifier]):
            if from_gui:
                callback_object.root.stored_data.wallet_authenticated = False
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None
        else:
            if from_gui:
                callback_object.root.stored_data.wallet_authenticated = True
                callback_object.root.title(f"{wallet_client_version} GUI ({filename})")
                if callback_object.get_operation_mode() == "send":
                    DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                    return True
                else:
                    callback_object.clear_wallet_data()

        # Handle warnings based on wallet size and command-line arguments
        if 'send' in sys.argv:
            print("\nA private key is required to send funds. \nSince a private key has not been provided, the wallet client will attempt to decrypt each entry in the wallet file until it finds the private key associated with the address specified. \nYou can use the '-private-key' argument to make this process alot faster. However, doing this is not secure and can put your funds at risk.\n")
        
        if index + imported_entries_length >= 32:
            logging.warning(f"The encrypted wallet file contains {index} entries and is quite large. Decryption {'and balance requests ' if 'balance' in sys.argv else ''}may take a while.\n")
    
    elif from_gui:
        callback_object.root.stored_data.wallet_authenticated = True
        callback_object.root.title(f"{wallet_client_version} GUI ({filename})")
        if callback_object.get_operation_mode() == "send":
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return True
        else:
            callback_object.clear_wallet_data()
               
    elif index + imported_entries_length >= 32 and 'balance' in sys.argv:
        logging.warning(f"The wallet file contains {index} entries and is quite large. Balance requests may take a while.\n")
    
    if from_gui:
        include_mnemonic = 0
        callback_object.root.stored_data.entry_count = combined_length
        if is_encrypted and deterministic:
            include_mnemonic = 12
        callback_object.configure_progress_bar(max_value=combined_length+include_mnemonic)

    # Special case: If only 'mnemonic' is requested and the wallet is deterministic
    if fields == ["mnemonic"] and deterministic:
        master_mnemonic = decrypt_and_parse_mnemonic(data["wallet_data"]["entry_data"]["key_data"], password, totp_secret, hmac_salt, verification_salt, stored_verifier, from_gui=from_gui, callback_object=callback_object, stop_signal=stop_signal) if is_encrypted else data["wallet_data"]["entry_data"]["master_mnemonic"]
        if master_mnemonic:
            master_mnemonic_json = json.dumps({"entry_data": {"master_mnemonic": master_mnemonic}}, indent=4)
            print(f"Wallet Data for: {filename}")
            result = master_mnemonic_json if to_json else f"Master Mnemonic: {master_mnemonic}"
            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
            return result
        else:
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None

    mnemonic = ""
    if deterministic:
        mnemonic = decrypt_and_parse_mnemonic(data["wallet_data"]["entry_data"]["key_data"], password, totp_secret, hmac_salt, verification_salt, stored_verifier, from_gui=from_gui, callback_object=callback_object, stop_signal=stop_signal) if is_encrypted else data["wallet_data"]["entry_data"]["master_mnemonic"]
        if not mnemonic:
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None
        if from_gui:
            callback_object.root.stored_data.master_mnemonic = mnemonic
            callback_object.root.stored_data.wallet_data["entry_data"]["master_mnemonic"] = mnemonic
        
    generated_entries = []
    imported_entries = []
    fields = fields or ["mnemonic", "id", "private_key", "public_key", "address", "is_import"]
    ordered_fields = ["id", "mnemonic", "private_key", "public_key", "address"]
    
    entry_count = 0
    max_entry_count = combined_length
    

    # Define a function to handle entry decryption and data generation
    def handle_entry_decryption(entry, is_import):
        # Decrypt entry data
        entry_with_encrypted_values = json.loads(EncryptDecryptUtils.decrypt_data(entry, password, totp_secret, hmac_salt, verification_salt, stored_verifier)) if is_encrypted else entry

        # Decrypt the 'id' field for all entries if the wallet is encrypted
        if 'id' in entry_with_encrypted_values and is_encrypted:
            decrypted_id = EncryptDecryptUtils.decrypt_data(entry_with_encrypted_values['id'], password, totp_secret, hmac_salt, verification_salt, stored_verifier)
            entry_with_encrypted_values['id'] = int(decrypted_id)

        # Decrypt the 'mnemonic' field if the wallet is encrypted
        if 'mnemonic' in entry_with_encrypted_values and is_encrypted:
            decrypted_mnemonic = EncryptDecryptUtils.decrypt_data(entry_with_encrypted_values['mnemonic'], password, totp_secret, hmac_salt, verification_salt, stored_verifier)
            entry_with_encrypted_values['mnemonic'] = decrypted_mnemonic

        if 'private_key' in entry_with_encrypted_values and is_encrypted:
            decrypted_private_key = EncryptDecryptUtils.decrypt_data(entry_with_encrypted_values['private_key'], password, totp_secret, hmac_salt, verification_salt, stored_verifier)
            entry_with_encrypted_values['private_key'] = decrypted_private_key

        # Generate data fields based on the deterministic flag
        generated_data = {}

        if not is_import:
            if deterministic:
                # Generate data for deterministic wallet with index
                generated_data = generate(mnemonic_phrase=mnemonic, passphrase=password, index=entry_with_encrypted_values['id'] - 1, deterministic=deterministic, fields=fields, wallet_version=wallet_version)
                if "mnemonic" in generated_data:
                    del generated_data["mnemonic"]
                
                generated_data["id"] = entry_with_encrypted_values['id']                

            else:
                # Generate data for non-deterministic wallet without index
                generated_data = generate(mnemonic_phrase=entry_with_encrypted_values['mnemonic'], deterministic=deterministic, fields=fields, wallet_version=wallet_version)
        else:
            # Generate data from private key for imported entries
            generated_data = generate_from_private_key(private_key_hex=entry_with_encrypted_values["private_key"], fields=fields)
            generated_data["is_import"] = True

        generated_data["id"] = entry_with_encrypted_values['id']
        return generated_data

    # Check if address filtering is applied
    address_filtering_applied = bool(address) and 'address' not in fields
    if address_filtering_applied:
        fields.append('address')
        
    if show == "imported":
        combined_length -= index
    if show == "generated":
        combined_length -= imported_entries_length   
    


    address_found = False
    # Main loop for processing entry_data object array
    for entry_type, entries in data["wallet_data"]["entry_data"].items():
        # Exclude key_data and master_mnemonic from loop
        if entry_type not in ["key_data", "master_mnemonic"]:
            # Seconary nested loop for processing entries
            for entry in entries:
                is_import = entry_type == "imported_entries"
                # Skip decryption and processing if the entry type doesn't match the 'show' parameter
                if (show == "imported" and not is_import) or (show == "generated" and is_import):
                    continue
                # Decrypt the entry only if the wallet is encrypted
                if is_encrypted:
                    if entry_count < max_entry_count:
                        entry_count += 1
                    decrypted_entry = handle_entry_decryption(entry, is_import)
                    # Handle decrypted entries when using the 'send' or 'generate paperwallet' sub-commands
                    if 'send' in sys.argv or 'paperwallet' in sys.argv:
                        if not from_gui:
                            print(f"\rDecrypting wallet entry {entry_count} of {combined_length} | Address: {decrypted_entry['address']}", end='')
                        if address[0] in decrypted_entry['address']:
                            print("\nAddress Found.\n")                                      
                            if is_import:
                                imported_entries.clear()
                                imported_entries.append(decrypted_entry)
                            else:
                                generated_entries.clear()
                                generated_entries.append(decrypted_entry)
                            address_found = True
                            break
                        else:
                            if is_import:
                                imported_entries.clear()
                            else:
                                generated_entries.clear()
                    else:
                        if not from_gui:
                            print(f"\rDecrypting wallet entry {entry_count} of {combined_length}", end='')
                            if entry_count >= combined_length:
                                print("\r\n",end='')
                    if from_gui:
                        if stop_signal.is_set():
                            #print("Loop 2 inner break 1")
                            break
                        else:
                            #print("Loop 2 still running")
                            callback_object.root.stored_data.progress_bar_increment = True
                            time.sleep(0.01)
                            if not callback_object.set_wallet_data(decrypted_entry, is_import=is_import, stop_signal=stop_signal):
                                #print("Loop 2 inner break 1-2")
                                break
                else:
                    # For non-encrypted wallets, use the entry as-is
                    decrypted_entry = entry
                    if is_import:
                        decrypted_entry["is_import"] = True
                    if from_gui:
                        if stop_signal.is_set():
                            #print("Loop 2 inner break 2-1")
                            break
                        else:
                            #print("Loop 2 still running")
                            callback_object.root.stored_data.progress_bar_increment = True
                            time.sleep(0.01)
                            if not callback_object.set_wallet_data(decrypted_entry, is_import=is_import, stop_signal=stop_signal):
                                #print("Loop 2 inner break 2-2")
                                break

                # Order and filter by specific fields
                filtered_entry = OrderedDict((field, decrypted_entry[field]) for field in ordered_fields if field in decrypted_entry and field in fields)
                
                # Append to the appropriate list
                if is_import:
                    imported_entries.append(filtered_entry)
                else:
                    generated_entries.append(filtered_entry)
                
                if from_gui:
                    if stop_signal.is_set():
                        #print("Loop 2 outer break")
                        break
                    #else:
                    #    print("Loop 2 still running")

        if from_gui:
            if stop_signal.is_set():
                #print("Loop 1 outer break")
                break
            #else:
            #    print("Loop 1 still running")
            
        if address_found:
            break
    
    if from_gui:
        if stop_signal.is_set():
            result = False
        else:
            result = True
        callback_object.root.stored_data.wallet_authenticated = False
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        #print("End of decryptWalletEntries")
        return result
        
    # Remove 'address' from fields if it was added for filtering
    if address_filtering_applied:
        fields.remove('address')
    
    # Function to filter entries by address
    def filter_entries(entries, address_filter, unmatched_addresses):
        include_addresses = set(addr for addr in address_filter if not addr.startswith("-"))
        exclude_addresses = set(addr[1:] for addr in address_filter if addr.startswith("-"))
        
        filtered = []    
        for entry in entries:
            entry_addr = entry.get("address")
            if entry_addr:
                if entry_addr in exclude_addresses:
                    unmatched_addresses.discard(entry_addr)
                    continue
                elif include_addresses and entry_addr in include_addresses:
                    filtered.append(entry)
                    unmatched_addresses.discard(entry_addr)
                elif not include_addresses:
                    filtered.append(entry)    
        return filtered  
    
    unmatched_addresses = set()
    # Apply address filtering to generated and imported entries separately
    if address:
        # Initialize a set to keep track of unmatched addresses
        unmatched_addresses = set(addr[1:] if addr.startswith("-") else addr for addr in address)
        
        generated_entries = filter_entries(generated_entries, address, unmatched_addresses)
        imported_entries = filter_entries(imported_entries, address, unmatched_addresses)
        
        # Generate warnings after all entries have been processed
        if len(unmatched_addresses) >= 1:
            #if is_encrypted:
                #print()
            logging.warning(f"The following {'address was' if len(unmatched_addresses) == 1 else 'addresses were'} not found: {', '.join(unmatched_addresses)}")
        
        # Check if all entries have been excluded after filtering
        if not generated_entries and not imported_entries:
            #if is_encrypted and not len(unmatched_addresses) >= 1:
                #print()
            logging.warning("All wallet entries have been excluded by the filter. The output will contain no entries.")
    
    # Remove 'address' from entries if it wasn't in the original fields list
    if address_filtering_applied:
        for entry_list in [generated_entries, imported_entries]:
            for entry in entry_list:
                entry.pop('address', None)

    # Function to check if all entries in a list are empty
    def are_all_entries_empty(entries):
        return all(not entry for entry in entries)

    # Construct the final output
    output = {"entry_data": {}}

    # Include master_mnemonic if 'mnemonic' is in fields and the wallet is deterministic
    if "mnemonic" in fields and deterministic and len(generated_entries) > 0:
        output["entry_data"]["master_mnemonic"] = mnemonic

    # Add entries to the output if they are not empty or do not contain only empty objects
    if show != "imported" and generated_entries and not are_all_entries_empty(generated_entries):
        output["entry_data"]["entries"] = generated_entries
    if show != "generated" and imported_entries and not are_all_entries_empty(imported_entries):
        output["entry_data"]["imported_entries"] = imported_entries
    
    if not "balance" in sys.argv and not "send" in sys.argv and not "paperwallet" in sys.argv:
        if len(output["entry_data"]) > 0:
            if not is_encrypted and not len(unmatched_addresses) >= 1:
                print("\033[F",end='')
            print(f"\nWallet Data for: {filename}")
        else:
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None
    
    # Convert to JSON format if requested
    if to_json:
        json_output = json.dumps(output, indent=4)
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not json_output])
        return json_output
    
    else:
        if len(generated_entries) > 0:
            print("-"*32+"Internally Generated Entries"+"-"*32)   
            if "mnemonic" in fields and deterministic:
                print(f"Master Mnemonic: {mnemonic}\n")
            for entry in generated_entries:
                for key, value in entry.items():
                    if key == 'id':
                        formatted_key = 'Wallet Entry'
                        print(f"{formatted_key} #{value}:")
                    else:
                        formatted_key = ' '.join(word.capitalize() for word in key.split('_'))
                        print(f"{formatted_key}: {value}")
                print()         
        if len(imported_entries) > 0:
            print("-"*38+"Imported Entries"+"-"*38)
            for entry in imported_entries:
                for key, value in entry.items():
                    if key == 'id':
                        formatted_key = 'Imported Entry'
                        print(f"{formatted_key} #{value}:")
                    else:
                        formatted_key = ' '.join(word.capitalize() for word in key.split('_'))
                        print(f"{formatted_key}: {value}")
                print()  

    DataManipulation.secure_delete([var for var in locals().values() if var is not None])
    return None

    
def generatePaperWallet(filename, password, totp_code, address, private_key, file_type):
    try:
        address_data, private_key_data = get_address_and_private_key(filename, password, totp_code, address, private_key)
        
        if not private_key_data or not address_data:
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None
    
        private_key_qr = PaperWalletGenerator.generate_qr_code(private_key_data)
        public_address_qr = PaperWalletGenerator.generate_qr_code(address_data)
        final_image = PaperWalletGenerator.overlay_qr_code(private_key_qr, public_address_qr, private_key_data, address_data, file_type)
    
        if private_key and not filename:
            filename = address_data
    
        file_directory = os.path.join(os.path.dirname(filename), "wallets/paper_wallets")
        ensure_wallet_directories_exist(custom=file_directory)
        
        if not os.path.exists("./wallets/paper_wallets/paper_wallet_back.png") and file_type.lower() == 'png':
            shutil.copy("./denaro/wallet/paper_wallet_back.png", "wallets/paper_wallets")
        
        if not private_key:
            wallet_name = os.path.splitext(os.path.basename(filename))[0]
            file_directory = os.path.join(file_directory, wallet_name)
            ensure_wallet_directories_exist(custom=file_directory)
    
        if file_type.lower() == 'png':
            file_path = os.path.join(file_directory, f"{address_data}_paper_wallet_front.png")
            final_image.save(file_path)
            
        elif file_type.lower() == 'pdf':
            file_path = os.path.join(file_directory, f"{address_data}_paper_wallet.pdf")
            c = canvas.Canvas(file_path, pagesize=letter)
            width, height = letter  # Letter size in points
    
            # Function to process image with transparency
            def process_image(image):
                if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[3])  # Use alpha channel as mask
                    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not background])
                    return background
                else:
                    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not image])
                    return image
    
            # Save and scale the front image
            temp_front_path = file_path.replace('.pdf', '.temp_front.png')
            front_image = process_image(final_image)
            front_image.save(temp_front_path)
            front_img = Image.open(temp_front_path)
            scale = min(width / front_img.width, height / front_img.height)
            c.drawImage(temp_front_path, 0, height - front_img.height * scale, width=front_img.width * scale, height=front_img.height * scale)
            c.showPage()
    
            # Save and scale the second image
            temp_back_path = file_path.replace('.pdf', '.temp_back.png')
            second_image_path = "./denaro/wallet/paper_wallet_back.png"
    
            with Image.open(second_image_path) as back_img:
                back_image = process_image(back_img)
                back_image.save(temp_back_path)

            back_img = Image.open(temp_back_path)
            scale = min(width / back_img.width, height / back_img.height)
            c.drawImage(temp_back_path, 0, height - back_img.height * scale, width=back_img.width * scale, height=back_img.height * scale)
    
            # Clean up temporary files and save PDF
            os.remove(temp_front_path)
            os.remove(temp_back_path)
            c.save()
        
        if os.path.exists(file_path):
            print(f"\nPaper wallet successfully generated at: {file_path}")
        else:
            logging.error(f"Error in generating paper wallet: {e}")
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        
    except Exception as e:
        logging.error(f"Error in generating paper wallet: {e}")
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])

#Configuration Functions
def read_config(config_path='settings.cfg', disable_err_msg = False):
    """
    Reads the configuration from a JSON file.

    Parameters:
    - config_path (str): The path to the configuration file. Defaults to 'update_config.json'.

    Returns:
    - dict: The configuration as a dictionary, or None if the file is not found or contains invalid JSON.
    """
    if not os.path.exists(config_path):
        config = {"default_node": "https://denaro-node.gaetano.eu.org", "node_validation": "True", "default_currency": "USD"}
        write_config(config=config)

    try:
        with open(config_path, 'r') as config_file:
            return json.load(config_file)  # Loads and returns the configuration as a dictionary
    except FileNotFoundError:
        if not disable_err_msg:
            logging.error(" Config file not found. Please initialize the configuration using 'set-config'.")
        return None  # Returns None if the configuration file is not found
    except json.JSONDecodeError:
        logging.error(" Config file contains invalid JSON data.")
        return None  # Returns None if the JSON is invalid
    
def write_config(config_path='settings.cfg', config=None):
    """
    Writes the given configuration to a JSON file.

    Parameters:
    - config (dict): The configuration to write.
    - config_path (str): The path to the configuration file. Defaults to 'update_config.json'.

    Returns:
    - bool: True if the configuration was written successfully, False otherwise.
    """
    try:
        with open(config_path, 'w') as config_file:
            json.dump(config, config_file, indent=4)  # Writes the configuration to the file with indentation
        return True  # Returns True if the operation was successful
    except Exception as e:
        logging.error(f"Failed to write config: {e}")
        return False  # Returns False if any exception occurred during file writing
    
#Transaction Functions
def validate_and_select_node(node):
    """
    Overview:
        This function is responsible for ensuring that the address of a Denaro node is valid and usable for 
        interactions with the blockchain network. It first checks if a node address is provided. If so, it
        validates the address by calling the `validate_node_address` method. If no address is provided,
        it defaults to a pre-defined, reliable node address. This function is essential for ensuring that
        subsequent blockchain operations such as transactionsor balance queries are directed to a valid node.

    Parameters:
        node (str): The node address to validate. If None, a default node address is used.

    Returns:
        str or None: The function returns the node address if the validation is successful or the default 
        node address if no address is provided. It returns None if the provided address is invalid.
    """
    if node:
        is_node_valid, node, _, _ = Verification.validate_node_address(node, referer="validate_and_select_node")
        if not is_node_valid:
            node = 'https://denaro-node.gaetano.eu.org'
    else:
        node = 'https://denaro-node.gaetano.eu.org'
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not node])
    return node

def initialize_wallet(filename):
    ensure_wallet_directories_exist()
    filename = get_normalized_filepath(filename)
    data, wallet_exists = _load_data(filename, False)

    # Determine if wallet is encrypted
    encrypted = False
    if wallet_exists:
        data_segment = json.dumps(data["wallet_data"])
        encrypted = is_wallet_encrypted(data_segment)
       
    result = wallet_exists, filename, encrypted
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

def get_address_and_private_key(filename, password, totp_code, address, private_key):
    encrypted = False
    address_pattern = r'^[DE][1-9A-HJ-NP-Za-km-z]{44}$'
    
    if filename and address and not private_key:
        #Validate wallet address using regex pattern        
        if not re.match(address_pattern, address):
             logging.error("The wallet address provided is not valid.")
             DataManipulation.secure_delete([var for var in locals().values() if var is not None])
             return None, None
    
        wallet_exists, filename, encrypted = initialize_wallet(filename)
        if not wallet_exists:
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None, None

        # If wallet is encrypted and password is not provided, log an error
        if encrypted and not password:
            logging.error("Wallet is encrypted. A password is required.")
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None, None

        decrypted_data = decryptWalletEntries(filename=filename, password=password, totp_code=totp_code if totp_code else "", address=[address], fields=['private_key'], to_json=True)

        if decrypted_data is not None:
            decrypted_data = json.loads(decrypted_data)
            entry_data = decrypted_data.get('entry_data', {})        
            
            # Check 'entries' and extract the private key if available
            entries = entry_data.get('entries')
            if entries and isinstance(entries, list) and len(entries) > 0:
                private_key = entries[0].get('private_key')        
            
            # If not found in 'entries', check 'imported_entries'
            if not private_key:
                imported_entries = entry_data.get('imported_entries')
                if imported_entries and isinstance(imported_entries, list) and len(imported_entries) > 0:
                    private_key = imported_entries[0].get('private_key')
        
        if private_key is None:
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None, None

    if not filename and private_key:
        # Validate private key using regex pattern
        private_key_pattern = r'^(0x)?[0-9a-fA-F]{64}$'
        if not re.match(private_key_pattern, private_key):
            logging.error("The private key provided is not valid.")
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None, None
        
        # Remove 0x prefix from private key if it exists 
        if private_key.startswith('0x'):
            private_key = private_key[2:]

        # Generate sending address from private key
        generated_address = generate_from_private_key(private_key_hex=private_key, fields=["address"])
        address = generated_address['address']
    
    result = address, private_key
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

def checkBalance(filename, password, totp_code=None, address = [], node = None, to_json = False, to_file = False, show=None, currency_code=None, currency_symbol=None, address_data=None, from_gui=False, callback_object=None, stop_signal=None):
     
    # Select a valid node
    if not from_gui:
        node = validate_and_select_node(node)
    if node is None:
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None

    encrypted = False
    if filename:
        
        wallet_exists, filename, encrypted = initialize_wallet(filename)
        if not wallet_exists:
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None

        # Error logging for encrypted wallet without a password
        if encrypted and not password and not from_gui:
            logging.error("Wallet is encrypted. A password is required.")
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None
        
        # Decrypt wallet entries
        if not from_gui:
            address_data = decryptWalletEntries(filename=filename, password=password, totp_code=totp_code if totp_code else "", address=address if address else [], fields=['address','id', "is_import"], to_json=True, show=show, from_gui=from_gui, callback_object=callback_object)

        if not address_data:
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None
        
        entry_data = json.loads(address_data)['entry_data']
        total_balance = 0
        total_pending = 0
        is_import = False
        
        # Count total entries including imported ones
        index = len(entry_data["entries"])
        imported_entries_length = len(entry_data.get("imported_entries", []))
        combined_length = index + imported_entries_length
        
        if show:
            if "imported" in show:
                if "imported_entries" in entry_data and "entries" in entry_data:
                    del entry_data["entries"]
            
            if "generated" in show:
                if "imported_entries" in entry_data:
                    del entry_data["imported_entries"]
                            
        # Get price data and convert to Decimal
        formatted_price = get_price_info(currency_code)
        if formatted_price:
            formatted_price = Decimal(str(formatted_price))
        else:
            formatted_price = Decimal('0')
            
            #currency_code = "USD"
            #currency_symbol = "$"
        
        if from_gui:
            if not stop_signal.is_set():
                #callback_object.set_price_data(formatted_price)
                callback_object.configure_progress_bar(max_value=combined_length)

        formatted_price_str = "{:.8f}".format(formatted_price)
        
        if entry_data is not None:                    
            if not to_json and not to_file:
                # Print balance information
                print(f"\nDNR/{currency_code} Price: {currency_symbol}{formatted_price_str} {'(Calculated from USD)' if not currency_code == 'USD' else ''}\nBalance Information For: {filename}")
                print("-"*59)
                for entry_feild in entry_data:
                    if entry_feild == "imported_entries":
                        is_import = True
                    for entry in entry_data[entry_feild]:
                        id = entry['id']
                        address = entry['address']
                        balance, pending_balance, is_error = get_balance_info(address, node)
                        # Convert balance to Decimal and perform multiplication
                        balance_decimal = Decimal(str(balance))
                        balance_value = balance_decimal * formatted_price
                        # Format the balance value as a regular decimal string
                        formatted_balance_value = "{:.7f}".format(balance_value)
                        if is_error:
                            break
                        total_balance += balance
                        total_pending += pending_balance
                        # Output the balance in DNR and its value in the chosen currency                  
                        print(f'{"Imported " if is_import else ""}Address #{id}: {address}\nBalance: {balance} DNR{f" (Pending: {pending_balance} DNR)" if pending_balance != 0 else ""}\n{currency_code} Value: {currency_symbol}{formatted_balance_value}\n')
                print("\033[F"+"-"*59)
                # Convert total_balance to Decimal
                total_balance_decimal = Decimal(str(total_balance))
                total_balance_value = total_balance_decimal * formatted_price
                # Format the total balance value as a regular decimal string
                formatted_total_balance_value = "{:.7f}".format(total_balance_value)
                print(f'Total Balance: {total_balance} DNR\nTotal {currency_code} Value: {currency_symbol}{formatted_total_balance_value}')
                DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            
            if to_json or to_file and not stop_signal.is_set():
                # Prepare JSON data
                balance_data = {"balance_data": {"wallet_file_path": filename, "wallet_version":"0.2.2", "addresses": [], "imported_addresses" : [], f"exchange_rate":f'{currency_symbol}{formatted_price}',"total_balance":"", f"total_{currency_code.lower()}_value":"", "lastUpdated": datetime.utcnow().isoformat() + "Z"}}

                if not "imported_entries" in entry_data or entry_data["imported_entries"] == []:
                    del balance_data["balance_data"]["imported_addresses"]

                if not "entries" in entry_data or entry_data["entries"] == []:
                    del balance_data["balance_data"]["addresses"]

                for entry_feild in entry_data:
                    #print("Loop 1 running", filename)
                    #if from_gui:
                    #    if stop_signal.is_set():
                    #        #print("Loop 1 break", filename)
                    #        break
                    if not entry_feild == "master_mnemonic":
                        if entry_feild == "imported_entries":
                            is_import = True                    
                        for entry in entry_data[entry_feild]:
                            #print("Loop 2 running", filename)
                            #if from_gui:
                            #    if stop_signal.is_set():
                            #        #print("Loop 2 break", filename)
                            #        break
                            address = entry['address']
                            balance, pending_balance, is_error = get_balance_info(address, node, from_gui=from_gui, callback_object=callback_object, stop_signal=stop_signal)
                            if is_error:
                                break
                            total_balance += balance
                            if not is_import:
                                address_entry = {
                                    "id": entry['id'],
                                    "address": address,
                                    "balance": {
                                        "currency": "DNR",
                                        "amount": f'{"{:.6f}".format(Decimal(str(balance)))}',
                                        f"{currency_code.lower()}_value": f'{currency_symbol}{"{:.7f}".format(Decimal(str(balance * formatted_price)))}'
                                    }
                                }
                                if from_gui:  # Add pending_balance only if from_gui is True
                                    address_entry["balance"]["pending_balance"] = f'{"{:.6f}".format(Decimal(str(pending_balance)))}'
                                balance_data["balance_data"]["addresses"].append(address_entry)
                            else:
                                imported_address_entry = {
                                    "id": entry['id'],
                                    "address": address,
                                    "balance": {
                                        "currency": "DNR",
                                        "amount": f'{"{:.6f}".format(Decimal(str(balance)))}',
                                        f"{currency_code.lower()}_value": f'{currency_symbol}{"{:.7f}".format(Decimal(str(balance * formatted_price)))}'
                                    }
                                }
                                if from_gui:  # Add pending_balance only if from_gui is True
                                    imported_address_entry["balance"]["pending_balance"] = f'{"{:.6f}".format(Decimal(str(pending_balance)))}'
                                balance_data["balance_data"]["imported_addresses"].append(imported_address_entry)                                                                
                            if from_gui: 
                                if not stop_signal.is_set():
                                    callback_object.root.stored_data.progress_bar_increment = True
                                    callback_object.set_balance_data(balance_data, Decimal(str(total_balance)), f'{currency_symbol}{"{:.7f}".format(Decimal(str(total_balance))*formatted_price)}', stop_signal=stop_signal)
                                else:
                                    #print("Loop 2 break", filename)
                                    break
                    
                    if from_gui and stop_signal.is_set():
                                #print("Loop 1 break", filename)
                                break
                                          
                #print("Outside loop")
                if from_gui:
                    if stop_signal.is_set():
                        #print("End of balance check 1")
                        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                        return None
                    else:
                        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                        return True

                balance_data['balance_data']['total_balance'] = str(total_balance)+" DNR"
                balance_data['balance_data'][f'total_{currency_code.lower()}_value'] = f'{currency_symbol}{"{:.7f}".format(Decimal(str(total_balance))*formatted_price)}'
                
                if to_json:
                    if not from_gui:
                        print(json.dumps(balance_data, indent=4,ensure_ascii=False))      
                
                if to_file:
                    # Define the file path and name
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    wallet_name = os.path.splitext(os.path.basename(filename))[0]
                    balance_info_dir = os.path.join(os.path.dirname(filename), "balance_information")
                    file_directory = os.path.join(balance_info_dir, wallet_name)
                    file_name = f"{wallet_name}_balance_{timestamp}.json"
                    file_path = os.path.join(file_directory, file_name)
        
                    # Ensure balance_information directory exists
                    if not os.path.exists(balance_info_dir):
                        os.makedirs(balance_info_dir)
        
                    # Create wallet-specific directory if it doesn't exist
                    if not os.path.exists(file_directory):
                        os.makedirs(file_directory)

                    # Save the balance data to file
                    with open(file_path, 'w') as file:
                        json.dump(balance_data, file, indent=4,ensure_ascii=False)        
                    print(f"\nBalance information saved to file: {file_path}")
            
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            #print("End of balance check")
            return None
        else:
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None
      
def prepareTransaction(filename, password, totp_code, amount, sender, private_key, receiver, message, node, from_gui=None):
    global transaction_message_extension
    max_message_length = 256 - len(transaction_message_extension) + 3
   
    if len(message) > max_message_length:
        logging.error(f"Message length exceeded, must be between 0-{max_message_length} characters.")
        result = None, f"\n[{datetime.now()}]\nError: Message length exceeded, must be between 0-{max_message_length} characters."
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result
    
    if not from_gui:
        node = validate_and_select_node(node)
   
    if node is None:
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None, None
    
    sender, private_key = get_address_and_private_key(filename, password, totp_code, sender, private_key)
    
    if not private_key:
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None, None
    
    # Convert private key to int
    private_key = int(private_key, 16)

    # Handle message variable
    if not message:
        message = transaction_message_extension
    else:
        message = message+" | "+transaction_message_extension
    try:
        message = bytes.fromhex(message)
    except ValueError:
        message = message.encode('utf-8')
    
    address_pattern = r'^[DE][1-9A-HJ-NP-Za-km-z]{44}$'
    #Validate receiving address using regex pattern        
    if not re.match(address_pattern, receiver):
        logging.error("The recieving address is not valid.")
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None, "Error: The recieving address is not valid."

    # Create the transaction
    result, msg_str = create_transaction([private_key], sender, receiver, amount, message, node=node)
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result, msg_str
    
def create_transaction(private_key, sender, receiving_address, amount, message: bytes = None, send_back_address=None, node=None):
    
    print(f"\n[{datetime.now()}]\nAttempting to send {amount} DNR from {sender} to {receiving_address}.")
    msg_str = ''
    msg_str += f'[{datetime.now()}]\nAttempting to send {amount} DNR from {sender} to {receiving_address}.\n\n'

    amount = Decimal(amount)
    inputs = []
    
    for key in private_key:
        if send_back_address is None:
            send_back_address = sender
        balance, address_inputs, is_pending, pending_transactions, pending_transaction_hashes, is_error, msg = get_address_info(sender, node)
        msg_str = msg_str + msg

        if is_error:
            result = None, msg_str
            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
            return result
        
        for address_input in address_inputs:
            address_input.private_key = key
        inputs.extend(address_inputs)
        if sum(input.amount for input in sorted(inputs, key=lambda item: item.amount, reverse=False)[:255]) >= amount:
            break
    
    if not inputs:
        if is_pending:
            print(f"\n[{datetime.now()}]\nERROR: No spendable outputs. Please wait for pending transactions to be confirmed.")
            msg_str += f'[{datetime.now()}]\nERROR: No spendable outputs. Please wait for pending transactions to be confirmed.\n'
            if pending_transactions is not None:
                print(f"\nTransactions awaiting confirmation:")
                msg_str += f'Transactions awaiting confirmation:\n'
                count = 0
                for tx in pending_transaction_hashes:
                    count += 1
                    print(f"{count}: {tx}")
                    msg_str += f"{count}: {tx}\n"
        else:
            print(f'\n[{datetime.now()}]\nERROR: No spendable outputs.')
            msg_str += f'[{datetime.now()}]\nERROR: No spendable outputs.\n'
            if not balance > 0:
                print(f"The associated address dose not have enough funds.\n")
                msg_str += f'The associated address dose not have enough funds.\n'
        result = None, msg_str
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result
    
    # Check if accumulated inputs are sufficient
    if sum(input.amount for input in inputs) < amount:
        print(f"\n[{datetime.now()}]\nERROR: The associated address dose not have enough funds.\n")
        msg_str += f'[{datetime.now()}]\nERROR: The associated address dose not have enough funds.\n'
        result = None, msg_str
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result

    # Select appropriate transaction inputs
    transaction_inputs = []
    for tx_input in sorted(inputs, key=lambda item: item.amount, reverse=False):
        transaction_inputs.append(tx_input)
        if sum(input.amount for input in transaction_inputs) >= amount:
            break

    # Ensure that the transaction amount is adequate
    transaction_amount = sum(input.amount for input in transaction_inputs)
    if transaction_amount < amount:
        print(f"\n[{datetime.now()}]\nERROR:\nConsolidate outputs: send {transaction_amount} Denari to yourself\n")
        msg_str += f'[{datetime.now()}]\nERROR:\nConsolidate outputs: send {transaction_amount} Denari to yourself\n'
        result = None, msg_str
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result
    
    # Create the transaction
    transaction = Transaction(transaction_inputs, [TransactionOutput(receiving_address, amount=amount)], message)
    if transaction_amount > amount:
        transaction.outputs.append(TransactionOutput(send_back_address, transaction_amount - amount))

    # Sign and send the transaction
    transaction.sign([private_key])
    
    # Push transaction to node
    try:
        request = requests.post(f'{node}/push_tx', json={'tx_hex': transaction.hex()}, timeout=10)
        request.raise_for_status()
        response = request.json()
                
        if not response.get('ok'):
            print(response.get('error'))
            msg_str += f'[{datetime.now()}]\n{response.get("error")}\n'
            result = None, msg_str
            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
            return result
        result = transaction, msg_str
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result
    
    except requests.RequestException as e:
        # Handles exceptions that occur during the request
        print(f"\n[{datetime.now()}]\nError during request to node:\n {e}")
        msg_str += f'[{datetime.now()}]\nError during request to node. See console output for more details.\n'
        result = None, msg_str
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result

    except ValueError as e:
        # Handles JSON decoding errors
        print(f"\n[{datetime.now()}]\nError decoding JSON response from node:\n {e}")
        msg_str += f'[{datetime.now()}]\nError decoding JSON response from node. See console output for more details.\n'
        result = None, msg_str
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result

    except KeyError as e:
        # Handles missing keys in response data
        print(f"\n[{datetime.now()}]\nMissing expected data in response from node:\n {e}")
        msg_str += f'[{datetime.now()}]\nMissing expected data in response from node. See console output for more details.\n'
        result = None, msg_str
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result

def get_address_info(address: str, node: str):
    try:
        # Send the request to the node
        request = requests.get(f'{node}/get_address_info', {'address': address, 'transactions_count_limit': 0, 'show_pending': True})
        request.raise_for_status()

        response = request.json()

        if not response.get('ok'):
            print(f"\n[{datetime.now()}]\n{response.get('error')}")
            msg_str = f"\n[{datetime.now()}]\n{response.get('error')}\n"
            result = None, None, None, None, None, True, msg_str
            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
            return result

        result = response['result']
        is_pending = False
        tx_inputs = []
        pending_spent_outputs = []
        pending_transaction_hashes = []

        for value in result['pending_spent_outputs']:
            pending_spent_outputs.append((value['tx_hash'], value['index']))

        for spendable_tx_input in result['spendable_outputs']:
            if (spendable_tx_input['tx_hash'], spendable_tx_input['index']) in pending_spent_outputs:
                is_pending = True
                continue
            
            tx_input = TransactionInput(spendable_tx_input['tx_hash'], spendable_tx_input['index'])
            tx_input.amount = Decimal(str(spendable_tx_input['amount']))
            tx_input.public_key = string_to_point(address)
            tx_inputs.append(tx_input)
        
        if is_pending:
            for value in result['pending_transactions']:
                pending_transaction_hashes.append((value['hash']))
        
        final_result = Decimal(result['balance']), tx_inputs, is_pending, pending_spent_outputs, pending_transaction_hashes, False, ""
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not final_result])
        return final_result

    except requests.RequestException as e:
        # Handles exceptions that occur during the request
        print(f"\n[{datetime.now()}]\nError during request to node:\n {e}")
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        msg_str = f'[{datetime.now()}]\nError during request to node. See console output for more details.\n'
        return None, None, None, None, None, True, msg_str

    except ValueError as e:
        # Handles JSON decoding errors
        print(f"\n[{datetime.now()}]\nError decoding JSON response from node:\n {e}")
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        msg_str = f'[{datetime.now()}]\nError decoding JSON response from node. See console output for more details.\n'
        return None, None, None, None, None, True, msg_str

    except KeyError as e:
        # Handles missing keys in response data
        print(f"\n[{datetime.now()}]\nMissing expected data in response from node:\n {e}")
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        msg_str = f'[{datetime.now()}]\nMissing expected data in response from node. See console output for more details.\n'
        return None, None, None, None, None, True, msg_str

def get_balance_info(address: str, node: str, from_gui= False, callback_object=None, stop_signal=None):
    """
    Fetches the account data from the node and calculates the pending balance.

    :param address: The address of the account.
    :param node: The node URL to fetch data from.
    :return: The total balance and pending balance of the account.
    :raises: ConnectionError, ValueError, KeyError
    """
    if from_gui and stop_signal.is_set():
        return None, None, True
    try:        
        #print("Start balance request")
        # Send the request to the node
        request = requests.get(f'{node}/get_address_info', params={'address': address, 'show_pending': True})
        request.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code

        response = request.json()
        result = response.get('result')

        if not response.get('ok'):
            print(f"\n[{datetime.now()}]\n{response.get('error')}")
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None, None, True
    
        # Handle potential missing 'result' key
        if result is None:
            print(f"\n[{datetime.now()}]\nERROR: Missing 'result' key in response")
            DataManipulation.secure_delete([var for var in locals().values() if var is not None])
            return None, None, True

        pending_transactions = result.get('pending_transactions', [])
        spendable_outputs = result.get('spendable_outputs', [])
        
        # Create a set of spendable transaction hashes for easy lookup
        spendable_hashes = {output['tx_hash'] for output in spendable_outputs}
        
        # Ensure the balance is a string before converting to Decimal
        total_balance = Decimal(str(result['balance']))
        pending_balance = Decimal('0')

        for transaction in pending_transactions:
            # Adjust the balance based on inputs
            for input in transaction.get('inputs', []):
                if input.get('address') == address and input.get('tx_hash') in spendable_hashes:
                    input_amount = Decimal(str(input.get('amount', '0')))
                    pending_balance -= input_amount

            # Adjust the balance based on outputs
            for output in transaction.get('outputs', []):
                if output.get('address') == address:
                    output_amount = Decimal(str(output.get('amount', '0')))
                    pending_balance += output_amount

        # Format the total balance and pending balance to remove unnecessary trailing zeros
        formatted_total_balance = total_balance.quantize(Decimal('0.000001'), rounding=ROUND_DOWN)
        formatted_pending_balance = pending_balance.quantize(Decimal('0.000001'), rounding=ROUND_DOWN)        

        balance_data = formatted_total_balance, formatted_pending_balance, False
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not balance_data])
        return balance_data
    
    except requests.RequestException as e:
        # Handles exceptions that occur during the request
        print(f"\n[{datetime.now()}]\nError during request to node:\n {e}")
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None, None, True

    except ValueError as e:
        # Handles JSON decoding errors
        print(f"\n[{datetime.now()}]\nError decoding JSON response from node:\n {e}")
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None, None, True

    except KeyError as e:
        # Handles missing keys in response data
        print(f"\n[{datetime.now()}]\nMissing expected data in response from node:\n {e}")
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return None, None, True
    #finally:
    #    print("End of balance request")

def get_price_info(currency_code=None):
    """
    Fetches and calculates the price of DNR in the specified currency.
    """
    try:
        # Validate or set default currency code
        if not currency_code:
            currency_code = 'USD'
        currency_code = currency_code.upper()

        try:
            # CoinMarketCap API request
            cmc_url = 'https://api.coinmarketcap.com/dexer/v3/dexer/pair-info?dexer-platform-name=bsc&address=0x638da797f50131c7f8fe1b0de864acee773d0bab&t=1705093806632'
            cmc_response = requests.get(cmc_url)
            cmc_response.raise_for_status()
            price_usd = Decimal(cmc_response.json()['data']['priceUsd']).quantize(Decimal('0.0000001'))
        except requests.RequestException as e:
            print(f"\nError during request to CoinMarketCap API:\n {e}")
            # Fallback URL if the first request fails
            try:
                fallback_url = 'https://cmc-api.denaro.is/price'
                print(f"\nUsing fallback API at: {fallback_url}")
                fallback_response = requests.get(fallback_url)
                fallback_response.raise_for_status()
                price_usd = Decimal(fallback_response.json()['USD']).quantize(Decimal('0.00000001'))
            except requests.RequestException as e:
                print(f"\nError during request to fallback API:\n {e}")
                print("\nFailed to get the real-world price of Denaro.")
                price_usd = Decimal('0')

        # Early return for USD
        if currency_code == 'USD':
            return price_usd
        
        try:
        # Exchange rate for fiat currencies
            currency_exchange_rate_url = 'https://open.er-api.com/v6/latest/USD'
            currency_response = requests.get(currency_exchange_rate_url)
            currency_response.raise_for_status()
            rates = currency_response.json()['rates']
            if currency_code in rates:
                currency_exchange_rate = Decimal(rates[currency_code]).quantize(Decimal('0.01'))
                return price_usd * currency_exchange_rate
        except requests.RequestException as e:
            print(f"\nError during request to OpenExchangeRate API:\n {e}")
            print("\nFailed to get the exchange rate of fiat currencies.")

        # Exchange rate for cryptocurrencies
        try:
            cryptocurrency_exchange_rate_url = 'https://api.coincap.io/v2/assets'
            crypto_response = requests.get(cryptocurrency_exchange_rate_url)
            crypto_response.raise_for_status()
            crypto_data = crypto_response.json()['data']
            amount = next((Decimal(item['priceUsd']).quantize(Decimal('0.0000001')) for item in crypto_data if item['symbol'] == currency_code), None)
            if amount:
                return price_usd / amount
        except requests.RequestException as e:
            print(f"\nError during request to CoinCap API:\n {e}")
            print("\nFailed to get the exchange rate of crypto-currencies.")


        return Decimal('0')

    except requests.RequestException as e:
        #logging.error(f"Request Error: {e}")
        return Decimal('0')
    except Exception as e:
        #logging.error(f"General Error: {e}")
        return Decimal('0')

def getTransactionInfo():
    print()
    
# Argparse Helper Functions
def sort_arguments_based_on_input(argument_names):
    """
    Overview:
        Sorts a list of CLI argument names based on their positional occurrence in sys.argv.
        Any argument not found in sys.argv is filtered out. The returned list is then formatted
        as a comma-separated string. This version also handles arguments with an '=' sign.

        Parameters:
        - argument_names (list): A list of argument names to be sorted.
    
        Returns:
        - str: A string of sorted argument names separated by commas with 'and' added before the last argument.
    
        Note:
            This function leverages the sys.argv array, which captures the command-line arguments passed to the script.
    """
    # Process each argument in sys.argv to extract the argument name before the '=' sign
    processed_argv = [arg.split('=')[0] for arg in sys.argv]

    # Filter out arguments that are not present in the processed sys.argv
    filtered_args = [arg for arg in argument_names if arg in processed_argv]

    # Sort the filtered arguments based on their index in the processed sys.argv
    sorted_args = sorted(filtered_args, key=lambda x: processed_argv.index(x))    

    # Join the arguments into a string with proper formatting
    if len(sorted_args) > 1:
        result = ', '.join(sorted_args[:-1]) + ', and ' + sorted_args[-1]    
    elif sorted_args:
        result = sorted_args[0]
    else:
        result = ''
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

def check_args(parser, args):
    """Overview:
        Validates combinations of CLI arguments and returns an error message via the parser
        if invalid combinations are found. Specifically, it checks for required combinations
        that involve the '-password' flag.

        Parameters:
        - parser (argparse.ArgumentParser): The argument parser object.
        - args (argparse.Namespace): The argparse namespace containing parsed arguments.
    
        Note:
            Utilizes the `sort_arguments_based_on_input` function to display arguments in the
            order in which they were passed in the command line.
    """
    if args.command == "wallet":
        # -deterministic, -2fa, and -encrypt requires -password
            
        if args.deterministic and args.tfa and args.encrypt and not args.password:
            sorted_args = sort_arguments_based_on_input(['-deterministic','-phrase', '-2fa', '-encrypt', '-password'])
            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not sorted_args])
            parser.error(f"{sorted_args} requires the -password argument to be set.\n\nContext: A password is required to encrypt the wallet, enable 2-Factor Authentication, and for deterministic address generation{' using the provided mnemonic' if args.phrase else ''}.")
    
        # -2fa and -encrypt requires -password
        if args.tfa and args.encrypt and not args.password:
            sorted_args = sort_arguments_based_on_input(['-2fa', '-encrypt', '-password'])
            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not sorted_args])
            parser.error(f"{sorted_args} requires the -password argument to be set.\n\nContext: A password is required for encrypted wallets with 2-Factor Authentication enabled.")
    
        # -2fa requires both -encrypt and -password
        if args.tfa and (not args.encrypt or not args.password):
            sorted_args = sort_arguments_based_on_input(['-2fa', '-encrypt', '-password'])
            if not args.encrypt:
                context_str = "2-Factor Authentication is only supported for encrypted wallets."
            
            if not args.password:
                context_str = "2-Factor Authentication is only supported for encrypted wallets, which requires a password."
            
            # -2fa and -deterministic requires both -encrypt and -password
            if args.deterministic:
                sorted_args = sort_arguments_based_on_input(['-2fa', '-deterministic','-phrase', '-encrypt', '-password'])
                if not args.password:
                    context_str += f" Deterministic address generation {'using the provided mnemonic' if args.phrase else ''} also requires a password."

            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not sorted_args and var is not context_str])
            parser.error(f"{sorted_args} requires both the -encrypt and -password arguments to be set.\n\nContext: {context_str}")
    
        # -encrypt and -deterministic requires -password
        if args.encrypt and args.deterministic and not args.password:
            sorted_args = sort_arguments_based_on_input(['-encrypt', '-deterministic','-phrase', '-password'])
            parser.error(f"{sorted_args} requires the -password argument to be set.\n\nContext: A password is required to encrypt the wallet and for deterministic address generation{' using the provided mnemonic' if args.phrase else ''}.")

        # -deterministic alone requires -password
        #if args.deterministic and not args.password:
        #    sorted_args = sort_arguments_based_on_input(['-deterministic','-phrase', '-password'])
        #    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not sorted_args])
        #    parser.error(f"{sorted_args} requires the -password argument to be set.\n\nContext: A password is required for deterministic address generation{' using the provided mnemonic' if args.phrase else ''}.")
    
        # -encrypt alone requires -password
        if args.encrypt and not args.password:
            sorted_args = sort_arguments_based_on_input(['-encrypt', '-password'])
            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not sorted_args])
            parser.error(f"{sorted_args} requires the -password argument to be set.\n\nContext: A password is required to encrypt the wallet.")

    if args.command == "send" or args.command == "paperwallet":
        # -wallet and -private-key cannot be used together
        if args.wallet and args.private_key:
            sorted_args = sort_arguments_based_on_input(['-wallet', '-private-key'])
            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not sorted_args])
            parser.error(f"{sorted_args} cannot be used together.\n\nContext: The script automatically retrieves the private key of the specified address from the wallet file. The -private-key option is unnessesary in this instance.")
        
        # -wallet requires -address
        if args.wallet and not args.address:
            sorted_args = sort_arguments_based_on_input(['-wallet', '-address'])
            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not sorted_args])
            parser.error(f"{sorted_args} requires the -address argument to be set.\n\nContext: An address that is associated with the wallet file must be specified.")
        
        # -address requires -wallet
        if args.address and not args.wallet:
            sorted_args = sort_arguments_based_on_input(['-address', '-wallet'])
            DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not sorted_args])
            parser.error(f"{sorted_args} requires the -wallet argument to be set.\n\nContext: A wallet file must be specified in order to use the given address. The address should also be associated with the wallet file.")

def process_decryptwallet_filter(args):
    """Overview:
        This function manages the '-filter' argument and 'filter' subparser in the 'decryptwallet' command-line interface.. 
        It is tasked with extracting and returning specified filter options, which could be based on address and/or field.
        
        - One or more addresses can be filtered.
        - Addresses can be excluded by adding a hyphen '-' to the begining of it.
        - Multiple field parameters are supported.
    
        Valid Field Parameters: id, mnemonic, private_key, public_key, address
    
        For the '-filter' Argument:
        The expected input format is: "field={id,mnemonic,private_key,public_key,address},address={ADDRESS_1, ADDRESS_2, ADDRESS_3, ...}"
            - Parameters must be enclosed within curly braces '{}'.
            - The entire filter string must be enclosed in quotation marks.
        
        For 'filter' Subparser:
        - Utilize the '-address' option to specify one or more addresses to be filtered.
        - Utilize the '-field' option to specify one or more field parameters for filtering.
    
        Parameters:
            - args (argparse.Namespace): The namespace from argparse containing all the parsed command-line arguments.
        
        Returns:
            - tuple: A tuple consisting of the filtered address, the filtered field(s), and the value of args.filter_subparser_pretty.
    """
    # Initialize address and field variables
    addresses = []
    field = []
    fields_to_string = ""  
    filter_subparser_show = None

    if not args.command == 'balance':
        # Handle the case when the 'filter' subparser is used
        if args.filter_subparser == 'filter':
            filter_subparser_show = args.filter_subparser_show
            if args.address:
                addresses = args.address.split(',')
            if args.field:
                field = args.field.split(',')
                fields_to_string = ", ".join(field)
    
        # If no subparser is used, set show to None
        elif args.filter_subparser != 'filter':
            args.filter_subparser_show = None

        # Validate the field values against a list of valid options
        valid_fields = ["id","mnemonic", "private_key", "public_key", "address"]
        invalid_fields = []
        
        #Handle field validation
        if field:
            for f in field:
                if f not in valid_fields:
                    invalid_fields.append(f)                    
            for f in invalid_fields:
                field.remove(f)
            #Remove duplicate fields
            seen_fields = set() # A set to keep track of seen elements
            unique_fields = [] # A list to store the unique elements        
            for item in field:
                if item not in seen_fields:
                    seen_fields.add(item) # Add unseen item to the set
                    unique_fields.append(item) # Append unseen item to the unique_fields list
            field = unique_fields
            fields_to_string = ", ".join(field)
        if len(invalid_fields) > 0:
            logging.error(f"Invalid field value{'s' if len(invalid_fields) > 1 else ''}: {invalid_fields}. Must be one of {valid_fields}\n")
    else:
        if args.address:
            addresses = args.address.split(',')   

    # Remove duplicate addresses including hyphenated duplicates
    seen_addresses = set()
    addresses = [entry for entry in addresses if entry not in seen_addresses and not seen_addresses.add(entry)]
    addresses = remove_duplicates_from_address_filter(addresses)
    
    # Validate addresses using regex pattern
    address_pattern = r'^-?[DE][1-9A-HJ-NP-Za-km-z]{44}$'
    valid_addresses = [addr for addr in addresses if re.match(address_pattern, addr)]
    invalid_addresses = [addr for addr in addresses if addr not in valid_addresses]

    if len(invalid_addresses) >= 1:
        print(f"Warning: The following {'address is' if len(invalid_addresses) == 1 else 'addresses are'} not valid: {invalid_addresses}")
        if not len(valid_addresses) >=1:
            print()
    
    addresses = valid_addresses
    new_line = '\n'

    # Output the filtering criteria to the console
    if addresses:
        print(f'Filtering wallet by address: "{", ".join(addresses)}"{new_line if not field and not filter_subparser_show else ""}')
    if field:
        print(f'Filtering wallet by field: "{fields_to_string}"{new_line if not filter_subparser_show else ""}')
    if filter_subparser_show:
        print(f'Filtering wallet by "{filter_subparser_show}" entries.\n')
    
    result = addresses, field, filter_subparser_show
    DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
    return result

def remove_duplicates_from_address_filter(address_list):
    """Overview:
        Remove duplicate addresses from the list while honoring the first occurrence of hyphenated or non-hyphenated versions.
        
        Parameters:
            address_list (list): The list of addresses, possibly containing duplicates and/or hyphenated versions.
            
        Returns:
            list: A deduplicated list of addresses.
    """
    
    # Dictionary to keep track of the first occurrence of each unhyphenated address.
    # The key is the unhyphenated address and the value is the actual address (hyphenated or not).
    seen_unhyphenated = {}
    
    # List to hold the deduplicated addresses.
    deduplicated_list = []
    
    # Iterate through the list of addresses.
    for addr in address_list:
        # Remove hyphen prefix, if any, for comparison.
        unhyphenated = addr.lstrip('-')
        
        # If this unhyphenated address hasn't been seen before, add it to both the seen dictionary and the deduplicated list.
        if unhyphenated not in seen_unhyphenated:
            seen_unhyphenated[unhyphenated] = addr
            deduplicated_list.append(addr)
        # If the unhyphenated version has been seen and the hyphenation status is the same, skip this address.
        elif seen_unhyphenated[unhyphenated].startswith('-') == addr.startswith('-'):
            continue
        # If the unhyphenated version has been seen but the hyphenation status is different, check which one appeared first.
        else:
            if address_list.index(seen_unhyphenated[unhyphenated]) > address_list.index(addr):
                # If the current address appeared first, replace the older one with this one in both the seen dictionary and deduplicated list.
                deduplicated_list.remove(seen_unhyphenated[unhyphenated])
                deduplicated_list.append(addr)
                seen_unhyphenated[unhyphenated] = addr
                
    return deduplicated_list

def is_valid_currency_code(code="", get_return=False):
    is_valid_currency_code.valid_codes = {
        # International Currencies
        "AED": "د.إ", "AFN": "؋", "ALL": "L", "AMD": "֏", "ANG": "ƒ", "AOA": "Kz", "ARS": "$", "AUD": "$", "AWG": "ƒ", 
        "AZN": "₼", "BAM": "KM", "BBD": "$", "BDT": "৳", "BGN": "лв", "BHD": ".د.ب", "BIF": "FBu", "BMD": "$", "BND": "$", 
        "BOB": "Bs.", "BRL": "R$", "BSD": "$", "BTN": "Nu.", "BWP": "P", "BYN": "Br", "BZD": "$", "CAD": "$", "CDF": "FC", 
        "CHF": "Fr", "CLP": "$", "CNY": "¥", "COP": "$", "CRC": "₡", "CUP": "$", "CVE": "$", "CZK": "Kč", "DJF": "Fdj", 
        "DKK": "kr", "DOP": "$", "DZD": "دج", "EGP": "£", "ERN": "Nfk", "ETB": "Br", "EUR": "€", "FJD": "$", "FKP": "£", 
        "FOK": "kr", "GBP": "£", "GEL": "₾", "GGP": "£", "GHS": "₵", "GIP": "£", "GMD": "D", "GNF": "FG", "GTQ": "Q", 
        "GYD": "$", "HKD": "$", "HNL": "L", "HRK": "kn", "HTG": "G", "HUF": "Ft", "IDR": "Rp", "ILS": "₪", "IMP": "£", 
        "INR": "₹", "IQD": "ع.د", "IRR": "﷼", "ISK": "kr", "JEP": "£", "JMD": "$", "JOD": "د.ا", "JPY": "¥", "KES": "Sh", 
        "KGS": "с", "KHR": "៛", "KID": "$", "KMF": "CF", "KRW": "₩", "KWD": "د.ك", "KYD": "$", "KZT": "₸", "LAK": "₭", 
        "LBP": "ل.ل", "LKR": "₨", "LRD": "$", "LSL": "L", "LYD": "ل.د", "MAD": "د.م.", "MDL": "L", "MGA": "Ar", "MKD": "ден", 
        "MMK": "K", "MNT": "₮", "MOP": "P", "MRU": "UM", "MUR": "₨", "MVR": "Rf", "MWK": "MK", "MXN": "$", "MYR": "RM", 
        "MZN": "MT", "NAD": "$", "NGN": "₦", "NIO": "C$", "NOK": "kr", "NPR": "₨", "NZD": "$", "OMR": "ر.ع.", "PAB": "B/.", 
        "PEN": "S/.", "PGK": "K", "PHP": "₱", "PKR": "₨", "PLN": "zł", "PYG": "₲", "QAR": "ر.ق", "RON": "lei", "RSD": "дин", 
        "RUB": "₽", "RWF": "FRw", "SAR": "ر.س", "SBD": "$", "SCR": "₨", "SDG": "ج.س.", "SEK": "kr", "SGD": "$", "SHP": "£", 
        "SLL": "Le", "SOS": "Sh", "SRD": "$", "SSP": "£", "STN": "Db", "SVC": "$", "SYP": "£", "SZL": "L", "THB": "฿", 
        "TJS": "ЅМ", "TMT": "m", "TND": "د.ت", "TOP": "T$", "TRY": "₺", "TTD": "$", "TVD": "$", "TWD": "NT$", "TZS": "Sh", 
        "UAH": "₴", "UGX": "Sh", "USD": "$", "UYU": "$", "UZS": "лв", "VES": "Bs.", "VND": "₫", "VUV": "Vt", "WST": "T", 
        "XAF": "FCFA", "XCD": "$", "XOF": "CFA", "XPF": "₣", "YER": "﷼", "ZAR": "R", "ZMW": "ZK", "ZWL": "$",
        # Top 100 crpytocurrencies
        'BTC' : '₿','ETH' : 'Ξ','USDT' : '₮','BNB' : '','SOL' : '','XRP' : '✕','USDC' : '','ADA' : '₳','AVAX' : '','DOGE' : 'Ð','DOT' : '●','TRX' : '',
        'MATIC' : '','LINK' : '','WBTC' : '₿','ICP' : '','SHIB' : '','DAI' : '◈','LTC' : 'Ł','BCH' : 'Ƀ','XLM' : '*','UNI' : '','ALGO' : '','XMR' : 'ɱ',
        'ATOM' : '','VET' : '','XTZ' : '','THETA' : 'ϑ','EOS' : 'ε','IOTA' : '','AAVE' : '','COMP' : '','CAKE' : '','MANA' : '','CRV' : '','FLOW' : '','MINA' : '',
        'HNT' : '','HBAR' : '','FTM' : '','SAND' : '','AXS' : '','FTT' : '','KCS' : '','WEMIX' : '','SNX' : '','NEO' : '','KAVA' : '','ROSE' : '','CHZ' : '',
        'WOO' : '','RPL' : '','GALA' : '','XEC' : '','FXS' : '','CFX' : '','KLAY' : '','XDC' : '','AR' : '','AKT' : '','FET' : '','CSPR' : '','1INCH' : '',
        'GNO' : '','BUSD' : '','SC' : '','DYDX' : '','GT' : '','NEXO' : '','TWT' : '','BTG' : '','SKL' : '','ENJ' : '','FEI' : '','PENDLE' : '','CELO' : '',
        'IOTX' : '','ELF' : '','GAS' : '','HT' : '','ZEC' : '','ZIL' : '','USDP' : ''
    }
    if get_return:
        if code in is_valid_currency_code.valid_codes:
            return True, is_valid_currency_code.valid_codes[code]
        else:
            return False, "$"

# Main Function
def main():
    # Verbose parser for shared arguments
    verbose_parser = argparse.ArgumentParser(add_help=False)
    verbose_parser.add_argument('-verbose', action='store_true', help='Enables info and debug messages.')
    
    #Node URL parser 
    denaro_node = argparse.ArgumentParser(add_help=False)
    denaro_node.add_argument('-node', type=str, help="Specifies the URL or IP address of a Denaro node.")

    # Create the parser
    parser = argparse.ArgumentParser(description="Manages wallets and transactions for the Denaro crypto-currency.")
    subparsers = parser.add_subparsers(dest='command')
    
    # Main parser for 'generate' command
    parser_generate = subparsers.add_parser('generate', help="Generate wallets, addresses, or paper wallets", parents=[verbose_parser])
    
    # Create a single set of subparsers for 'generate'
    generate_subparsers = parser_generate.add_subparsers(dest='command', required=True, help="Sub-commands for generating wallets, addresses, and paper wallets")
    
    # Subparser for generating a new wallet
    parser_generatewallet = generate_subparsers.add_parser('wallet', help="Generates a new wallet with various options like encryption and 2FA", parents=[verbose_parser])
    parser_generatewallet.add_argument('-wallet', help="Specifies the wallet filename. Defaults to the `./wallets/` directory if no specific filepath is provided.", required=True)
    parser_generatewallet.add_argument('-encrypt', help="Enables encryption for new wallets.", action='store_true')
    parser_generatewallet.add_argument('-2fa', help="Enables 2-Factor Authentication for new encrypted wallets.", dest='tfa', action='store_true')
    parser_generatewallet.add_argument('-deterministic', help="Enables deterministic address generation for new wallets.", action='store_true')
    parser_generatewallet.add_argument('-phrase', help="Generates a wallet based on a 12 word mnemonic phrase provdided by the user. The mnemonic phrase must be enclosed in quotation marks. This option also enables deterministic address generation, therefore password is required.")
    parser_generatewallet.add_argument('-password', help="Password used for wallet encryption and/or deterministic address generation.")
    parser_generatewallet.add_argument('-backup', help="Disables wallet backup warning when attempting to overwrite an existing wallet. A 'True' or 'False' parameter is required, and will specify if the wallet should be backed up or not.", choices=['False', 'True'])
    parser_generatewallet.add_argument('-disable-overwrite-warning', help="Disables overwrite warning if an existing wallet is not backed up.", dest='disable_overwrite_warning', action='store_true')
    parser_generatewallet.add_argument('-overwrite-password', help="Used to bypass the password confirmation prompt when overwriteing a wallet that is encrypted. A string paramter is required, and should specify the password used for the encrypted wallet.", dest='overwrite_password')

    # Subparser for generating a new address
    parser_generateaddress = generate_subparsers.add_parser('address', help="Generate a new address for an existing wallet", parents=[verbose_parser])
    parser_generateaddress.add_argument('-wallet', help="Specifies the wallet filename. Defaults to the `./wallets/` directory if no specific filepath is provided.", required=True)
    parser_generateaddress.add_argument('-password', help="The password of the specified wallet. Required for encrypted and/or deterministic wallets.")
    parser_generateaddress.add_argument('-2fa-code', help="Optional Two-Factor Authentication code for encrypted wallets that have 2FA enabled. Should be the 6-digit code generated from an authenticator app.", dest='tfacode', required=False, type=str)
    parser_generateaddress.add_argument('-amount', help="Specifies the amount of addresses to generate (Maximum of 256).", type=int)
 
    # Subparser for generating a paper wallet
    parser_generatepaperwallet = generate_subparsers.add_parser('paperwallet', help="Used to generate a Denaro paper wallet either by using an address that is associated with a wallet file, or directly via a private key that corresponds to a particular address.", parents=[verbose_parser])
    parser_generatepaperwallet.add_argument('-wallet', help="Specifies the wallet filename. Defaults to the `./wallets/` directory if no specific filepath is provided.")
    parser_generatepaperwallet.add_argument('-password', help="The password of the specified wallet. Required for wallets that are encrypted.")
    parser_generatepaperwallet.add_argument('-2fa-code', help="Optional Two-Factor Authentication code for encrypted wallets that have 2FA enabled. Should be the 6-digit code generated from an authenticator app.", dest='tfacode', required=False, type=str)
    parser_generatepaperwallet.add_argument('-address', help="Specifies a Denaro address associated with the wallet file. A paper wallet will be generated for this Denaro address.")
    parser_generatepaperwallet.add_argument('-private-key', help="Specifies the private key associated with a Denaro address. Not required if specifying an address from a wallet file.", dest='private_key')   
    parser_generatepaperwallet.add_argument('-type', help="Specifies the file type for the paper wallet. The default filetype is PDF.", choices=['pdf','png'], default='pdf')

    # Subparser for decrypting the wallet
    parser_decryptwallet = subparsers.add_parser('decryptwallet',help="Used to decrypt all entries in a wallet file, or selectivly decrypt specific entries based on a provided filter, and returns the decrypted data back to the console.", parents=[verbose_parser])
    parser_decryptwallet.add_argument('-wallet', help="Specifies the wallet filename. Defaults to the `./wallets/` directory if no specific filepath is provided.", required=True)
    parser_decryptwallet.add_argument('-password', help="The password of the specified wallet. Required for wallets that are encrypted.")
    parser_decryptwallet.add_argument('-2fa-code', help="Optional Two-Factor Authentication code for encrypted wallets that have 2FA enabled. Should be the 6-digit code generated from an authenticator app.", dest='tfacode', required=False, type=str)
    parser_decryptwallet.add_argument('-json', help="Prints formatted JSON output for better readability.", action='store_true')
        
    # Subparser for filter under decryptwallet
    filter_subparser = parser_decryptwallet.add_subparsers(dest='filter_subparser', required=False)
    parser_filter = filter_subparser.add_parser('filter', help="Filters wallet entries by address, field, and/or origin", parents=[verbose_parser])
    parser_filter.add_argument('-address', help='One or more addresses to filter by. Adding a hyphen `-` to the beginning of an address will exclude it from the output. Format is: `address=ADDRESS_1, ADDRESS_2, ADDRESS_3,...`')
    parser_filter.add_argument('-field', help='One or more wallet entry fields to filter by. Format is: `field=id,mnemonic,private_key,public_key,address`.')
    parser_filter.add_argument('-show', help="Filters wallet entries origin. 'generated' is used to retrieve only the information of internally generated wallet entries. 'imported' is used to retrieve only the information of imported wallet entries.", choices=['generated', 'imported'], dest="filter_subparser_show")    
    
    # Subparser for importing wallet data based on a private key
    parser_import = subparsers.add_parser('import',help="Used to import a wallet entry into a specified wallet file using the private key of a Denaro address.", parents=[verbose_parser])
    parser_import.add_argument('-wallet', help="Specifies the wallet filename. Defaults to the `./wallets/` directory if no specific filepath is provided.", required=True)
    parser_import.add_argument('-password', help="The password of the specified wallet. Required for wallets that are encrypted.")
    parser_import.add_argument('-2fa-code', help="Optional Two-Factor Authentication code for encrypted wallets that have 2FA enabled. Should be the 6-digit code generated from an authenticator app.", dest='tfacode', required=False, type=str)
    parser_import.add_argument('-private-key', help="Specifies the private key associated with a Denaro address to import.", dest='private_key', required=True)

    # Subparser for backing up wallet
    parser_backupwallet = subparsers.add_parser('backupwallet',help="Used to create a backup of a wallet file.", parents=[verbose_parser])
    parser_backupwallet.add_argument('-wallet', help="Specifies the wallet filename. Defaults to the `./wallets/` directory if no specific filepath is provided.", required=True)
    parser_backupwallet.add_argument('-path', help="Specifies the directory to save the wallet backup file. Defaults to the `./wallets/wallet_backups/` directory if no specific filepath is provided.")

    # Subparser for sending a transaction
    parser_send = subparsers.add_parser('send',help="Main command to initiate a Denaro transaction.", parents=[verbose_parser, denaro_node])
    parser_send.add_argument('-amount', required=True, help="Specifies the amount of Denaro to be sent.")    
    
    # Subparser to specify the wallet file and address to send from. The private key of an address can also be specified.
    send_from_subparser = parser_send.add_subparsers(dest='transaction_send_from_subparser', required=True)
    parser_send_from = send_from_subparser.add_parser('from',help="Specifies the sender's details.", parents=[verbose_parser, denaro_node])
    parser_send_from.add_argument('-wallet', help="Specifies the wallet filename. Defaults to the `./wallets/` directory if no specific filepath is provided.")
    parser_send_from.add_argument('-password', help="The password of the specified wallet. Required for wallets that are encrypted.")
    parser_send_from.add_argument('-2fa-code', help="Optional Two-Factor Authentication code for encrypted wallets that have 2FA enabled. Should be the 6-digit code generated from an authenticator app.", dest='tfacode', required=False, type=str)
    parser_send_from.add_argument('-address', help="The Denaro address to send from. The address must be associated with the specified wallet.")
    parser_send_from.add_argument('-private-key', help="Specifies the private key associated with a Denaro address. Not required if specifying an address from a wallet file.", dest='private_key')
    
    # Subparser to specify the receiving address and optional transaction message.
    parser_send_to_subparser = parser_send_from.add_subparsers(dest='transaction_send_to_subparser', required=True)
    parser_send_to = parser_send_to_subparser.add_parser('to',help="Specifies the receiver's details.", parents=[verbose_parser, denaro_node])
    parser_send_to.add_argument('receiver', help="The receiveing address.")
    parser_send_to.add_argument('-message', help="Optional transaction message.", default="")
    
    # Subparser for checking balance
    parser_balance = subparsers.add_parser('balance',help="Used to check the balance of addresses in the Denaro blockchain that are asociated with a specified wallet file.", parents=[verbose_parser, denaro_node])
    parser_balance.add_argument('-wallet', help="Specifies the wallet filename. Defaults to the `./wallets/` directory if no specific filepath is provided.", required=True)
    parser_balance.add_argument('-password', help="The password of the specified wallet. Required for wallets that are encrypted.")
    parser_balance.add_argument('-2fa-code', help="Optional Two-Factor Authentication code for encrypted wallets that have 2FA enabled. Should be the 6-digit code generated from an authenticator app.", dest='tfacode', required=False, type=str)
    parser_balance.add_argument('-address', help="Specifies one or more addresses to get the balance of. Adding a hyphen `-` to the beginning of an address will exclude it. Format is: `address=ADDRESS_1, ADDRESS_2, ADDRESS_3,...`")
    parser_balance.add_argument('-convert-to', help="Converts the monetary value of balances to a user specified currency, factoring in current exchange rates against the USD value of DNR. Supports 161 international currencies and major cryptocurrencies. A valid currency code is required (e.g., 'USD', 'EUR', 'GBP', 'BTC'). By default balance values are calculated in USD.", dest='currency_code', type=str)
    parser_balance.add_argument('-show', help="Filters balance information based on entry origin. 'generated' is used to retrieve only the balance information of internally generated wallet entries. 'imported' is used to retrieve only the balance information of imported wallet entries.", choices=['generated', 'imported'])
    parser_balance.add_argument('-json', help="Prints the balance information in JSON format.", action='store_true')
    parser_balance.add_argument('-to-file', help="Saves the output of the balance information to a file. The resulting file will be in JSON format and named as '[WalletName]_balance_[Timestamp].json' and will be stored in '/[WalletDirectory]/balance_information/[WalletName]/'.", dest='to_file', action='store_true')
       
    args = parser.parse_args()

    if args.command == "wallet":
        address=None
        if args.phrase:
            if is_valid_mnemonic(args.phrase):
                args.deterministic = True
                check_args(parser, args)
                address = generateAddressHelper(filename=args.wallet, password=args.password, totp_code=None, new_wallet=True, encrypt=args.encrypt, use2FA=args.tfa, deterministic=args.deterministic, backup=args.backup, disable_warning=args.disable_overwrite_warning, overwrite_password=args.overwrite_password,mnemonic=args.phrase)
        else:
            check_args(parser, args)
            address = generateAddressHelper(filename=args.wallet, password=args.password, totp_code=None, new_wallet=True, encrypt=args.encrypt, use2FA=args.tfa, deterministic=args.deterministic, backup=args.backup, disable_warning=args.disable_overwrite_warning, overwrite_password=args.overwrite_password)    
        if address:
            print(address)

    elif args.command == "address":
        address = generateAddressHelper(filename=args.wallet, password=args.password, totp_code=args.tfacode if args.tfacode else None, new_wallet=False, encrypt=False, use2FA=False, amount=args.amount if args.amount else 1)    
        if address:
            print(address)
    
    elif args.command == 'paperwallet':
        check_args(parser, args)
        generatePaperWallet(filename=args.wallet, password=args.password, totp_code=args.tfacode if args.tfacode else None, address=args.address if args.address else None, private_key=args.private_key if args.private_key else None, file_type=args.type)

    elif args.command == 'decryptwallet':
        address, field, args.filter_subparser_show = process_decryptwallet_filter(args)
        decrypted_data = decryptWalletEntries(filename=args.wallet, password=args.password, totp_code=args.tfacode if args.tfacode else "", address=address if address else None, fields=field if field else [], to_json=args.json if args.json else False, show=args.filter_subparser_show if args.filter_subparser_show else None)
        if decrypted_data:
            print(decrypted_data)
    
    elif args.command == 'import':
        generateAddressHelper(filename=args.wallet, password=args.password, totp_code=args.tfacode if args.tfacode else None, new_wallet=False, encrypt=False, use2FA=False, private_key=args.private_key, is_import=True)
    
    elif args.command == 'backupwallet':
        args.path = args.path if args.path else None
        ensure_wallet_directories_exist(custom=args.path)        
        filename = get_normalized_filepath(args.wallet)
        _, wallet_exists = _load_data(filename, False)
        if wallet_exists:
            DataManipulation.backup_wallet(filename, args.path)

    elif args.command == 'send':
        check_args(parser, args)
        transaction, _ = prepareTransaction(filename=args.wallet, password=args.password, totp_code=args.tfacode if args.tfacode else "", amount=args.amount, sender=args.address if args.address else None, private_key=args.private_key if args.private_key else None, receiver=args.receiver, message=args.message, node=args.node)
        if transaction:
            print(f'Transaction successfully pushed to node. \nTransaction hash: {sha256(transaction.hex())}')
            print(f'\nDenaro Explorer link: http://explorer.denaro.is/transaction/{sha256(transaction.hex())}')
    
    elif args.command == 'balance':
        # Check if the currency code is valid and get the corresponding symbol
        is_valid, currency_symbol = is_valid_currency_code(code=args.currency_code.upper(), get_return=True) if args.currency_code else (False, "$")        
        # Set the currency code to upper case if valid, else default to "USD"
        currency_code = str(args.currency_code).upper() if is_valid else "USD"
        
        if not is_valid and args.currency_code:
            print(f"{str(args.currency_code).upper()} is not a valid currency code. Defaulting to USD.\n")

        # Process other arguments
        address, _, _, = process_decryptwallet_filter(args)
        # Call checkBalance with the updated currency_code and currency_symbol
        checkBalance(filename=args.wallet, password=args.password, totp_code=args.tfacode if args.tfacode else "", address=address if args.address else None, node=args.node, to_json=args.json, to_file=args.to_file, show=args.show, currency_code=currency_code, currency_symbol=currency_symbol)
    
    DataManipulation.secure_delete([var for var in locals().values() if var is not None])

if __name__ == "__main__":
    exit_code = 1
    try:
        main()
        exit_code = 0 
    except KeyboardInterrupt:
        print("\r  ")
        print("\rProcess terminated by user.")
        QRCodeUtils.close_window = True
        exit_code = 1
    #except Exception as e:
    #    logging.error(f"{e}")
    #    exit_code = 1    
    finally:
        DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        gc.collect()
        #sys.exit(exit_code)