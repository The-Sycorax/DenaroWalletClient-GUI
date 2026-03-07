import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    CircleModuleDrawer,
    SquareModuleDrawer,
    RoundedModuleDrawer,
    GappedSquareModuleDrawer,
    VerticalBarsDrawer,
    HorizontalBarsDrawer
)
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image, ImageDraw

import tkinter as tk
from tkinter import font

from data_manipulation_util import DataManipulation
from thread_manager import WalletThreadManager
from tkinter_utils.dialogs import Dialogs



class QRCodeUtils:  

    @staticmethod
    def get_module_drawer(drawer_type, **kwargs):
        """
        Overview:
        Returns the appropriate module drawer based on the drawer type.
        
        Arguments:
        - drawer_type (str): Type of module drawer ('square', 'circle', 'rounded', 'gapped', 'vertical', 'horizontal')
        - **kwargs: Additional parameters for specific drawers (e.g., radius_ratio for circle)
        
        Returns:
        - Module drawer instance
        """
        drawer_map = {
            'square': SquareModuleDrawer,
            'circle': CircleModuleDrawer,
            'rounded': RoundedModuleDrawer,
            'gapped': GappedSquareModuleDrawer,
            'vertical': VerticalBarsDrawer,
            'horizontal': HorizontalBarsDrawer
        }
        
        drawer_class = drawer_map.get(drawer_type, CircleModuleDrawer)
        
        # Set default parameters for specific drawers
        if drawer_type == 'circle':
            kwargs.setdefault('radius_ratio', 1.5)
        elif drawer_type == 'rounded':
            kwargs.setdefault('radius_ratio', 0.5)
        
        return drawer_class(**kwargs)
    
    @staticmethod
    def get_color_palette(color_style):
        """
        Overview:
        Returns a color palette based on the color style.
        
        Arguments:
        - color_style (str): Color style ('gradient_blue', 'gradient_purple', 'gradient_green', 'black', 'blue', 'red', 'green', 'purple')
        
        Returns:
        - list: List of RGB tuples for the color palette
        """
        palettes = {
            'gradient_blue': [(51, 76, 154), (51, 76, 154),
                             (14, 117, 165), (83, 134, 162),
                             (83, 134, 162), (14, 117, 165),
                             (51, 76, 154), (51, 76, 154)],
            'gradient_purple': [(75, 0, 130), (75, 0, 130),
                               (138, 43, 226), (186, 85, 211),
                               (186, 85, 211), (138, 43, 226),
                               (75, 0, 130), (75, 0, 130)],
            'gradient_green': [(0, 100, 0), (0, 100, 0),
                              (34, 139, 34), (50, 205, 50),
                              (50, 205, 50), (34, 139, 34),
                              (0, 100, 0), (0, 100, 0)],
            'black': [(0, 0, 0)],
            'blue': [(0, 0, 255)],
            'red': [(255, 0, 0)],
            'green': [(0, 128, 0)],
            'purple': [(128, 0, 128)]
        }
        return palettes.get(color_style, palettes['gradient_blue'])
    
    @staticmethod
    def generate_qr(data, module_drawer_type='circle', color_style='gradient_blue'):
        """
        Overview: 
        Generates a custom styled QR code with configurable module drawer and colors.
        
        Arguments:
        - data (str): The data to encode in the QR code.
        - module_drawer_type (str): Type of module drawer ('square', 'circle', 'rounded', 'gapped', 'vertical', 'horizontal')
        - color_style (str): Color style ('gradient_blue', 'gradient_purple', 'gradient_green', 'black', 'blue', 'red', 'green', 'purple')
        
        Returns:
        - PIL.Image: The generated QR code image with styling.
        """
        # Initialize QR Code with high error correction and no border (quiet zone)
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=0)  
        qr.add_data(data)  
        
        # Get the module drawer
        module_drawer = QRCodeUtils.get_module_drawer(module_drawer_type)
        
        # Create a styled QR code image
        qr_img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=module_drawer,
            color_mask=SolidFillColorMask(back_color=(255, 255, 255))
        )  
        
        # Get color palette
        palette = QRCodeUtils.get_color_palette(color_style)
        
        # If single color (not gradient), create solid color image
        if len(palette) == 1:
            # For solid colors, directly modify the QR code
            qr_array = qr_img.load()
            width, height = qr_img.size
            color = palette[0]
            
            for x in range(width):
                for y in range(height):
                    pixel = qr_array[x, y]
                    # If pixel is not white (is part of QR code), replace with chosen color
                    if pixel != (255, 255, 255):
                        qr_array[x, y] = color
        else:
            # Apply gradient based on the color palette
            gradient_img = Image.new("RGB", qr_img.size, (255, 255, 255))  
            gradient_img = QRCodeUtils.generate_qr_gradient(gradient_img, palette)  
            
            # Create a mask for the gradient
            mask = qr_img.convert("L")  
            threshold = 200  
            mask = mask.point(lambda p: p < threshold and 255)  
            
            # Apply gradient to the QR code
            qr_img = Image.composite(gradient_img, qr_img, mask)
        
        # Return the styled QR code image
        DataManipulation.secure_delete([var for var in locals().values() if var is not None and var is not qr_img])
        return qr_img

    @staticmethod
    def add_logo_to_qr(qr_img, logo_path):
        """
        Overview:
        Adds a logo to the center of a QR code image.
        
        Arguments:
        - qr_img (PIL.Image): The QR code image to add the logo to.
        - logo_path (str): The path to the logo image file.
        
        Returns:
        - PIL.Image: The QR code image with logo added.
        """
        if not logo_path:
            return qr_img
        
        # Load, resize and place the logo
        logo_img = Image.open(logo_path)
        basewidth = min(qr_img.size[0] // 4, logo_img.size[0])  
        wpercent = (basewidth / float(logo_img.size[0]))  
        hsize = int((float(logo_img.size[1]) * float(wpercent)))  
        logo_img = logo_img.resize((basewidth, hsize))  
        
        # Calculate logo position and center it in the QR code
        logo_pos = ((qr_img.size[0] - logo_img.size[0]) // 2, (qr_img.size[1] - logo_img.size[1]) // 2)
        
        # Paste the logo onto the QR code
        qr_img.paste(logo_img, logo_pos, logo_img)
        
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