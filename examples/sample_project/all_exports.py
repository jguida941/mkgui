"""Test __all__ filtering with class methods."""

__all__ = ["public_func", "ExportedClass"]


def public_func() -> str:
    """This function is in __all__, should be included."""
    return "public"


def hidden_func() -> str:
    """This function is NOT in __all__, should be excluded."""
    return "hidden"


class ExportedClass:
    """This class is in __all__, its static/class methods should be included."""

    @staticmethod
    def static_method() -> int:
        """Should be included because ExportedClass is in __all__."""
        return 1

    @classmethod
    def class_method(cls) -> str:
        """Should be included because ExportedClass is in __all__."""
        return "class"

    def instance_method(self) -> None:
        """Instance methods are skipped in v1 anyway."""
        pass


class HiddenClass:
    """This class is NOT in __all__, its methods should be excluded."""

    @staticmethod
    def hidden_static() -> None:
        """Should be excluded because HiddenClass is not in __all__."""
        pass
