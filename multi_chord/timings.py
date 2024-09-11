class Timings:
    """
    Timings class is responsible for keeping all time-related settings of the application.
    """

    def __init__(self, stabilize_interval: float = 1.0, live_interval: float = 1.0,
                 command_timeout: float = 1.0, get_data_timeout: float = 1.0):
        """
        Creates a new instance of the Timings class.
        :param stabilize_interval: time in seconds between hosted virtual node stabilization cycles.
        :param live_interval: time in seconds remote node liveness check
        :param command_timeout: max rpc call time in seconds
        :param get_data_timeout: max get data rpc call time in seconds
        """
        self.stabilize_interval = stabilize_interval
        self.live_interval = live_interval
        self.command_timeout = command_timeout
        self.get_data_timeout = get_data_timeout
