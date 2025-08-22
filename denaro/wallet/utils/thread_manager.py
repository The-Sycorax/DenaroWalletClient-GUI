import threading
import continuous_threading # type: ignore
import queue
import time

class WalletThreadManager:
    def __init__(self, root):
        self.root = root
        self.threads = {}
        self.thread_stop_signals = {}
        self.thread_result = {}
        self.lock = threading.RLock()
        self.request_queue = queue.Queue()        
        #self.dialog_event = threading.Event()

        self._shutdown_poller = threading.Event() # Signal to stop the fallback poller

        try:
            # The preferred, GUI-safe way
            #print("Attempting to use GUI scheduler (root.after).")
            self.root.after(100, self.process_gui_requests)
            #print("Successfully attached to GUI event loop.")
        except AttributeError:
            # The fallback for non-GUI objects.
            # This will run the request processor in a separate thread.
            #print("WARNING: root object has no 'after' method. Falling back to a background polling thread.")
            #print("         GUI updates from this manager will be UNSAFE and may cause crashes.")
            poller_thread = threading.Thread(target=self.process_poller_requests)
            poller_thread.daemon = True # Allows main program to exit even if this thread is running
            poller_thread.start()


    def post_and_wait(self, target_callable):
        """
        Posts a request to the GUI thread and waits for a result.
        This is the centralized, thread-safe way to get a return value from a GUI operation.

        Args:
            target_callable (function): A function (often a lambda) that takes a single
                                        argument: `result_queue`. This function will be
                                        executed on the GUI thread.
        
        Returns:
            The result put into the queue by the target_callable.
        """
        # 1. Create a unique queue for this specific request.
        result_queue = queue.Queue(maxsize=1)

        # 2. Wrap the user's callable in a new lambda that injects the queue.
        #    The `dialogs.ask_string` function will now receive the queue.
        request_wrapper = lambda: target_callable(result_queue=result_queue)

        # 3. Put the wrapped request on the main processing queue for the GUI thread.
        self.request_queue.put(request_wrapper)

        # 4. Block this (worker) thread and wait for the result.
        result = result_queue.get()

        # 5. Return the result to the original caller (e.g., post_ask_string).
        return result

    def process_gui_requests(self):
        """Processes the queue and reschedules itself. GUI-safe."""
        while not self.request_queue.empty():
            try:
                # Get the wrapped request (e.g., `lambda: target_callable(result_queue=result_queue)`)
                request = self.request_queue.get_nowait()
                # Execute it. This runs the `dialogs.ask_string(...)` on the GUI thread.
                request()
            except queue.Empty:
                pass # This can happen in rare race conditions, it's safe to ignore.
            except Exception as e:
                print(f"Error executing request from queue: {e}")
        
        self.root.after(100, self.process_gui_requests)

    def process_poller_requests(self):
        """
        Processes the queue in a loop. This is NOT GUI-safe.
        This method runs in its own background thread.
        """
        while not self._shutdown_poller.is_set():
            while not self.request_queue.empty():
                request = self.request_queue.get_nowait()
                try:
                    request()
                except Exception as e:
                    print(f"Error executing request from poller thread: {e}")
            time.sleep(0.1) # sleep to prevent this loop from consuming 100% CPU


    def start_thread(self, name, target, args=(), periodic=[False]):
        # This method remains the same
        self.stop_thread(name)
        if periodic[0]:
            stop_signal = continuous_threading.Event()
        else:
            stop_signal = threading.Event()
        with self.lock:
            self.thread_stop_signals[name] = stop_signal

        def wrapped_target(stop_signal, *args, **kwargs):
            try:
                target(stop_signal, *args, **kwargs)
            finally:
                with self.lock:
                    self.threads.pop(name, None)
                    self.thread_stop_signals.pop(name, None)

        prepared_args = (stop_signal,) + args
        if periodic[0]:
            thread = continuous_threading.PeriodicThread(periodic[1], target=wrapped_target, args=prepared_args)
        else:
            thread = threading.Thread(target=wrapped_target, args=prepared_args)
        thread.daemon = True

        with self.lock:
            self.threads[name] = thread

        thread.start()

    def stop_thread(self, name):
        # This method remains the same
        with self.lock:
            if name in self.thread_stop_signals:
                self.thread_stop_signals[name].set()
            thread_to_join = self.threads.get(name)
        
        if thread_to_join:
            thread_to_join.join(timeout=2)
            with self.lock:
                self.threads.pop(name, None)
                self.thread_stop_signals.pop(name, None)
    
    def stop_all_threads(self):
        # Also signal the fallback poller thread to shut down
        self._shutdown_poller.set()
        
        continuous_threading.shutdown(0)
        with self.lock:            
            for name in list(self.threads.keys()):
                self.stop_thread(name)

    def stop_specific_threads(self, names=[]):
        with self.lock:
            for name in names:
                handler = getattr(self.root, 'event_handler', None)
                if handler and name in handler.thread_event:
                    self.stop_thread(name)