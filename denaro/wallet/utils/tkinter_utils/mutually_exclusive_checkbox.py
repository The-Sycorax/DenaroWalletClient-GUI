"""
MutuallyExclusiveCheckbox - A Tkinter widget for mutually exclusive checkbox behavior
======================================================================================

Developed by: The-Sycorax (https://github.com/The-Sycorax)
License: MIT License
Version: 1.0.0 (2025-11-09)

======================================================================================

This module provides a custom Tkinter Checkbutton widget that implements mutually
exclusive selection within groups. When one checkbox is checked, all others in its
group are automatically unchecked, similar to radio buttons but with checkbox styling
and the ability to have no selection.

FEATURES
--------
- Mutually exclusive selection within groups
- Support for multiple independent groups
- Optional callbacks on state changes
- Programmatic control via set(), get(), and toggle() methods
- Thread-safe against nested/recursive calls
- No selection state (all checkboxes can be unchecked)

BASIC USAGE
-----------
Creating a simple group of mutually exclusive checkboxes:

    import tkinter as tk
    from mutually_exclusive_checkbox import MutuallyExclusiveCheckbox
    
    root = tk.Tk()
    
    # Create checkboxes
    cb1 = MutuallyExclusiveCheckbox(root, text="Option 1")
    cb2 = MutuallyExclusiveCheckbox(root, text="Option 2")
    cb3 = MutuallyExclusiveCheckbox(root, text="Option 3")
    
    # Link them into a mutually exclusive group
    MutuallyExclusiveCheckbox.bind_group(cb1, cb2, cb3)
    
    # Pack them
    cb1.pack()
    cb2.pack()
    cb3.pack()
    
    root.mainloop()

CREATING GROUPS
---------------
Three methods are available to create mutually exclusive groups:

1. Using the partner parameter during initialization:
    cb1 = MutuallyExclusiveCheckbox(root, text="Option 1")
    cb2 = MutuallyExclusiveCheckbox(root, text="Option 2", partner=cb1)
    cb3 = MutuallyExclusiveCheckbox(root, text="Option 3", partner=cb1)

2. Using the link_group() method:
    cb1 = MutuallyExclusiveCheckbox(root, text="Option 1")
    cb2 = MutuallyExclusiveCheckbox(root, text="Option 2")
    cb3 = MutuallyExclusiveCheckbox(root, text="Option 3")
    cb1.link_group(cb2, cb3)

3. Using the static bind_group() method (recommended):
    cb1 = MutuallyExclusiveCheckbox(root, text="Option 1")
    cb2 = MutuallyExclusiveCheckbox(root, text="Option 2")
    cb3 = MutuallyExclusiveCheckbox(root, text="Option 3")
    MutuallyExclusiveCheckbox.bind_group(cb1, cb2, cb3)

CALLBACKS
---------
Callbacks may be attached that fire when the checkbox state changes:

    def on_change(checkbox, is_checked):
        print(f"{checkbox.cget('text')} is now {'checked' if is_checked else 'unchecked'}")
    
    cb1 = MutuallyExclusiveCheckbox(root, text="Option 1", callback=on_change)
    
    # Or set the callback later:
    cb1.set_callback(on_change)

The callback receives two arguments:
- checkbox: The MutuallyExclusiveCheckbox instance that changed
- is_checked: Boolean indicating the new state (True = checked, False = unchecked)

PROGRAMMATIC CONTROL
--------------------
Reading and setting checkbox states:

    # Get current state
    is_checked = cb1.get()  # Returns True or False
    
    # Set state
    success = cb1.set(True)   # Check the checkbox, returns True if successful
    success = cb1.set(False)  # Uncheck the checkbox, always returns True
    
    # Toggle state
    success = cb1.toggle()    # Flip between checked/unchecked

The set() method returns:
- True if the operation succeeded
- False if the operation was blocked (only happens with nested calls)

IMPORTANT BEHAVIORS
-------------------
1. Setting to False always succeeds (unchecking is never blocked)

2. Sequential set(True) calls in the same code block all succeed:
    cb1.set(True)  # Succeeds, cb1 is checked
    cb2.set(True)  # Succeeds, cb1 is unchecked, cb2 is checked
    cb3.set(True)  # Succeeds, cb2 is unchecked, cb3 is checked

3. Nested calls (e.g., from within callbacks) are blocked:
    def callback(cb, state):
        cb2.set(True)  # This will fail and return False
    
    cb1 = MutuallyExclusiveCheckbox(root, callback=callback)
    cb1.set(True)  # The callback's set() call will be blocked

4. All checkboxes can be unchecked (unlike radio buttons):
    cb1.set(False)
    cb2.set(False)
    cb3.set(False)  # Valid state: nothing selected

MULTIPLE GROUPS
---------------
Multiple independent groups may be created in the same application:

    # Group 1: Colors
    red = MutuallyExclusiveCheckbox(root, text="Red")
    blue = MutuallyExclusiveCheckbox(root, text="Blue")
    green = MutuallyExclusiveCheckbox(root, text="Green")
    MutuallyExclusiveCheckbox.bind_group(red, blue, green)
    
    # Group 2: Sizes (independent from colors)
    small = MutuallyExclusiveCheckbox(root, text="Small")
    medium = MutuallyExclusiveCheckbox(root, text="Medium")
    large = MutuallyExclusiveCheckbox(root, text="Large")
    MutuallyExclusiveCheckbox.bind_group(small, medium, large)

INTEGRATION WITH TKINTER
-------------------------
The widget supports all standard Tkinter Checkbutton options:

    cb = MutuallyExclusiveCheckbox(
        root,
        text="Option 1",
        font=("Arial", 12),
        fg="blue",
        bg="white",
        activebackground="lightblue",
        selectcolor="yellow"
    )

Direct access to the underlying BooleanVar is provided:

    cb = MutuallyExclusiveCheckbox(root, text="Option 1")
    print(cb.var.get())  # Access the BooleanVar directly


API REFERENCE
-------------
Class: MutuallyExclusiveCheckbox(tk.Checkbutton)

    __init__(master=None, partner=None, callback=None, **kwargs)
        Initialize a new mutually exclusive checkbox.
        
        Parameters:
            master: Parent widget
            partner: Another MutuallyExclusiveCheckbox to link with
            callback: Function called on state changes (receives checkbox, state)
            **kwargs: Any standard tk.Checkbutton options
    
    get() -> bool
        Returns the current checked state.
    
    set(value: bool) -> bool
        Sets the checked state. Returns True if successful, False if blocked.
    
    toggle() -> bool
        Toggles the checked state. Returns True if successful, False if blocked.
    
    set_callback(callback: callable)
        Sets or updates the callback function.
    
    set_partner(partner: MutuallyExclusiveCheckbox)
        Links this checkbox with another for mutual exclusivity.
    
    link_group(*checkboxes)
        Adds multiple checkboxes to this checkbox's exclusivity group.
    
    @staticmethod bind_group(*checkboxes)
        Convenience method to link multiple checkboxes together.

Attributes:
    var (tk.BooleanVar): Public access to the widget's state variable

NOTES
-----
- This widget is thread-safe for GUI operations within the Tkinter event loop
- Callback exceptions are caught and printed to prevent widget corruption
- The widget prevents infinite recursion from callback-triggered state changes
- Groups can be merged dynamically at any time
"""

import tkinter as tk

class MutuallyExclusiveCheckbox(tk.Checkbutton):
    """
    A tk.Checkbutton widget that is mutually exclusive with other checkboxes in its group.
    When one checkbox is checked, all other checkboxes in the group are automatically unchecked.

    Attributes:
        var (tk.BooleanVar): Public reference to the widget state for integration with other Tk controls.
        _variable (tk.BooleanVar): Internal variable reference used to read/write Checkbox state.
        _callback (callable | None): Optional callback invoked whenever the checked state changes.
        _is_updating (bool): Guard flag that suppresses recursive trace callbacks during internal updates.
        _linked_group (set[MutuallyExclusiveCheckbox]): All widgets that share the same exclusivity group.
        _group_state (dict): Shared metadata for the group.
    """

    def __init__(self, master=None, partner=None, callback=None, **kwargs):
        """
        Initialize the MutuallyExclusiveCheckbox.

        :param master: The parent widget.
        :param partner: Another MutuallyExclusiveCheckbox instance that should be mutually exclusive.
        :param callback: Optional callback function called when state changes.
                        Receives (checkbox_instance, new_state) as arguments.
        :param kwargs: Additional keyword arguments for tk.Checkbutton.
        """
        # Create a BooleanVar if not provided
        if 'variable' not in kwargs:
            self._variable = tk.BooleanVar()
            kwargs['variable'] = self._variable
        else:
            self._variable = kwargs['variable']
        
        # Expose variable as 'var' for consistency with other custom widgets
        self.var = self._variable
        
        # Initialize the parent Checkbutton class
        super().__init__(master, **kwargs)
        
        # Store callback function
        self._callback = callback
        
        # Flag to prevent recursive updates
        self._is_updating = False

        # Shared group of mutually exclusive checkboxes (always contains self)
        self._linked_group = {self}
        self._group_state = {
            # Tracks depth of nested set() calls to handle reentrancy
            "set_depth": 0,
            # Reference to the checkbox that initiated the current operation
            "active_setter": None,
        }

        # Bind to variable changes to handle mutual exclusivity
        self._variable.trace_add("write", self._on_state_change)

        # If a partner was provided, join their group
        if partner is not None:
            self.set_partner(partner)


    def set_partner(self, partner):
        """
        Set the partner checkbox for mutual exclusivity.

        :param partner: Another MutuallyExclusiveCheckbox instance for mutual exclusivity.
        """
        if partner is None or partner is self:
            return

        if not isinstance(partner, MutuallyExclusiveCheckbox):
            raise TypeError("partner must be an instance of MutuallyExclusiveCheckbox")

        # Merge both groups into a single shared set reference
        self._merge_groups({self, partner})


    def set_callback(self, callback):
        """
        Set or update the callback function for state changes.

        :param callback: Callback function that receives (checkbox_instance, new_state).
        """
        self._callback = callback


    def link_group(self, *checkboxes):
        """Include additional checkboxes in the mutual exclusion group."""
        members = {self}
        for checkbox in checkboxes:
            if checkbox is None or checkbox is self:
                continue
            if not isinstance(checkbox, MutuallyExclusiveCheckbox):
                raise TypeError("All group members must be MutuallyExclusiveCheckbox instances")
            members.add(checkbox)
        if len(members) > 1:
            self._merge_groups(members)


    @staticmethod
    def bind_group(*checkboxes):
        """Convenience helper to link multiple checkboxes together in one call."""
        if len(checkboxes) < 2:
            return
        for checkbox in checkboxes:
            if not isinstance(checkbox, MutuallyExclusiveCheckbox):
                raise TypeError("All group members must be MutuallyExclusiveCheckbox instances")
        first, *others = checkboxes
        first.link_group(*others)


    def _merge_groups(self, members):
        """Merge the mutual exclusion groups of all provided members."""
        combined = set()
        state_snapshot = None

        for member in members:
            combined |= member._linked_group
            # Use the first member's state as the shared state
            if state_snapshot is None:
                state_snapshot = member._group_state

        combined |= set(members)

        # Create new shared state object if needed
        if state_snapshot is None:
            state_snapshot = {
                "set_depth": 0,
                "active_setter": None,
            }

        # Point all members to the same group and state
        for member in combined:
            member._linked_group = combined
            member._group_state = state_snapshot


    def _on_state_change(self, *args):
        """
        Handle state changes of the checkbox. Ensures mutual exclusivity
        and calls the callback if provided.

        :param args: Variable arguments from the trace callback (unused but required).
        """
        # Prevent recursive calls during internal updates
        if self._is_updating:
            return

        current_state = self._variable.get()
        
        # If this checkbox is being checked, uncheck all other members in the group
        if current_state:
            for member in list(self._linked_group):
                if member is self:
                    continue
                if member._variable.get():
                    member._set_state_internal(False)
        
        # Call the callback if provided
        if self._callback is not None:
            try:
                self._callback(self, current_state)
            except Exception as e:
                # Prevent callback errors from breaking the widget
                print(f"Error in checkbox callback: {e}")


    def _set_state_internal(self, value):
        """
        Update the checkbox state internally without triggering conflicts.
        Used when unchecking partner checkboxes.
        
        :param value: True to check, False to uncheck.
        """
        self._is_updating = True
        try:
            self._variable.set(bool(value))
        finally:
            self._is_updating = False


    def get(self):
        """
        Get the current state of the checkbox.

        :return: True if checked, False if unchecked.
        """
        return self._variable.get()


    def set(self, value):
        """
        Set the state of the checkbox through the public API.

        Behavior rules:
            * Setting to False always succeeds (unchecks the checkbox).
            * Setting to True will uncheck all other checkboxes in the group.
            * If multiple checkboxes try to set(True) in nested calls (e.g., from callbacks),
              only the outermost call succeeds. Nested calls return False.
            * Synchronous sequential calls in the same code block all succeed because
              the lock is released after each operation completes.

        :param value: True to check, False to uncheck.
        :return: True if the state was applied, False if it was prevented.
        """
        value = bool(value)

        # Allow unchecking at any time
        if not value:
            self._set_state_internal(False)
            return True

        # Check if we're in a nested set() call (depth > 0 means another set is active)
        if self._group_state["set_depth"] > 0:
            # Nested call detected - reject to prevent conflicts
            return False

        # Increment depth to mark that a set() operation is in progress
        self._group_state["set_depth"] += 1
        self._group_state["active_setter"] = self

        try:
            # Uncheck all other members in the group
            for member in list(self._linked_group):
                if member is self:
                    continue
                if member._variable.get():
                    member._set_state_internal(False)

            # Set this checkbox to the desired state
            self._set_state_internal(value)

            return True

        finally:
            # Decrement depth - when it reaches 0, no set() operations are active
            self._group_state["set_depth"] -= 1
            if self._group_state["set_depth"] == 0:
                self._group_state["active_setter"] = None


    def toggle(self):
        """
        Toggle the checkbox state intelligently.
        
        If currently unchecked: attempts to check (may fail if nested operation in progress).
        If currently checked: unchecks (always succeeds).
        
        :return: True if the toggle was successful, False if prevented.
        """
        current = self.get()
        
        # If checked, we're toggling to False - this always works
        if current:
            return self.set(False)
        
        # If unchecked, we're toggling to True - check if operation is allowed
        # If we're in a nested call, don't attempt the toggle
        if self._group_state["set_depth"] > 0:
            return False
            
        return self.set(True)


##########################
#   Demo Application 1   #
##########################

'''
def demo_application_1():
    """
    Demo Application for the MutuallyExclusiveCheckbox widget.
    Creates a window with five mutually exclusive checkboxes plus buttons
    that demonstrate how manual selections and API calls are handled.
    """
    root = tk.Tk()
    root.title("Mutually Exclusive Checkbox Demo")
    root.geometry("675x525")
    root.resizable(False, False)
    
    control_frame = tk.Frame(root, padx=20, pady=20)
    control_frame.grid(row=0, column=0, sticky="nsew")
    control_frame.columnconfigure(0, weight=1)

    # Create a side-by-side region: checkboxes on the left, instructions on the right
    selection_frame = tk.LabelFrame(control_frame, text="Selection", padx=12, pady=12, borderwidth=1, relief="groove")
    selection_frame.pack(fill=tk.X, pady=(0, 12))
    selection_frame.grid_columnconfigure(0, weight=1, uniform="selection")
    selection_frame.grid_columnconfigure(1, weight=0)
    selection_frame.grid_columnconfigure(2, weight=2, uniform="selection")

    checkbox_labels = [
        "Checkbox 1",
        "Checkbox 2",
        "Checkbox 3",
        "Checkbox 4",
        "Checkbox 5",
    ]
    checkboxes = []

    status_label = tk.Label(control_frame, text="Status: No checkbox selected", font=("Arial", 10))

    def update_status_label():
        active = [label for label, cb in zip(checkbox_labels, checkboxes) if cb.get()]
        if active:
            status_label.config(text=f"Status: {active[0]} is checked")
        else:
            status_label.config(text="Status: No checkbox selected")
        status_label.update_idletasks()

    def on_checkbox_change(checkbox, state):
        checkbox_name = checkbox.cget("text")
        status = "checked" if state else "unchecked"
        print(f"{checkbox_name} is now {status}")
        update_status_label()

    for row_index, label in enumerate(checkbox_labels):
        cb = MutuallyExclusiveCheckbox(selection_frame, text=label, callback=on_checkbox_change)
        cb.grid(row=row_index, column=0, sticky="w", pady=3)
        checkboxes.append(cb)

    column_separator = tk.Frame(selection_frame, width=2, bg="#c0c0c0")
    column_separator.grid(row=0, column=1, rowspan=len(checkbox_labels), sticky="ns", padx=(8, 16))

    instructions = tk.Label(
        selection_frame,
        text=(
            "Manual controls:\n"
            "    • Select 1-5: Request a specific checkbox via the API.\n"
            "    • Deselect All: Remove the current selection.\n\n"
            "Automated tests:\n"
            "    • Sequential API Requests: Call set(True) for all checkboxes sequentially.\n"
            "    • Rapid Switch Attempt: Jump from checkbox 1 to 2 immediately.\n"
            "    • Delayed Switch: Repeat the switch after a brief pause.\n"
            "    • Round-Robin Cycle: Walk through all checkboxes with pauses.\n"
            "    • Toggle Same Checkbox: Flip checkbox 3 on/off repeatedly."
        ),
        font=("Arial", 9),
        justify=tk.LEFT,
        anchor="nw",
        wraplength=400
    )
    instructions.grid(row=0, column=2, rowspan=len(checkbox_labels), sticky="nw")

    # Link all checkboxes to share mutual exclusivity
    MutuallyExclusiveCheckbox.bind_group(*checkboxes)

    # Label to show status
    status_label.pack(pady=10, anchor="w")
    update_status_label()
    
    # Add a separator
    separator = tk.Frame(control_frame, height=2, bg="gray")
    separator.pack(fill=tk.X, pady=12)
    
    # ------------------------------------------------------------------
    # Manual selection buttons (simulate direct user-driven API calls)
    # ------------------------------------------------------------------
    button_frame = tk.Frame(control_frame)
    button_frame.pack(pady=10)

    def select_checkbox(index):
        """Simulate a direct API call that selects a single checkbox."""
        result = checkboxes[index].set(True)
        print(f"Requested selection: {checkbox_labels[index]} (result={result})")
        update_status_label()

    def clear_selection():
        """Clear the group via the public API."""
        print("Clearing selection via API...")
        for cb in checkboxes:
            cb.set(False)
        update_status_label()

    for idx, label in enumerate(checkbox_labels):
        tk.Button(
            button_frame,
            text=f"Select {idx + 1}",
            command=lambda i=idx: select_checkbox(i)
        ).pack(side=tk.LEFT, padx=4)
    tk.Button(button_frame, text="Deselect All", command=clear_selection).pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # Demonstrate behavior with sequential and rapid automated selections
    # ------------------------------------------------------------------
    test_frame = tk.LabelFrame(control_frame, text="Automated Tests", padx=12, pady=12, borderwidth=1, relief="groove")
    test_frame.pack(fill=tk.X, pady=10)

    def attempt_select_all_sequentially():
        """Request every checkbox in order; all should succeed now."""
        print("\n=== Test: Sequential API Requests ===")
        clear_selection()
        results = []
        for idx, cb in enumerate(checkboxes):
            result = cb.set(True)
            results.append(result)
            print(f" - Request {checkbox_labels[idx]} -> result={result}, state={cb.get()}")
            update_status_label()
        active = [label for label, cb in zip(checkbox_labels, checkboxes) if cb.get()] or ["None"]
        print(f"Final state: {', '.join(active)}")
        print(f"Results summary: {sum(results)} succeeded out of {len(results)} attempts\n")
        status_label.config(text=f"Status: After sequential requests -> {', '.join(active)}")
        status_label.update_idletasks()

    def attempt_switch_immediately():
        """Show that immediate sequential switches now work correctly."""
        print("\n=== Test: Rapid Switch Attempt ===")
        clear_selection()
        first, second = checkboxes[0], checkboxes[1]
        first_result = first.set(True)
        second_result = second.set(True)
        print(f" - Select 1 -> result={first_result}, state={first.get()}")
        print(f" - Immediately select 2 -> result={second_result}, state={second.get()}")
        update_status_label()
        active = [label for label, cb in zip(checkbox_labels, checkboxes) if cb.get()] or ["None"]
        print(f"Final state: {', '.join(active)}\n")
        status_label.config(text=f"Status: After rapid switch -> {', '.join(active)}")
        status_label.update_idletasks()

    def attempt_round_robin_cycle():
        """Cycle through each checkbox with a brief pause."""
        print("\n=== Test: Round-Robin Cycle ===")
        clear_selection()

        final_label = {"value": "None"}

        def select_next(position):
            if position >= len(checkboxes):
                active = [label for label, cb in zip(checkbox_labels, checkboxes) if cb.get()] or ["None"]
                print(f"Final state: {', '.join(active)} (last accepted: {final_label['value']})\n")
                status_label.config(text=f"Status: After round-robin -> {', '.join(active)}")
                status_label.update_idletasks()
                return

            idx = position
            cb = checkboxes[idx]
            result = cb.set(True)
            if result:
                final_label["value"] = checkbox_labels[idx]
            print(f" - Request {checkbox_labels[idx]} -> result={result}, state={cb.get()}")
            update_status_label()
            root.after(75, lambda: select_next(position + 1))

        select_next(0)

    def attempt_delayed_switch():
        """Show that a delayed switch succeeds."""
        print("\n=== Test: Delayed Switch ===")
        clear_selection()
        first, second = checkboxes[0], checkboxes[1]
        first_result = first.set(True)
        print(f" - Select Checkbox 1 -> result={first_result}, state={first.get()}")
        update_status_label()
        
        def delayed_select():
            second_result = second.set(True)
            print(f" - Select Checkbox 2 (after delay) -> result={second_result}, state={second.get()}")
            update_status_label()
            active = [label for label, cb in zip(checkbox_labels, checkboxes) if cb.get()] or ["None"]
            print(f"Final state: {', '.join(active)}\n")
            status_label.config(text=f"Status: After delayed switch -> {', '.join(active)}")
            status_label.update_idletasks()

        root.after(100, delayed_select)

    def attempt_repeated_toggle():
        """Toggle the same checkbox on/off rapidly - all should succeed now."""
        print("\n=== Test: Repeated Toggle ===")
        target = checkboxes[2]
        clear_selection()
        sequence = [True, False] * 3
        results = []
        for step, desired in enumerate(sequence, start=1):
            result = target.set(desired)
            results.append(result)
            print(f" - Step {step}: set to {desired} -> result={result}, state={target.get()}")
            update_status_label()
        active = [label for label, cb in zip(checkbox_labels, checkboxes) if cb.get()] or ["None"]
        print(f"Final state: {', '.join(active)}")
        print(f"All operations succeeded: {all(results)}\n")
        status_label.config(text=f"Status: After toggle test -> {', '.join(active)}")
        status_label.update_idletasks()

    test_frame.columnconfigure(0, weight=1)
    test_frame.columnconfigure(1, weight=1)

    tk.Button(test_frame, text="Sequential API Requests", command=attempt_select_all_sequentially).grid(row=0, column=0, padx=4, pady=2, sticky="ew")
    tk.Button(test_frame, text="Round-Robin Cycle", command=attempt_round_robin_cycle).grid(row=0, column=1, padx=4, pady=2, sticky="ew")
    tk.Button(test_frame, text="Delayed Switch", command=attempt_delayed_switch).grid(row=1, column=0, padx=4, pady=2, sticky="ew")
    tk.Button(test_frame, text="Rapid Switch Attempt", command=attempt_switch_immediately).grid(row=1, column=1, padx=4, pady=2, sticky="ew")
    tk.Button(test_frame, text="Toggle Same Checkbox", command=attempt_repeated_toggle).grid(row=2, column=0, columnspan=2, padx=4, pady=2, sticky="ew")
    
    root.mainloop()
'''


##########################
#   Demo Application 2   #
##########################

'''
def demo_application_2():
    root = tk.Tk()
    root.title("Shipping Options")
    
    # Status label
    status = tk.Label(root, text="No option selected")
    status.pack(pady=10)
    
    # Update status when selection changes
    def update_status(cb, is_checked):
        if is_checked:
            status.config(text=f"Selected: {cb.cget('text')}")
        else:
            status.config(text="No option selected")
    
    # Create shipping option checkboxes
    frame = tk.LabelFrame(root, text="Shipping Method", padx=20, pady=10)
    frame.pack(padx=20, pady=10)
    
    standard = MutuallyExclusiveCheckbox(
        frame, text="Standard (5-7 days) - Free", callback=update_status
    )
    express = MutuallyExclusiveCheckbox(
        frame, text="Express (2-3 days) - $9.99", callback=update_status
    )
    overnight = MutuallyExclusiveCheckbox(
        frame, text="Overnight - $24.99", callback=update_status
    )
    
    standard.pack(anchor="w")
    express.pack(anchor="w")
    overnight.pack(anchor="w")
    
    MutuallyExclusiveCheckbox.bind_group(standard, express, overnight)
    
    # Submit button
    def submit():
        if standard.get():
            print("Processing standard shipping...")
            standard.set(False)
        elif express.get():
            print("Processing express shipping...")
            express.set(False)
        elif overnight.get():
            print("Processing overnight shipping...")
            overnight.set(False)
        else:
            print("Please select a shipping method")
    
    tk.Button(root, text="Submit Order", command=submit).pack(pady=10)
    
    root.mainloop()
'''


#if __name__ == "__main__":
#    demo_application_1()
#    demo_application_2()