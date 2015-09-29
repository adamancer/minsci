class DMSException(Exception):
    """Root exception. Used only to except any error, never raised."""
    pass

class DMSException1(DMSException):
    """Root exception. Used only to except any error, never raised."""
    pass

class DMSException2(DMSException):
    """Root exception. Used only to except any error, never raised."""
    pass

class TaxonNotFound(DMSException):
    pass
