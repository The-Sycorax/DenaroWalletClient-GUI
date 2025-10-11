import os
import logging
import getpass
import shutil
import datetime
import time
import threading
import select
import sys
import base64
import data_manipulation_util
import verification_util
import queue


close_qr_window = False

is_windows = os.name == 'nt'

if is_windows:
    import msvcrt
else:
    import termios, fcntl


class UserPrompts:    
    @staticmethod
    def confirmation_prompt(msg, cli_param=False):
        """
        Displays a prompt message and awaits user input for confirmation.
    
        Parameters:
        - msg (str): The prompt message to display to the user.
    
        Returns:
        - bool: True if the user confirms ('y'), False if the user declines ('n') or quits ('/q').
        """
        while True:
            confirmation = cli_param or input(msg)  # Displays the prompt and awaits input
            if confirmation.strip().lower() in ['y', 'n']:
                return confirmation.strip().lower() == 'y'  # Returns True if 'y', False if 'n'
            elif confirmation.strip().lower() == "/q":
                return
            else:
                print("Invalid input.\n")  # Informs the user of invalid input and repeats the prompt


    @staticmethod
    def get_password(password=None):
        """
        Overview:
        Prompts the user for a password and its confirmation.

        Arguments:
        - password (str, optional): Default password. If provided, no prompt will be displayed.

        Returns:
        - str: The password entered by the user.
        """
        # Loop until passwords match
        while True:
            # If password is not provided
            if not password:
                # Prompt for password
                password_input = getpass.getpass("Enter wallet password: ")
                # Prompt for password confirmation
                password_confirm = getpass.getpass("Confirm password: ")
            else:
                # Use the provided password or prompt for it
                password_input = password or getpass.getpass("Enter wallet password: ")
                password_confirm = password_input
            # Check if the passwords match
            if password_input == password_confirm:
                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not password_input])
                return password_input
            else:
                print("Passwords do not match. Please try again.\n")


    @staticmethod
    def user_input_listener(stop_event):
        """
        Overview:
        Listens for user input and sets a global variable when input is received.

        Arguments:
        - stop_event (threading.Event): Event to stop listening for input.
        """
        global user_input_received
        # Wait for a keypress
        UserPrompts.get_input(stop_event)
        # Set the global flag indicating that input was received
        user_input_received = True

    @staticmethod
    def get_input(stop_event):
        """
        Overview:
        Waits for a single keypress from the user.

        Arguments:
        - stop_event (threading.Event): Event to stop waiting for input.

        Returns:
        - str: The key pressed by the user, or None if the stop event is set.
        """
        # Loop until the stop event is set
        while not stop_event.is_set():
            # Check if the operating system is Windows
            if is_windows:
                if msvcrt.kbhit():
                    return msvcrt.getch().decode('utf-8')
            else:
                # Save the current terminal settings
                fd = sys.stdin.fileno()
                oldterm = termios.tcgetattr(fd)
                newattr = termios.tcgetattr(fd)
                newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
                termios.tcsetattr(fd, termios.TCSANOW, newattr)

                try:
                    # Check for available input
                    if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                        return sys.stdin.read(1)
                except Exception:
                    pass
                finally:
                    # Restore the terminal settings
                    termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
            # Sleep briefly to avoid busy-waiting
            time.sleep(0.1)

    
    @staticmethod
    def wait_for_input(timeout: int, from_gui=False, callback_object=None):
        """
        Controls a countdown timer. For GUI mode, it launches a secondary worker thread
        to display a dialog and listen for a user interrupt, while this primary
        thread runs the timer loop.
    
        This method is the "Controller" in the Controller-View pattern.
    
        Args:
            timeout (int): The number of seconds to wait for user input.
            from_gui (bool): Determines if the GUI or CLI logic is used.
            callback_object (Callbacks): The GUI callbacks object.
    
        Returns:
            bool: True if the timer completes without user input (timeout).
                  False if the user provides input to cancel (interrupt).
        """
        if not from_gui:
            # --- Command-Line Interface Path ---
            # This logic is synchronous and does not involve the GUI.
            global user_input_received
            user_input_received = False
    
            stop_event = threading.Event()
            user_input_thread = threading.Thread(target=UserPrompts.user_input_listener, args=(stop_event,))
            user_input_thread.daemon = True
            user_input_thread.start()
    
            start_time = time.time()
            for i in range(timeout, -1, -1):
                if user_input_received:
                    print('\nOperation canceled.')
                    stop_event.set()
                    return False  # Canceled
    
                print(f"\rExisting wallet data will be erased in {i} seconds. Press any key to cancel operation...", end='')
                time.sleep(1)
    
            print("\nTimeout reached.")
            stop_event.set()
            return True  # Timed out
    
        # --- Graphical User Interface Path ---
        # This path uses a two-worker-thread model to satisfy all constraints.
        # Thread A (this thread): Runs the timer loop.
        # Thread B (launched by the manager): Blocks on the UI dialog.
    
        interrupt_queue = queue.Queue(maxsize=1)
        close_dialog_event = threading.Event()
        
        try:
            # 1. Ask the DialogFunctions bridge to start the secondary listener thread (Thread B).
            #    This call is NON-BLOCKING and returns immediately. The thread manager
            #    will create and start the new thread.
            callback_object.root.dialogs.dialog_functions.setup_input_listener_thread(
                close_event=close_dialog_event,
                interrupt_queue=interrupt_queue
            )
            
            # 2. This thread (Thread A) now enters its master control loop.
            start_time = time.time()
            while time.time() - start_time < timeout:
                # Check non-blockingly for an interrupt signal from Thread B.
                if not interrupt_queue.empty():
                    keypress_result = interrupt_queue.get()
                    if keypress_result is True:
                        print('Operation canceled.')
                        # The dialog is already closed because the keypress submitted it.
                        # We still set the event to ensure Thread B's close listener stops cleanly.
                        close_dialog_event.set()
                        return False  # Canceled by keypress
    
                # Update shared state for the dialog's label (optional).
                # If the dialog's label were dynamic, it would read this value.
                time_remaining = timeout - int(time.time() - start_time)
                callback_object.root.stored_data.input_listener_time_remaining = time_remaining
                
                time.sleep(0.1) # Prevent this loop from consuming 100% CPU.
    
            # 3. If the loop finishes, the timer has expired.
            #print("Timeout reached.")
            
            # 4. Signal the dialog (and the listening Thread B) to shut down.
            #    This will cause the dialog's `check_if_should_close` loop to trigger
            #    `dialog.cancel()`, which unblocks `post_and_wait` in Thread B.
            close_dialog_event.set()
            
            return True  # Timed out
    
        except Exception as e:
            print(f"An error occurred in wait_for_input: {e}")
            # Ensure cleanup happens even on unexpected errors.
            close_dialog_event.set()
            return True # Fail-safe: assume timeout to prevent accidental data loss.

    @staticmethod
    def backup_and_overwrite_helper(data, filename, password, encrypt, backup, disable_warning, deterministic, from_gui=False, callback_object=None):
        """
        Overview:
        Handles the logic for backing up and overwriting wallet data.

        Args:
        - data (dict): The wallet data.
        - filename (str): The name of the file to backup or overwrite.
        - password (str): The user's password.
        - encrypt (bool): Whether to encrypt the backup.
        - backup (str): User's preference for backing up.
        - disable_warning (bool): Whether to display warnings.
        - deterministic (bool): Whether the wallet type is deterministic.

        Returns:
        - bool: True if successful, False or None otherwise.
        """
        # Initialize variables
        password_verified = False
        hmac_verified = False        
        
        # Convert CLI boolean values to 'y' or 'n'
        if backup in ["True"]:
            backup = "y"
        if backup in ["False"]:
            backup = "n"

        # Handle the backup preference
        if from_gui:
            perform_backup = callback_object.post_confirmation_prompt('Backup Wallet', 'Wallet file already exists. Do you want to back it up?')
        else:
            perform_backup = UserPrompts.confirmation_prompt("WARNING: Wallet already exists. Do you want to back it up? [y/n] (or type '/q' to exit the script): ", backup)

            if perform_backup is None:
                return
        
        if perform_backup:
            # Construct the backup filename
            base_filename = os.path.basename(filename)
            backup_name, _ = os.path.splitext(base_filename)
            backup_path = os.path.join("./wallets/wallet_backups", f"{backup_name}_backup_{datetime.datetime.fromtimestamp(int(time.time())).strftime('%Y-%m-%d_%H-%M-%S')}") + ".json"
            try:
                # Create the backup
                shutil.copy(filename, backup_path)
                if from_gui:
                    callback_object.post_messagebox("Info", f"Backup created at {backup_path}")
                print(f"Backup created at {backup_path}\n")
                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                return True

            except Exception as e:
                if from_gui:
                    callback_object.post_messagebox("Error", f"Could not create backup. Please see console log.")
                logging.error(f" Could not create backup: {e}\n")
                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                return
        else:            
            if not disable_warning:
                

                if from_gui:
                    perform_overwrite = callback_object.post_confirmation_prompt('Overwrite Wallet', 'You have chosen not to back up the existing wallet.\n\nProceeding will OVERWRITE the existing wallet. Do you want to Continue?')
                else:
                    if not backup:
                        print()
                    logging.critical("You have chosen not to back up the existing wallet.")
                    perform_overwrite = UserPrompts.confirmation_prompt("Proceeding will OVERWRITE the existing wallet. Do you want to Continue? [y/n] (or type '/q' to exit the script): ")
                    if perform_overwrite is None:
                        return
            else:
                perform_overwrite = True
            
            
            if perform_overwrite:
                # Print messages based on the CLI boolean values
                if disable_warning:
                    if backup == "n":
                        print("Wallet not backed up.")
                    print("Overwrite warning disabled.")

                if password and encrypt:
                    print("Overwrite password provided.")
                    # Verify the password and HMAC to prevent brute force
                    password_verified, hmac_verified, _ = verification_util.Verification.verify_password_and_hmac(data, password, base64.b64decode(data["wallet_data"]["hmac_salt"]), base64.b64decode(data["wallet_data"]["verification_salt"]), deterministic)
                    
                    # Based on password verification, update or reset the number of failed attempts
                    data = data_manipulation_util.DataManipulation.update_or_reset_attempts(data, filename, base64.b64decode(data["wallet_data"]["hmac_salt"]), password_verified, deterministic)
                    data_manipulation_util.DataManipulation._save_data(filename,data)
                    
                    # Check if there is still wallet data verify the password and HMAC again
                    if data:
                        password_verified, hmac_verified, _ = verification_util.Verification.verify_password_and_hmac(data, password, base64.b64decode(data["wallet_data"]["hmac_salt"]), base64.b64decode(data["wallet_data"]["verification_salt"]), deterministic)
                    # Handle error if the password and HMAC verification failed
                    if not (password_verified and hmac_verified):
                        logging.error("Authentication failed or wallet data is corrupted.")

                # If the wallet is encrypted and the password and hmac have not yet been varified then enter while loop
                if encrypt and not (password_verified and hmac_verified) and data:
                    
                    while True:
                        if from_gui:
                            password_input = callback_object.post_password_dialog_with_confirmation(title='Authentication Required', msg='Wallet is encrypted. Authentication is required to overwrite it.\n')
                            if password_input is None:
                                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                                return
                        else:
                            print()
                            # Prompt user for password
                            password_input = UserPrompts.get_password(password=password if password and (password_verified and hmac_verified) else None)
                        
                        # Verify the password and HMAC
                        password_verified, hmac_verified, _ = verification_util.Verification.verify_password_and_hmac(data, password_input, base64.b64decode(data["wallet_data"]["hmac_salt"]), base64.b64decode(data["wallet_data"]["verification_salt"]), deterministic)
                        
                        # Based on password verification, update or reset the number of failed attempts
                        data, attempts_msg, warning_msg, warning_type, data_erased_msg = data_manipulation_util.DataManipulation.update_or_reset_attempts(data, filename, base64.b64decode(data["wallet_data"]["hmac_salt"]), password_verified, deterministic, from_gui=from_gui, callback_object=callback_object)
                        data_manipulation_util.DataManipulation._save_data(filename, data)
                        
                        # If wallet data has not erased yet verify the password and HMAC again
                        if data:
                            password_verified, hmac_verified, _ = verification_util.Verification.verify_password_and_hmac(data, password_input, base64.b64decode(data["wallet_data"]["hmac_salt"]), base64.b64decode(data["wallet_data"]["verification_salt"]), deterministic)
                        
                        # Handle error if the password and HMAC verification failed
                        if data and not (password_verified and hmac_verified):
                            UserPrompts.handle_auth_error_messages(data, attempts_msg, warning_msg, warning_type, data_erased_msg, from_gui, callback_object)

                        # Handle error if wallet data was erased then continue
                        elif not data:
                            UserPrompts.handle_auth_error_messages(data, attempts_msg, warning_msg, warning_type, data_erased_msg, from_gui, callback_object)
                            break                        
                        # If the password and HMAC verification passed then continue
                        else:
                            break

                # Check data was not erased due to failed password attempts 
                if data:
                    if not from_gui:
                        print()
                    # Call wait_for_input and allow up to 5 seconds for the user to cancel overwrite operation
                    if not UserPrompts.wait_for_input(timeout=10, from_gui=from_gui, callback_object=callback_object):
                        if from_gui:
                            callback_object.root.stored_data.ask_bool_result = None
                            #callback_object.root.wallet_thread_manager.dialog_event.wait()
                        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                        return
                    # If no input is recieved within 5 seconds then continue
                    else:
                        if from_gui:
                            callback_object.root.stored_data.ask_bool_result = None
                            #callback_object.root.wallet_thread_manager.dialog_event.wait()
                        else:
                            print()
                        try:
                            # Overwrite wallet with empty data
                            data_manipulation_util.DataManipulation.delete_wallet(filename, data, from_gui=from_gui, callback_object=callback_object)
                            if from_gui:
                                callback_object.post_messagebox("Info", "Wallet data has been erased.")
                                if callback_object.root.progress_bar["value"] != 0:
                                    callback_object.root.progress_bar.config(maximum=0, value=0)
                            else:
                                print("Wallet data has been erased.\n")
                            time.sleep(0.5)
                        except Exception as e:
                            data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                            return
                        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                        return True
                else:
                    data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                    return True
            else:
                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                return
    

    @staticmethod
    def handle_auth_error_messages(data, attempts_msg, warning_msg, warning_type, data_erased_msg, from_gui=False, callback_object=None):
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
            print()
            gui_error_msg = f"{attempts_msg+new_line if attempts_msg else ''}{'WARNING: ' if warning_type == '1' else ''}{'CRITICAL: ' if warning_type == '2' else ''}{warning_msg+new_line if warning_msg else ''}{data_erased_msg+new_line if data_erased_msg else ''}{auth_error_msg}"
            callback_object.post_messagebox("Error", gui_error_msg)


    @staticmethod
    def handle_2fa_validation(data, totp_code=None, from_gui=False, callback_object=None):
        """
        Overview:
        Handles Two-Factor Authentication (2FA) validation.

        Arguments:
        - data (dict): Data used for 2FA.
        - totp_code (str, optional): Time-based One-Time Password (TOTP) code.

        Returns:
        - dict: A dictionary containing validation results and TOTP secret, or False if validation fails.
        """

        # Loop until the user provides the correct Two-Factor Authentication code or decides to exit
        while True:
            # Check if a TOTP code was already provided
            if not totp_code:
                # Get TOTP code from user input
                if not from_gui:
                    totp_code = input("Please enter the Two-Factor Authentication code from your authenticator app (or type '/q' to exit the script): ")
                else:                    
                    totp_code = callback_object.post_ask_string("2FA Required","Two-Factor Authentication is required.\nPlease enter the 6-digit Two-Factor Authentication code from your authenticator app:", modal=False)
                    if totp_code == None:
                        return False
                # Exit if the user chooses to quit
                if not from_gui and totp_code.lower() == '/q':
                    print("User exited before providing a valid Two-Factor Authentication code.\n")       
                    data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                    return False
                # Check if the totp_code is provided
                if not totp_code:
                    logging.error("No Two-Factor Authentication code provided. Please enter a valid Two-Factor Authentication code.\n")
                    if from_gui:
                        callback_object.post_messagebox("Error", "No Two-Factor Authentication code provided. Please enter a valid Two-Factor Authentication code.", modal=False)
                    continue
                # Validate that the TOTP code is a 6-digit integer
                try:
                    int(totp_code)
                    if len(totp_code) != 6:
                        logging.error("Two-Factor Authentication code should contain 6 digits. Please try again.\n")
                        if from_gui:
                            callback_object.post_messagebox("Error", "Two-Factor Authentication code should contain 6 digits. Please try again.", modal=False)
                        totp_code = None
                        continue
                except ValueError:
                    logging.error("Two-Factor Authentication code should be an integer. Please try again.\n")
                    if from_gui:
                        callback_object.post_messagebox("Error", "Two-Factor Authentication code should be an integer. Please try again.", modal=False)
                    totp_code = None
                    continue
            # Validate the TOTP code using utility method
            if verification_util.Verification.validate_totp_code(data, totp_code):
                result = {"valid": True, "totp_secret": data}
                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not result])
                return result
            else:
                logging.error("Authentication failed. Please try again.\n")
                if from_gui:
                    callback_object.post_messagebox("Error", "Authentication failed. Please try again.", modal=False)
                totp_code = None
                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])