import abc
import distutils.util


class BaseSetting(metaclass=abc.ABCMeta):
    name = None

    def __init__(self, value):
        self.value = value

    @abc.abstractmethod
    def check(self):
        pass

    @abc.abstractmethod
    def cast(self):
        pass

    def __eq__(self, rhs):
        if isinstance(rhs, type(self)):
            return self.cast() == rhs.cast()

        value = type(self)(rhs)
        return value.check() and self.cast() == value.cast()

    def __ne__(self, rhs):
        return not self.__eq__(rhs)


class Bool(BaseSetting):
    def check(self):
        if isinstance(self.value, bool):
            return True

        try:
            distutils.util.strtobool(self.value)
            return True
        except (AttributeError, ValueError):
            return False

    def cast(self):
        return self.value if isinstance(self.value, bool) else distutils.util.strtobool(self.value)


class String(BaseSetting):
    def check(self):
        return isinstance(self.value, str) and self.value.strip()

    def cast(self):
        return self.value.strip()


class Int(BaseSetting):
    def check(self):
        try:
            int(self.value)
            return not isinstance(self.value, float)
        except (TypeError, ValueError):
            return False

    def cast(self):
        return int(self.value)
