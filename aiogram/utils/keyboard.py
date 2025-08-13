class InlineKeyboardBuilder:
    def __init__(self):
        self.buttons = []
    def button(self, *args, **kwargs):
        self.buttons.append((args, kwargs))
    def adjust(self, *args, **kwargs):
        pass
    def as_markup(self):
        return None
