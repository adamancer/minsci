"""Custom exceptions for minsci module"""

class MinSciException(Exception):
    """Root exception. Used only to except any error, never raised."""
    pass

class PathError(MinSciException):
    """Called when pull request on DeepDict fails to resolve"""
    pass

class RowMismatch(MinSciException):
    """Called when columns in table have different numbers of rows"""
    pass

class TaxonNotFound(MinSciException):
    """Called when columns in table have different numbers of rows"""
    pass
