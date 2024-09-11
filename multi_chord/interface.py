class Interface:
    """
    Interface describes abstract network interface. This class may be used later for testing purposes or extending
    network interface implementations.
    """

    def send_message(self, remote, message):
        """
        Sends message to the specified description over the network.
        :param remote: remote node destination.
        :param message: rpc message.
        """
        pass
