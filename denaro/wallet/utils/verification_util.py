import hashlib
import hmac as hmac_module
import json
import base64
import pyotp
import logging
import requests
import urllib3
urllib3.disable_warnings()
import re
import random

from Crypto.Protocol.KDF import scrypt
import data_manipulation_util
import cryptographic_util

class Verification:
    """
    Handles data verification.
    """
    @staticmethod
    def hash_password(password, salt, wallet_version=None):        
        """
        Generate a cryptographic hash of the password using PBKDF2 and then Scrypt.
        """
        # First layer of hashing using PBKDF2
        
        salt_bytes = salt
        if not isinstance(salt, bytes):
            salt_bytes = bytes(salt, 'utf-8')
        pbkdf2_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt_bytes, 100000)
        

        # Second layer of hashing using Scrypt
        result = scrypt(pbkdf2_hash, salt=salt, key_len=32, N=2**14, r=8, p=1)
        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result


    @staticmethod
    def verify_password(stored_password_hash, provided_password, salt):
        """
        Compares the provided password with the stored hash.
        """
        # Generate hash of the provided password
        verifier = Verification.hash_password(provided_password, salt)
        # Securely compare the generated hash with the stored hash
        is_verified = hmac_module.compare_digest(verifier, stored_password_hash)

        # Nullify verifier if not verified
        if not is_verified:
            verifier = None
        result = is_verified, verifier
        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result
    
    @staticmethod
    def hmac_util(password=None,hmac_salt=None,stored_hmac=None, hmac_msg=None, verify=False):
        """
        Handle HMAC generation and verification.
        """
        # Generate HMAC key using Scrypt
        hmac_key = scrypt(password.encode(), salt=hmac_salt, key_len=32, N=2**14, r=8, p=1)
        # Generate HMAC of the message
        computed_hmac = hmac_module.new(hmac_key, hmac_msg, hashlib.sha256).digest()
        # If in verify mode, securely compare the computed HMAC with the stored HMAC
        if verify:
            result = hmac_module.compare_digest(computed_hmac, stored_hmac)
            data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
            return result
        else:
            data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not computed_hmac])
            return computed_hmac

    @staticmethod
    def verify_password_and_hmac(data, password, hmac_salt, verification_salt, deterministic):
        """
        Verifies the given password and HMAC.
        
        Arguments:
        - data: The wallet data
        - password: The user's password
        - hmac_salt: The HMAC salt
        
        Returns:
        - A tuple of booleans indicating if the password and HMAC are verified
        """
        # Decode and verify the stored password verifier
        stored_verifier = base64.b64decode(data["wallet_data"]["verifier"].encode('utf-8'))
        password_verified, _ = Verification.verify_password(stored_verifier, password, verification_salt)
        
        # Prepare and verify the HMAC message
        hmac_msg = json.dumps(data["wallet_data"]["entry_data"]["entries"]).encode()
        if "imported_entries" in data["wallet_data"]["entry_data"]:
            hmac_msg = json.dumps(data["wallet_data"]["entry_data"]["imported_entries"]).encode() + hmac_msg
        if deterministic:
            hmac_msg += json.dumps(data["wallet_data"]["entry_data"]["key_data"]).encode()
        stored_hmac = base64.b64decode(data["wallet_data"]["hmac"].encode('utf-8'))
        hmac_verified = Verification.hmac_util(password=password, hmac_salt=hmac_salt, stored_hmac=stored_hmac, hmac_msg=hmac_msg, verify=True)
        result = password_verified, hmac_verified, stored_verifier
        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result
    
    @staticmethod
    def verify_totp_secret(password,totp_secret,hmac_salt,verification_salt,stored_verifier):
        """
        Validates the given Two-Factor Authentication secret token
        """
        # Decrypt the stored TOTP secret to handle 2FA
        decrypted_totp_secret = cryptographic_util.EncryptDecryptUtils.decrypt_data(totp_secret, password, "", hmac_salt, verification_salt, stored_verifier)
        # Generate a predictable TOTP secret to check against
        predictable_totp_secret = cryptographic_util.TOTP.generate_totp_secret(True,verification_salt)
        # If the decrypted TOTP doesn't match the predictable one, handle 2FA validation
        if decrypted_totp_secret != predictable_totp_secret:
            result = decrypted_totp_secret, True
            data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
            return result
        else:
            result = "", False
            data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
            return result

    @staticmethod
    def validate_totp_code(secret, code):
        """
        Validates the given Two-Factor Authentication code using the provided secret.
        """
        totp = pyotp.TOTP(secret)
        result = totp.verify(code)
        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result
    
    @staticmethod
    def is_valid_address(address):
        """
        Validates if the provided address is a valid IPv4 address, URL without protocols, or localhost with optional port.
        """
        # Patterns for matching IPv4 addresses, URLs, and localhost with optional ports
        patterns = {
            'ipv4': r'^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(?::([0-5]?[0-9]{1,4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?$',
            'url': r'^(?!(http:\/\/|https:\/\/))[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}(?::([0-5]?[0-9]{1,4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?$',
            'localhost': r'^localhost(:([1-9]\d{0,3}|[1-5]\d{4}|6[0-4]\d{3}|65[0-4]\d{2}|655[0-2]\d|6553[0-5]))?$'
        }

        # Remove protocol from address
        stripped_address = re.sub(r'^https?://', '', address)

        # Check against each pattern
        for pattern in patterns.values():
            if re.match(pattern, stripped_address, re.IGNORECASE):
                return True

        # If no pattern matched, log and securely delete variables before returning False
        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        return False

    @staticmethod
    def is_valid_port(port):
        """
        Validates if the provided port number is within the valid range (1-65535).
        """
        try:
            port_num = int(port)
            if 1 <= port_num <= 65535:
                return True
            else:
                return False
                #raise ValueError("Port number out of valid range.")
        except ValueError as e:
            #logging.error(f"Invalid port: {e}")
            return False

    @staticmethod
    def validate_node_address(node, from_gui=False, check_connection=False, **kwargs):
        """
        Validates the node address and port, and attempts a connection based on the protocol and validation flag.
        """
      #  print(f"\nRunning validate_node_address | Called from: {kwargs.get('referer')}")
        node_validation = True if node[1] == True or node[1] == None else False

        if isinstance(node[1], str):
            node_validation = True if node[1] == "True" or node[1] == None else False

        node_address = node[0].rstrip('//').strip()

        # Determine protocol
        chosen_protocol = 0 if node_address.startswith("https://") else 1 if node_address.startswith("http://") else 2
        
        # Clean up node address
        cleaned_node_address = re.sub(r'\s+', ' ', node_address).replace(" :", ":").replace(": ", ":")
        
        try:
            if not str(cleaned_node_address.split(":",1)[1].split(":",1)[1]).isdigit():
                return_msg = "Invalid port number. Please enter a value between 1 and 65535."
                if not from_gui:
                    logging.error(return_msg)
                result = False, None, False, "ERROR: "+return_msg
                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
                return result
        except Exception:
            pass

        port_number_present = re.compile(r'^(?:http[s]?://)?(?:[\w\-\.]+)(?::(\d+))').search(cleaned_node_address)
        if port_number_present and port_number_present.group(1):
            port_invalid = False
            # Validate port, if present
            port_match = re.search(r':(0|([1-9][0-9]{0,3})|([1-5][0-9]{4})|(6[0-4][0-9]{3})|(65[0-4][0-9]{2})|(655[0-2][0-9])|(6553[0-5]))$', cleaned_node_address)
            if port_match:
                if not Verification.is_valid_port(port_match.group(0).replace(":","")):
                    port_invalid = True
            else:
                port_invalid = True        
            if port_invalid:
                return_msg = "Invalid port number. Please enter a value between 1 and 65535."
                if not from_gui:
                    logging.error(return_msg)
                result = False, None, False, "ERROR: "+return_msg
                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
                return result

        # Validate address
        if not Verification.is_valid_address(node_address):
            return_msg = "Invalid node address. Please provide a valid IP Address or URL."
            if not from_gui:
                logging.error(return_msg)
            result = False, None, False, return_msg
            data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
            return result

        # Attempt connection
        
        if check_connection:
            success, node, return_msg = Verification.try_request(cleaned_node_address, chosen_protocol, node_validation, from_gui)
        
            if success:
                return_msg = f"Successfully established connection with valid node at: {node}" if not from_gui else "Successfully established connection with node."
                if not from_gui:
                    print(return_msg)
                result = True, node, True, return_msg
                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
                return result
        else:
            result = True, node[0], True, ""
            
            data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
            return result
        
        # If connection attempt fails, securely delete variables and return failure
        result = False, None, True, return_msg
        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result
    
    @staticmethod
    def try_request(address, chosen_protocol, node_validation, from_gui=False):
        main_node_url = "denaro-node.gaetano.eu.org"
        protocols = ["https://", "http://"]

        # Configure logging for detailed error information
        logging.basicConfig(level=logging.DEBUG)

        # Check if the address already includes a protocol
        if re.match(r'^https?://', address):
            protocols_to_try = [""]
        else:
            protocols_to_try = protocols if chosen_protocol == 2 else [protocols[chosen_protocol], protocols[1 - chosen_protocol]]
         
        for index, protocol in enumerate(protocols_to_try):
            full_address = protocol + address
            if full_address.replace("https://", "").replace("http://", "") == main_node_url:
                node_validation = False
            try:
                if node_validation:
                    # Get the last block number from the main node
                    main_response = requests.get(f"https://{main_node_url}/get_mining_info", verify=False, timeout=5)
                    main_response.raise_for_status()
                    last_block_info = main_response.json().get('result', {}).get('last_block', {})
                    last_block_number = last_block_info.get('id')
                    if last_block_number is None:
                        return_msg = f"Node validation failed."# Last block number not found in main node response."
                        if not from_gui:
                            logging.warning(return_msg)
                        return_msg = "ERROR: "+return_msg
                        continue
    
                    # Generate a random block number
                    random_block_id = random.randint(0, last_block_number - 1)
    
                    # Get the block hash from the main node
                    main_block_response = requests.get(f"https://{main_node_url}/get_block?block={random_block_id}", verify=False, timeout=5)
                    main_block_response.raise_for_status()
                    main_node_block_info = main_block_response.json().get('result', {}).get('block', {})
                    main_node_block_hash = main_node_block_info.get('hash')
                    if main_node_block_hash is None:
                        return_msg = f"Node validation failed."# Block hash not found in main node response."
                        if not from_gui:
                            logging.error(return_msg)
                        return_msg = "ERROR: "+return_msg
                        continue
    
                    # Get the block hash from the user-specified node
                    user_block_response = requests.get(f"{full_address}/get_block?block={random_block_id}", verify=False, timeout=5)
                    user_block_response.raise_for_status()
                    user_node_block_info = user_block_response.json().get('result', {}).get('block', {})
                    user_node_block_hash = user_node_block_info.get('hash')
    
                    if user_node_block_hash is None:
                        return_msg = f"Node validation failed."# Block hash not found in specified node. {full_address} is not a valid Denaro node."
                        if not from_gui:
                            logging.error(return_msg)
                        return_msg = "ERROR: "+return_msg
                        continue
    
                    # Compare the block hashes
                    if main_node_block_hash == user_node_block_hash:
                        result = True, full_address, ""
                        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
                        return result
                    else:
                        return_msg = f"Node at {full_address} has invalid blockchain data."
                        if not from_gui:
                            logging.error(return_msg)
                        return_msg = "ERROR: "+return_msg
                        continue
                else:
                    main_response = requests.get(f"{full_address}/get_mining_info", verify=False, timeout=5)
                    main_response.raise_for_status()
                    if not main_response.json().get('ok'):
                        continue
                    else:
                        result = True, full_address, ""
                        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
                        return result
                    
            except requests.RequestException:
                if index < len(protocols_to_try) - 1:
                    #return_msg = f"Connection failed with {full_address}. Trying next protocol..."
                    return_msg = "Connection to node failed. Trying next protocol..."
                    if not from_gui:
                        logging.error(return_msg)
                else:
                    return_msg = "Connection to node failed."
                    if not from_gui:
                        logging.error(return_msg)
                    return_msg = "ERROR: "+return_msg
                continue

        # Secure delete before final return
        result = None, False, return_msg
        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
        return result