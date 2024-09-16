import tkinter as tk
from tkinter import ttk

class AutocompleteCombobox(ttk.Combobox):
    """
    Enhanced ttk.Combobox with autocompletion feature. This combobox suggests and
    auto-fills options from the provided list based on the user's typing.

    Attributes:
        _completion_list (list): List of values used for autocompletion.
        _typed (str): Text that has been manually typed by the user.
        _hits (list): List of autocompletion hits based on the current typed text.
    """

    def __init__(self, master=None, completevalues=None, **kwargs):
        """
        Initialize the AutocompleteCombobox.

        :param master: The parent widget.
        :param completevalues: A list of values for autocompletion.
        :param kwargs: Additional keyword arguments for ttk.Combobox.
        """
        super().__init__(master, values=completevalues, **kwargs)  # Initialize the parent Combobox class
        self._completion_list = completevalues  # Store the provided list of autocomplete values
        #self.set_completion_list(completevalues)  # Set and sort the completion list
        self.bind('<KeyRelease>', self.handle_keyrelease)  # Bind key release event for typing interaction
        #self.bind("<FocusOut>", self.on_focus_out)  # Bind focus-out event to handle loss of focus
        self._register_autocomplete_function()  # Enhance dropdown navigation via Tcl script
        self.var = tk.StringVar()  # StringVar to manage the text value of the combobox
        self.configure(textvariable=self.var)  # Configure the combobox to use StringVar
        self._typed = ''  # Track the text manually typed by the user

        # get the current bind tags
        bindtags = list(self.bindtags())
        # add our custom bind tag before the Canvas bind tag
        index = bindtags.index("TCombobox")
        bindtags.insert(index, "AutocompleteCombobox")

        # save the bind tags back to the widget
        self.bindtags(tuple(bindtags))



    def set_completion_list(self, completion_list):
        """
        Set and sort the completion list for the combobox. This list is used to
        suggest autocompletion values based on user input.

        :param completion_list: A list of values for autocompletion.
        """
        self._completion_list = sorted(completion_list)  # Sort the list for consistent autocomplete behavior

    def _register_autocomplete_function(self):
        """
        Registers a Tcl script to enhance the navigation within the dropdown list
        of the combobox.
        """
        # Tcl script for improved keyboard navigation in the dropdown
        self.tk.eval("""
            proc ComboListKeyPressed {w key} {
                if {[string length $key] > 1 && [string tolower $key] != $key} {
                    return
                }

                set cb [winfo parent [winfo toplevel $w]]
                set text [string map [list {[} {\[} {]} {\]}] $key]
                if {[string equal $text ""]} {
                    return
                }

                set values [$cb cget -values]
                set x [lsearch -glob -nocase $values $text*]
                if {$x < 0} {
                    return
                }

                set current [$w curselection]
                if {$current == $x && [string match -nocase $text* [lindex $values [expr {$x+1}]]]} {
                    incr x
                }

                $w selection clear 0 end
                $w selection set $x
                $w activate $x
                $w see $x
            }

            set popdown [ttk::combobox::PopdownWindow %s]
            bind $popdown.f.l <KeyPress> [list ComboListKeyPressed %%W %%K]
        """ % (self))
    
    def on_focus_out(self, event):
        """
        Handle the focus-out event. Resets the state of the combobox when it loses
        focus by clearing any autocompleted text and reverting to the last manually
        typed or selected text.

        :param event: The event object associated with the focus-out event.
        """
        self.set(self._typed)  # Reset text to manually typed text when focus is lost
        self['values'] = self._completion_list  # Reset the values in the dropdown list
    
    def handle_keyrelease(self, event):
        #print("handle_keyrelease")
        """
        Handle key release events to provide interactive autocompletion. Special keys
        like backspace, left, and right are handled to enhance the autocomplete interaction.

        :param event: The event object associated with the key release.
        """
        # Ignore specific keys that don't require action
        if event.keysym in ["Return", "Tab", "Up", "Down", "Escape"]:
            return
        
        # Get the current text from the combobox
        current_text = self.var.get()
        # Handle backspace key: remove preview while keeping typed text
        if event.keysym == "BackSpace":
            if len(current_text) > len(self._typed):
                self._typed = current_text
                
                self.set(self._typed)
                self.icursor(len(self._typed))

        # Handle left arrow key: acts like backspace when there's a preview
        elif event.keysym == "Left":
            if len(current_text) > len(self._typed) and self._hits:
                # Preserve the original case of the typed characters
                corrected_typed = self._typed
                preview_text = self._hits[0]
                for i, char in enumerate(corrected_typed):
                    if i < len(preview_text) and char.lower() == preview_text[i].lower():
                        corrected_typed = corrected_typed[:i] + preview_text[i] + corrected_typed[i+1:]
                self._typed = corrected_typed
                self.set(corrected_typed)
                self.icursor(len(corrected_typed))
            return       

        # Handle right arrow key: move cursor to the end if there's a preview
        elif event.keysym == "Right":
            if len(current_text) > len(self._typed):  
                self.icursor(tk.END) # Move cursor to the end if there are hits
            return
        else:
            if not event.keysym in ["Return", "Tab", "Up", "Down", "Escape", "Shift_R", "Shift_L"]:
                # Update typed text with the current text for any other key press
                self._typed = current_text
                self._update_autocomplete()

    def _update_autocomplete(self):
        #print("_update_autocomplete")
        """
        Update the autocomplete suggestions based on the current text input by the user.
        Filters the completion list for matches and updates the dropdown.
        """
        # Clear autocomplete if no text is typed
        if self._typed == '':
            self.set('')
            self['values'] = self._completion_list
            return

        # Filter the completion list based on the typed text
        self._hits = [v for v in self._completion_list if v.lower().startswith(self._typed.lower())]
        # Show preview if there are matching hits
        if self._hits:
            self._show_preview(self._typed, self._hits[0])
        else:
            self.set(self._typed)
            self['values'] = self._completion_list

    def _show_preview(self, typed, first_match):
        #print("_show_preview")
        """
        Show a preview of the first matching item in the dropdown, auto-filling the
        combobox while keeping the user-typed text intact. Provides a visual cue
        for the available autocompletion options.

        :param typed: The text typed by the user.
        :param first_match: The first matching item from the autocompletion list.
        """
        # Show the preview only if the typed text doesn't fully match the first hit
        if typed != first_match:
            self.set(first_match)
            self.icursor(len(typed))  # Place cursor at the end of the typed text
            self.select_range(len(typed), tk.END)  # Select the remaining part of the suggestion

"""Example Main Function"""
#def main():
#    root = tk.Tk()
#    root.title("Autocomplete Combobox")
#
#    label = ttk.Label(root, text="Select a value:")
#    label.pack(pady=10)
#
#    autocomplete_combobox = AutocompleteCombobox(root, completevalues=["Python", "Java", "C++", "JavaScript", "Ruby", "Perl", "C#", "Go"])
#    autocomplete_combobox.pack(pady=5)
#    root.mainloop()
#
#if __name__ == "__main__":
#    main()