class BaseConstants:
    def __init__(self) -> None:
        pass

    @classmethod
    def variables(cls):
        """Returns a list of all available variables"""
        variables = [
            prop
            for prop in dir(cls)
            if not prop.startswith("_") and not callable(getattr(cls, prop))
        ]

        return variables

class JOB_TYPE(BaseConstants):
    AUTORIFT = "AUTORIFT"
    RTC_GAMMA = "RTC_GAMMA"
    INSAR_GAMMA = "INSAR_GAMMA"
    INSAR_ISCE_BURST = "INSAR_ISCE_BURST"


class STATUS_CODE(BaseConstants):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    PENDING = "PENDING"
