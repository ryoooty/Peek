class _FieldInfo:
    def __init__(self, default=None, default_factory=None):
        self.default = default
        self.default_factory = default_factory

def Field(*, default=None, default_factory=None):
    return _FieldInfo(default, default_factory)


class BaseModel:
    def __init__(self, **data):
        ann = getattr(self.__class__, "__annotations__", {})
        for name, _ in ann.items():
            default = getattr(self.__class__, name, None)
            if isinstance(default, _FieldInfo):
                if name in data:
                    value = data[name]
                elif default.default_factory is not None:
                    value = default.default_factory()
                else:
                    value = default.default
            else:
                value = data.get(name, default)
            setattr(self, name, value)

    def model_dump(self):
        return {
            k: getattr(self, k)
            for k in getattr(self.__class__, "__annotations__", {})
        }
