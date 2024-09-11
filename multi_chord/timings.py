class Timings:
    def __init__(self, stabilize_interval: float = 1.0, live_interval: float = 1.0,
                 command_timeout: float = 1.0, get_data_timeout: float = 1.0):
        self.stabilize_interval = stabilize_interval
        self.live_interval = live_interval
        self.command_timeout = command_timeout
        self.get_data_timeout = get_data_timeout
