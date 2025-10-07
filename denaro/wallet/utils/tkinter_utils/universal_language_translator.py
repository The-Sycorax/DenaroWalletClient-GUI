# =================================================================================
# Universal Tkinter Translator
# =================================================================================
# Developed by: The-Sycorax (https://github.com/The-Sycorax)
# Licensed under the MIT License
# Version: 1.0.0
# =================================================================================
#
# OVERVIEW
# --------
# This module provides a comprehensive, production-ready translation engine for
# Tkinter applications. It uses monkey-patching to transparently translate all
# text content in Tkinter and TTK widgets without requiring modifications to
# existing application code.
#
# KEY FEATURES
# ------------
# - Runtime Language Control: Enable, disable, or change languages at any time
#
# - Comprehensive Widget Support: Handles standard widgets, Treeview, Notebook,
#   Menu, and dialog functions (messagebox, filedialog)
#
# - Automatic UI Refresh: Re-translates all tracked widgets on language change
#
# - Translation Integrity: Widgets configured inside a `with engine.no_translate()`
#   block are permanently marked as untranslatable
#
# - Feedback Loop Prevention: Uses reverse caching to prevent re-translation
#   corruption when widgets are reconfigured
#
# - Security Features: Redacts sensitive data patterns from logs and attempts
#   secure memory cleanup
#
# - Hybrid Translation: Three-tier system (cache → offline → online API)
#
# - Persistent Caching: Saves translations between sessions for improved performance
#
# - Detailed Logging: Provides comprehensive activity tracing and statistics
#
# DEPENDENCIES
# ------------
# Install required packages:
#   pip install argostranslate deep-translator
#
# BASIC USAGE
# -----------
# ```python
# from tkinter_translator import activate_tkinter_translation
# import logging
#
# # Initialize the translation engine (starts disabled)
# engine = activate_tkinter_translation(
#     source_language='en',
#     target_language='fr',
#     log_level=logging.INFO  # Use logging.DEBUG for verbose output
# )
#
# # ... your Tkinter application code ...
#
# # Enable German translation at runtime
# engine.set_language('de')
#
# # Disable translation (revert to original language)
# engine.set_language('en')
#
# # Mark specific widgets as untranslatable
# with engine.no_translate():
#     tk.Label(root, text="VERSION 1.0.0").pack()  # Never translated
# ```
#
# ADVANCED USAGE
# --------------
# ```python
# # Configure sensitive data patterns to redact from logs
# import re
# engine = activate_tkinter_translation(
#     source_language='en',
#     target_language='fr',
#     sensitive_patterns=[
#         re.compile(r'\d{3}-\d{2}-\d{4}'),  # SSN pattern
#     ],
#     non_translatable_patterns=[
#         re.compile(r'v\d+\.\d+\.\d+')       # Version strings
#     ]
# )
# ```

# Standard library imports
import os
import json
import inspect
import logging
import re
import atexit
import contextlib
import ctypes
from functools import wraps
import tkinter as tk
from tkinter import ttk
import tkinter.messagebox
import tkinter.filedialog
import html
import weakref

# Third-party translation library imports
import argostranslate.package
import argostranslate.translate
from deep_translator import GoogleTranslator

# Configure module logger
log = logging.getLogger("TkinterTranslator")


class TkinterUniversalLanguageTranslator:
    """
    A universal, hybrid translation engine for Tkinter applications.
    
    This class transparently translates text in all standard Tkinter and TTK
    widgets using a combination of offline models and online APIs. It supports
    runtime language switching, automatic UI refresh, and maintains translation
    integrity through intelligent caching.
    
    The engine operates by monkey-patching widget initialization and configuration
    methods to intercept and translate text-bearing keyword arguments. Original
    text values are preserved to enable proper re-translation when the language
    changes.
    
    Args:
        source_lang_code (str): ISO 639-1 source language code (e.g., 'en')
        target_lang_code (str): ISO 639-1 target language code (e.g., 'es')
        translation_enabled (bool): Whether translation is currently active
        tracked_widgets (WeakSet): All widgets being tracked for translation
        cache (dict): Forward translation cache (original → translated)
        reverse_cache (dict): Reverse translation cache (translated → original)
        
    Example:
        >>> engine = TkinterUniversalLanguageTranslator('en', 'es')
        >>> engine.activate()
        >>> # All subsequently created widgets will be translated
        >>> engine.set_language('fr')  # Switch to French
        >>> engine.set_language('en')  # Disable translation
    """

    def __init__(self, source_language='en', target_language='en'):
        """
        Initialize the translation engine.

        Args:
            source_language (str): ISO 639-1 source language code (default: 'en').
                This is the language your application is written in.
            target_language (str): ISO 639-1 target language code (default: 'en').
                Set this equal to source_language to start with translation disabled.
                
        Note:
            Translation is only enabled if source_language != target_language.
            When disabled, all text passes through unchanged.
        """
        # Control and configuration
        self.source_lang_code = source_language
        self.target_lang_code = target_language
        self.translation_enabled = (source_language != target_language)
        self.in_no_translate_block = False
        
        log.info(
            f"Initializing translator: {source_language} → {target_language}. "
            f"Translation enabled: {self.translation_enabled}"
        )
        
        # Widget tracking (WeakSet prevents memory leaks)
        self.tracked_widgets = weakref.WeakSet()

        # Translation backend services (initialized lazily)
        self.argos_translator = None
        self.google_translator = None

        # Caching and statistics
        self.cache_dir = "language_cache"
        self.cache_file = ""
        self.cache = {}
        self.reverse_cache = {}
        self.api_calls = 0
        self.offline_hits = 0
        self.cache_hits = 0
        
        # Widget configuration
        self.translatable_keywords = {'text', 'label', 'title', 'value', 'message'}
        self.translatable_list_keywords = {'values'}
        
        # Filtering patterns for security and data integrity
        self.sensitive_patterns = []
        self.non_translatable_patterns = []
        self.path_pattern = re.compile(
            r'((?:\.\/|\/|\\|)[A-Za-z]:\\[\w\.\\ -]+|(?:\.\/|\/|\\)[\w\.\\\/ -]+)'
        )

        # Initialize backends if translation is enabled at startup
        if self.translation_enabled:
            self._initialize_backends()

    def _initialize_backends(self):
        """
        Initialize translation services and load the persistent cache.
        
        This method is called automatically when translation is enabled. It:
        1. Sets up the cache file path for the current language pair
        2. Loads any existing translations from disk
        3. Builds the reverse cache for feedback loop prevention
        4. Initializes both offline (Argos) and online (Google) translators
        5. Resets session statistics
        
        The offline model will be automatically downloaded on first use if not
        already installed. This is a one-time operation per language pair.
        """
        if not self.target_lang_code or self.target_lang_code == self.source_lang_code:
            return
            
        log.info(f"Initializing translation backends for target: {self.target_lang_code}")
        
        # Set up cache file path
        self.cache_file = os.path.join(
            self.cache_dir,
            f"{self.source_lang_code}_{self.target_lang_code}.json"
        )
        
        # Load persistent cache and build reverse mapping
        self.cache = self._load_cache()
        self.reverse_cache = {v: k for k, v in self.cache.items()}
        
        # Initialize Google Translator (online API)
        try:
            self.google_translator = GoogleTranslator(
                source=self.source_lang_code,
                target=self.target_lang_code
            )
        except Exception as e:
            log.error(f"Failed to initialize Google Translator: {e}")
            
        # Initialize Argos Translate (offline model)
        self._initialize_argos()
        
        # Reset statistics for new session
        self.api_calls, self.offline_hits, self.cache_hits = 0, 0, 0

    def set_language(self, new_target_language):
        """
        Change the target language or disable translation.
        
        This is the primary method for runtime language control. It handles all
        state transitions, saves the current session, and triggers a full UI refresh.
        
        Args:
            new_target_language (str): ISO 639-1 language code (e.g., 'fr', 'de').
                To disable translation, pass the source language code.
                
        Behavior:
            - If new language == current language: No action taken
            - If new language == source language: Translation disabled, UI reverted
            - If new language != current language: Translation enabled/changed, UI updated
            
        Example:
            >>> engine.set_language('de')  # Enable German translation
            >>> engine.set_language('es')  # Switch to Spanish
            >>> engine.set_language('en')  # Disable (assuming 'en' is source)
        """
        if new_target_language == self.target_lang_code:
            log.info(
                f"Language is already set to '{new_target_language}'. "
                "No change needed."
            )
            return
            
        log.info(
            f"--- Changing language: '{self.target_lang_code}' → "
            f"'{new_target_language}' ---"
        )
        
        # Report statistics and save cache for outgoing language session
        if self.translation_enabled:
            self.report_stats()
            self._save_cache()
        
        # Update internal state
        previous_target_lang = self.target_lang_code
        self.target_lang_code = new_target_language

        # Handle state transitions
        if self.target_lang_code == self.source_lang_code:
            # DISABLING: Clear all translation resources
            self.translation_enabled = False
            self.argos_translator = None
            self.google_translator = None
            self.cache = {}
            self.reverse_cache = {}
            log.info("Translation disabled. Reverting UI to original language.")
        else:
            # ENABLING or CHANGING: Initialize backends for new language
            self.translation_enabled = True
            log.info(f"Enabling/changing translation from '{previous_target_lang}'.")
            self._initialize_backends()
        
        # Trigger full UI refresh
        self.refresh_all_widgets()


    def refresh_all_widgets(self):
        """
        Refresh all tracked widgets with their original text values.
        
        This method iterates through all tracked widgets and re-applies their
        original (untranslated) configuration. If translation is enabled, the
        text will be automatically translated during reconfiguration. If disabled,
        the original text is restored.
        
        Widgets marked as explicitly untranslatable (via no_translate() context)
        are skipped entirely to preserve their integrity.
        
        The refresh handles various widget types with special configuration methods:
        - Standard widgets: configure()
        - Windows/Toplevels: title()
        - Treeview: heading()
        - Notebook: tab()
        - Menu: entryconfigure()
        
        Note:
            This method is automatically called by set_language(). Manual calls
            are rarely needed unless you've made external modifications to widgets
            and want to re-synchronize the translation state.
        """
        state = 'ON' if self.translation_enabled else 'OFF'
        log.info(f"--- Refreshing UI for {len(self.tracked_widgets)} tracked widgets. New state: {state} ---")
        
        for widget in list(self.tracked_widgets):
            try:
                if hasattr(widget, '_explicitly_untranslatable'):
                    log.debug(f"Skipping refresh for explicitly untranslatable widget: {type(widget).__name__}")
                    continue
                
                if not hasattr(widget, '_original_options'):
                    continue

                log.debug(f"Refreshing widget: {type(widget).__name__} with options: {self._redact_sensitive(widget._original_options)}")
                opts = widget._original_options
                
                # Special handling for Combobox to preserve selection
                current_combo_index = -1
                if isinstance(widget, ttk.Combobox):
                    try:
                        current_combo_index = widget.current()
                    except tk.TclError:
                        pass # Ignore if widget is in a bad state

                config_opts = {k: v for k, v in opts.items() if k not in ['title', 'headings', 'tabs', 'entries']}
                if config_opts:
                    widget.configure(**config_opts)

                if 'title' in opts:
                    widget.title(opts['title'])
                if 'headings' in opts and isinstance(widget, ttk.Treeview):
                    for col, text in opts['headings'].items():
                        widget.heading(col, text=text)
                if 'tabs' in opts and isinstance(widget, ttk.Notebook):
                    for cid, t_opts in opts['tabs'].items():
                        widget.tab(cid, **t_opts)
                if 'entries' in opts and isinstance(widget, tk.Menu):
                    for index, entry_opts in opts['entries'].items():
                        widget.entryconfigure(index, **entry_opts)
                
                # After configuring, restore Combobox selection
                if isinstance(widget, ttk.Combobox) and current_combo_index != -1:
                    widget.current(current_combo_index)

            except tk.TclError as e:
                log.debug(f"Could not refresh widget (it may have been destroyed): {e}")
            except Exception as e:
                log.error(f"Unexpected error refreshing widget of type '{type(widget).__name__}': {e}", exc_info=True)
                
        log.info("--- UI Refresh Complete. ---")

    def _redact_sensitive(self, data):
        """
        Recursively redact sensitive data from log output.
        
        This security feature scans data structures for patterns matching
        sensitive information (e.g., SSN, credit cards, API keys) and replaces
        them with a redaction marker before logging.
        
        Args:
            data: Any data structure (dict, list, str, or scalar)
            
        Returns:
            A sanitized copy of the data structure with sensitive values redacted
            
        Note:
            Patterns are configured via the sensitive_patterns attribute, which
            should contain compiled regex patterns.
        """
        if isinstance(data, dict):
            return {k: self._redact_sensitive(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._redact_sensitive(item) for item in data]
        if not isinstance(data, str):
            return data
            
        # Check if string matches any sensitive pattern
        for pattern in self.sensitive_patterns:
            if pattern.fullmatch(data.strip()):
                return "[SENSITIVE DATA REDACTED]"
        return data

    @staticmethod
    def secure_delete(vars_to_delete):
        """
        Attempt to securely wipe variables from memory.
        
        This method overwrites the memory region of specified variables with zeros
        before deleting them. While not guaranteed to be completely secure (due to
        Python's memory management), it provides defense-in-depth for sensitive data.
        
        Args:
            vars_to_delete: A variable or list of variables to securely delete
            
        Note:
            This is a best-effort operation. For truly sensitive data, consider
            using specialized security libraries or hardware security modules.
        """
        if not isinstance(vars_to_delete, list):
            vars_to_delete = [vars_to_delete]
            
        for var in vars_to_delete:
            if var is None:
                continue
            try:
                var_size = ctypes.sizeof(var)
                zeros = (ctypes.c_byte * var_size)()
                ctypes.memmove(id(var), zeros, var_size)
            except (TypeError, SystemError):
                pass
            finally:
                try:
                    del var
                except NameError:
                    pass

    @contextlib.contextmanager
    def no_translate(self):
        """
        Context manager to mark widgets as permanently untranslatable.
        
        Any widget created or configured within this context will be marked with
        the _explicitly_untranslatable flag and will never be translated, even
        if translation is enabled or the language is changed later.
        
        Example:
            >>> with engine.no_translate():
            ...     tk.Label(root, text="MyApp v2.1.0").pack()
            ...     tk.Label(root, text="© 2024 Company").pack()
            
        Note:
            The untranslatable flag is permanent for the widget's lifetime.
            Widgets are still tracked but will be skipped during refresh operations.
        """
        original_state = self.translation_enabled
        self.translation_enabled = False
        self.in_no_translate_block = True
        log.debug("Entering no_translate context (untranslatable mode active)")
        
        try:
            yield
        finally:
            self.in_no_translate_block = False
            self.translation_enabled = original_state
            log.debug("Exiting no_translate context (returning to normal mode)")

    def _load_cache(self):
        """
        Load the persistent translation cache from disk.
        
        Returns:
            dict: The loaded cache dictionary, or an empty dict if loading fails
            
        Note:
            Cache files are stored as JSON in the language_cache directory with
            the naming convention: {source}_{target}.json
        """
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                log.info(
                    f"Loaded {len(data)} translations from cache: "
                    f"{self.cache_file}"
                )
                return data
            except Exception as e:
                log.error(
                    f"Could not load cache file. Starting with empty cache. "
                    f"Error: {e}"
                )
        else:
            log.info("No persistent cache file found. Starting with empty cache.")
            
        return {}

    def _save_cache(self):
        """
        Save the in-memory translation cache to disk.
        
        The cache is saved as a JSON file in the language_cache directory. This
        enables fast startup times for subsequent sessions as previously translated
        strings can be retrieved instantly from the cache.
        
        Note:
            The cache directory is created automatically if it doesn't exist.
            Save failures are logged but don't interrupt program execution.
        """
        if not self.cache or not self.cache_file:
            return
            
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            log.info(
                f"Saved {len(self.cache)} translations to cache: "
                f"{self.cache_file}"
            )
        except IOError as e:
            log.error(f"Could not save cache file: {e}")

    def _initialize_argos(self):
        """
        Initialize the Argos Translate offline translation model.
        
        This method checks if the required language model is installed and
        downloads it if necessary. Offline models enable translation without
        internet connectivity and reduce API costs.
        
        The download is a one-time operation per language pair and can be
        large depending on the language pair.
        
        Note:
            If initialization fails, the engine gracefully falls back to
            online-only translation without interrupting operation.
        """
        try:
            self.argos_translator = argostranslate.translate.get_translation_from_codes(
                self.source_lang_code,
                self.target_lang_code
            )
            log.info(
                f"Successfully loaded offline model: "
                f"{self.source_lang_code} → {self.target_lang_code}"
            )
        except Exception:
            log.warning(
                f"Offline model for {self.source_lang_code}→{self.target_lang_code} "
                f"not found. Downloading..."
            )
            try:
                argostranslate.package.update_package_index()
                package = next(
                    filter(
                        lambda x: (
                            x.from_code == self.source_lang_code and
                            x.to_code == self.target_lang_code
                        ),
                        argostranslate.package.get_available_packages()
                    )
                )
                log.info(f"Downloading and installing package: {package.package_version}")
                package.install()
                self.argos_translator = argostranslate.translate.get_translation_from_codes(
                    self.source_lang_code,
                    self.target_lang_code
                )
                log.info("Offline model installed and loaded successfully.")
            except Exception as e:
                log.error(
                    f"Failed to initialize Argos Translate. "
                    f"Online fallback will be used. Error: {e}"
                )
                self.argos_translator = None

    def _translate_segment(self, segment):
        """
        Translate a single text segment using the three-tier pipeline.
        
        Translation Pipeline:
        1. Cache lookup (instant, no overhead)
        2. Offline model (Argos Translate, no internet required)
        3. Online API (Google Translate, requires internet)
        
        Args:
            segment (str): The text segment to translate
            
        Returns:
            str: The translated text, or the original if translation fails
            
        Note:
            Successful translations are automatically added to both the forward
            and reverse caches for future use. Statistics are updated for each
            tier that is accessed.
        """
        # Pre-flight checks
        if not segment or not segment.strip():
            return segment
            
        log.debug(f"Processing segment: '{self._redact_sensitive(segment)}'")
        
        # Tier 1: Cache lookup
        if segment in self.cache:
            self.cache_hits += 1
            log.debug(
                f"Cache HIT: '{self._redact_sensitive(self.cache[segment])}'"
            )
            return self.cache[segment]
            
        log.debug("Cache MISS, attempting translation...")
        translated_text = None

        # Tier 2: Offline translation (Argos)
        if self.argos_translator:
            try:
                # Escape HTML entities to prevent mishandling of special characters
                escaped_segment = html.escape(segment, quote=False)
                result = self.argos_translator.translate(escaped_segment)
                
                if result and result.strip() and result.lower() != escaped_segment.lower():
                    self.offline_hits += 1
                    translated_text = result
                    log.debug(
                        f"Offline HIT: "
                        f"'{self._redact_sensitive(translated_text)}'"
                    )
            except Exception as e:
                log.warning(f"Argos Translate error: {e}")

        # Tier 3: Online fallback (Google)
        if not translated_text and self.google_translator:
            log.debug("Offline MISS, falling back to online API...")
            try:
                result = self.google_translator.translate(segment)
                if result and result.strip():
                    self.api_calls += 1
                    translated_text = result
                    log.debug(
                        f"Online HIT: "
                        f"'{self._redact_sensitive(translated_text)}'"
                    )
            except Exception as e:
                log.error(f"Online translation API failed: {e}")
        
        # Post-processing: Unescape HTML entities
        final_translation = html.unescape(translated_text or segment)
        
        if final_translation != (translated_text or segment):
            log.debug(
                f"Post-processed (unescaped HTML entities): "
                f"Raw: '{translated_text}', Clean: '{final_translation}'"
            )
        
        # Update caches if translation succeeded
        if final_translation != segment:
            self.cache[segment] = final_translation
            self.reverse_cache[final_translation] = segment
            log.debug(
                f"Added to cache: '{self._redact_sensitive(segment)}' → "
                f"'{self._redact_sensitive(final_translation)}'"
            )
            
        return final_translation

    def translate_text(self, text):
        """
        Translates a single text segment using the tiered translation pipeline.
        
        This is the main orchestrator function that handles:
        1. Pre-flight validation (enabled status, empty strings, etc.)
        2. Security filtering (sensitive patterns, non-translatable patterns)
        3. Path detection and preservation (file paths aren't translated)
        4. Segmentation and translation
        5. Reassembly of translated segments
        
        Args:
            text (str): The text to translate
            
        Returns:
            str: The translated text, or original if translation is not applicable
            
        Processing Logic:
            - Returns immediately if translation is disabled
            - Filters out empty strings, non-strings, and strings without letters
            - Preserves sensitive data and file paths
            - Splits by file paths and translates each segment independently
            - Reassembles segments maintaining path integrity
            
        Example:
            >>> engine.translate_text("Hello World")
            "Hola Mundo"  # If translating to Spanish
            >>> engine.translate_text("/path/to/file.txt")
            "/path/to/file.txt"  # Paths are preserved
        """
        # Check if translation is enabled
        if not self.translation_enabled:
            log.debug("Skipped: Translation is globally disabled")
            return text
            
        # Heuristic filters for non-translatable content
        if not text or not isinstance(text, str) or not text.strip():
            log.debug("Skipped: Input is empty, None, or not a string")
            return text
            
        if not re.search(r'[a-zA-Z]', text):
            log.debug("kipped: No letters detected (heuristic filter)")
            return text
        
        # Security and pattern-based filters
        stripped_text = text.strip()
        
        # Check sensitive patterns
        for pattern in self.sensitive_patterns:
            if pattern.fullmatch(stripped_text):
                log.debug("Skipped: Matched sensitive data pattern (redacted)")
                self.secure_delete([stripped_text])
                return text
                
        # Check non-translatable patterns
        for pattern in self.non_translatable_patterns:
            if pattern.fullmatch(stripped_text):
                log.debug(
                    f"Skipped: Matched non-translatable pattern "
                    f"'{pattern.pattern}'"
                )
                return text
        
        log.debug(f"--- TRANSLATE REQUEST: '{self._redact_sensitive(text)}' ---")

        # Split by file paths and translate segments independently
        segments = self.path_pattern.split(text)
        segments = [s for s in segments if s]
        
        if len(segments) <= 1:
            # No paths detected, translate entire string
            final_text = self._translate_segment(text)
        else:
            # Multiple segments detected, process each independently
            log.debug(
                f"Splitting into segments: "
                f"{self._redact_sensitive(segments)}"
            )
            processed = [
                self._translate_segment(s) if not self.path_pattern.fullmatch(s) else s
                for s in segments
            ]
            final_text = "".join(processed)
            
        log.debug(f"--- TRANSLATE RESULT: '{self._redact_sensitive(final_text)}' ---")
        return final_text

    def report_stats(self):
        """
        Logs a summary of translation activity for the last active session.
        
        Statistics include:
        - Total translation requests
        - Cache hit rate
        - Offline model usage
        - Online API usage
        
        This method is automatically called when changing languages and at
        program exit. It provides visibility into translation performance and
        can help optimize cache configuration.
        
        Note:
            No statistics are reported if translation is disabled or if no
            translation activity has occurred.
        """
        if not self.target_lang_code or self.target_lang_code == self.source_lang_code:
            return
            
        log.info(
            f"--- Translation Statistics: "
            f"{self.source_lang_code}→{self.target_lang_code} ---"
        )
        
        total = self.offline_hits + self.cache_hits + self.api_calls
        
        if total == 0:
            log.info("No translation activity recorded for this session.")
            return
            
        cache_rate = (self.cache_hits / total * 100) if total > 0 else 0
        
        log.info(f"Total translation requests: {total}")
        log.info(f"Cache hits:                 {self.cache_hits} ({cache_rate:.1f}%)")
        log.info(f"Offline model hits:         {self.offline_hits}")
        log.info(f"Online API calls:           {self.api_calls}")
        log.info("─" * 60)

    def _on_exit_cleanup(self):
        """
        A single cleanup function called at exit to save cache and report stats.
        
        This method ensures that statistics are reported and the cache is saved
        before the program terminates, preserving translation data for the next
        session.
        
        Note:
            This is registered via atexit and should not be called manually.
        """
        self.report_stats()
        if self.translation_enabled:
            self._save_cache()

    def register_report_on_exit(self):
        """
        Registers the cleanup function to be called reliably on program exit.
        
        This ensures that translation statistics are logged and the cache is
        saved even if the program exits unexpectedly (but gracefully).
        
        Note:
            This method is called automatically by activate_tkinter_translation()
            and should not need to be called manually.
        """
        atexit.register(self._on_exit_cleanup)
        log.info("Exit cleanup handler registered (statistics and cache saving)")

    def _translate_kwargs(self, kwargs):
        """
        Internal helper to translate known text-bearing keywords in a widget's options.
        
        This internal helper scans a kwargs dictionary for known translatable
        parameters (text, label, title, etc.) and translates their values.
        
        Args:
            kwargs (dict): Widget configuration keyword arguments
            
        Returns:
            dict: The same dictionary with translated values
        """
        if not self.translation_enabled:
            return kwargs
            
        # Translate single-value parameters
        for key in self.translatable_keywords:
            if key in kwargs:
                kwargs[key] = self.translate_text(kwargs[key])
                
        # Translate list-value parameters (e.g., Combobox values)
        for key in self.translatable_list_keywords:
            if key in kwargs and isinstance(kwargs[key], (list, tuple)):
                kwargs[key] = [
                    self.translate_text(str(item)) for item in kwargs[key]
                ]
                
        return kwargs

    def activate(self):
        """
        Activates the engine by monkey-patching all relevant Tkinter methods.

        
        This is the core of the translator's transparent integration. It wraps
        the constructors and configuration methods of Tkinter widgets to intercept
        and translate text properties before they are displayed.
         
        It patches:        
            1. Generic widget methods (__init__, configure) for all widgets
            2. Special methods with unique signatures (title, insert, etc.)
            3. Complex widgets (Treeview, Notebook, Menu)
            4. Dialog functions (messagebox, filedialog)
        
        Returns:
            TkinterUniversalLanguageTranslator: self (for method chaining)
            
        Example:
            >>> engine = TkinterUniversalLanguageTranslator('en', 'de')
            >>> engine.activate()
            >>> # All widgets created after this point will be translated
            
        Note:
            This method should only be called once. Multiple calls are safe but
            redundant. The patching persists for the lifetime of the program.
        """
        log.info("=" * 60)
        log.info("Activating Universal Tkinter Translation Engine")
        log.info("=" * 60)

        def manage_untranslatable_flag(widget):
            """
            Sets the _explicitly_untranslatable flag based on the context.
            
            This helper is called during widget initialization and configuration
            to mark widgets created inside a no_translate() context.
            
            Args:
                widget: The widget to flag or unflag
            """
            widget_class_name = type(widget).__name__
            
            if self.in_no_translate_block:
                log.debug(f"Marking widget as untranslatable: {widget_class_name}")
                widget._explicitly_untranslatable = True
            elif self.translation_enabled and not self.in_no_translate_block:
                if hasattr(widget, '_explicitly_untranslatable'):
                    log.debug(
                        f"Removing untranslatable flag from widget: "
                        f"{widget_class_name}"
                    )
                    del widget._explicitly_untranslatable

        # ═══════════════════════════════════════════════════════════════════════
        # SECTION 1: Generic Widget Patching
        # ═══════════════════════════════════════════════════════════════════════
        log.info("Patching generic widget methods (__init__, configure)...")
        
        def create_generic_patched_method(original_method):
            """
            Creates a wrapper for standard methods like __init__ and configure.
            
            This wrapper intercepts configuration calls, stores original text
            values, and translates them before passing to the original method.
            
            Args:
                original_method: The original unpatched method
                
            Returns:
                function: The patched wrapper function
            """
            @wraps(original_method)
            def patched_method(self_widget, *args, **kwargs):
                if kwargs:
                    manage_untranslatable_flag(self_widget)
                    
                    # Initialize storage for original text values
                    if not hasattr(self_widget, '_original_options'):
                        self_widget._original_options = {}
                    
                    # Store original values (only if not already stored)
                    # This prevents corruption from repeated reconfigurations
                    for key in self.translatable_keywords.union(
                        self.translatable_list_keywords
                    ):
                        if key in kwargs and key not in self_widget._original_options:
                            self_widget._original_options[key] = kwargs[key]
                    
                    self.tracked_widgets.add(self_widget)
                
                # Translate kwargs before passing to original method
                kwargs = self._translate_kwargs(kwargs)
                return original_method(self_widget, *args, **kwargs)
                
            return patched_method
        
        # Apply generic patches to all widget classes
        for module in (tk, ttk):
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, tk.Widget):
                    log.debug(f"Patching: {module.__name__}.{name}")
                    
                    if hasattr(obj, '__init__'):
                        obj.__init__ = create_generic_patched_method(obj.__init__)
                        
                    if hasattr(obj, 'configure'):
                        obj.configure = create_generic_patched_method(obj.configure)
                        obj.config = obj.configure  # Alias

        # ═══════════════════════════════════════════════════════════════════════
        # SECTION 2: Special Method Patching
        # ═══════════════════════════════════════════════════════════════════════
        log.info("Patching special methods with unique signatures...")
        
        # Patch: tk.Wm.title()
        original_title = tk.Wm.title
        
        @wraps(original_title)
        def patched_title(self_widget, string=None):
            """Patched version of tk.Wm.title() method."""
            if string is not None:
                manage_untranslatable_flag(self_widget)
                
                if not hasattr(self_widget, '_original_options'):
                    self_widget._original_options = {}
                    
                # Store original title (only if not already stored)
                if 'title' not in self_widget._original_options:
                    self_widget._original_options['title'] = string
                    
                self.tracked_widgets.add(self_widget)
                string = self.translate_text(string)
                
            return original_title(self_widget, string)
            
        tk.Wm.title = patched_title
        log.debug("Patched: tk.Wm.title()")

        # Patch: insert() method for Text, Entry, Listbox
        for cls in (tk.Text, tk.Entry, tk.Listbox):
            if hasattr(cls, 'insert'):
                original_insert = cls.insert
                
                @wraps(original_insert)
                def patched_insert(self_widget, index, *args, **kwargs):
                    """Patched version of insert() method."""
                    manage_untranslatable_flag(self_widget)
                    
                    new_args = list(args)
                    
                    # Handle string argument (can be positional or keyword)
                    if 'string' in kwargs:
                        translated_text = self.translate_text(kwargs.pop('string'))
                        new_args.insert(0, translated_text)
                    elif new_args and isinstance(new_args[0], str):
                        new_args[0] = self.translate_text(new_args[0])
                        
                    return original_insert(self_widget, index, *new_args, **kwargs)
                    
                cls.insert = patched_insert
                log.debug(f"Patched: {cls.__name__}.insert()")
        
        # ═══════════════════════════════════════════════════════════════════════
        # SECTION 3: Menu Widget Patching
        # ═══════════════════════════════════════════════════════════════════════
        log.info("Patching Menu widget methods...")
        
        # Patch: tk.Menu.add()
        original_menu_add = tk.Menu.add
        
        @wraps(original_menu_add)
        def patched_menu_add(self_widget, itemType, cnf={}, **kw):
            """Patched version of tk.Menu.add() method."""
            original_opts = {**cnf, **kw}

            # If in no_translate block, add item without translation or tracking
            if self.in_no_translate_block:
                return original_menu_add(self_widget, itemType, **original_opts)

            # Translate options
            translated_opts = self._translate_kwargs(original_opts.copy())
            
            # For menu items with labels, store original text for refresh
            if itemType in ['command', 'cascade', 'radiobutton', 'checkbutton']:
                if 'label' in original_opts:
                    result = original_menu_add(self_widget, itemType, **translated_opts)
                    
                    try:
                        index = self_widget.index('end')
                        
                        if not hasattr(self_widget, '_original_options'):
                            self_widget._original_options = {}
                        if 'entries' not in self_widget._original_options:
                            self_widget._original_options['entries'] = {}
                            
                        # Store original label (only if not already stored)
                        if index not in self_widget._original_options['entries']:
                            self_widget._original_options['entries'][index] = {
                                'label': original_opts['label']
                            }
                            
                        self.tracked_widgets.add(self_widget)
                    except tk.TclError:
                        pass  # Ignore errors for torn-off menus
                        
                    return result
            
            return original_menu_add(self_widget, itemType, **translated_opts)
            
        tk.Menu.add = patched_menu_add
        
        # Patch: tk.Menu.entryconfigure()
        if hasattr(tk.Menu, 'entryconfigure'):
            original_entryconfigure = tk.Menu.entryconfigure
            
            @wraps(original_entryconfigure)
            def patched_entryconfigure(self_widget, index, cnf=None, **kw):
                """Patched version of tk.Menu.entryconfigure() method."""
                opts = {**(cnf or {}), **kw}
                
                # If in no_translate block, configure without translation
                if self.in_no_translate_block:
                    return original_entryconfigure(self_widget, index, **opts)

                # Store original label if present
                if 'label' in opts:
                    if not hasattr(self_widget, '_original_options'):
                        self_widget._original_options = {}
                    if 'entries' not in self_widget._original_options:
                        self_widget._original_options['entries'] = {}
                        
                    # Store original label (only if not already stored)
                    if index not in self_widget._original_options['entries']:
                        self_widget._original_options['entries'][index] = {
                            'label': opts['label']
                        }
                        
                    self.tracked_widgets.add(self_widget)

                # Translate and apply
                translated_opts = self._translate_kwargs(opts.copy())
                return original_entryconfigure(self_widget, index, **translated_opts)
                
            tk.Menu.entryconfigure = patched_entryconfigure
            
        log.debug("Patched: tk.Menu.add() and tk.Menu.entryconfigure()")

        # ═══════════════════════════════════════════════════════════════════════
        # SECTION 4: Notebook Widget Patching
        # ═══════════════════════════════════════════════════════════════════════
        if hasattr(ttk, 'Notebook'):
            log.info("Patching Notebook widget...")
            
            original_nb_add = ttk.Notebook.add
            
            @wraps(original_nb_add)
            def patched_nb_add(self_widget, child, **kw):
                """Patched version of ttk.Notebook.add() method."""
                manage_untranslatable_flag(self_widget)
                
                # Store original tab text
                if 'text' in kw:
                    if not hasattr(self_widget, '_original_options'):
                        self_widget._original_options = {}
                    if 'tabs' not in self_widget._original_options:
                        self_widget._original_options['tabs'] = {}
                        
                    # Store original text (only if not already stored)
                    if child not in self_widget._original_options['tabs']:
                        self_widget._original_options['tabs'][child] = {
                            'text': kw['text']
                        }
                        
                    self.tracked_widgets.add(self_widget)
                
                # Translate and apply
                kw = self._translate_kwargs(kw)
                return original_nb_add(self_widget, child, **kw)
                
            ttk.Notebook.add = patched_nb_add
            log.debug("Patched: ttk.Notebook.add()")

        # ═══════════════════════════════════════════════════════════════════════
        # SECTION 5: Treeview Widget Patching
        # ═══════════════════════════════════════════════════════════════════════
        if hasattr(ttk, 'Treeview'):
            log.info("Patching Treeview widget...")
            
            # Patch: ttk.Treeview.heading()
            original_tv_heading = ttk.Treeview.heading
            
            @wraps(original_tv_heading)
            def patched_tv_heading(self_widget, column, *args, **kw):
                """
                Patched version of ttk.Treeview.heading() method.
                
                Handles sort indicators and prevents re-translation feedback loops
                using the reverse cache. This is specific to the Denaro Wallet Client GUI
                """
                manage_untranslatable_flag(self_widget)
                
                if 'text' in kw:
                    if not hasattr(self_widget, '_original_options'):
                        self_widget._original_options = {}
                    if 'headings' not in self_widget._original_options:
                        self_widget._original_options['headings'] = {}
                    
                    # Separate base text from sort indicator suffix
                    base_text = kw['text']
                    suffix = ''
                    match = re.search(r'(\s*[↾⇂⥮])$', base_text)
                    if match:
                        suffix = match.group(1)
                        base_text = base_text[:-len(suffix)]
                        log.debug(
                            f"Treeview heading: Isolated base='{base_text}', "
                            f"suffix='{suffix}'"
                        )
                    
                    # Use reverse cache to prevent re-translation feedback loops
                    # (Store only if not already stored)
                    if column not in self_widget._original_options['headings']:
                        untranslated_base = self.reverse_cache.get(base_text, base_text)
                        self_widget._original_options['headings'][column] = (
                            untranslated_base + suffix
                        )
                    
                    # Get stored original and re-apply translation
                    original_base_with_suffix = (
                        self_widget._original_options['headings'][column]
                    )
                    original_base_match = re.search(
                        r'(\s*[↾⇂⥮])$',
                        original_base_with_suffix
                    )
                    original_base = original_base_with_suffix
                    if original_base_match:
                        original_base = original_base_with_suffix[
                            :-len(original_base_match.group(1))
                        ]

                    kw['text'] = self.translate_text(original_base) + suffix
                    self.tracked_widgets.add(self_widget)
                    
                return original_tv_heading(self_widget, column, *args, **kw)
                
            ttk.Treeview.heading = patched_tv_heading

            # Patch: ttk.Treeview.item()
            original_tv_item = ttk.Treeview.item
            
            @wraps(original_tv_item)
            def patched_tv_item(self_widget, item_id, *args, **kw):
                """Patched version of ttk.Treeview.item() method."""
                return original_tv_item(self_widget, item_id, *args, **kw)
                
            ttk.Treeview.item = patched_tv_item
            
            # Patch: ttk.Treeview.insert()
            original_tv_insert = ttk.Treeview.insert
            
            @wraps(original_tv_insert)
            def patched_tv_insert(self_widget, parent, index, iid=None, **kw):
                """Patched version of ttk.Treeview.insert() method."""
                manage_untranslatable_flag(self_widget)
                return original_tv_insert(self_widget, parent, index, iid=iid, **kw)
                
            ttk.Treeview.insert = patched_tv_insert
            
            log.debug(
                "Patched: ttk.Treeview.heading(), .item(), and .insert()"
            )

        # ═══════════════════════════════════════════════════════════════════════
        # SECTION 6: Dialog Function Patching
        # ═══════════════════════════════════════════════════════════════════════
        log.info("Patching dialog functions (messagebox, filedialog)...")
        def create_patched_dialog(original_func):
            @wraps(original_func)
            def patched_func(*args, **kwargs):
                kwargs = self._translate_kwargs(kwargs)
                return original_func(*args, **kwargs)
            return patched_func
            
        for module in (tkinter.messagebox, tkinter.filedialog):
            for name, func in inspect.getmembers(module, inspect.isfunction):
                setattr(module, name, create_patched_dialog(func))

        log.info("--- [Translation Engine Activation Complete] ---")
        return self


def activate_tkinter_translation(source_language='en', target_language='en', log_level=logging.INFO, **kwargs):
    """
    Initializes and activates the translation engine.

    This is the main entry point for the library. It sets up logging, creates
    the translator instance, and applies the monkey-patches to Tkinter.

    Args:
        source_lang_code (str): ISO 639-1 source language code (e.g., 'en')
        target_lang_code (str): ISO 639-1 target language code (e.g., 'es')
        log_level (int): The logging level for the translator's operations,
                         e.g., `logging.INFO` or `logging.DEBUG`.
        **kwargs:
            sensitive_patterns (list[re.Pattern]): A list of compiled regex
                patterns. Strings that fully match any of these patterns will
                not be logged or translated.
            non_translatable_patterns (list[re.Pattern]): A list of compiled
                regex patterns. Strings that fully match will not be translated
                but may be logged.

    Returns:
        TkinterUniversalLanguageTranslator: The activated translator instance, which can
                                    be used to change languages at runtime.
    """
    # Configure a default stream handler if none exists for this logger.
    if not logging.getLogger("TkinterTranslator").hasHandlers():
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s [%(levelname)s] - %(message)s', datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        log.addHandler(handler)
    
    log.setLevel(log_level)

    engine = TkinterUniversalLanguageTranslator(source_language=source_language, target_language=target_language)
    engine.sensitive_patterns = kwargs.get('sensitive_patterns', [])
    engine.non_translatable_patterns = kwargs.get('non_translatable_patterns', [])

    engine.activate()
    engine.register_report_on_exit()
    
    return engine


# ==============================================================================
#                          EXAMPLE DEMO APPLICATION
# ==============================================================================

'''
if __name__ == '__main__':
    class DemoApp:
        """A demonstration of the TkinterUniversalLanguageTranslator."""
        def __init__(self, root, engine, language_map):
            self.root = root
            self.engine = engine
            self.language_map = language_map

            self.root.geometry("925x800")
            self.root.title("Tkinter Universal Language Translator Demo")
            
            self._configure_styles()
            self.create_menu()
            self.create_widgets()

        def _configure_styles(self):
            """Set up a modern theme and custom styles for visual clarity."""
            style = ttk.Style()
            style.theme_use('clam')
            style.configure("Help.TLabel", foreground="gray", font='-slant italic')
            style.configure("Excluded.TLabel", foreground="blue", font='-slant italic')
            style.configure("Pattern.TLabel", foreground="green")
            style.configure("Sensitive.TLabel", foreground="red")

        def create_menu(self):
            """Creates the main menu bar for language switching and actions."""
            menu_bar = tk.Menu(self.root)
            self.root.config(menu=menu_bar)

            lang_menu = tk.Menu(menu_bar, tearoff=0)
            menu_bar.add_cascade(label="Select Language", menu=lang_menu)
            lang_menu.add_command(label="English (Original)", command=lambda: self.engine.set_language('en'))
            lang_menu.add_separator()
            
            sorted_languages = sorted(self.language_map.items(), key=lambda item: item[1])
            for lang_code, lang_name in sorted_languages:
                if lang_code != 'en':
                    lang_menu.add_command(label=lang_name, command=lambda c=lang_code: self.engine.set_language(c))

            action_menu = tk.Menu(menu_bar, tearoff=0)
            menu_bar.add_cascade(label="Actions", menu=action_menu)
            action_menu.add_command(label="Show Message", command=self.show_message)
            action_menu.add_separator()
            action_menu.add_command(label="Exit", command=self.root.quit)

        def create_widgets(self):
            """Creates the main content of the demo window."""
            main_frame = ttk.Frame(self.root, padding=15)
            main_frame.pack(fill="both", expand=True)
            
            ttk.Label(main_frame, text="Please Note: Not everything will be translated correctly or accurately.", style="Help.TLabel").pack(fill="x", pady=(0, 10))


            lf1 = ttk.LabelFrame(main_frame, text="Display Widgets", padding=10)
            lf1.pack(fill="x", pady=(0, 10))
            
            ttk.Label(lf1, text="This is a standard label that will be translated.").pack(anchor='w', pady=2)
            ttk.Button(lf1, text="Show an Informational Message", command=self.show_message).pack(anchor='w', pady=2)

            lf2 = ttk.LabelFrame(main_frame, text="Input & Choice Widgets", padding=10)
            lf2.pack(fill="x", pady=(0, 10))
            
            ttk.Label(lf2, text="Combobox:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
            combo = ttk.Combobox(lf2, values=["First Option", "Second Option", "Third Option"])
            combo.grid(row=0, column=1, sticky='ew', padx=5, pady=5)
            combo.current(0)
            lf2.columnconfigure(1, weight=1)

            ttk.Label(lf2, text="Checkbox with lable:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
            ttk.Checkbutton(lf2, text="Enable advanced settings").grid(row=1, column=1, sticky='w', padx=5, pady=5)

            ttk.Label(lf2, text="Radio Group:").grid(row=2, column=0, sticky='nw', padx=5, pady=5)
            radio_frame = ttk.Frame(lf2)
            radio_frame.grid(row=2, column=1, sticky='w')
            radio_var = tk.StringVar(value="r1")
            ttk.Radiobutton(radio_frame, text="Choice A", variable=radio_var, value="r1").pack(anchor='w')
            ttk.Radiobutton(radio_frame, text="Choice B", variable=radio_var, value="r2").pack(anchor='w')

            lf3 = ttk.LabelFrame(main_frame, text="Treeview & Exclusions", padding=10)
            lf3.pack(fill="both", expand=True)

            ttk.Label(lf3, text="Treeview column headers are translated:").pack(anchor='w')
            tree = ttk.Treeview(lf3, columns=('item', 'status'), show='headings', height=2)
            tree.heading('item', text='Item Name')
            tree.heading('status', text='Current Status')
            tree.insert('', 'end', values=('Sample Data 1', 'Pending'))
            tree.insert('', 'end', values=('Sample Data 2', 'Complete'))
            tree.pack(fill='x', pady=5)
            ttk.Label(lf3, text="Note: Treeview items are not translated to preserve data integrity.", style="Help.TLabel").pack(anchor='w')

            ttk.Separator(lf3).pack(fill='x', pady=10)
            
            ttk.Label(lf3, text="Excluding widgets and patterns:", font='-weight bold').pack(anchor='w', pady=(5,2))
            
            exclusion_frame = ttk.Frame(lf3, padding=(10, 5))
            exclusion_frame.pack(fill='x')
            
            # --- The `no_translate` demonstration ---
            # We create a new frame to hold the composite label.
            no_translate_line = ttk.Frame(exclusion_frame)
            no_translate_line.grid(row=0, column=0, columnspan=2, sticky='w')

            # Part 1: Created OUTSIDE the context, so it will be translated.
            ttk.Label(no_translate_line, text="Using").pack(side='left')

            # Part 2: Created INSIDE the context, so it will be permanently untranslatable.
            with self.engine.no_translate():
                ttk.Label(no_translate_line, text=" `no_translate` ", style="Excluded.TLabel").pack(side='left')
            
            # Part 3: Created OUTSIDE the context, so it will be translated.
            ttk.Label(no_translate_line, text="context").pack(side='left')
            
            with self.engine.no_translate():
                ttk.Label(no_translate_line, text=":").pack(side='left')
                ttk.Label(no_translate_line, text="This text will not be translated.", style="Excluded.TLabel").pack(side='left')

            # --- Pattern Demonstrations ---
            ttk.Label(exclusion_frame, text="Non-translatable pattern:").grid(row=1, column=0, sticky='w', pady=(5,0))
            ttk.Label(exclusion_frame, text="10/05/2025", style="Pattern.TLabel").grid(row=1, column=1, sticky='w', padx=5, pady=(5,0))

            ttk.Label(exclusion_frame, text="Sensitive pattern:").grid(row=2, column=0, sticky='w')
            ttk.Label(exclusion_frame, text="example@email.com", style="Sensitive.TLabel").grid(row=2, column=1, sticky='w', padx=5)
            
            ttk.Label(lf3, text="Please Note:", style="Help.TLabel").pack(anchor='w', padx=10, pady=(5,0))
            ttk.Label(lf3, text="     Patterns must match the entire string to be excluded from translation.", style="Help.TLabel").pack(anchor='w', padx=10, pady=(5,0))
            ttk.Label(lf3, text="     Patterns within larger strings will still be translated.", style="Help.TLabel").pack(anchor='w', padx=10, pady=(5,0))
            ttk.Label(lf3, text="Example:", style="Help.TLabel").pack(anchor='w', padx=10, pady=(5,0))
            ttk.Label(lf3, text="     Your email is example@email.com", style="Help.TLabel").pack(anchor='w', padx=10, pady=(5,0))

        def show_message(self):
            tkinter.messagebox.showinfo(title="Information", message="This message box and its title are translated.")

    # --- Application Entry Point ---
    LANGUAGE_MAP = {
            'ar': "العربية",
            'zh': "中文",
            'en': "English",
            'fr': "Français",
            'de': "Deutsch",
            'hi': "हिन्दी",
            'it': "Italiano",
            'ja': "日本語",
            'pl': "Polski",
            'pt': "Português",
            'ru': "Русский",
            'es': "Español",
            'tr': "Türkçe"
        }       

    
    SENSITIVE_PATTERNS = [re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}')]

    # We include non-translatable patterns because Argos or Google Translate may inadvertantly translate certain strings.
    NON_TRANSLATABLE_PATTERNS = [
        re.compile(r'\d{1,2}\/\d{1,2}\/\d{2,4}'), # Date pattern
        re.compile(r'|'.join(re.escape(name) for name in LANGUAGE_MAP.values())) # Ensures language names are not translated
    ]

    
    translation_engine = activate_tkinter_translation(
        source_language='en', 
        target_language='en',
        log_level=logging.DEBUG,
        sensitive_patterns=SENSITIVE_PATTERNS,
        non_translatable_patterns=NON_TRANSLATABLE_PATTERNS
    )

    root = tk.Tk()
    app = DemoApp(root, translation_engine, LANGUAGE_MAP)
    root.mainloop()
'''
