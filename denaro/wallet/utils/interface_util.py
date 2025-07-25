import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
import pygame.freetype
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



close_qr_window = False

is_windows = os.name == 'nt'

if is_windows:
    import msvcrt
else:
    import termios, fcntl

# QRCode utility class


    @staticmethod
    def show_qr_with_timer(qr_image, filename, totp_secret):
        """
        Overview: Displays the QR code in a window with a timer.
        
        Arguments:
        - qr_image (PIL.Image): The QR code image to display.
        - filename (str): The filename for the caption.
        - totp_secret (str): The TOTP secret to display.
        
        Returns: None
        """
        # Initialize pygame
        global close_qr_window  
        close_qr_window = False  
        pygame.init()  
        
        # Set the initial dimensions of the window
        size = 500  
        screen = pygame.display.set_mode((size, size), pygame.RESIZABLE)  
        pygame.display.set_caption(f'2FA QR Code for {filename}')  
        
        # Initialize timer and clock
        countdown = 60  
        clock = pygame.time.Clock()  
        
        # Define the activation message
        activation_message = (
            "To enable Two-Factor Authentication (2FA) for this wallet, scan the QR code with an authenticator app,"
            " then provide the one-time code in the terminal.")  
        reveal_secret = False  
        
        # Define constants for resizing and text
        BASE_SIZE = 500  
        BASE_QR_WIDTH = BASE_SIZE - 125  
        BASE_FONT_SIZE = 24  
        BASE_SMALL_FONT_SIZE = 22  
        
        # Initialize time variables
        time_elapsed = 0 # Used to track time elapsed for countdown
        resize_delay = 0 # Used to introduce a delay for resizing the window

        # Main loop for displaying the window
        while countdown > 0 and not close_qr_window:
            dt = clock.tick(60) / 1000.0 # Delta time in seconds
            time_elapsed += dt # Increment elapsed time by delta time

            # If a second or more has passed reset elapsed time
            if time_elapsed >= 1:  
                countdown -= 1  
                time_elapsed = 0
            
            # Fill the screen with a white background
            screen.fill((255, 255, 255)) 

            # For loop for event handling
            for event in pygame.event.get():
                # Fill the screen again within the for loop
                screen.fill((255, 255, 255))
                # Capture window close event
                if event.type == pygame.QUIT:  
                    pygame.quit()
                    data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                    return
                # Capture window resize event
                elif event.type == pygame.VIDEORESIZE:  
                    resize_delay = 0.5
                # Ensure button_rect maintains the correct size
                button_rect = pygame.Rect(size - int(220 * size / BASE_SIZE), int(10 * size / BASE_SIZE), int(200 * size / BASE_SIZE), int(25 * size / BASE_SIZE))  
                # Capture mouse click event
                if event.type == pygame.MOUSEBUTTONDOWN:  
                    if button_rect.collidepoint(event.pos):  
                        reveal_secret = not reveal_secret

            # Handle window resizing
            if resize_delay > 0:  
                resize_delay -= dt  
                if resize_delay <= 0:  
                    size = min(pygame.display.get_window_size())  
                    screen = pygame.display.set_mode((size, size), pygame.RESIZABLE)  
                    resize_delay = 0  
            
            # Calculate scale factor for resizing
            scale_factor = size / BASE_SIZE  
            
            # Resize and display the QR code image
            qr_width = int(BASE_QR_WIDTH * scale_factor)  
            resized_surface = pygame.transform.scale(pygame.image.frombuffer(qr_image.convert("RGB").tobytes(), qr_image.size, 'RGB'), (qr_width, qr_width))  
            screen.blit(resized_surface, ((size - qr_width) // 2, int(40 * scale_factor)))  
            
            # Draw and display the "Reveal 2FA Token" button
            button_color = (100, 200, 100)  
            pygame.draw.rect(screen, button_color, button_rect)  
            font_button = pygame.font.SysFont(None, int(BASE_FONT_SIZE * scale_factor))  
            btn_text = "Reveal 2FA Token" if not reveal_secret else "Hide 2FA Token"  
            text_surf = font_button.render(btn_text, True, (0, 0, 0))  
            text_rect = text_surf.get_rect(center=button_rect.center)  
            screen.blit(text_surf, text_rect)  
            
            # Display the countdown timer
            font = pygame.font.SysFont(None, int(BASE_FONT_SIZE * scale_factor))  
            countdown_text = font.render(f"Closing window in: {countdown}s", True, (255, 0, 0))  
            screen.blit(countdown_text, (int(10 * scale_factor), int(10 * scale_factor)))  
            
            # Display the TOTP secret if the "Reveal" button was clicked
            font_secret = pygame.font.SysFont(None, int(BASE_FONT_SIZE * scale_factor))  
            secret_text_surf = font_secret.render(totp_secret, True, (0, 0, 255))  
            secret_text_rect = secret_text_surf.get_rect(center=(size // 2, qr_width + int(35 * scale_factor)))  
            if reveal_secret:  
                screen.blit(secret_text_surf, secret_text_rect)  
            
            # Display the activation message
            activation_message_start_y = secret_text_rect.bottom + int(20 * scale_factor)  
            font_small = pygame.font.SysFont(None, int(BASE_SMALL_FONT_SIZE * scale_factor))  
            wrapped_text = QRCodeUtils.wrap_text(
                activation_message, font_small, size - int(40 * scale_factor))  
            for idx, line in enumerate(wrapped_text):  
                text_line = font_small.render(line, True, (50, 50, 50))  
                text_line_pos = text_line.get_rect(center=(size // 2, activation_message_start_y + idx * int(25 * scale_factor)))  
                screen.blit(text_line, text_line_pos)  
            
            # Update the display
            pygame.display.flip()

        # Quit pygame when the countdown reaches zero or the window is closed
        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
        pygame.quit()

    @staticmethod
    def wrap_text(text, font, max_width):
        """
        Overview: Wraps text to fit within a given width.
        
        Arguments:
        - text (str): The text to wrap.
        - font (pygame.font.Font): The font used for measuring the text size.
        - max_width (int): The maximum width for the text.

        Returns:
        - list: The wrapped lines of text.
        """
        # Split text into words
        words = text.split(' ')          
        # Initialize list for wrapped lines
        lines = []        
        # Create lines with words that fit within max_width
        while words:  
            line = ''  
            while words and font.size(line + ' ' + words[0])[0] <= max_width:  
                line = (line + ' ' + words.pop(0)).strip()  
            lines.append(line)  
        # Return the wrapped lines
        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not lines])
        return lines 
    
    def close_qr_window(value):
        global close_qr_window
        close_qr_window = value

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
    def wait_for_input(timeout:int, from_gui=False, callback_object=None):
        """
        Overview:
        Waits for user input for a specified time before proceeding.

        Arguments:
        - timeout (int): The number of seconds to wait for user input.

        Returns:
        - bool: True if no input is received within the timeout, False otherwise.
        """
        try:
            # Initialize global variable
            global user_input_received
            user_input_received = False

            

            # Start a new thread to listen for user input
            if from_gui:
                callback_object.post_input_listener_dialog()
            else:
                # Create a threading event to stop listening for input
                stop_event = threading.Event()
                user_input_thread = threading.Thread(target=UserPrompts.user_input_listener, args=(stop_event,))
                user_input_thread.start()

            # Initialize timing variables
            start_time = time.time()
            last_second_passed = None

            # Loop until timeout
            while time.time() - start_time < timeout:
                user_input_received = callback_object.root.stored_data.ask_bool_result
        
                # Check for user input
                if user_input_received:

                    if not from_gui:
                        print(f"\rExisting wallet data will be erased in {time_remaining} seconds. Press any key to cancel operation... ")
                        print('Operation canceled.')
                        stop_event.set()
                    return False                
                # Countdown logic
                seconds_passed = int(time.time() - start_time)
                if last_second_passed != seconds_passed:
                    last_second_passed = seconds_passed
                    time_remaining = timeout - seconds_passed
                    if from_gui:
                        callback_object.root.stored_data.input_listener_time_remaining = time_remaining
                    else:
                        print(f"\rExisting wallet data will be erased in {time_remaining} seconds. Press any key to cancel operation...", end='')
                time.sleep(0.1)
            
            callback_object.root.stored_data.input_listener_time_remaining = 0
            
            # Stop listening for input
            if not from_gui:
                stop_event.set()
            return True
        
        # Handle exit on keyboard interrupt
        except KeyboardInterrupt:
            print(f"\rExisting wallet data will be erased in {time_remaining} seconds. Press any key to cancel operation...    ")
            print('Operation canceled. Process terminated by user.')
            stop_event.set()
            sys.exit(1)  

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
            perform_backup = callback_object.post_confirmation_prompt('Backup Prompt', 'Wallet file already exists. Do you want to back it up?')
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
                    perform_overwrite = callback_object.post_confirmation_prompt('Overwrite Prompt', 'You have chosen not to back up the existing wallet.\n\nProceeding will OVERWRITE the existing wallet. Do you want to Continue?')
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
                            callback_object.root.wallet_thread_manager.dialog_event.wait()
                        data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])
                        return
                    # If no input is recieved within 5 seconds then continue
                    else:
                        if from_gui:
                            callback_object.root.stored_data.ask_bool_result = None
                            callback_object.root.wallet_thread_manager.dialog_event.wait()
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
                    totp_code = callback_object.post_ask_string("2FA Required","Two-Factor Authentication is required.\nPlease enter the 6-digit Two-Factor Authentication code from your authenticator app:")
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
                        callback_object.post_messagebox("Error", "No Two-Factor Authentication code provided. Please enter a valid Two-Factor Authentication code.")
                    continue
                # Validate that the TOTP code is a 6-digit integer
                try:
                    int(totp_code)
                    if len(totp_code) != 6:
                        logging.error("Two-Factor Authentication code should contain 6 digits. Please try again.\n")
                        if from_gui:
                            callback_object.post_messagebox("Error", "Two-Factor Authentication code should contain 6 digits. Please try again.")
                        totp_code = None
                        continue
                except ValueError:
                    logging.error("Two-Factor Authentication code should be an integer. Please try again.\n")
                    if from_gui:
                        callback_object.post_messagebox("Error", "Two-Factor Authentication code should be an integer. Please try again.")
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
                    callback_object.post_messagebox("Error", "Authentication failed. Please try again.")
                totp_code = None
                data_manipulation_util.DataManipulation.secure_delete([var for var in locals().values() if var is not None])