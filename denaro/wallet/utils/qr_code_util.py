import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import CircleModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image, ImageDraw

import tkinter as tk
from tkinter import font

from data_manipulation_util import DataManipulation
from thread_manager import WalletThreadManager
from tkinter_utils.dialogs import Dialogs



class QRCodeUtils:  

    @staticmethod
    def generate_qr_with_logo(data, logo_path):
        """
        Overview: 
        Generates a custom QR code of the TOTP secret token with Denaro's logo in the center.
        The generated QR code is meant to be scanned by a Authenticator app. 

        Arguments:
        - data (str): The data to encode in the QR code.
        - logo_path (str): The path to the logo image file.
        
        Returns:
        - PIL.Image: The generated QR code image.
        """
        # Initialize QR Code with high error correction
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)  
        qr.add_data(data)  
        
        # Create a styled QR code image
        qr_img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=CircleModuleDrawer(radius_ratio=1.5),
            color_mask=SolidFillColorMask(back_color=(255, 255, 255))
        )  
        
        # Define color palette for gradient
        palette = [(51, 76, 154), (51, 76, 154), (14, 117, 165),
                   (83, 134, 162), (83, 134, 162), (14, 117, 165), (51, 76, 154), (51, 76, 154)]
        
        # Apply gradient based on the color pallette
        gradient_img = Image.new("RGB", qr_img.size, (255, 255, 255))  
        gradient_img = QRCodeUtils.generate_qr_gradient(gradient_img, palette)  
        
        # Create a mask for the gradient
        mask = qr_img.convert("L")  
        threshold = 200  
        mask = mask.point(lambda p: p < threshold and 255)  
        
        # Apply gradient to the QR code
        qr_img = Image.composite(gradient_img, qr_img, mask)  
        
        # Load, resize and place the logo
        logo_img = Image.open(logo_path)
        basewidth = min(qr_img.size[0] // 4, logo_img.size[0])  
        wpercent = (basewidth / float(logo_img.size[0]))  
        hsize = int((float(logo_img.size[1]) * float(wpercent)))  
        logo_img = logo_img.resize((basewidth, hsize))  
        
        # Calculate logo position
        logo_pos = ((qr_img.size[0] - logo_img.size[0]) //
                    2, (qr_img.size[1] - logo_img.size[1]) // 2)  
        
        # Paste the logo onto the QR code
        qr_img.paste(logo_img, logo_pos, logo_img)  
        
        # Return the final QR code image with the logo
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not qr_img])
        return qr_img  

    @staticmethod
    def generate_qr_gradient(image, palette):
        """
        Overview: Generates a gradient image based on a color palette.

        Arguments:
        - image (PIL.Image): The image to apply the gradient on.
        - palette (list): List of RGB tuples for the gradient.
        
        Returns:
        - PIL.Image: The image with gradient applied.
        """
        # Initialize the drawing object
        draw = ImageDraw.Draw(image)  
        
        # Get image dimensions
        width, height = image.size  
        
        # Calculate the last index of the palette
        max_index = len(palette) - 1  
        
        # Draw the gradient line by line
        for x in range(width):  
            blended_color = [
                int((palette[min(int(x / width * max_index), max_index - 1)][i] * (1 - (x / width * max_index - int(x / width * max_index))) +
                     palette[min(int(x / width * max_index) + 1, max_index)][i] * (x / width * max_index - int(x / width * max_index))))
                for i in range(3)
            ]
            draw.line([(x, 0), (x, height)], tuple(blended_color))  
        
        # Return the image with gradient applied
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not image])
        return image  
    

    #def show_qr_with_timer_tkinter(qr_image, filename, totp_secret):
    #    """
    #    Overview: Displays the QR code in a tkinter window with a timer.
    #    
    #    Arguments:
    #    - qr_image (PIL.Image): The QR code image to display.
    #    - filename (str): The filename for the caption.
    #    - totp_secret (str): The TOTP secret to display.
    #    
    #    Returns: None
    #    """
    #    root = tk.Tk()
    #    #app = QRCodeViewer(root, qr_image, filename, totp_secret)
    #    root.mainloop()

class _2FA_QR_Dialog():
    def __init__(self, qr_img, filename, totp_secret, from_gui=False, callback_object=None, modal=True):
        """
        Initializes the 2FA QR dialog. It can either be managed by an
        external GUI or run its own threaded process for terminal-based execution.
        """
        # --- Data for the QR Dialog ---
        self.qr_img = qr_img
        self.filename = filename
        self.totp_secret = totp_secret
        self.callback_object = callback_object
        self.from_gui = from_gui

        # --- State variables for the dialog's lifecycle ---
        self.countdown = 60
        self.reveal_secret = False
        self.close_window = False
        self.is_closing = False

        # --- References that will be populated ---
        self.dialog_instance = None
        self.tk_image = None
        self._timer_id = None
        self.context_menu = None
        self.data_manipulation_util = DataManipulation

        self.modal = modal

        # --- DUAL MODE LOGIC ---
        if self.from_gui:
            pass
        else:
            # If not from the GUI (terminal mode), set up and run its own
            # threaded dialog process.
            self.wallet_thread_manager = WalletThreadManager(self)
            self.dialogs = Dialogs(self)
            self.callbacks = Callbacks(self) # A simple Callbacks class for non-GUI mode
            self.callbacks.post_2FA_QR_dialog(modal=modal)


# A simple Callbacks class for non-GUI mode.
class Callbacks:
    def __init__(self, root):
        self.root = root

    def post_2FA_QR_dialog(self, modal=True):
        self.root.wallet_thread_manager.request_queue.put(
            lambda: self.root.dialogs.show_2FA_QR_dialog(
                qr_window_data=self.root, # In this context, self.root IS the data object
                from_gui=False, modal=modal
            )
        )