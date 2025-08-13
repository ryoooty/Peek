class FType:
    def __getattr__(self, name):
        return self
    def __eq__(self, other):
        return True

class Router:
    def __init__(self, *args, **kwargs):
        pass
    def message(self, *args, **kwargs):
        def decorator(fn):
            return fn
        return decorator
    def callback_query(self, *args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

F = FType()

class Bot:
    def __init__(self, *args, **kwargs):
        pass
