import exceptions

class Error(Exception):
    def __init__(self, str):
        self.error_info = str
    def __str__(self):
        return self.error_info

